# -*- coding: utf-8 -*-
"""INT-2086 优雅停止通道：Pa_Initialize 防楔死（停播放 → 等流关闭 → pa.terminate）。

锁定：
- PyAudioDriver.terminate() 调 pa.terminate() 并把 self.pa 置 None（端点会话释放）
- AudioService.shutdown() 先 set 全部 stop_event、等播放 future 结束，再 driver.terminate()
- servicer Shutdown handler 触发 server.initiate_graceful_shutdown()
- server.initiate_graceful_shutdown() 调 audio_service.shutdown() + server.stop(grace)，幂等
"""
import os
import sys
import tempfile
import types
import threading
from concurrent.futures import Future

os.environ.setdefault('DATABASE_URL',
                      'sqlite:///' + tempfile.mkdtemp(prefix='int2086_') + '/guard.db')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from audio_service.infrastructure.audio.audio_driver import PyAudioDriver
from audio_service.infrastructure.audio.audio_engine import AudioService
from audio_service.interfaces.grpc.servicers import AudioServiceServicer
from audio_service.interfaces.grpc import server as srv
from shared.proto import audio_service_pb2 as pb


# ---- PyAudioDriver.terminate() ----

def test_driver_terminate_calls_pa_terminate_and_clears_pa():
    """pa.terminate() 被调用，self.pa 置 None（后续 _get_driver 会重新初始化）。"""
    driver = object.__new__(PyAudioDriver)

    class _FakePa:
        def __init__(self):
            self.terminate_called = False

        def terminate(self):
            self.terminate_called = True

    fake_pa = _FakePa()
    driver.pa = fake_pa
    driver.terminate()
    assert fake_pa.terminate_called is True
    assert driver.pa is None


def test_driver_terminate_when_pa_already_none_is_noop():
    """pa 已为 None（重复终止/未初始化）时不再调用，也不抛异常。"""
    driver = object.__new__(PyAudioDriver)
    driver.pa = None
    driver.terminate()  # 不抛即通过


# ---- AudioService.shutdown() ----

class _FakeDriver:
    def __init__(self):
        self.terminate_called = False

    def terminate(self):
        self.terminate_called = True


def test_engine_shutdown_stops_players_and_terminates_driver():
    """set 全部 stop_event → 等 future → driver.terminate() → driver 置 None。"""
    engine = AudioService()
    fake_driver = _FakeDriver()
    engine.driver = fake_driver

    stop_event = threading.Event()
    future = Future()
    future.set_result(None)
    engine.active_players = {
        'task-1': {'dry': {'stop_event': stop_event, 'future': future}},
    }

    engine.shutdown(wait_seconds=1.0)

    assert stop_event.is_set()
    assert fake_driver.terminate_called is True
    assert engine.driver is None
    assert engine.active_players == {}


def test_engine_shutdown_with_no_driver_is_safe():
    """driver 未初始化（影子兜底/预初始化失败）时 shutdown 不抛。"""
    engine = AudioService()
    engine.driver = None
    engine.active_players = {}
    engine.shutdown(wait_seconds=0.1)  # 不抛即通过


def test_engine_shutdown_wait_timeout_warns_but_still_terminates():
    """播放线程超时不阻塞退出：告警后仍执行 driver.terminate()。"""
    engine = AudioService()
    fake_driver = _FakeDriver()
    engine.driver = fake_driver

    # 永不完成的 future：cf.wait(timeout=0.01) 超时返回
    never = Future()
    engine.active_players = {'task-x': {'dry': {'stop_event': threading.Event(),
                                                'future': never}}}
    engine.shutdown(wait_seconds=0.01)
    assert fake_driver.terminate_called is True


# ---- servicer Shutdown handler ----

def test_servicer_shutdown_triggers_initiate_graceful_shutdown(monkeypatch):
    """Shutdown handler 调用 server.initiate_graceful_shutdown() 并返回 success。"""
    called = {}

    def fake_initiate():
        called['initiated'] = True

    monkeypatch.setattr(srv, 'initiate_graceful_shutdown', fake_initiate)
    servicer = AudioServiceServicer()
    resp = servicer.Shutdown(pb.ShutdownRequest())
    assert called.get('initiated') is True
    assert resp.success is True


def test_servicer_shutdown_error_returns_failure(monkeypatch):
    """initiate_graceful_shutdown 抛异常时返回 success=False（协议不裸抛）。"""
    def boom():
        raise RuntimeError('shutdown failed')

    monkeypatch.setattr(srv, 'initiate_graceful_shutdown', boom)
    servicer = AudioServiceServicer()
    resp = servicer.Shutdown(pb.ShutdownRequest())
    assert resp.success is False
    assert 'shutdown failed' in resp.message


# ---- server.initiate_graceful_shutdown() ----

class _FakeEngine:
    def __init__(self):
        self.shutdown_called = False
        self.wait_seconds = None

    def shutdown(self, wait_seconds=10.0):
        self.shutdown_called = True
        self.wait_seconds = wait_seconds


class _FakeGrpcServer:
    def __init__(self):
        self.stopped = None

    def stop(self, grace):
        self.stopped = grace


def _patch_server_state(monkeypatch, fake_engine, fake_server):
    """替换 server._server 与 audio_service 单例（经 sys.modules 注入）。"""
    fake_mod = types.ModuleType('audio_service.infrastructure.audio.audio_engine')
    fake_mod.audio_service = fake_engine
    monkeypatch.setitem(sys.modules,
                        'audio_service.infrastructure.audio.audio_engine', fake_mod)
    monkeypatch.setattr(srv, '_server', fake_server)
    monkeypatch.setattr(srv, '_shutdown_started', False)


def test_initiate_graceful_shutdown_stops_engine_and_server(monkeypatch):
    """engine.shutdown(wait=10) 先执行，再 server.stop(15)，之后进程自然退出。"""
    fake_engine = _FakeEngine()
    fake_server = _FakeGrpcServer()
    _patch_server_state(monkeypatch, fake_engine, fake_server)

    srv.initiate_graceful_shutdown()

    assert fake_engine.shutdown_called is True
    assert fake_engine.wait_seconds == srv.GRACEFUL_STOP_PLAYER_WAIT_SECONDS
    assert fake_server.stopped == srv.GRACEFUL_STOP_GRACE_SECONDS


def test_initiate_graceful_shutdown_idempotent(monkeypatch):
    """重复触发不二次 shutdown / stop（避免并发 Shutdown 二次 pa.terminate）。"""
    fake_engine = _FakeEngine()
    fake_server = _FakeGrpcServer()
    _patch_server_state(monkeypatch, fake_engine, fake_server)

    srv.initiate_graceful_shutdown()
    srv.initiate_graceful_shutdown()

    assert fake_engine.shutdown_called is True  # 只调一次
    assert fake_server.stopped == srv.GRACEFUL_STOP_GRACE_SECONDS
