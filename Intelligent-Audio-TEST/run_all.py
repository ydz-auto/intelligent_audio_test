"""
一键启动所有微服务（FastAPI + DDD 版）

- 自动加载 .env 注入子进程环境变量
- 启动基础设施：redis / postgres / minio
- 启动 11 个后端微服务（FastAPI + gRPC-only）
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
import logging
import threading
import socket

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s %(name)s: %(message)s')

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

# 11 个后端微服务配置
# .env 里 PORT/GRPC_PORT 是全局变量，多个服务共用会互相覆盖，
# 这里按 services 配置在子进程环境里强制指定各自的端口
# - HTTP 服务用 uvicorn 启动 {dir}.app:app
# - gRPC-only 服务（audio_service / device_service）用 python -m {dir}.interfaces.grpc.server 启动
# - report_service HTTP 端口改为 5006，避免与 api_adapter_service 的 5008 冲突
services = [
    {'name': 'api_gateway',        'port': 5000, 'grpc_port': None,   'dir': 'api_gateway',         'http': True},
    {'name': 'task_service',        'port': 5001, 'grpc_port': 50061, 'dir': 'task_service',        'http': True},
    {'name': 'e2e_test_service',    'port': 5002, 'grpc_port': 50051, 'dir': 'e2e_test_service',    'http': True},
    {'name': 'api_test_service',    'port': 5003, 'grpc_port': 50071, 'dir': 'api_test_service',    'http': True},
    {'name': 'evaluation_service',  'port': 5004, 'grpc_port': 50091, 'dir': 'evaluation_service',  'http': True},
    {'name': 'algorithm_service',   'port': 5007, 'grpc_port': 50067, 'dir': 'algorithm_service',   'http': True},
    {'name': 'report_service',      'port': 5006, 'grpc_port': 50068, 'dir': 'report_service',      'http': True},
    {'name': 'auth_service',        'port': 5009, 'grpc_port': 50069, 'dir': 'auth_service',        'http': True},
    {'name': 'api_adapter_service', 'port': 5008, 'grpc_port': 50081, 'dir': 'api_adapter_service', 'http': True},
    # gRPC-only 服务：无 app.py，仅启动 gRPC server
    {'name': 'audio_service',       'port': None, 'grpc_port': 50052, 'dir': 'audio_service',      'http': False},
    {'name': 'device_service',      'port': None, 'grpc_port': 50053, 'dir': 'device_service',      'http': False},
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
            logger.debug("关闭子进程 stdout 失败", exc_info=True)


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


def _find_pids_on_port(port):
    """查找占用指定端口的进程 PID 集合。"""
    pids = set()
    # 优先用 psutil（跨平台）
    try:
        import psutil
        for conn in psutil.net_connections(kind='inet'):
            if (conn.status == psutil.CONN_LISTEN
                    and conn.laddr.port == port
                    and conn.pid):
                pids.add(conn.pid)
        if pids:
            return pids
    except Exception:
        logger.debug("psutil 查询占用端口 %s 的进程失败", port, exc_info=True)
    # 回退：Windows netstat
    if os.name == 'nt':
        try:
            result = subprocess.run(
                ['netstat', '-ano'], capture_output=True, text=True, timeout=5
            )
            for line in result.stdout.splitlines():
                if f':{port} ' in line and 'LISTEN' in line.upper():
                    parts = line.split()
                    if parts and parts[-1].isdigit():
                        pids.add(int(parts[-1]))
        except Exception:
            logger.debug("netstat 查询占用端口 %s 的进程失败", port, exc_info=True)
    return pids


def _kill_pid(pid):
    """杀掉指定 PID 的进程，返回是否成功。"""
    try:
        if os.name == 'nt':
            r = subprocess.run(
                ['taskkill', '/F', '/PID', str(pid)],
                capture_output=True, text=True, timeout=5
            )
            return r.returncode == 0
        else:
            import signal as _sig
            os.kill(pid, _sig.SIGKILL)
            return True
    except Exception:
        return False


def cleanup_occupied_ports():
    """启动前检查并清理被占用的服务端口（HTTP + gRPC + 前端，不含 infra）。"""
    ports_to_check = {FRONTEND_PORT}
    for svc in services:
        if svc.get('port'):
            ports_to_check.add(svc['port'])
        if svc.get('grpc_port'):
            ports_to_check.add(svc['grpc_port'])

    killed_any = False
    for port in sorted(ports_to_check):
        pids = _find_pids_on_port(port)
        if not pids:
            continue
        for pid in pids:
            proc_name = ''
            try:
                import psutil
                proc_name = psutil.Process(pid).name()
            except Exception:
                logger.debug("获取进程 %s 名称失败", pid, exc_info=True)
            print(f"[CLEAN] port {port} occupied by PID {pid} ({proc_name}), killing...",
                  flush=True)
            if _kill_pid(pid):
                killed_any = True

    if killed_any:
        time.sleep(1)  # 等端口释放
        print("[OK] occupied ports cleaned.", flush=True)


def start_service(svc):
    """启动一个微服务。

    - HTTP 服务（http=True）：用 uvicorn 启动 {dir}.app:app
    - gRPC-only 服务（http=False）：用 python -m {dir}.interfaces.grpc.server 启动
    """
    name = svc['name']
    port = svc['port']
    grpc_port = svc.get('grpc_port')

    env = dict(CHILD_ENV)
    # shared/proto 目录：*_pb2_grpc.py 使用裸导入 `import xxx_pb2`，
    # 需将 proto 目录加入 sys.path 才能解析。
    proto_dir = os.path.join(BASE_DIR, 'shared', 'proto')
    env['PYTHONPATH'] = (
        BASE_DIR + os.pathsep + proto_dir + os.pathsep + env.get('PYTHONPATH', '')
    )

    if svc.get('http', True):
        print(f"[START] {name} (HTTP) on port {port}...", flush=True)
        env['PORT'] = str(port)
        if grpc_port:
            env['GRPC_PORT'] = str(grpc_port)
        cmd = [
            sys.executable, '-m', 'uvicorn',
            f"{svc['dir']}.app:app",
            '--host', '0.0.0.0',
            '--port', str(port),
            '--workers', '1',
            '--log-level', 'info',
        ]
    else:
        print(f"[START] {name} (gRPC-only) on port {grpc_port}...", flush=True)
        if grpc_port:
            env['GRPC_PORT'] = str(grpc_port)
        cmd = [
            sys.executable, '-m', f"{svc['dir']}.interfaces.grpc.server",
        ]

    proc = subprocess.Popen(
        cmd,
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
    if port:
        _wait_port('localhost', port, name)
    elif grpc_port:
        _wait_port('localhost', grpc_port, name)


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
    cleanup_occupied_ports()
    start_redis()
    start_postgres()
    start_minio()
    for svc in services:
        start_service(svc)
    start_frontend()
    print(f"\n[OK] Started {len(processes)} processes (3 infra + 11 backend + 1 frontend).", flush=True)
    print("[INFO] Frontend:            http://localhost:5173", flush=True)
    print("[INFO] API Gateway:        http://localhost:5000", flush=True)
    print("[INFO] Task Service:       http://localhost:5001", flush=True)
    print("[INFO] E2E Test Service:   http://localhost:5002", flush=True)
    print("[INFO] API Test Service:   http://localhost:5003", flush=True)
    print("[INFO] Evaluation Service: http://localhost:5004", flush=True)
    print("[INFO] Report Service:     http://localhost:5006", flush=True)
    print("[INFO] Algorithm Service:  http://localhost:5007", flush=True)
    print("[INFO] Adapter Service:    http://localhost:5008", flush=True)
    print("[INFO] Auth Service:       http://localhost:5009", flush=True)
    print("[INFO] Audio Service:      gRPC :50052", flush=True)
    print("[INFO] Device Service:     gRPC :50053", flush=True)
    print("[INFO] MinIO Console:      http://localhost:9001", flush=True)
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
            logger.debug("停止子进程 %s 失败", p.get('name', '?'), exc_info=True)
    print("[OK] All services stopped.", flush=True)


if __name__ == '__main__':
    try:
        start_all()
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[INFO] Stopping all services...", flush=True)
        stop_all()
