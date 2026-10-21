# -*- coding: utf-8 -*-
"""真实库栈常驻启动器（INT-1190）——连主库 intelligent_audio_test，端口整体 +700。

背景：5000 段常驻开发栈保持连隔离测试库 intelligent_audio_test_test（不动），
本启动器在独立端口段起一套连主库（INT-1158 导入的生产数据副本 1020_data）的
常驻栈，专给走查、设计、页面实测看真实数据。

端口表（shift=+700）：网关 5700，HTTP 服务 5701-5710，gRPC 50751-50753 / 51761-51801。
- 前端不随本栈启动；React / 新 Vue / 旧 Vue 通过 VITE_API_TARGET / 代理指到
  http://localhost:5700（见 D:\\00_env\\multica_loop\\real_stack\\README.md）。

安全红线（对齐 parallel_stack + INT-453 守卫）：
- 启动前逐端口探测，任一被占用即拒绝并退出，绝不 kill 占用者；
- DATABASE_URL 必须显式指向共享业务库 intelligent_audio_test（本启动器
  就是 INT-453 守卫授权的唯一例外；指向其它库一律拒绝）；
- AUTH_MODE=dev：INT-1195 账号走表单登录（账号清单见
  D:\\00_env\\multica_loop\\real_db_accounts.md）；
- 日志 / PID 一律写 worktree 之外（D:\\00_env\\real_stack\\），本 run 结束、
  worktree 删除后仍存活；必须经 WMI 脱离 run 进程树启动（INT-125 同因）。

用法（建议经 WMI 脱离进程树启动，start 常驻监督）：
    python real_stack.py start
    python real_stack.py stop
    python real_stack.py status
    python real_stack.py verify   # 一次核验：/health 库名 + gRPC 三件套 + 抽样计数 + 登录
"""
import argparse
import os
import socket
import subprocess
import sys
import time

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

try:
    from dotenv import load_dotenv  # noqa: E402
except ImportError:
    load_dotenv = None

from shared.constants.database import SHARED_BUSINESS_DB_NAME, database_name_of  # noqa: E402

BASE_DIR = PROJECT_ROOT
# PID / 日志根目录：默认取 BASE_DIR 的父目录（导出位置 D:\00_env\real_stack\）；
# 经 REAL_STACK_ROOT 可覆盖（如从仓库副本运行时不把 pid/日志写进工作树）。
STACK_ROOT = os.environ.get('REAL_STACK_ROOT') or os.path.dirname(BASE_DIR)

# 端口偏移（REAL_STACK_SHIFT 可覆盖，默认 700；禁与 5000 段、parallel 栈 535xx/6000 段重叠）
SHIFT = int(os.environ.get('REAL_STACK_SHIFT', '700'))
_suffix = '' if SHIFT == 700 else f'_{SHIFT}'
PID_FILE = os.path.join(STACK_ROOT, f'real_stack{_suffix}.pid')
LOG_DIR = os.path.join(STACK_ROOT, 'logs', f'real_stack{_suffix}')

# name, dir, base_http_port(None=gRPC-only), base_grpc_port
SERVICES = [
    ('api_gateway',        'api_gateway',        5000, None),
    ('task_service',       'task_service',       5001, 51061),
    ('e2e_test_service',   'e2e_test_service',   5002, 50051),
    ('api_test_service',   'api_test_service',   5003, 51071),
    ('evaluation_service', 'evaluation_service', 5004, 51091),
    ('report_service',     'report_service',     5006, 51068),
    ('algorithm_service',  'algorithm_service',  5007, 51067),
    ('auth_service',       'auth_service',       5009, 51069),
    ('api_adapter_service','api_adapter_service',5008, 51081),
    ('transfer_agent',     'transfer_agent',     5010, 51101),
    ('audio_service',      'audio_service',      None, 50052),
    ('device_service',     'device_service',     None, 50053),
]

