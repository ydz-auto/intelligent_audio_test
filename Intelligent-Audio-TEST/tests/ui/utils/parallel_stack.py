# -*- coding: utf-8 -*-
"""UI 专用并行隔离栈（INT-260）：端口整体 +1000，隔离库 intelligent_audio_test_test。

背景：共享栈常被其它在途 run 占用（INT-261 UX 走查等），不可重启切换
--test-db；本启动器以全偏移端口并行起一套栈，DATABASE_URL 直指隔离库，
与共享栈互不干扰（端口/Redis DB/日志根全隔离）。

端口表（shift=+1000）：网关 6000，HTTP 服务 6001-6010，gRPC 51051-51101，
前端 vite 6273（VITE_API_TARGET=http://127.0.0.1:6000）。

安全红线：
- 启动前逐端口探测，任一被占用即拒绝并退出，绝不 kill 占用者
  （run_all.py 的 cleanup_occupied_ports 行为在此禁止复刻）；
- DATABASE_URL 强制指向隔离库，启动后 /health database 字段复核。

用法（建议经 run_gate.py 以 WMI 脱离 agent 进程树启动；start 常驻监督）：
    python tests/ui/utils/parallel_stack.py start
    python tests/ui/utils/parallel_stack.py stop
    python tests/ui/utils/parallel_stack.py status
"""
import argparse
import os
import socket
import subprocess
import sys
import time
from urllib.parse import urlsplit, urlunsplit

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, PROJECT_ROOT)

from dotenv import load_dotenv  # noqa: E402

from shared.constants.database import ISOLATED_TEST_DB_NAME  # noqa: E402

BASE_DIR = PROJECT_ROOT
FRONTEND_DIR = os.path.join(BASE_DIR, 'frontend')
PID_FILE = os.path.join(BASE_DIR, 'tests', 'ui', '_ui_stack.pid')
LOG_DIR = os.path.join(BASE_DIR, 'logs', 'ui_stack')

SHIFT = 1000

# name, dir, base_http_port(None=gRPC-only), base_grpc_port
SERVICES = [
    ('api_gateway',        'api_gateway',        5000, None),
    ('task_service',       'task_service',       5001, 50061),
    ('e2e_test_service',   'e2e_test_service',   5002, 50051),
    ('api_test_service',   'api_test_service',   5003, 50071),
    ('evaluation_service', 'evaluation_service', 5004, 50091),
    ('report_service',     'report_service',     5006, 50068),
    ('algorithm_service',  'algorithm_service',  5007, 50067),
    ('auth_service',       'auth_service',       5009, 50069),
    ('api_adapter_service','api_adapter_service',5008, 50081),
    ('transfer_agent',     'transfer_agent',     5010, 50101),
    ('audio_service',      'audio_service',      None, 50052),
    ('device_service',     'device_service',     None, 50053),
]

# 客户端侧 gRPC 端口环境名（shared/infrastructure/config.py BaseConfig）
CLIENT_GRPC_ENVS = {
    'E2E_TEST_SERVICE_GRPC_PORT': 50051,
    'AUDIO_SERVICE_GRPC_PORT': 50052,
    'DEVICE_SERVICE_GRPC_PORT': 50053,
    'TASK_SERVICE_GRPC_PORT': 50061,
    'ALGORITHM_SERVICE_GRPC_PORT': 50067,
    'REPORT_SERVICE_GRPC_PORT': 50068,
    'AUTH_SERVICE_GRPC_PORT': 50069,
    'API_TEST_SERVICE_GRPC_PORT': 50071,
    'ADAPTER_SERVICE_GRPC_PORT': 50081,
    'EVALUATION_SERVICE_GRPC_PORT': 50091,
    'TRANSFER_AGENT_GRPC_PORT': 50101,
}

GATEWAY_HTTP = 5000 + SHIFT
FRONTEND_PORT = 6273


def _shift(base: int) -> int:
    return base + SHIFT


def _base_env() -> dict:
    load_dotenv(os.path.join(BASE_DIR, '.env'))
    env = os.environ.copy()
    env['PYTHONUTF8'] = '1'
    # 隔离库（强制）：从 .env DATABASE_URL 推导仅换库名
    parts = urlsplit(env.get('DATABASE_URL', ''))
    if not parts.scheme.startswith('postgres'):
        raise SystemExit('[UI-STACK] .env DATABASE_URL 非 Postgres，无法推导隔离库连接串')
    env['DATABASE_URL'] = urlunsplit(
        (parts.scheme, parts.netloc, '/' + ISOLATED_TEST_DB_NAME, '', ''))
    # Redis 独立 DB index，避免与共享栈缓存互踩
    env['REDIS_URL'] = 'redis://localhost:6379/1'
    env['LOG_ROOT_DIR'] = os.path.join('logs', 'ui_stack')
    proto_dir = os.path.join(BASE_DIR, 'shared', 'proto')
    env['PYTHONPATH'] = BASE_DIR + os.pathsep + proto_dir + os.pathsep + env.get('PYTHONPATH', '')
    for env_name, base in CLIENT_GRPC_ENVS.items():
        env[env_name] = str(_shift(base))
    return env


