# -*- coding: utf-8 -*-
"""INT-54 守卫：gRPC 客户端默认 deadline 拦截器。

缺陷背景：依赖服务「接受连接但不响应」（进程驻留但处理线程假死）时，未设
timeout 的 gRPC 客户端调用在 grpc._channel._blocking 永久阻塞 —— 上层调用点
try/except 的失败收敛路径（设计上视为可降级，如引擎 _register_task_events_via_grpc）
永不执行，调用线程悬挂（集成回归现场：StartTaskLifecycle → RegisterTaskEvents
→ device_service 假死 → gateway.post 悬挂 25 分钟+）。

守卫语义：
1. 未显式传 timeout 的调用注入 BaseConfig.GRPC_CLIENT_DEADLINE_SECONDS 默认值；
2. 调用方显式传 timeout 时不改写（显式优先）；
3. 拦截器注册进 shared.clients._grpc_channels._CLIENT_INTERCEPTORS，
   且位于日志拦截器内层（紧邻真实 channel）；
4. 端到端：对「接受 RPC 但永不响应」的服务，调用在 deadline 处
   DEADLINE_EXCEEDED 而非永久悬挂；健康服务调用不受影响。
"""
import collections
import os
import threading
import time
from concurrent import futures

os.environ.setdefault('DATABASE_URL', 'postgresql://placeholder:placeholder@localhost:5432/placeholder')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import grpc
import pytest

from shared.infrastructure.config import BaseConfig
from shared.infrastructure.grpc_interceptors import (
    ClientDeadlineInterceptor,
    client_deadline_interceptor,
    client_log_interceptor,
)

# 与 grpc.ClientCallDetails 同构的轻量替身（拦截器只读 .timeout 与 ._replace）
CallDetails = collections.namedtuple(
    'CallDetails',
    ('method', 'timeout', 'metadata', 'credentials', 'wait_for_ready', 'compression'))


def _details(timeout=None):
    return CallDetails('/pkg.Svc/Method', timeout, None, None, None, None)


class _RecordingContinuation:
    def __init__(self):
        self.seen = None

    def __call__(self, client_call_details, request):
        self.seen = client_call_details
        return 'ok'


class TestDefaultDeadlineInjection:
    """deadline 注入语义：显式优先，缺省注入配置值。"""

    def test_injects_default_when_timeout_missing(self):
        cont = _RecordingContinuation()
        client_deadline_interceptor.intercept_unary_unary(cont, _details(None), 'req')
        assert cont.seen.timeout == BaseConfig.GRPC_CLIENT_DEADLINE_SECONDS

    def test_explicit_timeout_not_overridden(self):
        cont = _RecordingContinuation()
        client_deadline_interceptor.intercept_unary_unary(cont, _details(3.5), 'req')
        assert cont.seen.timeout == 3.5

    def test_reads_config_dynamically(self, monkeypatch):
        monkeypatch.setattr(BaseConfig, 'GRPC_CLIENT_DEADLINE_SECONDS', 7)
        cont = _RecordingContinuation()
        client_deadline_interceptor.intercept_unary_unary(cont, _details(None), 'req')
        assert cont.seen.timeout == 7


class TestRegistration:
    """拦截器必须注册进共享 channel 工厂，且位于日志拦截器内层。"""

    def test_registered_in_channel_factory(self):
        from shared.clients import _grpc_channels
        interceptors = _grpc_channels._CLIENT_INTERCEPTORS
        names = [type(i).__name__ for i in interceptors]
        assert any(isinstance(i, ClientDeadlineInterceptor) for i in interceptors), \
            f'deadline 拦截器未注册: {names}'
        # grpc.intercept_channel 以 reversed 顺序包裹（grpc/_interceptor.py）：
        # 列表首位最外层（日志先拦截、记录原始调用与总耗时），
        # 末位最内层（deadline 紧邻真实 channel 注入默认超时）。
        assert isinstance(interceptors[-1], ClientDeadlineInterceptor), \
            f'deadline 拦截器应为最内层: {names}'
        assert interceptors[0] is client_log_interceptor


