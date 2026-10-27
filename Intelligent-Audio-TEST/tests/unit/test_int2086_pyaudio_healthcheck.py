# -*- coding: utf-8 -*-
"""INT-2086 脚本逻辑级验证：Pa_Initialize 自检超时禁连试 + 停止脚本冷却顺序。

覆盖验收标准 1：
- check_pyaudio_health：单次自检、超时即失败退出不重试、失败日志含恢复指引
- stop_audio_service：kill 后先确认端口释放、再冷却 ≥5s；优雅停止失败才 taskkill
"""
import os
import subprocess
import sys
import tempfile

os.environ.setdefault('DATABASE_URL',
                      'sqlite:///' + tempfile.mkdtemp(prefix='int2086_') + '/guard.db')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

_here = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(_here))  # <root>/tests/unit -> <root>
SCRIPTS_DIR = os.path.join(PROJECT_ROOT, 'scripts', 'host_audio_service')
for p in (PROJECT_ROOT, SCRIPTS_DIR):
    if p not in sys.path:
        sys.path.insert(0, p)

import check_pyaudio_health as chk
import stop_audio_service as stop


# ---- check_pyaudio_health：interpret_result ----

def test_health_interpret_success():
    ok, msg = chk.interpret_result(0, 'pyaudio OK, devices: 42\n', False)
    assert ok is True
    assert 'pyaudio OK, devices: 42' in msg


def test_health_interpret_failure_has_guidance():
    ok, msg = chk.interpret_result(1, 'cannot import pyaudio\n', False)
    assert ok is False
    # 验收：失败日志含「重启 Audiosrv / 重启机器」指引
    assert 'net stop Audiosrv' in msg
    assert '重启机器' in msg


def test_health_interpret_timeout_has_guidance_and_no_retry():
    ok, msg = chk.interpret_result(None, '', True)
    assert ok is False
    assert 'TIMEOUT' in msg
    assert '未重试' in msg
    assert 'net stop Audiosrv' in msg


# ---- check_pyaudio_health：run_selfcheck 子进程超时（禁连试） ----

class _FakeOkProc:
    returncode = 0

    def __init__(self):
        self.killed = False

    def communicate(self, timeout=None):
        return ('pyaudio OK, devices: 42\n', None)

    def kill(self):
        self.killed = True

    def wait(self, timeout=None):
        return 0


def test_selfcheck_ok_child():
    proc = _FakeOkProc()
    rc, out, timed_out = chk.run_selfcheck('py', 5.0, popen=lambda *a, **k: proc)
    assert rc == 0
    assert 'pyaudio OK' in out
    assert timed_out is False
    assert proc.killed is False


class _FakeHangingProc:
    """communicate(timeout) 抛 TimeoutExpired → 触发超时失败路径。"""

    def __init__(self):
        self.killed = False
        self._out = ''

    def communicate(self, timeout=None):
        raise subprocess.TimeoutExpired('py', timeout, output=self._out)

    def kill(self):
        self.killed = True

    def wait(self, timeout=None):
        return 0


def test_selfcheck_hang_times_out_no_retry():
    """超时一次即失败退出：子进程被 kill，不自动重试（run_selfcheck 只 spawn 一次）。"""
    proc = _FakeHangingProc()
    rc, out, timed_out = chk.run_selfcheck('py', 0.1, popen=lambda *a, **k: proc)
    assert rc is None
    assert timed_out is True
    assert proc.killed is True
    ok, msg = chk.interpret_result(rc, out, timed_out)
    assert ok is False
    assert 'TIMEOUT' in msg


# ---- stop_audio_service：端口释放 + 冷却顺序 ----

def test_find_listener_pid_parses_netstat(monkeypatch):
    fake_out = (
        '\n'
        '  TCP    0.0.0.0:50052           0.0.0.0:0              LISTENING       12345\n'
        '  TCP    0.0.0.0:50053           0.0.0.0:0              LISTENING       54321\n'
    )

    class _FakeResult:
        stdout = fake_out

    def fake_run(*args, **kwargs):
        return _FakeResult()

    monkeypatch.setattr(subprocess, 'run', fake_run)
    assert stop.find_listener_pid(50052) == '12345'
    assert stop.find_listener_pid(9999) is None


