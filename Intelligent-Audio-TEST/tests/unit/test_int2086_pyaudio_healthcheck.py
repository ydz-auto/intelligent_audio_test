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
import types

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
import run_audio_service_noshim as noshim
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


# ---- graceful_stop：gRPC 报错不得崩溃（INT-2086 打回 P1 修复） ----

class _FakeInactiveRpcError(Exception):
    """模拟 grpc>=1.5x 的 _InactiveRpcError：_state.code 是 StatusCode 枚举值（不可调用）。

    旧实现 `getattr(getattr(e, '_state', None), 'code', lambda: None)()` 会把它当函数
    硬调 → TypeError，优雅停止失败路径崩溃、taskkill 兜底不可达。必须走 e.code() API。
    """

    def __init__(self, status_code):
        super().__init__()
        self._state = types.SimpleNamespace(code=status_code)

    def code(self):
        return self._state.code


def _fake_pb_grpc_shutdown_raising(err):
    """返回 (pb, pb_grpc, None)：AudioServiceStub.Shutdown 抛 err（无需真实 server）。"""

    class _FakeStub:
        def Shutdown(self, request, timeout=None):
            raise err

    class _FakePbGrpc:
        def AudioServiceStub(self, channel):
            return _FakeStub()

    pb = types.SimpleNamespace(ShutdownRequest=lambda: None)
    return pb, _FakePbGrpc(), None


def test_graceful_stop_unimplemented_returns_fallback_not_crash():
    """Shutdown RPC 抛 UNIMPLEMENTED（枚举值 _state.code）→ 返回回退强停消息，不崩溃。"""
    import grpc
    pb, pb_grpc, _ = _fake_pb_grpc_shutdown_raising(
        _FakeInactiveRpcError(grpc.StatusCode.UNIMPLEMENTED))
    ok, msg = stop.graceful_stop(50052, timeout=1.0, _stubs=(pb, pb_grpc, None))
    assert ok is False
    assert '不支持 Shutdown RPC' in msg


def test_graceful_stop_generic_rpc_error_returns_fallback_not_crash():
    """任意 RPC 错误（UNAVAILABLE/超时）→ 返回失败消息，不崩溃，taskkill 兜底可达。"""
    import grpc
    pb, pb_grpc, _ = _fake_pb_grpc_shutdown_raising(
        _FakeInactiveRpcError(grpc.StatusCode.UNAVAILABLE))
    ok, msg = stop.graceful_stop(50052, timeout=1.0, _stubs=(pb, pb_grpc, None))
    assert ok is False
    assert 'gRPC Shutdown 调用失败' in msg


def test_main_stop_real_unimplemented_reaches_taskkill(monkeypatch):
    """真实 graceful_stop 命中 UNIMPLEMENTED → 不崩溃，main() 走 taskkill 兜底 + 释放 + 冷却。"""
    import grpc
    pb, pb_grpc, _ = _fake_pb_grpc_shutdown_raising(
        _FakeInactiveRpcError(grpc.StatusCode.UNIMPLEMENTED))
    monkeypatch.setattr(stop, '_import_grpc_stubs', lambda: (pb, pb_grpc, None))
    monkeypatch.setattr(stop, 'find_listener_pid', lambda port: '1234')
    monkeypatch.setattr(stop, 'wait_port_released',
                        lambda port, timeout: (True, 0.3))

    events = []
    monkeypatch.setattr(stop, 'cooldown', lambda s: events.append(('cooldown', s)))
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


# ---- 裸调用路径解析（审计 P2-1/P2-2 打回修复） ----

def test_resolve_repo_repo_layout_without_env(monkeypatch):
    """仓库规范版裸调用（无 AUDIO_SERVICE_REPO）：scripts/host_audio_service/../.. = 仓库根。"""
    monkeypatch.delenv('AUDIO_SERVICE_REPO', raising=False)
    monkeypatch.setattr(stop, '__file__', os.path.join(
        PROJECT_ROOT, 'scripts', 'host_audio_service', 'stop_audio_service.py'))
    repo = stop._resolve_repo()
    # 不能多退一层到仓库根父级（那会解析出 No module named 'shared'）
    assert os.path.basename(repo) == 'Intelligent-Audio-TEST'
    assert os.path.isdir(os.path.join(repo, 'shared', 'proto'))
    assert os.path.isdir(os.path.join(repo, 'audio_service'))


def test_resolve_repo_host_copy_fallback_without_env(monkeypatch):
    """宿主运行副本裸调用（无 AUDIO_SERVICE_REPO、不在 scripts/ 布局）→ 主 clone 兜底。"""
    monkeypatch.delenv('AUDIO_SERVICE_REPO', raising=False)
    monkeypatch.setattr(stop, '__file__',
                        r'D:\00_env\host_audio_service\stop_audio_service.py')
    assert stop._resolve_repo() == r'D:\00_code\V9.7.31\Intelligent-Audio-TEST'


def test_resolve_repo_env_override_wins(monkeypatch):
    """AUDIO_SERVICE_REPO 显式传入时优先（cmd 部署路径）。"""
    monkeypatch.setenv('AUDIO_SERVICE_REPO', r'C:\repo_a')
    assert stop._resolve_repo() == r'C:\repo_a'


def test_import_grpc_stubs_bare_invocation_succeeds(monkeypatch):
    """审计 P2-1：裸调用（无 AUDIO_SERVICE_REPO）桩导入成功 → 优雅停止不被静默降级为 taskkill。"""
    monkeypatch.delenv('AUDIO_SERVICE_REPO', raising=False)
    pb, pb_grpc, err = stop._import_grpc_stubs()
    assert err is None, f"裸调用 gRPC 桩导入失败: {err}"
    assert pb is not None and pb_grpc is not None


def test_noshim_resolve_repo_repo_layout(monkeypatch):
    """审计 P2-2：noshim 仓库规范版裸调用解析到仓库根，audio_service 模块可达。"""
    monkeypatch.delenv('AUDIO_SERVICE_REPO', raising=False)
    monkeypatch.setattr(noshim, '__file__', os.path.join(
        PROJECT_ROOT, 'scripts', 'host_audio_service',
        'run_audio_service_noshim.py'))
    repo = noshim._resolve_repo()
    assert os.path.basename(repo) == 'Intelligent-Audio-TEST'
    assert os.path.isdir(os.path.join(repo, 'audio_service'))


def test_noshim_resolve_repo_host_copy_fallback(monkeypatch):
    """noshim 宿主运行副本裸调用（不在 scripts/ 布局）→ 主 clone 兜底。"""
    monkeypatch.delenv('AUDIO_SERVICE_REPO', raising=False)
    monkeypatch.setattr(noshim, '__file__',
                        r'D:\00_env\host_audio_service\run_audio_service_noshim.py')
    assert noshim._resolve_repo() == r'D:\00_code\V9.7.31\Intelligent-Audio-TEST'