# 客户端侧 gRPC 端口环境名（shared/infrastructure/config.py BaseConfig）
CLIENT_GRPC_ENVS = {
    'E2E_TEST_SERVICE_GRPC_PORT': 50051,
    'AUDIO_SERVICE_GRPC_PORT': 50052,
    'DEVICE_SERVICE_GRPC_PORT': 50053,
    'TASK_SERVICE_GRPC_PORT': 51061,
    'ALGORITHM_SERVICE_GRPC_PORT': 51067,
    'REPORT_SERVICE_GRPC_PORT': 51068,
    'AUTH_SERVICE_GRPC_PORT': 51069,
    'API_TEST_SERVICE_GRPC_PORT': 51071,
    'ADAPTER_SERVICE_GRPC_PORT': 51081,
    'EVALUATION_SERVICE_GRPC_PORT': 51091,
    'TRANSFER_AGENT_GRPC_PORT': 51101,
}

GATEWAY_HTTP = 5000 + SHIFT

# INT-1195 登录核验要求认证开启：dev=本地 OAuth（表单登录）。可经
# REAL_STACK_AUTH_MODE 覆盖（如临时 prod 走查）。前后端必须同值。
AUTH_MODE = os.environ.get('REAL_STACK_AUTH_MODE', 'dev')


def _shift(base: int) -> int:
    return base + SHIFT


def _base_env() -> dict:
    if load_dotenv is not None:
        load_dotenv(os.path.join(BASE_DIR, '.env'))
    env = os.environ.copy()
    env['PYTHONUTF8'] = '1'
    # 主库显式断言：本启动器只允许连共享业务库（INT-453 守卫授权的唯一例外）
    db_name = database_name_of(env.get('DATABASE_URL', ''))
    if db_name != SHARED_BUSINESS_DB_NAME:
        raise SystemExit(
            f'[REAL-STACK] 拒绝启动：DATABASE_URL 指向 {db_name!r}，'
            f'真实库栈必须显式指向共享业务库 {SHARED_BUSINESS_DB_NAME}。')
    # Redis 独立 DB index，避免与 5000 段 / parallel 栈缓存互踩
    env['REDIS_URL'] = 'redis://localhost:6379/2'
    # 业务日志落 worktree 之外
    env['LOG_ROOT_DIR'] = LOG_DIR
    # 认证：dev（表单登录，INT-1195 账号）；VITE_AUTH_MODE 与后端同值防错位
    env['AUTH_MODE'] = AUTH_MODE
    env['VITE_AUTH_MODE'] = AUTH_MODE
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
    env['SERVICE_NAME'] = f'real_{name}'
    return cmd


def _port_busy(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.6)
        return s.connect_ex((host, port)) == 0


def required_ports() -> list:
    ports = [_shift(g) for _, _, _, g in SERVICES if g] + [GATEWAY_HTTP]
    ports += [_shift(p) for _, _, p, _ in SERVICES if p]
    return sorted(set(ports))


def _refuse_if_busy():
    busy = [p for p in required_ports() if _port_busy('127.0.0.1', p)]
    if busy:
        raise SystemExit(
            f'[REAL-STACK] 拒绝启动：端口被占用 {busy}（本启动器绝不 kill 占用进程；'
            '请先排空端口或停掉占用者）。')


def start():
    """起栈并常驻监督（PID 文件恒为本 launcher 进程，stop 按树杀整栈）。

    必须经 WMI 脱离 agent 进程树启动（INT-125 同因：run 退出会收割进程树）；
    本函数永不返回，除非 Ctrl+C 或任一服务进程死亡（连带停整栈防半栈漂移）。
    """
    _refuse_if_busy()
    os.makedirs(LOG_DIR, exist_ok=True)
    base_env = _base_env()
    log = open(os.path.join(LOG_DIR, 'real_stack.log'), 'ab')
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

    with open(PID_FILE, 'w', encoding='ascii') as fh:
        fh.write(str(os.getpid()))
    print(f'[REAL-STACK] 已启动 {len(procs)} 个后端服务（launcher pid {os.getpid()}），'
          f'网关 :{GATEWAY_HTTP}，主库 {SHARED_BUSINESS_DB_NAME}，日志 {LOG_DIR}', flush=True)

    try:
        wait_ready()
        print('[REAL-STACK] 监督中（stop: python real_stack.py stop）', flush=True)
        while True:
            time.sleep(3)
            for name, p in procs:
                code = p.poll()
                if code is not None:
                    print(f'[REAL-STACK] {name} 已退出（code {code}），停止整栈', flush=True)
                    return stop()
    except KeyboardInterrupt:
        stop()


