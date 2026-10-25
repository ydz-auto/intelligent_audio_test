# -*- coding: utf-8 -*-
"""INT-1292 守卫：gRPC 客户端 channel 收发消息上限放大。

缺陷背景：grpcio 客户端默认收包上限 4MiB，大响应 RPC（任务导出 23MB 包、
报告/评估只读导出）在客户端收不下 → RESOURCE_EXHAUSTED
（CLIENT: Received message larger than max (23448138 vs. 4194304)）。
第一轮修复按 transfer_agent.TRANSFER_GRPC_MAX_MESSAGE_MB（16MB）放大仍不够：
INT-1292 实测任务 419 导出跨服务响应 ExportDimensionsForTasks = 23,448,131B、
ExportReportsForTasks = 20,439,856B，均超 16MiB → (23448138 vs. 16777216)。
故共享配置 GRPC_MAX_MESSAGE_MB 默认放大到 64MB，覆盖最大实测单响应并留余量。

守卫语义（与服务端 test_transfer_service_startup.py 断言口径对应）：
1. 所有共享 channel（含 task/report/evaluation 等 9 条）在创建时携带放大后的
   grpc.max_receive_message_length / grpc.max_send_message_length；
2. 配置随 BaseConfig.GRPC_MAX_MESSAGE_MB 动态变化；
3. 默认上限必须 ≥ 实测最大单响应 23,448,131B；
4. 端到端：经共享 channel 工厂创建的客户端可收下 ≥ 实测边界的响应。
"""
import importlib
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

# INT-1425 测试自愈：9 个共享服务 gRPC 端口的互异已知值（与 config.py 默认一致）。
# _grpc_channels 的 *_GRPC_ADDR 是模块级常量、import 时从 BaseConfig 一次性求值；
# 全量套件前序测试会污染 *_SERVICE_GRPC_PORT env，污染值下部分 getter 解析到同一
# target → 按 target 去重计数不足 9。固定端口后 reload 模块使模块级 ADDR 按互异
# 值重新求值，消除 target 串扰（monkeypatch 自动还原 BaseConfig 类属性）。
_DISTINCT_GRPC_PORTS = {
    'E2E_TEST_SERVICE_GRPC_PORT': 50051,
    'AUDIO_SERVICE_GRPC_PORT': 50052,
    'DEVICE_SERVICE_GRPC_PORT': 50053,
    'TASK_SERVICE_GRPC_PORT': 50061,
    'API_TEST_SERVICE_GRPC_PORT': 50071,
    'EVALUATION_SERVICE_GRPC_PORT': 50091,
    'ALGORITHM_SERVICE_GRPC_PORT': 50067,
    'REPORT_SERVICE_GRPC_PORT': 51068,
    'AUTH_SERVICE_GRPC_PORT': 51069,
}

# INT-1292 实测任务 419（138 用例）导出跨服务最大单响应（ExportDimensionsForTasks，
# 真实库栈 5700 实测抓取），低于默认上限即会重演 400 RESOURCE_EXHAUSTED。
_REAL_EXPORT_RESPONSE_BYTES = 23_448_131
# 端到端响应量级：大于实测边界（23.4MB），低于默认 64MB，验证放大后真实故障量级可收下。
_E2E_PAYLOAD_BYTES = 32 * 1024 * 1024


def _expected_max_bytes() -> int:
    return max(int(BaseConfig.GRPC_MAX_MESSAGE_MB), 1) * 1024 * 1024


class TestChannelOptions:
    """共享 channel 工厂必须向 grpc.insecure_channel 传入放大后的收发上限。"""

    def test_all_channels_carry_enlarged_message_limits(self, monkeypatch):
        from shared.clients import _grpc_channels
        from shared.infrastructure.config import BaseConfig

        # 全量套件前序测试会污染 *_SERVICE_GRPC_PORT env，而 *_GRPC_ADDR 是
        # 模块级常量、import 时从 BaseConfig 一次性求值 → 污染值下不同 getter
        # 解析到同一 target，按 target 去重计数不足 9（INT-1425 全量回归失败点）。
        # 先把 9 个端口固定为互异已知值（monkeypatch 自动还原），再 reload
        # 模块使模块级 ADDR 按固定值重新求值，消除 target 串扰。
        for attr, port in _DISTINCT_GRPC_PORTS.items():
            monkeypatch.setattr(BaseConfig, attr, port)
        _grpc_channels = importlib.reload(_grpc_channels)

        created = []  # (getter 名, target, options)：逐 getter 独立记录
        real_insecure_channel = grpc.insecure_channel
        current_getter = [None]

        def _fake_insecure_channel(target, options=None, **kwargs):
            created.append((current_getter[0], target, options))
            return real_insecure_channel(target)

        monkeypatch.setattr(_grpc_channels.grpc, 'insecure_channel', _fake_insecure_channel)
        expected = _expected_max_bytes()

        try:
            for name in _ALL_CHANNEL_GETTERS:
                current_getter[0] = name
                getter = getattr(_grpc_channels, name)
                getter.cache_clear()
                getter()
        finally:
            for name in _ALL_CHANNEL_GETTERS:
                getattr(_grpc_channels, name).cache_clear()

        # 逐 getter 独立校验收发上限（不再按 target 去重计数）：即使多个 getter
        # 恰巧解析到同一 target，各自 channel 也必须携带放大上限。
        assert len(created) == len(_ALL_CHANNEL_GETTERS), \
            f'应创建 {len(_ALL_CHANNEL_GETTERS)} 个共享 channel: {created}'
        for name, target, options in created:
            opts = dict(options or [])
            assert opts['grpc.max_receive_message_length'] == expected, f'{name} -> {target}'
            assert opts['grpc.max_send_message_length'] == expected, f'{name} -> {target}'

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

    def test_default_limit_covers_real_export_response(self):
        """默认 GRPC_MAX_MESSAGE_MB 必须 ≥ INT-1292 实测最大单响应
        (23,448,131B)，否则任务 419 导出会重演 400 RESOURCE_EXHAUSTED。"""
        max_bytes = _expected_max_bytes()
        assert max_bytes >= _REAL_EXPORT_RESPONSE_BYTES, (
            f'默认 GRPC_MAX_MESSAGE_MB={BaseConfig.GRPC_MAX_MESSAGE_MB}MB '
            f'({max_bytes}B) 小于实测导出响应 {_REAL_EXPORT_RESPONSE_BYTES}B'
        )

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
    """端到端守卫：经共享 channel 工厂创建的客户端可收下实测边界量级的响应。

    复现 INT-1292 现场：未放大时客户端以 RESOURCE_EXHAUSTED 失败；
    放大后（默认 64MB）实测边界量级（32MiB，> 真实 23,448,131B）响应可正常收下。
    """

    def test_task_channel_receives_real_scale_response(self, monkeypatch):
        from shared.clients import _grpc_channels

        payload_size = _E2E_PAYLOAD_BYTES  # 32MiB > 实测 23,448,131B 边界
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
            resp = call(b'ping', timeout=60)
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