class _HangHandler(grpc.GenericRpcHandler):
    """接受 RPC 但永不返回 —— INT-54 假死现场的进程内复现。

    处理线程以 Event 等待替代 sleep：测试拆除时 set 释放并停服，避免
    非守护线程池 worker 阻塞 pytest 进程退出。
    """

    def __init__(self):
        self.release = threading.Event()

    def service(self, handler_call_details):
        def _hang(request, context):
            self.release.wait(timeout=600)
        return grpc.unary_unary_rpc_method_handler(_hang)


class _EchoHandler(grpc.GenericRpcHandler):
    def service(self, handler_call_details):
        def _echo(request, context):
            return request
        return grpc.unary_unary_rpc_method_handler(_echo)


class TestEndToEnd:
    """端到端：假死服务有界失败；健康服务不受影响。"""

    @staticmethod
    def _channel(port):
        from shared.clients import _grpc_channels
        return grpc.intercept_channel(
            grpc.insecure_channel(f'127.0.0.1:{port}'),
            *_grpc_channels._CLIENT_INTERCEPTORS)

    def test_wedged_service_fails_bounded(self, monkeypatch):
        monkeypatch.setattr(BaseConfig, 'GRPC_CLIENT_DEADLINE_SECONDS', 1)
        handler = _HangHandler()
        server = grpc.server(futures.ThreadPoolExecutor(max_workers=2),
                             handlers=[handler])
        port = server.add_insecure_port('127.0.0.1:0')
        server.start()
        try:
            call = self._channel(port).unary_unary('/pkg.Svc/Method')
            t0 = time.monotonic()
            with pytest.raises(grpc.RpcError) as exc:
                call(b'ping')
            elapsed = time.monotonic() - t0
            assert exc.value.code() == grpc.StatusCode.DEADLINE_EXCEEDED
            assert elapsed < 10, f'调用应在 deadline 处有界失败: {elapsed:.1f}s'
        finally:
            handler.release.set()   # 先释放假死 handler 线程
            server.stop(grace=None).wait(timeout=5)

    def test_healthy_service_unaffected(self):
        handler = _EchoHandler()
        server = grpc.server(futures.ThreadPoolExecutor(max_workers=2),
                             handlers=[handler])
        port = server.add_insecure_port('127.0.0.1:0')
        server.start()
        try:
            call = self._channel(port).unary_unary('/pkg.Svc/Echo')
            t0 = time.monotonic()
            assert call(b'hello') == b'hello'
            assert time.monotonic() - t0 < 5
        finally:
            server.stop(grace=None).wait(timeout=5)


