"""
一键启动所有微服务 + 前端（开发模式）

- 自动加载 .env 注入子进程环境变量
- 后端服务：实时打印 stdout/stderr
- 前端服务：通过 npm run dev 启动 Vite，实时打印日志
"""
import subprocess
import sys
import os
import time
import signal
import threading

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

services = [
    {'name': 'api_gateway',    'port': 5000, 'grpc_port': None,  'dir': 'api_gateway'},
    {'name': 'task_service',    'port': 5001, 'grpc_port': 50061, 'dir': 'task_service'},
    {'name': 'e2e_test_service','port': 5002, 'grpc_port': 50051, 'dir': 'e2e_test_service'},
    {'name': 'api_test_service','port': 5003, 'grpc_port': 50071, 'dir': 'api_test_service'},
]

# 前端 Vite dev server
FRONTEND_DIR = os.path.join(BASE_DIR, 'frontend')

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


def start_service(svc):
    name = svc['name']
    print(f"[START] {name} on port {svc['port']}...", flush=True)
    # 用 -c 方式启动并把 app.py 当模块导入，避免脚本所在目录被加到 sys.path[0]
    # 从而防止 task_service/grpc、e2e_test_service/grpc 等子目录遮蔽第三方 grpc 库
    env = dict(CHILD_ENV)
    env['PYTHONPATH'] = BASE_DIR + os.pathsep + env.get('PYTHONPATH', '')
    # .env 里多个服务共用 PORT/GRPC_PORT 变量名会互相覆盖，这里按 services 配置强制指定
    env['PORT'] = str(svc['port'])
    if svc.get('grpc_port'):
        env['GRPC_PORT'] = str(svc['grpc_port'])
    proc = subprocess.Popen(
        [sys.executable, '-c',
         f"import runpy; runpy.run_path({os.path.join(svc['dir'], 'app.py')!r}, run_name='__main__')"],
        cwd=BASE_DIR,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=0,
    )
    # 起一个线程实时转发日志，避免管道缓冲区写满导致进程阻塞
    t = threading.Thread(target=_stream, args=(proc, name), daemon=True)
    t.start()
    processes.append({'name': name, 'proc': proc, 'thread': t})
    time.sleep(2)


def start_frontend():
    if not os.path.isdir(FRONTEND_DIR):
        print(f"[WARN] frontend dir not found: {FRONTEND_DIR}", flush=True)
        return
    pkg = os.path.join(FRONTEND_DIR, 'package.json')
    if not os.path.exists(pkg):
        print(f"[WARN] frontend/package.json not found: {pkg}", flush=True)
        return
    print("[START] frontend (vite) on port 5173...", flush=True)
    # Windows 上用 npm.cmd
    npm_cmd = 'npm.cmd' if os.name == 'nt' else 'npm'
    proc = subprocess.Popen(
        [npm_cmd, 'run', 'dev'],
        cwd=FRONTEND_DIR,
        env=CHILD_ENV,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=0,
        shell=False,
    )
    t = threading.Thread(target=_stream, args=(proc, 'frontend'), daemon=True)
    t.start()
    processes.append({'name': 'frontend', 'proc': proc, 'thread': t})


def _is_port_open(host, port):
    """探测端口是否可连接。"""
    import socket
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


def start_redis():
    """本地直接启动 redis-server（Windows 下用 redis-server.exe）。"""
    if _is_port_open('localhost', 6379):
        print("[INFO] redis already running on :6379", flush=True)
        return
    # Windows 下查找 redis-server.exe
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
        # 退回 PATH 查找
        try:
            import shutil
            redis_bin = shutil.which('redis-server')
        except Exception:
            redis_bin = None
    if not redis_bin:
        print("[WARN] redis-server not found, please start redis manually on :6379", flush=True)
        return
    print(f"[START] redis-server: {redis_bin}", flush=True)
    proc = subprocess.Popen(
        [redis_bin],
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
    # Windows 下查找 pg_ctl.exe
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
    # pg_ctl start 会在后台启动 postgres 并立即返回
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
    # Windows 下查找 minio.exe
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
    # 从 .env 读取 MinIO 凭据（与 BaseConfig 一致）
    minio_root_user = CHILD_ENV.get('OSS_ACCESS_KEY', 'minio')
    minio_root_password = CHILD_ENV.get('OSS_SECRET_KEY', 'minio123')
    # 数据目录：优先 .env 的 MINIO_DATA_DIR，否则回落到 minio.exe 同级 data 目录
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


def start_all():
    start_redis()
    start_postgres()
    start_minio()
    for svc in services:
        start_service(svc)
    start_frontend()
    print(f"\n[OK] Started {len(processes)} processes (4 backend + 1 frontend).", flush=True)
    print("[INFO] Frontend: http://localhost:5173", flush=True)
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
