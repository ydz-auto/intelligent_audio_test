# -*- coding: utf-8 -*-
"""宿主服务（audio_service / device_service）启停与环境口径。

单一来源原则：
- **端口/基础设施**：以 ``docker compose config`` 的解析结果为准（compose 与脚本用同一份
  env 文件），不再在启动脚本里各抄一份宿主端口——历史上 15432/15435/5432 三份口径
  漂移，导致宿主 audio_service 连到测试库、音频列表“消失”。
- **DB/Redis/OSS 地址**：由上面解析出的宿主端口拼装，宿主服务永远连 Docker 栈暴露的
  入口（主库 intelligent_audio_test），不读仓库根 .env 里给 pytest 用的测试库地址。
- **宿主服务自身端口**：audio 50052 / device 50053（shared/config/service_ports.py 注册值）。

只被 ``stack.py`` 调用，不单独作为命令行入口。
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PY = sys.executable

PROJECT = os.environ.get('COMPOSE_PROJECT_NAME', 'intelligent-audio-test')
COMPOSE_FILE = REPO / 'docker' / 'docker-compose.yml'
LOG_DIR = REPO / 'logs' / 'host_services'
AUDIO_DIR = REPO / 'scripts' / 'host_audio_service'
SHIM_DIR = REPO / 'tests' / 'fixtures' / 'pyaudio_shim'

AUDIO_PORT = 50052
DEVICE_PORT = 50053

ENTRY = Path(__file__).with_name('service_entry.py')

# WMI 拉起的进程父级是 WmiPrvSE（系统服务），不在 agent run 的 job 对象里；
# 否则 run 结束会整树回收，宿主服务刚起来就被杀掉。
_WMI_SCRIPT = (
    '$r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create '
    '-Arguments @{CommandLine=$env:STACK_LAUNCH_CMD; '
    'CurrentDirectory=$env:STACK_LAUNCH_CWD}; '
    'Write-Output $r.ProcessId; exit $r.ReturnValue'
)

# 容器内 gRPC 端口 → 宿主服务作为客户端要读的环境变量（BaseConfig）。
# 宿主端口值从 compose config 解析，避免与 docker/.env 各处手抄漂移。
_GRPC_ENV_BY_CONTAINER_PORT = {
    50051: 'E2E_TEST_SERVICE_GRPC_PORT',
    51061: 'TASK_SERVICE_GRPC_PORT',
    51067: 'ALGORITHM_SERVICE_GRPC_PORT',
    51068: 'REPORT_SERVICE_GRPC_PORT',
    51069: 'AUTH_SERVICE_GRPC_PORT',
    51091: 'EVALUATION_SERVICE_GRPC_PORT',
    51071: 'API_TEST_SERVICE_GRPC_PORT',
    51081: 'API_ADAPTER_SERVICE_GRPC_PORT',
    51101: 'TRANSFER_AGENT_GRPC_PORT',
}

# 这些服务的 *HOST 统一指向本机（宿主服务经 compose 发布端口访问容器）
_GRPC_HOST_VARS = (
    'E2E_TEST_SERVICE_HOST',
    'TASK_SERVICE_HOST',
    'ALGORITHM_SERVICE_HOST',
    'REPORT_SERVICE_HOST',
    'AUTH_SERVICE_HOST',
    'EVALUATION_SERVICE_HOST',
    'API_TEST_SERVICE_HOST',
    'API_ADAPTER_SERVICE_HOST',
    'TRANSFER_AGENT_SERVICE_HOST',
)

# 默认基础设施宿主端口（compose 未发布会回落到这些值）
_DEFAULT_INFRA_PORTS = {5432: 5432, 6379: 6379, 9000: 9000}

DEFAULT_DB_USER = 'intelligent_audio_test'
DEFAULT_DB_PASSWORD = 'intelligent_audio_test666'
DEFAULT_DB_NAME = 'intelligent_audio_test'

READY_TIMEOUT_DEFAULT = 90.0
DEVICE_STOP_TIMEOUT = 15.0


# ---------------------------------------------------------------- 环境口径

def published_ports() -> dict[int, int]:
    """容器内端口 → 宿主发布端口（直接问 compose，唯一口径）。"""
    cmd = ['docker', 'compose', '-p', PROJECT, '-f', str(COMPOSE_FILE),
           'config', '--format', 'json']
    result = subprocess.run(cmd, cwd=str(REPO), capture_output=True,
                            text=True, encoding='utf-8', errors='replace')
    if result.returncode != 0:
        raise RuntimeError(f'解析 compose 配置失败: {(result.stderr or "").strip()}')
    config = json.loads(result.stdout)
    ports: dict[int, int] = {}
    for service in (config.get('services') or {}).values():
        for item in service.get('ports') or []:
            target, published = item.get('target'), item.get('published')
            if target and published:
                ports[int(target)] = int(published)
    return ports


def host_env() -> dict:
    """宿主服务子进程环境：仓库根 .env + compose 解析出的宿主端口。"""
    from dotenv import load_dotenv
    load_dotenv(REPO / '.env', override=False)

    env = os.environ.copy()
    ports = published_ports()
    infra = {**{k: ports.get(k, v) for k, v in _DEFAULT_INFRA_PORTS.items()}}

    user = env.get('POSTGRES_USER', DEFAULT_DB_USER)
    password = env.get('POSTGRES_PASSWORD', DEFAULT_DB_PASSWORD)
    database = env.get('POSTGRES_DB', DEFAULT_DB_NAME)
    env['DATABASE_URL'] = (
        f'postgresql://{user}:{password}@127.0.0.1:{infra[5432]}/{database}')
    env['REDIS_URL'] = f"redis://127.0.0.1:{infra[6379]}"
    env['OSS_ENDPOINT'] = f"http://127.0.0.1:{infra[9000]}"
    env['OSS_PUBLIC_ENDPOINT'] = f"http://127.0.0.1:{infra[9000]}"

    for container_port, env_name in _GRPC_ENV_BY_CONTAINER_PORT.items():
        if container_port in ports:
            env[env_name] = str(ports[container_port])
    for env_name in _GRPC_HOST_VARS:
        env[env_name] = '127.0.0.1'

    env['AUDIO_SERVICE_HOST'] = '127.0.0.1'
    env['AUDIO_SERVICE_GRPC_PORT'] = str(AUDIO_PORT)
    env['DEVICE_SERVICE_HOST'] = '127.0.0.1'
    env['DEVICE_SERVICE_GRPC_PORT'] = str(DEVICE_PORT)
    # 容器经 host.docker.internal 访问宿主服务，必须绑全部网卡
    env['SERVICE_HOST'] = '0.0.0.0'
    env['PYTHONUTF8'] = env.get('PYTHONUTF8', '1')
    return env


# ---------------------------------------------------------------- 端口探测

def port_listening(port: int, host: str = '127.0.0.1') -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        try:
            sock.connect((host, port))
            return True
        except OSError:
            return False


def listener_pid(port: int) -> int | None:
    """Windows: netstat 找监听指定端口的 PID。"""
    try:
        out = subprocess.run(
            ['netstat', '-ano', '-p', 'tcp'],
            capture_output=True, text=True, encoding='utf-8', errors='replace',
        ).stdout
    except OSError:
        return None
    needle = f':{port}'
    for line in out.splitlines():
        if needle in line and 'LISTENING' in line.upper():
            parts = line.split()
            if parts and parts[-1].isdigit():
                return int(parts[-1])
    return None


def wait_port(port: int, want_open: bool, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if port_listening(port) is want_open:
            return True
        time.sleep(0.5)
    return port_listening(port) is want_open


# ---------------------------------------------------------------- 进程拉起

def _wmi_create(command_line: str, cwd: Path) -> int:
    """经 WMI 拉起进程，返回 PID；失败抛 RuntimeError。"""
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


def _launch(service: str, mode: str) -> int:
    """把完整环境落成 JSON（WMI 进程不继承调用方环境），再 WMI 拉起入口。"""
    env = host_env()
    if service == 'audio' and mode == 'shim':
        env['PYTHONPATH'] = os.pathsep.join(
            [str(SHIM_DIR), str(REPO), str(REPO / 'shared' / 'proto')])
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    env_file = LOG_DIR / f'{service}.env.json'
    env_file.write_text(json.dumps(env, ensure_ascii=False), encoding='utf-8')
    command_line = (
        f'"{PY}" "{ENTRY}" --service {service} --mode {mode} --env-file "{env_file}"')
    return _wmi_create(command_line, REPO)


def _start(name: str, service: str, mode: str, port: int,
           timeout: float, log_name: str) -> tuple[bool, str]:
    if port_listening(port):
        return True, f'[skip] {name} 已在 :{port} 监听'
    try:
        pid = _launch(service, mode)
    except RuntimeError as exc:
        return False, f'[fail] {name} 拉起失败: {exc}'
    if wait_port(port, True, timeout):
        return True, f'[ok] {name} 已启动 pid={pid} :{port}（WMI 脱离 run 树）'
    tail = _log_tail(log_name)
    return False, (f'[fail] {name} 在 {timeout:.0f}s 内未监听 :{port}，'
                   f'日志: {LOG_DIR / log_name}\n{tail}')


def _log_tail(log_name: str, lines: int = 20) -> str:
    path = LOG_DIR / log_name
    if not path.is_file():
        return ''
    try:
        content = path.read_text(encoding='utf-8', errors='replace').splitlines()
    except OSError:
        return ''
    return '\n'.join(content[-lines:])


# ---------------------------------------------------------------- audio

def start_audio(mode: str = 'real', timeout: float = READY_TIMEOUT_DEFAULT,
                check_timeout: float = 60.0) -> tuple[bool, str]:
    """启动宿主 audio_service。mode=real 走真实 pyaudio；shim 走影子模块。"""
    if port_listening(AUDIO_PORT):
        return True, f'[skip] audio_service 已在 :{AUDIO_PORT} 监听'
    if mode not in ('real', 'shim'):
        return False, f'[fail] 未知 --audio-mode: {mode}（real|shim）'
    if mode == 'real':
        check = subprocess.run(
            [PY, str(AUDIO_DIR / 'check_pyaudio_health.py'),
             '--timeout', str(int(check_timeout)), '--python', PY],
            cwd=str(REPO), env=host_env(), capture_output=True, text=True,
            encoding='utf-8', errors='replace',
        )
        if check.returncode != 0:
            output = (check.stdout or '') + (check.stderr or '')
            return False, f'[fail] real pyaudio 自检未通过（不重试）:\n{output.strip()}'
    log_name = 'audio_service.log' if mode == 'real' else 'audio_service_shim.log'
    return _start('audio_service', 'audio', mode, AUDIO_PORT, timeout, log_name)


def stop_audio(cooldown: float = 8.0, timeout: float = 90.0) -> tuple[bool, str]:
    """优雅停止 audio_service（gRPC Shutdown → 端口释放 → 冷却）。"""
    env = host_env()
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [PY, str(AUDIO_DIR / 'stop_audio_service.py'),
         '--port', str(AUDIO_PORT), '--cooldown', str(cooldown),
         '--log', str(LOG_DIR / 'audio_stop.log')],
        cwd=str(REPO), env=env, capture_output=True, text=True,
        encoding='utf-8', errors='replace', timeout=timeout,
    )
    output = ((result.stdout or '') + (result.stderr or '')).strip()
    ok = result.returncode == 0 and not port_listening(AUDIO_PORT)
    return ok, output


# ---------------------------------------------------------------- device

def start_device(timeout: float = READY_TIMEOUT_DEFAULT) -> tuple[bool, str]:
    return _start('device_service', 'device', 'real', DEVICE_PORT, timeout,
                  'device_service.log')


def stop_device() -> tuple[bool, str]:
    """device_service 无 Shutdown RPC：按端口定位 PID 后杀进程树并等端口释放。"""
    pid = listener_pid(DEVICE_PORT)
    if pid is None:
        return True, f'[skip] device_service 未在 :{DEVICE_PORT} 监听'
    subprocess.run(['taskkill', '/PID', str(pid), '/T', '/F'],
                   capture_output=True, text=True)
    if not wait_port(DEVICE_PORT, False, DEVICE_STOP_TIMEOUT):
        return False, f'[fail] device_service :{DEVICE_PORT} 在 {DEVICE_STOP_TIMEOUT}s 内未释放'
    return True, f'[ok] device_service 已停止 pid={pid}'


# ---------------------------------------------------------------- 状态

def status() -> list[tuple[str, int, int | None]]:
    """返回 [(服务名, 端口, PID 或 None)]。"""
    rows = []
    for name, port in (('audio_service', AUDIO_PORT), ('device_service', DEVICE_PORT)):
        rows.append((name, port, listener_pid(port) if port_listening(port) else None))
    return rows
