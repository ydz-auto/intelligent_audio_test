"""
一键启动所有微服务（FastAPI + DDD 版）

- 自动加载 .env 注入子进程环境变量
- 启动基础设施：redis / postgres / minio
- 启动 5 个 FastAPI 后端服务（uvicorn）
- 实时转发每个子进程的 stdout/stderr
- 端口就绪探测，Ctrl+C 优雅停止全部

用法：
    python run_all.py
"""
import subprocess
import sys
import os
import time
import signal
import threading
import socket

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_FILE = os.path.join(BASE_DIR, '.env')

# 加载 .env 到当前进程环境变量，子进程会继承
try:
    from dotenv import load_dotenv
    if os.path.exists(ENV_FILE):
        load_dotenv(ENV_FILE)
        print(f"[ENV] loaded {ENV_FILE}", flush=True)
    else:
        print(f"[WARN] .env not found at {ENV_FILE}, backend services may fail to start", flush=True)
except ImportError:
    print("[WARN] python-dotenv not installed, skipping .env loading", flush=True)

# 子进程环境（继承当前进程 + .env）
CHILD_ENV = os.environ.copy()

# 5 个 FastAPI 后端微服务配置
# .env 里 PORT/GRPC_PORT 是全局变量，多个服务共用会互相覆盖，
# 这里按 services 配置在子进程环境里强制指定各自的端口
services = [
    {'name': 'api_gateway',        'port': 5000, 'grpc_port': None,   'dir': 'api_gateway'},
    {'name': 'task_service',        'port': 5001, 'grpc_port': 50061, 'dir': 'task_service'},
    {'name': 'e2e_test_service',    'port': 5002, 'grpc_port': 50051, 'dir': 'e2e_test_service'},
    {'name': 'api_test_service',    'port': 5003, 'grpc_port': 50071, 'dir': 'api_test_service'},
    {'name': 'api_adapter_service', 'port': 5008, 'grpc_port': 50081, 'dir': 'api_adapter_service'},
]

# 前端 Vite dev server
# 前端已复制到本项目 frontend/ 目录下。
# 端口：vite.config.ts 默认 6173；如要用 5173，通过环境变量 VITE_PORT 覆盖。
# 连后端：vite proxy 把 /api、/ws、/socket.io 转发到 VITE_API_TARGET（默认 6000=旧 Flask 网关）。
# 新 FastAPI 网关在 5000，必须在子进程环境里注入 VITE_API_TARGET=http://localhost:5000，
# 否则前端会连到旧项目 6000 端口。
FRONTEND_DIR = os.path.join(BASE_DIR, 'frontend')
FRONTEND_PORT = 5173
# 新 FastAPI 网关地址，注入给 vite proxy
API_GATEWAY_URL = f"http://localhost:{services[0]['port']}"

processes = []


def _stream(proc, name):
    """实时读取子进程 stdout 并加上服务名前缀打印到主进程。"""
    try:
        for line in iter(proc.stdout.readline, b''):
            if not line:
                break
            try:
                text = line.decode('utf-8', errors='replace').rstrip('\r\n')
            except Exception:
                text = repr(line)
            print(f"[{name}] {text}", flush=True)
    finally:
        try:
            proc.stdout.close()
        except Exception:
            pass


