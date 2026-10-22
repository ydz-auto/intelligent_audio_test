# -*- coding: utf-8 -*-
"""INT-1292 守卫：gRPC 客户端 channel 收发消息上限放大。

缺陷背景：grpcio 客户端默认收包上限 4MiB，大响应 RPC（任务导出 23MB 包、
报告/评估只读导出）在客户端收不下 → RESOURCE_EXHAUSTED
（CLIENT: Received message larger than max (23448138 vs. 4194304)）。
transfer_agent 服务端已按 TRANSFER_GRPC_MAX_MESSAGE_MB（默认 16MB）放大，
server.py 注释明确「客户端 stub 侧需同步设置」，但共享 channel 工厂一直没同步。

守卫语义（与服务端 test_transfer_service_startup.py 断言口径对应）：
1. 所有共享 channel（含 task/report/evaluation 等 9 条）在创建时携带放大后的
   grpc.max_receive_message_length / grpc.max_send_message_length；
2. 配置随 BaseConfig.GRPC_MAX_MESSAGE_MB 动态变化；
3. 端到端：经共享 channel 工厂创建的客户端可收下 >4MiB 的响应。
"""
import os
from concurrent import futures

os.environ.setdefault('DATABASE_URL', 'postgresql://placeholder:placeholder@localhost:5432/placeholder')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import grpc
import pytest

from shared.infrastructure.config import BaseConfig

# 所有共享 channel 工厂（_grpc_channels._get_*_channel）
_ALL_CHANNEL_GETTERS = (
    '_get_e2e_channel', '_get_audio_channel', '_get_device_channel',
    '_get_task_channel', '_get_api_test_channel', '_get_evaluation_channel',
    '_get_algorithm_channel', '_get_report_channel', '_get_auth_channel',
)


def _expected_max_bytes() -> int:
    return max(int(BaseConfig.GRPC_MAX_MESSAGE_MB), 1) * 1024 * 1024


class TestChannelOptions:
    """共享 channel 工厂必须向 grpc.insecure_channel 传入放大后的收发上限。"""

    def test_all_channels_carry_enlarged_message_limits(self, monkeypatch):
        from shared.clients import _grpc_channels

        seen = {}
        real_insecure_channel = grpc.insecure_channel

        def _fake_insecure_channel(target, options=None, **kwargs):
            seen[target] = options
            return real_insecure_channel(target)

        monkeypatch.setattr(_grpc_channels.grpc, 'insecure_channel', _fake_insecure_channel)
        expected = _expected_max_bytes()

        try:
            for name in _ALL_CHANNEL_GETTERS:
                getter = getattr(_grpc_channels, name)
                getter.cache_clear()
                getter()
        finally:
            for name in _ALL_CHANNEL_GETTERS:
                getattr(_grpc_channels, name).cache_clear()

        assert len(seen) == len(_ALL_CHANNEL_GETTERS), \
            f'应创建 {len(_ALL_CHANNEL_GETTERS)} 个共享 channel: {list(seen)}'
        for target, options in seen.items():
            opts = dict(options or [])
            assert opts['grpc.max_receive_message_length'] == expected, target
            assert opts['grpc.max_send_message_length'] == expected, target

    def test_reads_config_dynamically(self, monkeypatch):
        from shared.clients import _grpc_channels

        seen = {}
        real_insecure_channel = grpc.insecure_channel

        def _fake_insecure_channel(target, options=None, **kwargs):
            seen[target] = options
            return real_insecure_channel(target)

        monkeypatch.setattr(_grpc_channels.grpc, 'insecure_channel', _fake_insecure_channel)
        monkeypatch.setattr(BaseConfig, 'GRPC_MAX_MESSAGE_MB', 32)

        try:
            getter = _grpc_channels._get_task_channel
            getter.cache_clear()
            getter()
        finally:
            _grpc_channels._get_task_channel.cache_clear()

        opts = dict(next(iter(seen.values())))
        assert opts['grpc.max_receive_message_length'] == 32 * 1024 * 1024
        assert opts['grpc.max_send_message_length'] == 32 * 1024 * 1024

    def test_instance_channel_carries_same_limits(self, monkeypatch):
        from shared.clients import grpc_instance_client

        seen = {}
        real_insecure_channel = grpc.insecure_channel

        def _fake_insecure_channel(target, options=None, **kwargs):
            seen[target] = options
            return real_insecure_channel(target)

        monkeypatch.setattr(grpc_instance_client.grpc, 'insecure_channel', _fake_insecure_channel)
        expected = _expected_max_bytes()

        grpc_instance_client._get_channel.cache_clear()
        try:
            grpc_instance_client._get_channel('127.0.0.1:1')
        finally:
            grpc_instance_client._get_channel.cache_clear()

        opts = dict(next(iter(seen.values())))
        assert opts['grpc.max_receive_message_length'] == expected
        assert opts['grpc.max_send_message_length'] == expected


class TestLargeResponseEndToEnd:
    """端到端守卫：经共享 channel 工厂创建的客户端可收下 >4MiB 的响应。

    复现 INT-1292 现场：未放大时客户端以 RESOURCE_EXHAUSTED 失败，
    放大后（默认 16MB 对齐 transfer_agent）超 4MiB 响应可正常收下。
    """

    def test_task_channel_receives_large_response(self, monkeypatch):
        from shared.clients import _grpc_channels

        payload_size = 6 * 1024 * 1024  # 6MiB > grpcio 默认 4MiB
        handler = grpc.unary_unary_rpc_method_handler(
            lambda req, ctx: b'y' * payload_size,
            request_deserializer=None, response_serializer=None)
        server = grpc.server(futures.ThreadPoolExecutor(max_workers=2))
        server.add_generic_rpc_handlers(
            (grpc.method_handlers_generic_handler('svc', {'echo': handler}),))
        port = server.add_insecure_port('127.0.0.1:0')
        server.start()
        try:
            monkeypatch.setattr(_grpc_channels, 'TASK_GRPC_ADDR', f'127.0.0.1:{port}')
            _grpc_channels._get_task_channel.cache_clear()
            call = _grpc_channels._get_task_channel().unary_unary('/svc/echo')
            resp = call(b'ping', timeout=30)
            assert len(resp) == payload_size
        finally:
            _grpc_channels._get_task_channel.cache_clear()
            server.stop(grace=None).wait(timeout=5)

    def test_large_response_fails_without_enlarged_limit(self, monkeypatch):
        """反例（对照）：默认 4MiB 上限下同一响应以 RESOURCE_EXHAUSTED 失败，
        证明守卫命中缺陷本体而非空转。"""
        from shared.clients import _grpc_channels

        handler = grpc.unary_unary_rpc_method_handler(
            lambda req, ctx: b'y' * (6 * 1024 * 1024),
            request_deserializer=None, response_serializer=None)
        server = grpc.server(futures.ThreadPoolExecutor(max_workers=2))
        server.add_generic_rpc_handlers(
            (grpc.method_handlers_generic_handler('svc', {'echo': handler}),))
        port = server.add_insecure_port('127.0.0.1:0')
        server.start()
        try:
            plain = grpc.insecure_channel(f'127.0.0.1:{port}')
            with pytest.raises(grpc.RpcError) as exc:
                plain.unary_unary('/svc/echo')(b'ping', timeout=30)
            assert exc.value.code() == grpc.StatusCode.RESOURCE_EXHAUSTED
            assert 'larger than max' in str(exc.value)
            plain.close()
        finally:
            server.stop(grace=None).wait(timeout=5)