def test_wait_port_released_confirms_before_cooldown(monkeypatch):
    """端口释放确认（wait_port_released=True）后才进入冷却。"""
    order = []

    def fake_is_listening(port):
        return False  # 已释放

    released, elapsed = stop.wait_port_released(50052, timeout=5.0,
                                                is_listening=fake_is_listening)
    assert released is True
    order.append('release')

    monkeypatch.setattr(stop.time, 'sleep', lambda s: order.append(f'cooldown:{s}'))
    stop.cooldown(8.0)
    assert order == ['release', 'cooldown:8.0']


def test_wait_port_released_timeout_returns_false():
    """端口一直不释放 → (False, elapsed)，调用方应报残留进程。"""
    released, elapsed = stop.wait_port_released(50052, timeout=0.3,
                                                is_listening=lambda port: True)
    assert released is False
    assert elapsed >= 0.3


def test_cooldown_floor_is_5_seconds():
    """冷却默认 8s（负责人拍板 5~10s 区间内），低于 5 视为不达标。"""
    assert stop.COOLDOWN_DEFAULT >= 5.0
    assert stop.COOLDOWN_DEFAULT <= 10.0


def test_main_stop_graceful_then_release_then_cooldown(monkeypatch):
    """优雅停止成功路径：不 taskkill，先端口释放再冷却。"""
    events = []

    monkeypatch.setattr(stop, 'find_listener_pid', lambda port: '1234')
    monkeypatch.setattr(stop, 'graceful_stop',
                        lambda port, timeout: (True, 'graceful shutdown initiated'))
    monkeypatch.setattr(stop, 'wait_port_released',
                        lambda port, timeout: (True, 0.2))
    monkeypatch.setattr(stop, 'cooldown',
                        lambda s: events.append(('cooldown', s)))

    taskkill_called = []

    def fake_taskkill(*a, **k):
        taskkill_called.append(a)
        class _R:
            returncode = 0
            stdout = ''
            stderr = ''
        return _R()

    monkeypatch.setattr(subprocess, 'run', fake_taskkill)

    rc = stop.main(['--port', '50052', '--cooldown', '8', '--graceful-timeout', '15'])
    assert rc == 0
    assert taskkill_called == []  # 优雅停止成功就不强杀
    assert events == [('cooldown', 8.0)]


def test_main_stop_fallback_taskkill_when_unimplemented(monkeypatch):
    """优雅停止不可用（旧代码 UNIMPLEMENTED）→ 回退 taskkill，且仍走释放+冷却。"""
    events = []

    monkeypatch.setattr(stop, 'find_listener_pid', lambda port: '1234')
    monkeypatch.setattr(stop, 'graceful_stop',
                        lambda port, timeout: (False, '服务端不支持 Shutdown RPC'))
    monkeypatch.setattr(stop, 'wait_port_released',
                        lambda port, timeout: (True, 0.3))
    monkeypatch.setattr(stop, 'cooldown',
                        lambda s: events.append(('cooldown', s)))

    taskkill_calls = []

    def fake_taskkill(*a, **k):
        taskkill_calls.append(a[0] if a else [])
        class _R:
            returncode = 0
            stdout = ''
            stderr = ''
        return _R()

    monkeypatch.setattr(subprocess, 'run', fake_taskkill)

    rc = stop.main(['--port', '50052', '--cooldown', '8'])
    assert rc == 0
    assert any('taskkill' in ' '.join(c) for c in taskkill_calls)
    assert events == [('cooldown', 8.0)]


def test_main_stop_port_not_released_is_fatal(monkeypatch):
    """端口未释放 → 退出码 1（残留进程需人工清理，不重复强杀）。"""
    monkeypatch.setattr(stop, 'find_listener_pid', lambda port: '1234')
    monkeypatch.setattr(stop, 'graceful_stop', lambda port, timeout: (True, 'ok'))
    monkeypatch.setattr(stop, 'wait_port_released',
                        lambda port, timeout: (False, 60.0))
    monkeypatch.setattr(stop, 'cooldown', lambda s: None)
    rc = stop.main(['--port', '50052', '--cooldown', '8'])
    assert rc == 1
