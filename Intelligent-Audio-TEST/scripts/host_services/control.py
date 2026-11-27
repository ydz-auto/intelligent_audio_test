# -*- coding: utf-8 -*-
"""宿主服务（e2e_test_service / audio_agent / device_service）启停与环境口径。

单一来源原则：
- **端口/基础设施**：以 ``docker compose config`` 的解析结果为准（compose 与脚本用同一份
  env 文件），不再在启动脚本里各抄一份宿主端口——历史上 15432/15435/5432 三份口径
  漂移，导致宿主 audio_service 连到测试库、音频列表“消失”。
- **DB/Redis/OSS 地址**：由上面解析出的宿主端口拼装，宿主服务永远连 Docker 栈暴露的
  入口（主库 intelligent_audio_test），不读仓库根 .env 里给 pytest 用的测试库地址。
- **宿主服务自身端口**：e2e 5002/50051、audio_agent 50052 / device 50053
  （shared/config/service_ports.py 注册值）。

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

# 宿主服务必须用项目 conda 解释器（装了 pyaudio / devicetest 等硬件依赖）；
# 用 `python stack.py` 时的 sys.executable 可能是 miniconda，缺 devicetest 会让
# 鸿蒙 UiDriver=None、设备初始化必失败。可用 HOST_SERVICE_PYTHON 覆盖。
DEFAULT_HOST_PYTHON = r'D:\00_env\conda_envs\intelligent_audio_test\python.exe'


def _dotenv() -> dict:
    """仓库根 .env 的键值。

    只返回字典、不写 os.environ：本模块会以子进程调用 `docker compose config`
    解析端口，若把根 .env 的 TASK_SERVICE_GRPC_PORT=51061（容器内口径）注入
    环境，会覆盖 compose 的宿主端口插值，把 53061 解析成 51061。
    """
    try:
        from dotenv import dotenv_values
        return {k: v for k, v in dotenv_values(REPO / '.env').items() if v is not None}
    except ImportError:
        return {}


def _resolve_python() -> str:
    configured = (os.environ.get('HOST_SERVICE_PYTHON')
                  or _dotenv().get('HOST_SERVICE_PYTHON'))
    if configured and Path(configured).is_file():
        return configured
    if Path(DEFAULT_HOST_PYTHON).is_file():
        return DEFAULT_HOST_PYTHON
    return sys.executable


PY = _resolve_python()
# 宿主服务用 pythonw.exe 拉起：WMI Create 的 python.exe 会弹出常驻黑色控制台窗口，
# pythonw 无控制台；日志由 service_entry 重定向到 logs/host_services/*.log。
_PYW = str(Path(PY).with_name('pythonw.exe'))
RUNNER = _PYW if Path(_PYW).is_file() else PY

PROJECT = os.environ.get('COMPOSE_PROJECT_NAME', 'intelligent-audio-test')
COMPOSE_FILE = REPO / 'docker' / 'docker-compose.yml'
LOG_DIR = REPO / 'logs' / 'host_services'
AUDIO_DIR = REPO / 'scripts' / 'host_audio_service'
SHIM_DIR = REPO / 'tests' / 'fixtures' / 'pyaudio_shim'

AUDIO_PORT = 50052
DEVICE_PORT = 50053
# E2E：HTTP / gRPC 同进程（e2e_test_service.app），固定宿主原生端口。
# compose 里同名服务已改为 profile 门控（container-e2e），默认由本节拉起。
E2E_HTTP_PORT = 5002
E2E_GRPC_PORT = 50051

ENTRY = Path(__file__).with_name('service_entry.py')
# 守护壳：退出即 5s 重启的循环，子进程 service_entry 崩了会被它拉回来。
# 用 pythonw 而不是 PowerShell：WMI 拉起的进程没有控制台，PowerShell 会新开一个
# conhost，Windows Terminal 下 `-WindowStyle Hidden` 不生效 → 桌面多出空白黑窗。
SUPERVISOR = Path(__file__).with_name('supervisor.py')

# WMI 拉起的进程父级是 WmiPrvSE（系统服务），不在 agent run 的 job 对象里；
# 否则 run 结束会整树回收，宿主服务刚起来就被杀掉。
_WMI_SCRIPT = (
    '$r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create '
    '-Arguments @{CommandLine=$env:STACK_LAUNCH_CMD; '
    'CurrentDirectory=$env:STACK_LAUNCH_CWD}; '
    'Write-Output $r.ProcessId; exit $r.ReturnValue'
)

# 从无控制台的父进程（IDE / agent）拉起控制台程序时 Windows 会另开一个黑窗；
# 只取输出的辅助调用统一禁窗（非 Windows 传 0 无效）。
_NO_WINDOW = 0x08000000 if os.name == 'nt' else 0

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

# 执行机 audio_agent 不需要的数据面凭据（拆分方案 §6：agent 无 DB / 无 COS）
_AUDIO_AGENT_ENV_DROP = (
    'DATABASE_URL',
    'POSTGRES_USER', 'POSTGRES_PASSWORD', 'POSTGRES_DB',
    'POSTGRES_HOST', 'POSTGRES_PORT',
    'OSS_ENDPOINT', 'OSS_PUBLIC_ENDPOINT', 'OSS_ACCESS_KEY', 'OSS_SECRET_KEY',
    'OSS_BUCKET_NAME', 'OSS_KEY_PREFIX', 'OSS_REGION', 'OSS_ADDRESSING_STYLE',
)

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
                            text=True, encoding='utf-8', errors='replace',
                            creationflags=_NO_WINDOW)
    if result.returncode != 0:
        raise RuntimeError(f'解析 compose 配置失败: {(result.stderr or "").strip()}')
    config = json.loads(result.stdout)
    ports: dict[int, int] = {}
    for service in (config.get('services') or {}).values():
        # profile 门控服务（如 container-e2e）默认不启动，其 ports 不代表本栈实际发布端口
        if service.get('profiles'):
            continue
        for item in service.get('ports') or []:
            target, published = item.get('target'), item.get('published')
            if target and published:
                ports[int(target)] = int(published)
    return ports


def host_env() -> dict:
    """宿主服务子进程环境：仓库根 .env + compose 解析出的宿主端口。"""
    env = {**_dotenv(), **os.environ}  # 进程环境优先于 .env
    ports = published_ports()
    infra = {**{k: ports.get(k, v) for k, v in _DEFAULT_INFRA_PORTS.items()}}

    user = env.get('POSTGRES_USER', DEFAULT_DB_USER)
    password = env.get('POSTGRES_PASSWORD', DEFAULT_DB_PASSWORD)
    database = env.get('POSTGRES_DB', DEFAULT_DB_NAME)
    env['DATABASE_URL'] = (
        f'postgresql://{user}:{password}@127.0.0.1:{infra[5432]}/{database}')
    env['REDIS_URL'] = f"redis://127.0.0.1:{infra[6379]}"
    # STORAGE_BACKEND=local 时宿主服务只落本地磁盘，不注入（也不探测）对象存储地址
    if (env.get('STORAGE_BACKEND') or 'auto').strip().lower() == 'local':
        env.pop('OSS_ENDPOINT', None)
        env.pop('OSS_PUBLIC_ENDPOINT', None)
    else:
        env['OSS_ENDPOINT'] = f"http://127.0.0.1:{infra[9000]}"
        env['OSS_PUBLIC_ENDPOINT'] = f"http://127.0.0.1:{infra[9000]}"

    for container_port, env_name in _GRPC_ENV_BY_CONTAINER_PORT.items():
        if container_port in ports:
            env[env_name] = str(ports[container_port])
    for env_name in _GRPC_HOST_VARS:
        env[env_name] = '127.0.0.1'

    # 数据面 audio_service（服务器容器）与硬件面 audio_agent（本机宿主）已拆分：
    # - 宿主 e2e/device 的音频元数据走容器发布端口（compose 映射，dev 默认 50054）；
    # - 播放/试听/SPL 仍走本机 agent :50052。
    env['AUDIO_SERVICE_HOST'] = '127.0.0.1'
    env['AUDIO_SERVICE_GRPC_PORT'] = str(ports.get(50052, AUDIO_PORT))
    env['AUDIO_AGENT_HOST'] = '127.0.0.1'
    env['AUDIO_AGENT_GRPC_PORT'] = str(AUDIO_PORT)
    env['DEVICE_SERVICE_HOST'] = '127.0.0.1'
    env['DEVICE_SERVICE_GRPC_PORT'] = str(DEVICE_PORT)
    # 容器经 host.docker.internal 访问宿主服务，必须绑全部网卡
    env['SERVICE_HOST'] = '0.0.0.0'
    # 生产形态：本机只跑硬件服务，数据面（DB/Redis/对象存储）在服务器
    remote_env = REPO / 'logs' / 'host_services' / 'remote.env'
    if remote_env.is_file():
        for line in remote_env.read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, value = line.split('=', 1)
            env[key.strip()] = value.strip()
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
            creationflags=_NO_WINDOW,
        ).stdout
    except OSError:
        return None
    for line in out.splitlines():
        if 'LISTENING' not in line.upper():
            continue
        parts = line.split()
        # netstat -ano 列：Proto / Local Address / Foreign Address / State / PID。
        # 必须按端口号精确比较：:5002 不能被 :15002 的行命中（容器端口覆盖时会误杀）。
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


# ---------------------------------------------------------------- 守护进程

def _supervisor_files(service: str) -> tuple[Path, Path]:
    """守护进程的 pid 文件与停止标记文件。"""
    return (LOG_DIR / f'{service}.supervisor.pid',
            LOG_DIR / f'{service}.supervisor.stop')


def _supervisor_log(service: str) -> Path:
    return LOG_DIR / f'{service}.supervisor.log'


def _supervisor_pid(service: str) -> int | None:
    pid_file, _ = _supervisor_files(service)
    try:
        return int(pid_file.read_text(encoding='ascii').strip())
    except (OSError, ValueError):
        return None


def _supervisor_alive(service: str) -> bool:
    """pid 文件里的进程还活着，且确实是这个服务的守护壳（按 --tag/-Tag 识别）。"""
    pid = _supervisor_pid(service)
    if not pid:
        return False
    result = subprocess.run(
        ['powershell', '-NoProfile', '-Command',
         f'(Get-CimInstance Win32_Process -Filter "ProcessId={pid}").CommandLine'],
        capture_output=True, text=True, encoding='utf-8', errors='replace',
        creationflags=_NO_WINDOW,
    )
    cmdline = (result.stdout or '').strip()
    return f'--tag {service}' in cmdline or f'-Tag {service}' in cmdline


# ------------------------------------------------------------ 代码/配置指纹
# `up` 只在“当前进程就是当前代码+配置”时跳过；否则停旧进程再拉起，
# 避免改完 remote.env / 代码后 up 只是把旧进程留着（历史上 device 因此一直
# 用旧 STORAGE_BACKEND，上传 403）。
_FP_KEYS = {
    'DATABASE_URL', 'REDIS_URL',
    'STORAGE_BACKEND', 'STORAGE_FALLBACK_ENABLED',
    'LOCAL_STORAGE_ROOT', 'STORAGE_LOCAL_ROOT',
    'PORT', 'GRPC_PORT', 'SERVICE_NAME', 'SERVICE_HOST', 'LAB_NAME',
    'AUDIO_SERVICE_HOST', 'AUDIO_SERVICE_GRPC_PORT',
    'AUDIO_AGENT_HOST', 'AUDIO_AGENT_GRPC_PORT', 'AUDIO_ROLE',
    'STORAGE_SERVER_FETCH_URL',
    'DEVICE_SERVICE_HOST', 'DEVICE_SERVICE_GRPC_PORT',
}
# 各宿主服务真正加载的源码目录（改动后必须重启才生效）
_SERVICE_SOURCE_DIRS = {
    'e2e': ('e2e_test_service',),
    'audio': ('audio_service',),
    'device': ('device_service',),
}


def _config_keys() -> set:
    """配置文件（.env / remote.env）里出现的键 + 关键运行端口键。"""
    keys = set(_dotenv()) | set(_FP_KEYS)
    remote_env = LOG_DIR / 'remote.env'
    if remote_env.is_file():
        for line in remote_env.read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                keys.add(line.split('=', 1)[0].strip())
    return keys


def _config_snapshot(env: dict) -> dict:
    """只保留会影响运行结果的键，避免 PATH 等易变项造成误判重启。"""
    return {k: env[k] for k in sorted(_config_keys()) if k in env}


def _code_mtime(service: str) -> float:
    """服务源码 + shared + 启停脚本（control/supervisor/service_entry）的最新修改时间。"""
    latest = 0.0
    for name in ('shared', 'scripts/host_services',
                 *_SERVICE_SOURCE_DIRS.get(service, ())):
        for path in (REPO / name).rglob('*.py'):
            if '__pycache__' in path.parts:
                continue
            try:
                latest = max(latest, path.stat().st_mtime)
            except OSError:
                continue
    return round(latest, 6)


def _launch_record_file(service: str) -> Path:
    return LOG_DIR / f'{service}.launch.json'


def _launch_record(service: str, mode: str, env: dict) -> dict:
    return {
        'mode': mode,
        'config': _config_snapshot(env),
        'code_mtime': _code_mtime(service),
    }


def _needs_restart(service: str, mode: str) -> bool:
    """在跑的进程是否已不是当前代码/配置（无记录文件的老进程一律视为需要重启）。"""
    try:
        saved = json.loads(_launch_record_file(service).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return True
    return saved != _launch_record(service, mode, _service_env(service, mode))


def _request_stop(service: str, on: bool = True) -> None:

    """落/清停止标记：守护进程看到标记后不再重启子进程。"""
    _, stop_flag = _supervisor_files(service)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    if on:
        stop_flag.write_text('stop\n', encoding='ascii')
    elif stop_flag.exists():
        stop_flag.unlink()


def _kill_supervisor(service: str, timeout: float = DEVICE_STOP_TIMEOUT) -> None:
    if _supervisor_alive(service):
        pid = _supervisor_pid(service)
        subprocess.run(['taskkill', '/PID', str(pid), '/T', '/F'],
                       capture_output=True, text=True, encoding='utf-8',
                       errors='replace', creationflags=_NO_WINDOW)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline and _supervisor_alive(service):
            time.sleep(0.3)
    _supervisor_files(service)[0].unlink(missing_ok=True)


def _service_processes(service: str) -> list[int]:
    """按命令行找同一服务的所有进程（守护壳 + 服务本体）。

    只靠 pid 文件和端口判断会漏掉两类残留：pid 文件被删但守护还在跑、
    服务进程还没绑定端口（启动中）或已解绑端口（僵死）。这类孤儿不与新实例
    冲突检测，于是出现"旧服务还在、又起了一套新的"。拉起前用命令行兜底。
    """
    script = ("Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
              "ForEach-Object { \"$($_.ProcessId)`t$($_.CommandLine)\" }")
    try:
        out = subprocess.run(
            ['powershell', '-NoProfile', '-Command', script],
            capture_output=True, text=True, encoding='utf-8', errors='replace',
            creationflags=_NO_WINDOW,
        ).stdout
    except OSError:
        return []
    pids: list[int] = []
    for line in (out or '').splitlines():
        pid_text, _, cmdline = line.partition('\t')
        if not (pid_text.strip().isdigit() and cmdline):
            continue
        cmd = cmdline.lower()
        is_entry = 'service_entry.py' in cmd and f'--service {service}' in cmd
        is_supervisor = ('supervisor.py' in cmd
                         and (f'--tag {service}' in cmd or f'-tag {service}' in cmd))
        if is_entry or is_supervisor:
            pids.append(int(pid_text))
    return sorted(set(pids))


def _reap_stale(service: str, timeout: float = 10.0) -> list[int]:
    """拉起新实例前清光该服务的残留进程，保证任何时刻只有一套。"""
    pids = [pid for pid in _service_processes(service) if pid != os.getpid()]
    for pid in pids:
        subprocess.run(['taskkill', '/PID', str(pid), '/T', '/F'],
                       capture_output=True, text=True, encoding='utf-8',
                       errors='replace', creationflags=_NO_WINDOW)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and _service_processes(service):
        time.sleep(0.3)
    return pids


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
        creationflags=_NO_WINDOW,
    )
    lines = [line.strip() for line in (result.stdout or '').splitlines() if line.strip()]
    pid = int(lines[-1]) if lines and lines[-1].isdigit() else None
    if result.returncode != 0 or not pid:
        detail = (result.stderr or result.stdout or '').strip()
        raise RuntimeError(f'WMI 拉起失败 rc={result.returncode}: {detail}')
    return pid


def _service_env(service: str, mode: str) -> dict:
    """服务进程最终环境（WMI 进程不继承调用方环境）：启动与漂移检测共用一份口径。"""
    env = host_env()
    py_dir = Path(PY).parent
    env['PATH'] = os.pathsep.join([
        str(py_dir), str(py_dir / 'Library' / 'bin'), str(py_dir / 'Scripts'),
        env.get('PATH', ''),
    ])
    if service == 'audio':
        # 执行机 audio_agent 只承担硬件面：不连 DB、不直连 OSS（见拆分方案 §6）。
        for key in _AUDIO_AGENT_ENV_DROP:
            env.pop(key, None)
        env['AUDIO_ROLE'] = 'agent'
        env['AUDIO_AGENT_HOST'] = '127.0.0.1'
        env['AUDIO_AGENT_GRPC_PORT'] = str(AUDIO_PORT)
        env.setdefault('LAB_NAME', 'lab-a')
        if not env.get('STORAGE_SERVER_FETCH_URL'):
            # 音频字节只经服务器网关取流（agent 禁直连 OSS）
            gateway_port = published_ports().get(5000, 5000)
            env['STORAGE_SERVER_FETCH_URL'] = f'http://127.0.0.1:{gateway_port}'
    if service == 'audio' and mode == 'shim':
        env['PYTHONPATH'] = os.pathsep.join(
            [str(SHIM_DIR), str(REPO), str(REPO / 'shared' / 'proto')])
    if service == 'e2e':
        # 宿主进程：固定原生端口；SERVICE_HOST 用于 Redis 注册（容器经
        # host.docker.internal 寻址），不能沿用 host_env 给 audio/device 的 0.0.0.0
        env.update({
            'PORT': str(E2E_HTTP_PORT),
            'GRPC_PORT': str(E2E_GRPC_PORT),
            'SERVICE_NAME': 'e2e_test_service',
            'SERVICE_HOST': 'host.docker.internal',
            'LAB_NAME': env.get('LAB_NAME') or 'lab-a',
        })
        env['PYTHONPATH'] = os.pathsep.join(
            [str(REPO), str(REPO / 'shared' / 'proto'), env.get('PYTHONPATH', '')])
    return env


def _launch(service: str, mode: str) -> int:
    """把完整环境落成 JSON（WMI 进程不继承调用方环境），再 WMI 拉起入口。"""
    env = _service_env(service, mode)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    env_file = LOG_DIR / f'{service}.env.json'
    env_file.write_text(json.dumps(env, ensure_ascii=False), encoding='utf-8')
    _launch_record_file(service).write_text(
        json.dumps(_launch_record(service, mode, env), ensure_ascii=False),
        encoding='utf-8')
    pid_file, stop_flag = _supervisor_files(service)
    _request_stop(service, False)          # 清掉上次 stop 留下的标记
    pid_file.unlink(missing_ok=True)
    command_line = (
        f'"{RUNNER}" "{SUPERVISOR}" --tag {service} --python "{RUNNER}" '
        f'--entry "{ENTRY}" --mode {mode} --env-file "{env_file}" '
        f'--log "{_supervisor_log(service)}" --stop-flag "{stop_flag}" '
        f'--pid-file "{pid_file}"')
    return _wmi_create(command_line, REPO)


def _start(name: str, service: str, mode: str, port: int,
           timeout: float, log_name: str, restart=None) -> tuple[bool, str]:
    head = ''
    if port_listening(port):
        if not _needs_restart(service, mode):
            return True, f'[skip] {name} 已在 :{port} 监听（代码/配置未变）'
        if restart is None:
            return False, (f'[fail] {name} 旧进程仍在 :{port} 监听，且代码/配置已变更，'
                           f'请先 python stack.py restart {service}')
        ok, stop_msg = restart()
        if not ok or port_listening(port):
            return False, f'[fail] {name} 旧进程停止失败: {stop_msg}'
        head = f'[restart] {name} 代码/配置已变更，{stop_msg}；'
    if _supervisor_alive(service):
        # 子进程崩溃后正由守护进程重启中：不再重复拉一个守护
        if wait_port(port, True, timeout):
            return True, f'{head}[ok] {name} 由守护进程拉起 :{port}'
        return False, (f'{head}[fail] {name} 守护进程存活但 :{port} 在 {timeout:.0f}s 内未监听，'
                       f'日志: {_supervisor_log(service)}\n'
                       f'{_log_tail(_supervisor_log(service).name)}')
    reaped = _reap_stale(service)
    if reaped:
        head += f'[clean] 清理 {service} 残留进程 pid={reaped}；'
    try:
        pid = _launch(service, mode)
    except RuntimeError as exc:
        return False, f'{head}[fail] {name} 拉起失败: {exc}'
    if wait_port(port, True, timeout):
        return True, f'{head}[ok] {name} 已启动 守护pid={pid} :{port}（WMI 脱离 run 树）'
    tail = _log_tail(log_name)
    sup_tail = _log_tail(_supervisor_log(service).name)
    return False, (f'{head}[fail] {name} 在 {timeout:.0f}s 内未监听 :{port}，'
                   f'日志: {LOG_DIR / log_name}\n{tail}\n'
                   f'守护日志: {_supervisor_log(service)}\n{sup_tail}')


def _log_tail(log_name: str, lines: int = 20) -> str:
    path = LOG_DIR / log_name
    if not path.is_file():
        return ''
    try:
        content = path.read_text(encoding='utf-8', errors='replace').splitlines()
    except OSError:
        return ''
    return '\n'.join(content[-lines:])


# ---------------------------------------------------------------- e2e

def start_e2e(timeout: float = READY_TIMEOUT_DEFAULT) -> tuple[bool, str]:
    """启动宿主 e2e_test_service（HTTP :5002 + gRPC :50051 同进程）。"""
    if (port_listening(E2E_HTTP_PORT) and not port_listening(E2E_GRPC_PORT)
            and not _needs_restart('e2e', 'real')):
        return False, (f'[fail] e2e_test_service :{E2E_HTTP_PORT} 已监听，'
                       f'但 gRPC :{E2E_GRPC_PORT} 未就绪')
    ok, msg = _start('e2e_test_service', 'e2e', 'real', E2E_HTTP_PORT,
                     timeout, 'e2e_test_service.log', restart=stop_e2e)
    if not ok:
        return ok, msg
    if not wait_port(E2E_GRPC_PORT, True, timeout):
        return False, (f'[fail] e2e_test_service gRPC :{E2E_GRPC_PORT} 在 {timeout:.0f}s 内'
                       f'未监听，日志: {LOG_DIR / "e2e_test_service.log"}\n'
                       f'{_log_tail("e2e_test_service.log")}')
    return True, msg


def stop_e2e(timeout: float = DEVICE_STOP_TIMEOUT) -> tuple[bool, str]:
    """停止宿主 e2e_test_service：落停止标记 → 按 5002/50051 杀进程树 → 收守护。"""
    _request_stop('e2e')
    try:
        pids = sorted({pid for pid in (listener_pid(E2E_HTTP_PORT),
                                       listener_pid(E2E_GRPC_PORT)) if pid})
        if not pids:
            return True, f'[skip] e2e_test_service 未在 :{E2E_HTTP_PORT}/:{E2E_GRPC_PORT} 监听'
        for pid in pids:
            subprocess.run(['taskkill', '/PID', str(pid), '/T', '/F'],
                           capture_output=True, text=True, encoding='utf-8',
                           errors='replace', creationflags=_NO_WINDOW)
        if not (wait_port(E2E_HTTP_PORT, False, timeout)
                and wait_port(E2E_GRPC_PORT, False, timeout)):
            return False, (f'[fail] e2e_test_service :{E2E_HTTP_PORT}/:{E2E_GRPC_PORT} '
                           f'在 {timeout}s 内未释放')
        return True, f'[ok] e2e_test_service 已停止 pid={pids}'
    finally:
        _kill_supervisor('e2e')
        if not _supervisor_alive('e2e'):
            _request_stop('e2e', False)


# ---------------------------------------------------------------- audio

def start_audio(mode: str = 'real', timeout: float = READY_TIMEOUT_DEFAULT,
                check_timeout: float = 60.0) -> tuple[bool, str]:
    """启动宿主 audio_agent（AUDIO_ROLE=agent）。mode=real 走真实 pyaudio；shim 走影子模块。"""
    if mode not in ('real', 'shim'):
        return False, f'[fail] 未知 --audio-mode: {mode}（real|shim）'
    if port_listening(AUDIO_PORT) and not _needs_restart('audio', mode):
        return True, f'[skip] audio_agent 已在 :{AUDIO_PORT} 监听（代码/配置未变）'
    if mode == 'real':
        check = subprocess.run(
            [PY, str(AUDIO_DIR / 'check_pyaudio_health.py'),
             '--timeout', str(int(check_timeout)), '--python', PY],
            cwd=str(REPO), env=host_env(), capture_output=True, text=True,
            encoding='utf-8', errors='replace', creationflags=_NO_WINDOW,
        )
        if check.returncode != 0:
            output = (check.stdout or '') + (check.stderr or '')
            return False, f'[fail] real pyaudio 自检未通过（不重试）:\n{output.strip()}'
    log_name = 'audio_agent.log' if mode == 'real' else 'audio_agent_shim.log'
    return _start('audio_agent', 'audio', mode, AUDIO_PORT, timeout, log_name,
                  restart=stop_audio)


def stop_audio(cooldown: float = 8.0, timeout: float = 90.0) -> tuple[bool, str]:
    """优雅停止 audio_agent（gRPC Shutdown → 端口释放 → 冷却），并收掉守护进程。"""
    _request_stop('audio')
    try:
        env = host_env()
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            [PY, str(AUDIO_DIR / 'stop_audio_service.py'),
             '--port', str(AUDIO_PORT), '--cooldown', str(cooldown),
             '--log', str(LOG_DIR / 'audio_stop.log')],
            cwd=str(REPO), env=env, capture_output=True, text=True,
            encoding='utf-8', errors='replace', timeout=timeout,
            creationflags=_NO_WINDOW,
        )
        output = ((result.stdout or '') + (result.stderr or '')).strip()
        ok = result.returncode == 0 and not port_listening(AUDIO_PORT)
        return ok, output
    finally:
        _kill_supervisor('audio')
        if not _supervisor_alive('audio'):
            _request_stop('audio', False)


# ---------------------------------------------------------------- device

def start_device(timeout: float = READY_TIMEOUT_DEFAULT) -> tuple[bool, str]:
    return _start('device_service', 'device', 'real', DEVICE_PORT, timeout,
                  'device_service.log', restart=stop_device)


def stop_device() -> tuple[bool, str]:
    """device_service 无 Shutdown RPC：落停止标记 → 杀进程树等端口释放 → 收守护。"""
    _request_stop('device')
    try:
        pid = listener_pid(DEVICE_PORT)
        if pid is None:
            return True, f'[skip] device_service 未在 :{DEVICE_PORT} 监听'
        subprocess.run(['taskkill', '/PID', str(pid), '/T', '/F'],
                       capture_output=True, text=True, encoding='utf-8',
                       errors='replace', creationflags=_NO_WINDOW)
        if not wait_port(DEVICE_PORT, False, DEVICE_STOP_TIMEOUT):
            return False, f'[fail] device_service :{DEVICE_PORT} 在 {DEVICE_STOP_TIMEOUT}s 内未释放'
        return True, f'[ok] device_service 已停止 pid={pid}'
    finally:
        _kill_supervisor('device')
        if not _supervisor_alive('device'):
            _request_stop('device', False)


# ---------------------------------------------------------------- 状态

def status() -> list[tuple[str, int, int | None]]:
    """返回 [(服务名, 端口, PID 或 None)]。"""
    rows = []
    for name, port in (('e2e_test_service', E2E_HTTP_PORT),
                       ('audio_agent', AUDIO_PORT),
                       ('device_service', DEVICE_PORT)):
        rows.append((name, port, listener_pid(port) if port_listening(port) else None))
    return rows