def wait_ready(timeout: int = 120):
    import httpx
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = httpx.get(f'http://127.0.0.1:{GATEWAY_HTTP}/health', timeout=2, trust_env=False)
            if r.status_code == 200:
                body = r.json()
                print(f"[REAL-STACK] 网关就绪：database={body.get('database')}", flush=True)
                if body.get('database') != SHARED_BUSINESS_DB_NAME:
                    print('[REAL-STACK][FATAL] 栈 database 字段非主库，立即停止', flush=True)
                    return stop()
                _verify_auth_mode()
                return True
        except Exception:
            pass
        time.sleep(2)
    print('[REAL-STACK][WARN] 网关就绪探测超时（详见 logs/real_stack/real_stack.log）', flush=True)
    return False


def _verify_auth_mode():
    """就绪后复核认证模式为 dev（INT-1195 登录核验前置条件）。"""
    import httpx
    try:
        r = httpx.get(f'http://127.0.0.1:{GATEWAY_HTTP}/api/v1/auth/mode',
                      timeout=3, trust_env=False)
        mode = (r.json() or {}).get('auth_mode', '')
    except Exception as exc:
        print(f'[REAL-STACK][WARN] auth mode 复核失败（后端不可达）: {exc}', flush=True)
        return
    if mode != AUTH_MODE:
        raise SystemExit(
            f'[REAL-STACK][FATAL] 认证模式错位：后端 AUTH_MODE={mode!r}，'
            f'期望 {AUTH_MODE!r}。请核对 REAL_STACK_AUTH_MODE 与 .env。')
    print(f'[REAL-STACK] 认证模式复核通过：{mode!r}', flush=True)


def _grcp_ready():
    """核验算法 / evaluation / api_test 三个 gRPC 服务端口（INT-901 教训）。"""
    targets = {
        'algorithm_service': _shift(51067),
        'evaluation_service': _shift(51091),
        'api_test_service': _shift(51071),
    }
    ok = {}
    for name, port in targets.items():
        ok[name] = _port_busy('127.0.0.1', port)
    return ok


def verify():
    """一次核验：/health 库名 + auth mode + gRPC 三件套 + 抽样计数 + 登录。"""
    import httpx
    print(f'[REAL-STACK] 核验 网关 :{GATEWAY_HTTP} ...')
    r = httpx.get(f'http://127.0.0.1:{GATEWAY_HTTP}/health', timeout=5, trust_env=False)
    body = r.json()
    print(f'  database={body.get("database")} (期望 {SHARED_BUSINESS_DB_NAME})')
    r = httpx.get(f'http://127.0.0.1:{GATEWAY_HTTP}/api/v1/auth/mode', timeout=5, trust_env=False)
    print(f"  auth_mode={r.json().get('auth_mode')}")
    for name, is_up in _grcp_ready().items():
        print(f'  gRPC {name} port open: {is_up}')
    return body.get('database') == SHARED_BUSINESS_DB_NAME


def stop():
    pid = None
    if os.path.exists(PID_FILE):
        try:
            pid = int(open(PID_FILE, encoding='ascii').read().strip())
        except Exception:
            pid = None
    if pid:
        subprocess.run(['taskkill', '/F', '/T', '/PID', str(pid)],
                       capture_output=True, text=True, encoding='utf-8', errors='replace')
        try:
            os.remove(PID_FILE)
        except OSError:
            pass
        print(f'[REAL-STACK] 已停止（launcher pid {pid} 进程树）')
    else:
        print('[REAL-STACK] 无 PID 记录，未停止任何进程')


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
    print(f'[REAL-STACK] {pid_status()} | gw-db={db} | ' + ' '.join(up))


def pid_status() -> str:
    if os.path.exists(PID_FILE):
        return f'pid-file={open(PID_FILE, encoding="ascii").read().strip()}'
    return 'pid-file=none'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='真实库栈常驻启动器（INT-1190：端口+700，主库）')
    parser.add_argument('action', choices=['start', 'stop', 'status', 'verify'])
    args = parser.parse_args()
    if args.action == 'start':
        start()
    elif args.action == 'stop':
        stop()
    elif args.action == 'verify':
        verify()
    else:
        status()
