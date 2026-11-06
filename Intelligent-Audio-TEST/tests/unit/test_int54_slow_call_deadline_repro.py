# -*- coding: utf-8 -*-
"""INT-54 打回项复现锁定（测试工程师验收，2026-10-09）。

打回理由：ClientDeadlineInterceptor 无法区分「服务假死（接受连接永不响应）」
与「合法慢调用（同步执行耗时任务后正常返回）」——二者在 60s 默认 deadline 下
同样被 DEADLINE_EXCEEDED 击杀。

受影响的生产调用点（均无显式 timeout，且同步等待长任务）：
1. task_service/core/execution_engine/mixins/grpc_helpers.py:114
   stub.StartE2ETask(...) —— e2e_test_service/application/services/
   e2e_executor/executor.py:81 的用例执行为 rounds 多轮结构，gRPC handler
   同步内联跑完整个用例（e2e_service.py:59 docstring「同步执行」），
   多轮语音链路（设备准备/播放/录音/识别/评估）总时长结构性可超 60s。
   超时后 _execute_e2e_case_via_grpc except → return False → 用例被标
   FAILED（task_service/.../case_execution.py:142 为唯一执行路径）。
   修复前（无 deadline）该调用会正确等待用例跑完。
2. api_test_service/infrastructure/acl/adapter_acl_repository.py:33
   stub.SendRound(request) —— 适配器同步执行被测 API 单轮请求，
   单轮超时 session_timeout 默认 60（api_test_service/core/session_context.py:42）
   与 GRPC_CLIENT_DEADLINE_SECONDS 默认 60 相等：被测 API 慢响应跑满
   单轮超时 + 渲染/评估开销即触发 deadline 竞态击杀，用户调大
   session_timeout 后必杀。

本文件锁定机制语义（修复调用点加显式 timeout 后本测试仍然通过——
它锁的是拦截器行为，不是调用点）：
- 未显式传 timeout 的合法慢调用（慢而非死）会被默认 deadline 击杀
  → 证明「有界失败」与「误杀慢调用」是同一机制的两面，已知长耗时
  调用点必须显式传更大 timeout；
- 显式传 timeout 的调用不受影响（拦截器透传，为官方修复方向）。
"""
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
from shared.clients import _grpc_channels


class _SlowButHealthyHandler(grpc.GenericRpcHandler):
    """合法慢调用复现：处理线程耗时 WORK_SECONDS 后正常返回（非假死）。

    与 INT-54 假死现场的区分：假死 = 永不返回；本 handler = 延迟后
    返回正确结果，即 E2E 多轮用例 / SendRound 慢请求的机制缩影。
    使用 Event 而非 sleep，便于拆除时立即释放。
    """

    WORK_SECONDS = 2.5

    def __init__(self):
        self.release = threading.Event()

    def service(self, handler_call_details):
        def _slow_work(request, context):
            self.release.wait(timeout=self.WORK_SECONDS)
            return b'ok'
        return grpc.unary_unary_rpc_method_handler(_slow_work)


def _channel(port):
    return grpc.intercept_channel(
        grpc.insecure_channel(f'127.0.0.1:{port}'),
        *_grpc_channels._CLIENT_INTERCEPTORS)


@pytest.fixture()
def slow_server():
    handler = _SlowButHealthyHandler()
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=2),
                         handlers=[handler])
    port = server.add_insecure_port('127.0.0.1:0')
    server.start()
    yield handler, port
    handler.release.set()
    server.stop(grace=None).wait(timeout=5)


class TestInt54SlowCallKilledByDefaultDeadline:
    """打回项复现：默认 deadline 击杀合法慢调用（无显式 timeout 时）。"""

    def test_slow_but_healthy_call_killed_without_explicit_timeout(self, slow_server, monkeypatch):
        handler, port = slow_server
        monkeypatch.setattr(BaseConfig, 'GRPC_CLIENT_DEADLINE_SECONDS', 1)
        call = _channel(port).unary_unary('/pkg.Svc/SlowWork')
        t0 = time.monotonic()
        with pytest.raises(grpc.RpcError) as exc:
            call(b'ping')
        elapsed = time.monotonic() - t0
        # 期望（修复前正确行为）：等待 2.5s 拿到 b'ok'
        # 实际（INT-54 修复态）：1s 即被默认 deadline 击杀
        assert exc.value.code() == grpc.StatusCode.DEADLINE_EXCEEDED
        assert elapsed < 2, f'合法慢调用在 {elapsed:.1f}s 被默认 deadline 击杀'

    def test_explicit_timeout_allows_slow_call(self, slow_server, monkeypatch):
        """官方修复方向验证：调用点显式传更大 timeout 后慢调用正常完成。"""
        handler, port = slow_server
        monkeypatch.setattr(BaseConfig, 'GRPC_CLIENT_DEADLINE_SECONDS', 1)
        call = _channel(port).unary_unary('/pkg.Svc/SlowWork')
        t0 = time.monotonic()
        assert call(b'ping', timeout=10) == b'ok'
        assert time.monotonic() - t0 >= handler.WORK_SECONDS - 0.2, \
            '显式 timeout 应等待慢调用完成而非提前击杀'