class TestExplicitLongCallSites:
    """打回项（INT-54 P1-1/P1-2）守卫：同步执行长工作的调用点必须显式传
    大于其工作上限的 deadline，且该 deadline 须随请求内工作上限联动。

    - StartE2ETask：e2e 处理器内同步跑完整个多轮用例 → 显式
      GRPC_E2E_SYNC_TIMEOUT_SECONDS（默认 600s > 默认 deadline 60s）。
    - SendRound：同步执行被测请求，单轮上限 = request.timeout
      （session_timeout，默认 60s，用户可调大）→ deadline = 上限 + 余量，
      恒大于单轮上限，消除竞态击杀。
    """

    class _KwargsCaptured(Exception):
        def __init__(self, kwargs):
            super().__init__('captured')
            self.kwargs = kwargs

    def test_send_round_deadline_exceeds_default_session_timeout(self, monkeypatch):
        import types

        import shared.clients.grpc_clients as gc

        captured = {}

        class _Stub:
            def SendRound(self, request, **kwargs):
                captured.update(kwargs)
                raise TestExplicitLongCallSites._KwargsCaptured(kwargs)

        monkeypatch.setattr(gc, 'get_adapter_service_stub', lambda: _Stub())
        from api_test_service.infrastructure.acl.adapter_acl_repository import (
            AdapterAclRepositoryImpl,
        )
        with pytest.raises(self._KwargsCaptured):
            AdapterAclRepositoryImpl().send_round(types.SimpleNamespace(timeout=60))
        # session_timeout 默认 60s == 默认 deadline（竞态）→ 显式 deadline 必须严格更大
        assert captured['timeout'] > 60
        assert captured['timeout'] == 60 + BaseConfig.GRPC_SENDROUND_DEADLINE_MARGIN_SECONDS

    def test_send_round_deadline_follows_raised_session_timeout(self, monkeypatch):
        import types

        import shared.clients.grpc_clients as gc

        captured = {}

        class _Stub:
            def SendRound(self, request, **kwargs):
                captured.update(kwargs)
                raise TestExplicitLongCallSites._KwargsCaptured(kwargs)

        monkeypatch.setattr(gc, 'get_adapter_service_stub', lambda: _Stub())
        from api_test_service.infrastructure.acl.adapter_acl_repository import (
            AdapterAclRepositoryImpl,
        )
        # 用户调大 session_timeout 后 deadline 必须同步放大（否则必杀）
        with pytest.raises(self._KwargsCaptured):
            AdapterAclRepositoryImpl().send_round(types.SimpleNamespace(timeout=300))
        assert captured['timeout'] == 300 + BaseConfig.GRPC_SENDROUND_DEADLINE_MARGIN_SECONDS

    def test_send_round_zero_timeout_falls_back_to_default_base(self, monkeypatch):
        import types

        import shared.clients.grpc_clients as gc

        captured = {}

        class _Stub:
            def SendRound(self, request, **kwargs):
                captured.update(kwargs)
                raise TestExplicitLongCallSites._KwargsCaptured(kwargs)

        monkeypatch.setattr(gc, 'get_adapter_service_stub', lambda: _Stub())
        from api_test_service.infrastructure.acl.adapter_acl_repository import (
            AdapterAclRepositoryImpl,
        )
        with pytest.raises(self._KwargsCaptured):
            AdapterAclRepositoryImpl().send_round(types.SimpleNamespace(timeout=0))
        assert captured['timeout'] == BaseConfig.GRPC_CLIENT_DEADLINE_SECONDS + \
            BaseConfig.GRPC_SENDROUND_DEADLINE_MARGIN_SECONDS

    def test_start_e2e_task_passes_explicit_sync_deadline(self, monkeypatch):
        import types

        import shared.clients.grpc_clients as gc

        captured = {}

        class _Stub:
            def StartE2ETask(self, request, **kwargs):
                captured.update(kwargs)
                return types.SimpleNamespace(success=True, message='ok', data='{}')

        monkeypatch.setattr(gc, 'get_e2e_execution_service_stub', lambda: _Stub())
        from task_service.core.execution_engine.mixins.grpc_helpers import (
            _execute_e2e_case_via_grpc,
        )
        assert _execute_e2e_case_via_grpc(1, 2) is True
        assert captured['timeout'] == BaseConfig.GRPC_E2E_SYNC_TIMEOUT_SECONDS
        # 结构性要求：同步 E2E 用例总时长上限必须大于默认 deadline（60s）
        assert captured['timeout'] > BaseConfig.GRPC_CLIENT_DEADLINE_SECONDS

    def test_start_e2e_task_returns_false_on_failure(self, monkeypatch):
        import types

        import shared.clients.grpc_clients as gc

        class _Stub:
            def StartE2ETask(self, request, **kwargs):
                return types.SimpleNamespace(success=False, message='no', data='')

        monkeypatch.setattr(gc, 'get_e2e_execution_service_stub', lambda: _Stub())
        from task_service.core.execution_engine.mixins.grpc_helpers import (
            _execute_e2e_case_via_grpc,
        )
        assert _execute_e2e_case_via_grpc(1, 2) is False