def _service_cmd(name: str, svc_dir: str, http_port, grpc_port, env: dict):
    if http_port is not None:
        env['PORT'] = str(http_port)
        if grpc_port:
            env['GRPC_PORT'] = str(grpc_port)
        cmd = [sys.executable, '-m', 'uvicorn', f'{svc_dir}.app:app',
               '--host', '0.0.0.0', '--port', str(http_port),
               '--workers', '1', '--log-level', 'info']
    else:
        env['GRPC_PORT'] = str(grpc_port)
        # gRPC-only 服务的 main() 忽略 GRPC_PORT（静态默认端口），经显式入参偏移
        cmd = [sys.executable, '-c',
               'import logging; logging.basicConfig(level=logging.INFO); '
               f'from {svc_dir}.interfaces.grpc.server import start_grpc_server; '
               f's = start_grpc_server({grpc_port}); s.wait_for_termination()']
        if name == 'audio_service':
            shim = os.path.join(BASE_DIR, 'tests', 'fixtures', 'pyaudio_shim')
            env['PYTHONPATH'] = shim + os.pathsep + env['PYTHONPATH']
    env['SERVICE_NAME'] = f'ui_{name}'
    return cmd


def _port_busy(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.6)
        return s.connect_ex((host, port)) == 0


def required_ports() -> list:
    ports = [_shift(g) for _, _, _, g in SERVICES if g] + [GATEWAY_HTTP, FRONTEND_PORT]
    ports += [_shift(p) for _, _, p, _ in SERVICES if p]
    return sorted(set(ports))


def _refuse_if_busy():
    busy = [p for p in required_ports() if _port_busy('127.0.0.1', p)]
    if busy:
        raise SystemExit(
            f'[UI-STACK] 拒绝启动：端口被占用 {busy}（本启动器绝不 kill 占用进程；'
            '请先排空端口或停掉占用者）。')


def _ensure_postgres():
    """Postgres 5432 不可达时经 WMI 脱离进程树拉起（绝不 kill 已有进程）。

    postgres.exe 若从 agent run 内直接启动（Start-Process 等）会加入 run
    进程树，run 退出被平台整树收割（2026-10-13 16:43:57 实证）；WMI 启动
    parent=WmiPrvSE，run 退出不受影响（INT-125 同口径）。
    """
    if _port_busy('127.0.0.1', 5432):
        return
    print('[UI-STACK] Postgres 5432 未监听，经 WMI 脱离进程树拉起...', flush=True)
    payload = os.path.join(BASE_DIR, 'tests', 'ui', '_pg_start.cmd')
    ps = (
        "$r = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{"
        f"CommandLine = 'cmd.exe /c \"{payload}\"';"
        f"CurrentDirectory = '{BASE_DIR}'"
        "}; $r.ReturnValue"
    )
    r = subprocess.run(['powershell', '-NoProfile', '-Command', ps],
                       capture_output=True, text=True, timeout=30)
    import time as _t
    deadline = _t.time() + 60
    while _t.time() < deadline:
        if _port_busy('127.0.0.1', 5432):
            print('[UI-STACK] Postgres 已就绪（5432）', flush=True)
            return
        _t.sleep(2)
    raise SystemExit('[UI-STACK] Postgres 60s 内未就绪（见 pgsql\\log\\pg_wmi.log），中止起栈。')


