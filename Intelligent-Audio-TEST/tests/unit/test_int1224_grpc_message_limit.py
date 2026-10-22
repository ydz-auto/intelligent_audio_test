# -*- coding: utf-8 -*-
"""INT-1224 专项：gRPC 消息大小上限显式放大。

背景：grpcio 默认收发上限 4MiB，用例标签视图 view=tag perPage=50 真实库响应
实测 4.07MiB → api_gateway 客户端 RESOURCE_EXHAUSTED（CLIENT: Received message
larger than max (4,194,304)）。修复 = BaseConfig.GRPC_MAX_MESSAGE_MB 显式放大，
客户端 channel 与服务端 server 两侧需同步设置（对齐 transfer_agent 既有做法）。

覆盖：
- 共享客户端 channel 选项构造（_grpc_channel_options）大于默认 4MiB
- task_service gRPC server 启动时传入 max_send/max_receive_message_length
"""
import os

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from shared.infrastructure.config import BaseConfig

_DEFAULT_GRPC_LIMIT = 4 * 1024 * 1024  # grpcio 默认 4MiB


def _expected_bytes():
    return BaseConfig.GRPC_MAX_MESSAGE_MB * 1024 * 1024


class TestGrpcMessageLimitClientChannel:
    """共享客户端 channel 放大（INT-1224）。"""

    def test_channel_options_exceed_default(self):
        from shared.clients._grpc_channels import _grpc_channel_options

        opts = dict(_grpc_channel_options())
        assert opts['grpc.max_receive_message_length'] == _expected_bytes()
        assert opts['grpc.max_send_message_length'] == _expected_bytes()
        # 必须大于 grpcio 默认 4MiB，否则修复无效
        assert opts['grpc.max_receive_message_length'] > _DEFAULT_GRPC_LIMIT

    def test_task_channel_uses_raised_options(self, monkeypatch):
        """_get_task_channel 的 channel 必须携带放大后的选项（API 网关侧）。"""
        import shared.clients._grpc_channels as channels

        captured = {}
        sentinel = object()

        def _fake_insecure_channel(target, options=None):
            captured['options'] = options or []
            return sentinel

        # 同时替换 intercept_channel，避免对哨兵对象做真实拦截包装
        monkeypatch.setattr(channels.grpc, 'insecure_channel', _fake_insecure_channel)
        monkeypatch.setattr(channels.grpc, 'intercept_channel',
                            lambda *a, **k: sentinel)
        channels._get_task_channel.cache_clear()
        try:
            channels._get_task_channel()
        finally:
            channels._get_task_channel.cache_clear()

        opts = dict(captured['options'])
        assert opts.get('grpc.max_receive_message_length') == _expected_bytes()
        assert opts.get('grpc.max_send_message_length') == _expected_bytes()


class TestGrpcMessageLimitTaskServer:
    """task_service gRPC server 放大（INT-1224）。"""

    def test_server_options_raised(self, monkeypatch):
        import task_service.interfaces.grpc.server as server_mod

        captured = {}

        class _FakeServer:
            def __getattr__(self, name):
                return lambda *a, **k: None

        def _fake_grpc_server(*args, **kwargs):
            captured['options'] = kwargs.get('options')
            return _FakeServer()

        monkeypatch.setattr(server_mod.grpc, 'server', _fake_grpc_server)
        server_mod.start_grpc_server(port=1)

        opts = dict(captured.get('options') or [])
        assert opts.get('grpc.max_receive_message_length') == _expected_bytes()
        assert opts.get('grpc.max_send_message_length') == _expected_bytes()
        assert opts['grpc.max_receive_message_length'] > _DEFAULT_GRPC_LIMIT
