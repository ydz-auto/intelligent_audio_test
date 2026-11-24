# -*- coding: utf-8 -*-
"""ASR 服务手动启停 + 进程守护 + 开机自启。

守护模型与 scripts/host_services 一致：
    WMI（脱离调用方进程树）
      └─ powershell run_forever_asr.ps1      # while($true)，子进程退出 5s 重启
           └─ pythonw asr_server.py

用法：
    python asr_server/asr_control.py start [--with-tunnel] [--timeout 180]
    python asr_server/asr_control.py stop
    python asr_server/asr_control.py restart [--with-tunnel]
    python asr_server/asr_control.py status
    python asr_server/asr_control.py tunnel-start | tunnel-stop
    python asr_server/asr_control.py install-autostart | uninstall-autostart

解释器优先级：ASR_PYTHON 环境变量 → 仓库根 .env 的 ASR_PYTHON → 运行本脚本的
Python。ASR 依赖 funasr/torch，必须指向装好依赖的环境。
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent
REPO = APP_ROOT.parent
ENTRY = APP_ROOT / 'asr_server.py'
SUPERVISOR = APP_ROOT / 'run_forever_asr.ps1'
TUNNEL = APP_ROOT / 'ssh_tunnel_asr.ps1'
AUTOSTART_PS1 = APP_ROOT / 'autostart_asr.ps1'

LOG_DIR = APP_ROOT / 'logs'
PID_FILE = LOG_DIR / 'asr.supervisor.pid'
STOP_FLAG = LOG_DIR / 'asr.supervisor.stop'
SUP_LOG = LOG_DIR / 'asr.supervisor.log'
ENV_FILE = LOG_DIR / 'asr.env.json'
TUNNEL_LAUNCHER = LOG_DIR / 'asr.tunnel.launcher.ps1'

STARTUP_DIR = (Path(os.environ.get('APPDATA', '')) /
               'Microsoft' / 'Windows' / 'Start Menu' / 'Programs' / 'Startup')
STARTUP_VBS = STARTUP_DIR / 'IAT-ASR.vbs'

READY_TIMEOUT = 180.0     # 首次启动含模型加载 60-80s，留足下载余量
STOP_TIMEOUT = 15.0

_WMI_SCRIPT = (
    '$r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create '
    '-Arguments @{CommandLine=$env:STACK_LAUNCH_CMD; '
    'CurrentDirectory=$env:STACK_LAUNCH_CWD}; '
    'Write-Output $r.ProcessId; exit $r.ReturnValue'
)


# ---------------------------------------------------------------- 基础探测

def asr_port() -> int:
    return int(os.environ.get('ASR_PORT', '10095'))


def port_listening(port: int, host: str = '127.0.0.1') -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        try:
            sock.connect((host, port))
            return True
        except OSError:
            return False


def listener_pid(port: int) -> int | None:
    """Windows: netstat 找监听指定端口的 PID（按端口精确匹配，避免 :10095 命中 :110095）。"""
    try:
        out = subprocess.run(
            ['netstat', '-ano', '-p', 'tcp'],
            capture_output=True, text=True, encoding='utf-8', errors='replace',
        ).stdout
    except OSError:
        return None
    for line in out.splitlines():
        if 'LISTENING' not in line.upper():
            continue
        parts = line.split()
        if len(parts) < 5 or parts[1].rsplit(':', 1)[-1] != str(port):
            continue
        if parts[-1].isdigit():
            return int(parts[-1])
    return None


def wait_port(port: int, want_open: bool, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if port_listening(port) is want_open:
            return True
        time.sleep(0.5)
    return port_listening(port) is want_open


def _powershell_pids(pattern: str) -> list[int]:
    """按命令行正则找存活的 powershell 进程（排除探测进程自身）。"""
    script = (
        'Get-CimInstance Win32_Process | Where-Object { '
        f"$_.ProcessId -ne $PID -and $_.Name -match '^(powershell|pwsh)\\.exe$' "
        f"-and $_.CommandLine -match '{pattern}' "
        '} | Select-Object -ExpandProperty ProcessId'
    )
    result = subprocess.run(
        ['powershell', '-NoProfile', '-Command', script],
        capture_output=True, text=True, encoding='utf-8', errors='replace',
    )
    return [int(x) for x in (result.stdout or '').split() if x.strip().isdigit()]


def _taskkill(pid: int) -> None:
    subprocess.run(['taskkill', '/PID', str(pid), '/T', '/F'],
                   capture_output=True, text=True)


# ---------------------------------------------------------------- 解释器

def _dotenv_value(key: str) -> str | None:
    env_file = REPO / '.env'
    if not env_file.is_file():
        return None
    for line in env_file.read_text(encoding='utf-8', errors='replace').splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        name, value = line.split('=', 1)
        if name.strip() == key:
            return value.strip().strip('"').strip("'")
    return None


def resolve_python() -> str:
    for candidate in (os.environ.get('ASR_PYTHON'), _dotenv_value('ASR_PYTHON')):
        if candidate and Path(candidate).exists():
            return str(Path(candidate))
    return sys.executable


def _runner(python: str) -> str:
    """优先同目录 pythonw.exe：守护进程无控制台，避免闪窗。"""
    exe = Path(python)
    windowless = exe.with_name('pythonw.exe')
    return str(windowless) if windowless.exists() else python


# ---------------------------------------------------------------- 守护进程

def _supervisor_alive() -> bool:
    try:
        pid = int(PID_FILE.read_text(encoding='ascii').strip())
    except (OSError, ValueError):
        return False
    result = subprocess.run(
        ['powershell', '-NoProfile', '-Command',
         f'(Get-CimInstance Win32_Process -Filter "ProcessId={pid}").CommandLine'],
        capture_output=True, text=True, encoding='utf-8', errors='replace',
    )
    cmdline = (result.stdout or '').strip()
    return 'run_forever_asr.ps1' in cmdline


def _request_stop(on: bool = True) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    if on:
        STOP_FLAG.write_text('stop\n', encoding='ascii')
    elif STOP_FLAG.exists():
        STOP_FLAG.unlink()


def _kill_supervisor() -> None:
    if not _supervisor_alive():
        PID_FILE.unlink(missing_ok=True)
        return
    try:
        pid = int(PID_FILE.read_text(encoding='ascii').strip())
    except (OSError, ValueError):
        return
    _taskkill(pid)
    deadline = time.monotonic() + STOP_TIMEOUT
    while time.monotonic() < deadline and _supervisor_alive():
        time.sleep(0.3)
    PID_FILE.unlink(missing_ok=True)


def _wmi_create(command_line: str, cwd: Path) -> int:
    env = {**os.environ,
           'STACK_LAUNCH_CMD': command_line,
           'STACK_LAUNCH_CWD': str(cwd)}
    result = subprocess.run(
        ['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass',
         '-Command', _WMI_SCRIPT],
        capture_output=True, text=True, encoding='utf-8', errors='replace', env=env,
    )
    lines = [line.strip() for line in (result.stdout or '').splitlines() if line.strip()]
    pid = int(lines[-1]) if lines and lines[-1].isdigit() else None
    if result.returncode != 0 or not pid:
        detail = (result.stderr or result.stdout or '').strip()
        raise RuntimeError(f'WMI 拉起失败 rc={result.returncode}: {detail}')
    return pid


def _launch_supervisor() -> int:
    """完整环境落 JSON（WMI 子进程不继承调用方环境），再由守护壳注入。"""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    python = resolve_python()
    env = {**os.environ, 'PYTHONUTF8': '1', 'ASR_PORT': str(asr_port())}
    py_dir = Path(python).parent
    env['PATH'] = os.pathsep.join([str(py_dir), env.get('PATH', '')])
    ENV_FILE.write_text(json.dumps(env, ensure_ascii=False), encoding='utf-8')

    _request_stop(False)
    PID_FILE.unlink(missing_ok=True)
    command_line = (
        f'powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden '
        f'-File "{SUPERVISOR}" -Python "{_runner(python)}" '
        f'-Entry "{ENTRY}" -EnvFile "{ENV_FILE}" '
        f'-Log "{SUP_LOG}" -StopFlag "{STOP_FLAG}" -PidFile "{PID_FILE}"')
    return _wmi_create(command_line, APP_ROOT)


# ---------------------------------------------------------------- 服务启停

def start(timeout: float = READY_TIMEOUT, with_tunnel: bool = False) -> tuple[bool, str]:
    if not ENTRY.is_file():
        return False, f'缺少入口文件: {ENTRY}'
    if with_tunnel:
        tunnel_start()
    port = asr_port()
    if port_listening(port):
        return True, f'ASR 已在监听 :{port}（未重复启动）'
    if _supervisor_alive():
        ok = wait_port(port, True, timeout)
        return ok, (f'ASR 守护已在运行，等待就绪成功 :{port}' if ok
                    else f'等待 :{port} 超时，见 {SUP_LOG}')
    try:
        _launch_supervisor()
    except RuntimeError as exc:
        return False, str(exc)
    ok = wait_port(port, True, timeout)
    if ok:
        return True, f'ASR 已启动 :{port}（模型加载完成前 /health 仍为 *_loaded=false）'
    return False, f'启动超时，见 {SUP_LOG} 与 {LOG_DIR / "asr_server.log"}'


def stop() -> tuple[bool, str]:
    port = asr_port()
    _request_stop(True)
    pid = listener_pid(port)
    if pid:
        _taskkill(pid)
    _kill_supervisor()
    ok = wait_port(port, False, STOP_TIMEOUT)
    _request_stop(False)
    if ok:
        return True, f'ASR 已停止 :{port}'
    return False, f'ASR 停止超时，仍有进程占用 :{port}'


# ---------------------------------------------------------------- 反向隧道

def _tunnel_pids() -> list[int]:
    return _powershell_pids(r'asr\.tunnel\.launcher\.ps1|ssh_tunnel_asr\.ps1')


def tunnel_start() -> tuple[bool, str]:
    if _tunnel_pids():
        return True, '反向隧道已在运行（未重复启动）'
    if not TUNNEL.is_file():
        return False, f'缺少隧道脚本: {TUNNEL}'
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    # WMI 进程拿到的是 provider 的精简 PATH，ssh 可能不在其中；
    # 用一层 launcher 把调用方的 PATH 带进去。
    TUNNEL_LAUNCHER.write_text(
        "$env:PATH = '{path}'\n& '{script}'\n".format(
            path=os.environ.get('PATH', ''), script=TUNNEL),
        encoding='utf-8-sig')
    try:
        _wmi_create(
            f'powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden '
            f'-File "{TUNNEL_LAUNCHER}"', APP_ROOT)
    except RuntimeError as exc:
        return False, str(exc)
    time.sleep(2)
    pids = _tunnel_pids()
    if pids:
        return True, f'反向隧道已启动 pid={pids[0]}'
    return False, f'隧道进程未存活，见 {LOG_DIR / "asr_server.log"}（隧道输出走控制台，无独立日志）'


def tunnel_stop() -> tuple[bool, str]:
    pids = _tunnel_pids()
    if not pids:
        return True, '反向隧道未运行'
    for pid in pids:
        _taskkill(pid)
    time.sleep(1)
    left = _tunnel_pids()
    if left:
        return False, f'隧道进程未退出: {left}'
    return True, f'反向隧道已停止 ({pids})'


# ---------------------------------------------------------------- 状态

def _health() -> dict | None:
    try:
        with urllib.request.urlopen(
                f'http://127.0.0.1:{asr_port()}/health', timeout=2) as resp:
            return json.loads(resp.read().decode('utf-8', errors='replace'))
    except (urllib.error.URLError, OSError, ValueError):
        return None


def status() -> bool:
    port = asr_port()
    listening = port_listening(port)
    sup = _supervisor_alive()
    tunnel = _tunnel_pids()
    health = _health() if listening else None
    print(f'解释器   : {resolve_python()}')
    print(f'入口     : {ENTRY} (exists={ENTRY.is_file()})')
    print(f'服务端口 : :{port} listening={listening} pid={listener_pid(port)}')
    print(f'守护进程 : alive={sup} '
          f'pid={PID_FILE.read_text(encoding="ascii").strip() if PID_FILE.exists() else None}')
    print(f'守护日志 : {SUP_LOG}')
    print(f'反向隧道 : {"运行中 pid=" + str(tunnel) if tunnel else "未运行"}')
    if health is not None:
        loaded = {k: health.get(k) for k in
                  ('status', 'vad_loaded', 'asr_loaded', 'paraformer_loaded')}
        print(f'健康检查 : {loaded}')
    else:
        print('健康检查 : 不可达')
    return listening


# ---------------------------------------------------------------- 自启

def install_autostart() -> tuple[bool, str]:
    if not AUTOSTART_PS1.is_file():
        return False, f'缺少自启脚本: {AUTOSTART_PS1}'
    if not STARTUP_DIR.is_dir():
        return False, f'启动目录不存在: {STARTUP_DIR}'
    STARTUP_VBS.write_text(
        'Set ws = CreateObject("Wscript.Shell")\n'
        'ws.Run "powershell -NoProfile -ExecutionPolicy Bypass -File '
        f'""{AUTOSTART_PS1}""", 0, False\n',
        encoding='ascii')
    return True, f'已写入登录自启: {STARTUP_VBS}'


