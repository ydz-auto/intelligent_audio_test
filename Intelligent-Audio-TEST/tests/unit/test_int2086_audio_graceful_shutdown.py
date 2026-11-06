# -*- coding: utf-8 -*-
"""INT-2086 优雅停止通道：Pa_Initialize 防楔死（停播放 → 等流关闭 → pa.terminate）。

锁定：
- PyAudioDriver.terminate() 调 pa.terminate() 并把 self.pa 置 None（端点会话释放）
- AudioService.shutdown() 先 set 全部 stop_event、等播放 future 结束，再 driver.terminate()
- servicer Shutdown handler 触发 server.initiate_graceful_shutdown()
- server.initiate_graceful_shutdown() 调 audio_service.shutdown() + server.stop(grace)，幂等
"""
import os
import runpy
import socket
import sys
import tempfile
import time
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
    """Shutdown handler 经实例 _grpc_server 触发 initiate_graceful_shutdown(server=...)。

    INT-2086 审计 P1：server 引用必须经实例传（start_grpc_server 挂的 _grpc_server），
    不能只靠 server.py 模块全局——runpy-as-__main__ 生产启动下惰性 import 拿到的是
    第二份拷贝、模块全局 _server=None，会假成功不真停。
    """
    called = {}

    def fake_initiate(server=None):
        called['initiated'] = True
        called['server'] = server

    monkeypatch.setattr(srv, 'initiate_graceful_shutdown', fake_initiate)
    servicer = AudioServiceServicer()
    fake_server = object()
    servicer._grpc_server = fake_server
    resp = servicer.Shutdown(pb.ShutdownRequest())
    assert called.get('initiated') is True
    assert called.get('server') is fake_server
    assert resp.success is True


def test_servicer_shutdown_without_attached_server_passes_none(monkeypatch):
    """实例未挂 _grpc_server（直接 new 出来未起服）时传 None，不抛。"""
    called = {}

    def fake_initiate(server=None):
        called['server'] = server

    monkeypatch.setattr(srv, 'initiate_graceful_shutdown', fake_initiate)
    servicer = AudioServiceServicer()
    resp = servicer.Shutdown(pb.ShutdownRequest())
    assert called.get('server') is None
    assert resp.success is True


def test_servicer_shutdown_error_returns_failure(monkeypatch):
    """initiate_graceful_shutdown 抛异常时返回 success=False（协议不裸抛）。"""
    def boom(server=None):
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


def test_initiate_graceful_shutdown_with_explicit_server(monkeypatch):
    """显式传 server（servicer._grpc_server 路径）时停显式引用，不读模块全局。

    模拟 runpy-as-__main__ 第二份拷贝：模块全局 _server 未设置（None），
    只要显式引用给了 server，仍真停（审计 P1 修复核心）。
    """
    fake_engine = _FakeEngine()
    fake_server = _FakeGrpcServer()
    _patch_server_state(monkeypatch, fake_engine, None)  # 模块全局 _server 置 None

    srv.initiate_graceful_shutdown(server=fake_server)

    assert fake_engine.shutdown_called is True
    assert fake_engine.wait_seconds == srv.GRACEFUL_STOP_PLAYER_WAIT_SECONDS
    assert fake_server.stopped == srv.GRACEFUL_STOP_GRACE_SECONDS


def test_initiate_graceful_shutdown_explicit_none_falls_back_to_global(monkeypatch):
    """server=None（Ctrl+C 路径）时回退模块全局 _server。"""
    fake_engine = _FakeEngine()
    fake_server = _FakeGrpcServer()
    _patch_server_state(monkeypatch, fake_engine, fake_server)

    srv.initiate_graceful_shutdown(server=None)

    assert fake_engine.shutdown_called is True
    assert fake_server.stopped == srv.GRACEFUL_STOP_GRACE_SECONDS


# ---- 生产启动路径：runpy-as-__main__（审计 P1 复现链） ----

def _pick_free_port():
    """挑空闲高位端口，避开 50052 与 Windows 已知排除/并行段。"""
    while True:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('127.0.0.1', 0))
            port = s.getsockname()[1]
        if (port in (50052,) or 50060 <= port <= 50159
                or 53500 <= port <= 53699 or 55900 <= port <= 56100):
            continue
        return port


def _tcp_port_listening(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.3)
        try:
            s.connect(('127.0.0.1', port))
            return True
        except OSError:
            return False


def test_shutdown_rpc_stops_runpy_started_server(monkeypatch):
    """runpy-as-__main__ 生产启动路径：真实 Shutdown RPC 停 gRPC 服务。

    审计 P1 复现链：runpy.run_module(..., run_name='__main__') 只登记 __main__、
    不登记真实模块名 → servicer 惰性 import server.py 拿到非 __main__ 拷贝
    （模块全局 _server=None）。修复后 server 引用挂在 servicer 实例 _grpc_server
    上，Shutdown 真停 gRPC 服务；未修复时只告警不 stop，wait_for_termination
    不返回、本用例超时失败。
    """
    import grpc
    from shared.infrastructure.config import BaseConfig
    from audio_service.infrastructure.audio.audio_engine import audio_service
    from audio_service.infrastructure.persistence import soft_delete_cleaner
    import shared.config.service_ports as service_ports
    from shared.proto import audio_service_pb2 as pb
    from shared.proto import audio_service_pb2_grpc as pb_grpc

    port = _pick_free_port()
    monkeypatch.setattr(service_ports, 'AUDIO_SERVICE_GRPC_PORT', port)
    # 测试不开上游预热 / 真 pyaudio / 真清理线程；起服只验证优雅停止通道
    monkeypatch.setattr(BaseConfig, 'AUDIO_TAG_ACL_WARMUP_ENABLED', False)
    monkeypatch.setattr(audio_service, 'init_driver', lambda: None)

    class _FakeCleaner:
        def start(self):
            pass

    monkeypatch.setattr(soft_delete_cleaner, 'get_cleaner', lambda: _FakeCleaner())

    errors = []

    def _run_module():
        try:
            runpy.run_module('audio_service.interfaces.grpc.server',
                             run_name='__main__', alter_sys=True)
        except BaseException as e:  # noqa: BLE001 - 抓进 errors 供断言
            errors.append(e)

    t = threading.Thread(target=_run_module, daemon=True)
    t.start()
    channel = None
    try:
        deadline = time.monotonic() + 20.0
        while time.monotonic() < deadline:
            if _tcp_port_listening(port):
                break
            if errors:
                raise AssertionError(f"runpy 起服线程异常: {errors[0]}")
            time.sleep(0.1)
        else:
            raise AssertionError(f"runpy 起的服务 {port} 在 20s 内未监听")

        channel = grpc.insecure_channel(f'127.0.0.1:{port}')
        stub = pb_grpc.AudioServiceStub(channel)
        resp = stub.Shutdown(pb.ShutdownRequest(), timeout=10.0)
        assert resp.success is True, resp.message

        # wait_for_termination 应返回、runpy 线程退出、端口释放
        t.join(timeout=30.0)
        assert not errors, f"runpy 线程异常: {errors[0]}"
        assert not t.is_alive(), \
            "Shutdown RPC 后 runpy 起的服务未退出（wait_for_termination 未返回）"
        assert not _tcp_port_listening(port), f"端口 {port} 在 Shutdown 后仍监听"
    finally:
        if channel is not None:
            channel.close()
        if t.is_alive():
            # 兜底：测试失败时避免残留监听进程
            t.join(timeout=5.0)