def start():
    """起栈并常驻监督（PID 文件恒为本 launcher 进程，stop 按树杀整栈）。

    必须经 WMI 脱离 agent 进程树启动（INT-125 同因：run 退出会收割进程树）；
    本函数永不返回，除非 Ctrl+C 或任一服务进程死亡（连带停整栈防半栈漂移）。
    """
    _ensure_postgres()
    _refuse_if_busy()
    os.makedirs(LOG_DIR, exist_ok=True)
    base_env = _base_env()
    log = open(os.path.join(LOG_DIR, 'ui_stack.log'), 'ab')
    procs = []

    def _spawn(name, cmd, env, cwd=None):
        log.write(f'\n[START] {name}: {" ".join(cmd[:6])}...\n'.encode())
        log.flush()
        procs.append((name, subprocess.Popen(
            cmd, cwd=cwd or BASE_DIR, env=env, stdout=log, stderr=subprocess.STDOUT)))

    for name, svc_dir, http_port, grpc_port in SERVICES:
        env = dict(base_env)
        cmd = _service_cmd(name, svc_dir,
                           _shift(http_port) if http_port else None,
                           _shift(grpc_port) if grpc_port else None, env)
        _spawn(name, cmd, env)

    # 前端 vite（第二实例）：直接 node vite.js，绕开 npm.cmd 参数转发丢失问题
    fenv = dict(base_env)
    fenv['VITE_API_TARGET'] = f'http://127.0.0.1:{GATEWAY_HTTP}'
    node_dir = r'D:\00_env\node-v22.21.1-win-x64'
    node_exe = os.path.join(node_dir, 'node.exe')
    vite_js = os.path.join(FRONTEND_DIR, 'node_modules', 'vite', 'bin', 'vite.js')
    if not (os.path.isfile(node_exe) and os.path.isfile(vite_js)):
        raise SystemExit(f'[UI-STACK] node/vite 不存在: {node_exe} / {vite_js}')
    _spawn('frontend', [node_exe, vite_js,
                        '--port', str(FRONTEND_PORT), '--strictPort'], fenv,
           cwd=FRONTEND_DIR)

    with open(PID_FILE, 'w', encoding='ascii') as fh:
        fh.write(str(os.getpid()))
    print(f'[UI-STACK] 已启动 {len(procs)} 个进程（launcher pid {os.getpid()}），'
          f'网关 :{GATEWAY_HTTP}，前端 :{FRONTEND_PORT}，日志 {LOG_DIR}', flush=True)

    try:
        wait_ready()
        print('[UI-STACK] 监督中（stop: python tests/ui/utils/parallel_stack.py stop）', flush=True)
        while True:
            time.sleep(3)
            for name, p in procs:
                code = p.poll()
                if code is not None:
                    print(f'[UI-STACK] {name} 已退出（code {code}），停止整栈', flush=True)
                    return stop()
    except KeyboardInterrupt:
        stop()


def wait_ready(timeout: int = 90):
    import httpx
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = httpx.get(f'http://127.0.0.1:{GATEWAY_HTTP}/health', timeout=2, trust_env=False)
            if r.status_code == 200:
                body = r.json()
                print(f"[UI-STACK] 网关就绪：database={body.get('database')}", flush=True)
                if body.get('database') != ISOLATED_TEST_DB_NAME:
                    print('[UI-STACK][FATAL] 栈 database 字段非隔离库，立即停止', flush=True)
                    return stop()
                return True
        except Exception:
            pass
        time.sleep(2)
    print('[UI-STACK][WARN] 网关就绪探测超时（详见 logs/ui_stack/ui_stack.log）', flush=True)
    return False


def stop():
    pid = None
    if os.path.exists(PID_FILE):
        try:
            pid = int(open(PID_FILE, encoding='ascii').read().strip())
        except Exception:
            pid = None
    if pid:
        # taskkill 输出为 GBK，errors=replace 避免 UTF-8 侧解码炸线程
        subprocess.run(['taskkill', '/F', '/T', '/PID', str(pid)],
                       capture_output=True, text=True, encoding='utf-8', errors='replace')
        try:
            os.remove(PID_FILE)
        except OSError:
            pass
        print(f'[UI-STACK] 已停止（launcher pid {pid} 进程树）')
    else:
        print('[UI-STACK] 无 PID 记录，未停止任何进程')


def status():
    import httpx
    up = []
    for p in required_ports():
        up.append(f'{p}:{"OPEN" if _port_busy("127.0.0.1", p) else "closed"}')
    db = '?'
    try:
        r = httpx.get(f'http://127.0.0.1:{GATEWAY_HTTP}/health', timeout=2, trust_env=False)
        if r.status_code == 200:
            db = r.json().get('database', '?')
    except Exception:
        pass
    print(f'[UI-STACK] {pid_status()} | gw-db={db} | ' + ' '.join(up))


def pid_status() -> str:
    if os.path.exists(PID_FILE):
        return f'pid-file={open(PID_FILE, encoding="ascii").read().strip()}'
    return 'pid-file=none'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='UI 专用并行隔离栈（端口+1000，隔离库）')
    parser.add_argument('action', choices=['start', 'stop', 'status'])
    args = parser.parse_args()
    if args.action == 'start':
        start()
    elif args.action == 'stop':
        stop()
    else:
        status()
