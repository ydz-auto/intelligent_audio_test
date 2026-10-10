# -*- coding: utf-8 -*-
"""INT-114：api_adapter_service gRPC(50081) 随 app lifespan 自启验证。

缺陷：run_all 用 uvicorn 起 ``{dir}.app:app`` 不执行 run.py，多轮 SendRound
依赖的 gRPC 50081 无人监听 → 多轮 API 执行全部连接拒绝。修复：lifespan 内
自启 gRPC server（与 task_service 等其余 HTTP+gRPC 服务同款）。

- TestClient 上下文（触发 lifespan）内 gRPC 端口可达，退出后端口关闭
- 经 lifespan 拉起的 server 走真实 SendRound（vendor=mock，全内存无外部依赖）
- 端口注册表 / server 默认参 / 客户端 BaseConfig 三处同源防漂移

gRPC 端口经 ADAPTER_SERVICE_GRPC_PORT 注入 ephemeral 端口，xdist 分片并行安全。
"""
import json
import os
import socket

import grpc
import pytest
from fastapi.testclient import TestClient

import api_adapter_service.app as app_module
from shared.config.service_ports import API_ADAPTER_SERVICE_GRPC_PORT


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def _tcp_open(port: int) -> bool:
    try:
        with socket.create_connection(('127.0.0.1', port), timeout=2):
            return True
    except OSError:
        return False


def test_registry_and_defaults_aligned():
    """端口注册表 / gRPC server 默认参 / 客户端 BaseConfig 同源（防漂移）。"""
    import inspect

    from api_adapter_service.interfaces.grpc import server as grpc_server
    from shared.infrastructure.config import BaseConfig

    assert API_ADAPTER_SERVICE_GRPC_PORT == 50081
    default_port = inspect.signature(
        grpc_server.start_grpc_server).parameters['port'].default
    assert default_port == API_ADAPTER_SERVICE_GRPC_PORT
    if os.environ.get('ADAPTER_SERVICE_GRPC_PORT'):
        pytest.skip('ADAPTER_SERVICE_GRPC_PORT 由环境显式指定，跳过默认值对齐断言')
    assert BaseConfig.ADAPTER_SERVICE_GRPC_PORT == API_ADAPTER_SERVICE_GRPC_PORT


def test_lifespan_starts_and_stops_grpc(monkeypatch):
    """lifespan 启动后 gRPC 端口可达；退出后停止（不泄漏监听）。"""
    port = _free_port()
    monkeypatch.setenv('ADAPTER_SERVICE_GRPC_PORT', str(port))
    assert not _tcp_open(port)

    with TestClient(app_module.create_app()) as client:
        assert _tcp_open(port), 'lifespan 启动后 gRPC 端口应可达'
        r = client.get('/health')
        assert r.status_code == 200

    assert not _tcp_open(port), 'lifespan 退出后 gRPC 端口应关闭'


def test_sendround_via_lifespan_grpc(monkeypatch):
    """经 lifespan 拉起的 gRPC server 走真实 SendRound（mock 链路，echo 断言）。"""
    port = _free_port()
    monkeypatch.setenv('ADAPTER_SERVICE_GRPC_PORT', str(port))

    with TestClient(app_module.create_app()):
        from shared.proto import adapter_service_pb2 as adapter_pb
        from shared.proto import adapter_service_pb2_grpc as adapter_grpc

        channel = grpc.insecure_channel(f'127.0.0.1:{port}')
        grpc.channel_ready_future(channel).result(timeout=10)
        stub = adapter_grpc.AdapterServiceStub(channel)
        resp = stub.SendRound(adapter_pb.SendRoundRequest(
            session_id='int114-grpc-session',
            round=1,
            total_rounds=3,
            task_type='voice_llm',
            vendor='mock',
            input_type='text',
            input_data='你好',
            context='[]',
            context_for_request='[]',
            algorithm_params='[]',
            case_algorithm_params='{}',
        ))
        assert resp.success is True, resp.message
        data = json.loads(resp.data)
        assert data['asr_text'] == '你好'
        assert 'latency' in data['response_metrics']
        channel.close()