def uninstall_autostart() -> tuple[bool, str]:
    if STARTUP_VBS.exists():
        STARTUP_VBS.unlink()
        return True, f'已移除登录自启: {STARTUP_VBS}'
    return True, '登录自启未安装'


# ---------------------------------------------------------------- CLI

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='ASR 服务守护 / 启停')
    parser.add_argument('action', choices=[
        'start', 'stop', 'restart', 'status', 'tunnel-start', 'tunnel-stop',
        'install-autostart', 'uninstall-autostart',
    ])
    parser.add_argument('--with-tunnel', action='store_true', help='start/restart 时一并拉起反向隧道')
    parser.add_argument('--timeout', type=float, default=READY_TIMEOUT, help='等待服务就绪秒数')
    args = parser.parse_args(argv)

    if args.action in ('start', 'restart'):
        if args.action == 'restart':
            stop()
        ok, msg = start(timeout=args.timeout, with_tunnel=args.with_tunnel)
    elif args.action == 'stop':
        ok, msg = stop()
    elif args.action == 'status':
        return 0 if status() else 1
    elif args.action == 'tunnel-start':
        ok, msg = tunnel_start()
    elif args.action == 'tunnel-stop':
        ok, msg = tunnel_stop()
    elif args.action == 'install-autostart':
        ok, msg = install_autostart()
    else:
        ok, msg = uninstall_autostart()

    print(('[ok] ' if ok else '[fail] ') + msg)
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