def _is_port_open(host, port):
    """探测端口是否可连接。"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1)
        s.connect((host, port))
        s.close()
        return True
    except Exception:
        return False


def _wait_port(host, port, name, timeout=30):
    """等待端口就绪，返回是否就绪。"""
    for _ in range(timeout):
        if _is_port_open(host, port):
            print(f"[OK] {name} is ready", flush=True)
            return True
        time.sleep(1)
    print(f"[WARN] {name} readiness check timed out, continuing anyway", flush=True)
    return False


def start_service(svc):
    """启动一个 FastAPI 服务（uvicorn）。"""
    name = svc['name']
    port = svc['port']
    print(f"[START] {name} on port {port}...", flush=True)

    env = dict(CHILD_ENV)
    env['PYTHONPATH'] = BASE_DIR + os.pathsep + env.get('PYTHONPATH', '')
    env['PORT'] = str(port)
    if svc.get('grpc_port'):
        env['GRPC_PORT'] = str(svc['grpc_port'])

    # 用 uvicorn 启动，app 模块路径 = {dir}.app:app
    proc = subprocess.Popen(
        [sys.executable, '-m', 'uvicorn',
         f"{svc['dir']}.app:app",
         '--host', '0.0.0.0',
         '--port', str(port),
         '--workers', '1',
         '--log-level', 'info'],
        cwd=BASE_DIR,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=0,
    )
    t = threading.Thread(target=_stream, args=(proc, name), daemon=True)
    t.start()
    processes.append({'name': name, 'proc': proc, 'thread': t})
    # 等待端口就绪再启动下一个，避免资源争抢
    _wait_port('localhost', port, name)


def start_redis():
    """本地直接启动 redis-server（Windows 下用 redis-server.exe）。"""
    if _is_port_open('localhost', 6379):
        print("[INFO] redis already running on :6379", flush=True)
        return
    candidates = []
    if os.name == 'nt':
        candidates = [
            r'C:\S2TT\environment\redis\redis-server.exe',
            r'D:\00_env\redis\Redis-8.8.1-Windows-x64-cygwin-with-Service\redis-server.exe',
            r'D:\00_env\redis\redis-server.exe',
        ]
    else:
        candidates = ['redis-server']
    redis_bin = next((p for p in candidates if os.path.exists(p)), None)
    if not redis_bin:
        try:
            import shutil
            redis_bin = shutil.which('redis-server')
        except Exception:
            redis_bin = None
    if not redis_bin:
        print("[WARN] redis-server not found, please start redis manually on :6379", flush=True)
        return
    print(f"[START] redis-server: {redis_bin}", flush=True)
    # 纯运行时状态（Pub/Sub + 服务注册），无需持久化：禁用 RDB，AOF 默认关闭。
    proc = subprocess.Popen(
        [redis_bin, '--save', '', '--appendonly', 'no'],
        cwd=os.path.dirname(redis_bin) or None,
        env=CHILD_ENV,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=0,
    )
    t = threading.Thread(target=_stream, args=(proc, 'redis'), daemon=True)
    t.start()
    processes.append({'name': 'redis', 'proc': proc, 'thread': t})
    _wait_port('localhost', 6379, 'redis')


def start_postgres():
    """本地直接启动 Postgres（Windows 下用 pg_ctl start）。"""
    if _is_port_open('localhost', 5432):
        print("[INFO] postgres already running on :5432", flush=True)
        return
    candidates = []
    if os.name == 'nt':
        candidates = [
            r'D:\00_env\postgresql-16.8-1-windows-x64-binaries\pgsql\bin\pg_ctl.exe',
            r'D:\00_env\postgresql\bin\pg_ctl.exe',
        ]
    else:
        candidates = ['pg_ctl']
    pg_ctl = next((p for p in candidates if os.path.exists(p)), None)
    if not pg_ctl:
        try:
            import shutil
            pg_ctl = shutil.which('pg_ctl')
        except Exception:
            pg_ctl = None
    if not pg_ctl:
        print("[WARN] pg_ctl not found, please start postgres manually on :5432", flush=True)
        return
    data_dir = os.path.join(os.path.dirname(os.path.dirname(pg_ctl)), 'data')
    if not os.path.isdir(data_dir):
        print(f"[WARN] postgres data dir not found: {data_dir}", flush=True)
        return
    print(f"[START] postgres: {pg_ctl} (data: {data_dir})", flush=True)
    try:
        result = subprocess.run(
            [pg_ctl, 'start', '-D', data_dir, '-w', '-t', '30'],
            env=CHILD_ENV, capture_output=True, text=True,
        )
        if result.stdout:
            print(f"[postgres] {result.stdout.strip()}", flush=True)
        if result.stderr:
            print(f"[postgres] {result.stderr.strip()}", flush=True)
        if result.returncode != 0:
            print(f"[WARN] pg_ctl start returned {result.returncode}", flush=True)
    except Exception as e:
        print(f"[WARN] postgres startup failed: {e}", flush=True)
    _wait_port('localhost', 5432, 'postgres')


def start_minio():
    """本地直接启动 MinIO（Windows 下用 minio.exe server）。"""
    if _is_port_open('localhost', 9000):
        print("[INFO] minio already running on :9000", flush=True)
        return
    candidates = []
    if os.name == 'nt':
        candidates = [
            r'C:\S2TT\environment\minio\minio.exe',
            r'D:\00_env\minio\minio.exe',
        ]
    else:
        candidates = ['minio']
    minio_bin = next((p for p in candidates if os.path.exists(p)), None)
    if not minio_bin:
        try:
            import shutil
            minio_bin = shutil.which('minio')
        except Exception:
            minio_bin = None
    if not minio_bin:
        print("[WARN] minio not found, please start minio manually on :9000", flush=True)
        return
    minio_root_user = CHILD_ENV.get('OSS_ACCESS_KEY', 'minio')
    minio_root_password = CHILD_ENV.get('OSS_SECRET_KEY', 'minio123')
    minio_data_dir = CHILD_ENV.get('MINIO_DATA_DIR') or os.path.join(os.path.dirname(minio_bin), 'data')
    print(f"[START] minio: {minio_bin} (data: {minio_data_dir})", flush=True)
    env = dict(CHILD_ENV)
    env['MINIO_ROOT_USER'] = minio_root_user
    env['MINIO_ROOT_PASSWORD'] = minio_root_password
    proc = subprocess.Popen(
        [minio_bin, 'server', minio_data_dir, '--console-address', ':9001'],
        cwd=os.path.dirname(minio_bin) or None,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=0,
    )
    t = threading.Thread(target=_stream, args=(proc, 'minio'), daemon=True)
    t.start()
    processes.append({'name': 'minio', 'proc': proc, 'thread': t})
    _wait_port('localhost', 9000, 'minio')


def start_frontend():
    """启动前端 Vite dev server。

    关键：通过环境变量 VITE_API_TARGET 把 vite proxy 指向新 FastAPI 网关 (5000)，
    否则 vite.config.ts 默认连 6000（旧 Flask 网关），前端请求会打到旧项目。
    端口用 --port 覆盖 vite.config.ts 的 6173，改为 5173。
    """
    if not os.path.isdir(FRONTEND_DIR):
        print(f"[WARN] frontend dir not found: {FRONTEND_DIR}", flush=True)
        return
    pkg = os.path.join(FRONTEND_DIR, 'package.json')
    if not os.path.exists(pkg):
        print(f"[WARN] frontend/package.json not found: {pkg}", flush=True)
        return
    print(f"[START] frontend (vite) on port {FRONTEND_PORT}, proxy -> {API_GATEWAY_URL}", flush=True)
    # Windows 上用 npm.cmd
    npm_cmd = 'npm.cmd' if os.name == 'nt' else 'npm'
    env = dict(CHILD_ENV)
    env['VITE_API_TARGET'] = API_GATEWAY_URL
    proc = subprocess.Popen(
        [npm_cmd, 'run', 'dev', '--', '--port', str(FRONTEND_PORT), '--strictPort'],
        cwd=FRONTEND_DIR,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=0,
        shell=False,
    )
    t = threading.Thread(target=_stream, args=(proc, 'frontend'), daemon=True)
    t.start()
    processes.append({'name': 'frontend', 'proc': proc, 'thread': t})
    _wait_port('localhost', FRONTEND_PORT, 'frontend')


def start_all():
    start_redis()
    start_postgres()
    start_minio()
    for svc in services:
        start_service(svc)
    start_frontend()
    print(f"\n[OK] Started {len(processes)} processes (3 infra + 5 backend + 1 frontend).", flush=True)
    print("[INFO] Frontend:          http://localhost:5173", flush=True)
    print("[INFO] API Gateway:        http://localhost:5000", flush=True)
    print("[INFO] Task Service:      http://localhost:5001", flush=True)
    print("[INFO] E2E Test Service:  http://localhost:5002", flush=True)
    print("[INFO] API Test Service:  http://localhost:5003", flush=True)
    print("[INFO] Adapter Service:   http://localhost:5008", flush=True)
    print("[INFO] MinIO Console:     http://localhost:9001", flush=True)
    print("[INFO] Ctrl+C to stop all.", flush=True)


def stop_all():
    for p in reversed(processes):
        print(f"[STOP] {p['name']}...", flush=True)
        try:
            p['proc'].terminate()
            p['proc'].wait(timeout=5)
        except subprocess.TimeoutExpired:
            p['proc'].kill()
        except Exception:
            pass
    print("[OK] All services stopped.", flush=True)


if __name__ == '__main__':
    try:
        start_all()
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[INFO] Stopping all services...", flush=True)
        stop_all()
