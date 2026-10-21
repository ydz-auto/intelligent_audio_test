"""
一键启动所有微服务（FastAPI + DDD 版）

- 自动加载 .env 注入子进程环境变量
- 启动基础设施：redis / postgres / rustfs
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

# 从端口注册表集中引入所有端口常量，避免散落硬编码
from shared.config.service_ports import (
    API_GATEWAY_PORT,
    TASK_SERVICE_HTTP_PORT,
    TASK_SERVICE_GRPC_PORT,
    E2E_TEST_HTTP_PORT,
    E2E_TEST_GRPC_PORT,
    API_TEST_HTTP_PORT,
    API_TEST_SERVICE_GRPC_PORT,
    EVALUATION_SERVICE_HTTP_PORT,
    EVALUATION_SERVICE_GRPC_PORT,
    ALGORITHM_SERVICE_HTTP_PORT,
    ALGORITHM_SERVICE_GRPC_PORT,
    REPORT_SERVICE_HTTP_PORT,
    REPORT_SERVICE_GRPC_PORT,
    AUTH_SERVICE_HTTP_PORT,
    AUTH_SERVICE_GRPC_PORT,
    AUDIO_SERVICE_GRPC_PORT,
    DEVICE_SERVICE_GRPC_PORT,
    TRANSFER_AGENT_HTTP_PORT,
    TRANSFER_AGENT_GRPC_PORT,
    REDIS_PORT,
    POSTGRESQL_PORT,
    RUSTFS_PORT,
    RUSTFS_CONSOLE_PORT,
    FRONTEND_DEV_PORT,
    MOCK_THIRD_PARTY_EVAL_HTTP_PORT,
    MOCK_REALTIME_API_WS_PORT,
    MOCK_EVAL_SERVER_HTTP_PORT,
    MOCK_DUT_API_HTTP_PORT,
)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s %(name)s: %(message)s')

# INT-102：主进程 stdout/stderr 被重定向为文件时用 locale 编码（中文 Windows 为
# GBK），_stream 转发的服务日志常含 GBK 无法编码的字符（含 errors='replace'
# 产生的 U+FFFD），print 抛 UnicodeEncodeError 杀死转发线程 → 子进程 stdout
# 管道无人消化塞满 → 服务卡死、日志调用抛 OSError 炸业务路径。
# 显式改用 UTF-8 并对极少数不可编码字符替换，保证任何输出都不抛异常。
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

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
# INT-102：子进程 stdout 是管道（非控制台）时 Python 用 locale 编码（中文
# Windows 为 GBK），服务日志含 GBK 外字符即 UnicodeEncodeError，是服务启动期
# 死亡的另一根因。强制子进程 UTF-8 模式（外部显式设置的值优先，可覆盖）。
CHILD_ENV.setdefault('PYTHONUTF8', '1')

# 11 个后端微服务配置
# .env 里 PORT/GRPC_PORT 是全局变量，多个服务共用会互相覆盖，
# 这里按 services 配置在子进程环境里强制指定各自的端口
# - HTTP 服务用 uvicorn 启动 {dir}.app:app
# - gRPC-only 服务（audio_service / device_service）用 python -m {dir}.interfaces.grpc.server 启动
# - report_service HTTP 端口为 5006
# - transfer_agent（INT-28 跨区传输）HTTP 5010 / gRPC 50101
services = [
    {'name': 'api_gateway',        'port': API_GATEWAY_PORT,            'grpc_port': None,                          'dir': 'api_gateway',         'http': True},
    {'name': 'task_service',        'port': TASK_SERVICE_HTTP_PORT,     'grpc_port': TASK_SERVICE_GRPC_PORT,        'dir': 'task_service',        'http': True},
    {'name': 'e2e_test_service',    'port': E2E_TEST_HTTP_PORT,         'grpc_port': E2E_TEST_GRPC_PORT,            'dir': 'e2e_test_service',    'http': True},
    {'name': 'api_test_service',    'port': API_TEST_HTTP_PORT,         'grpc_port': API_TEST_SERVICE_GRPC_PORT,     'dir': 'api_test_service',    'http': True},
    {'name': 'evaluation_service',  'port': EVALUATION_SERVICE_HTTP_PORT, 'grpc_port': EVALUATION_SERVICE_GRPC_PORT, 'dir': 'evaluation_service',  'http': True},
    {'name': 'algorithm_service',   'port': ALGORITHM_SERVICE_HTTP_PORT,'grpc_port': ALGORITHM_SERVICE_GRPC_PORT,   'dir': 'algorithm_service',   'http': True},
    {'name': 'report_service',      'port': REPORT_SERVICE_HTTP_PORT,   'grpc_port': REPORT_SERVICE_GRPC_PORT,      'dir': 'report_service',      'http': True},
    {'name': 'auth_service',        'port': AUTH_SERVICE_HTTP_PORT,      'grpc_port': AUTH_SERVICE_GRPC_PORT,         'dir': 'auth_service',        'http': True},
    {'name': 'transfer_agent',      'port': TRANSFER_AGENT_HTTP_PORT,   'grpc_port': TRANSFER_AGENT_GRPC_PORT,      'dir': 'transfer_agent',      'http': True},
    # gRPC-only 服务：无 app.py，仅启动 gRPC server
    {'name': 'audio_service',       'port': None,                       'grpc_port': AUDIO_SERVICE_GRPC_PORT,        'dir': 'audio_service',      'http': False},
    {'name': 'device_service',      'port': None,                       'grpc_port': DEVICE_SERVICE_GRPC_PORT,       'dir': 'device_service',      'http': False},
]

# Mock 替身服务（INT-137，仅联调/验收/回归用）：MOCK_SERVICES_ENABLED=true 才启动，
# 默认关闭 —— 生产路径零依赖，mock 服务独立可运行（mock_services/ 下脚本）。
MOCK_SERVICES_ENABLED = str(CHILD_ENV.get('MOCK_SERVICES_ENABLED', '')).strip().lower() \
    in ('1', 'true', 'yes', 'on')

mock_services = [
    {'name': 'mock_third_party_eval', 'port': MOCK_THIRD_PARTY_EVAL_HTTP_PORT,
     'script': os.path.join('mock_services', 'mock_third_party_eval.py')},
    {'name': 'mock_realtime_api', 'port': MOCK_REALTIME_API_WS_PORT,
     'script': os.path.join('mock_services', 'mock_realtime_api.py')},
    {'name': 'mock_eval_server_judge', 'port': MOCK_EVAL_SERVER_HTTP_PORT,
     'script': os.path.join('mock_services', 'mock_eval_server_judge.py')},
    {'name': 'mock_dut_api', 'port': MOCK_DUT_API_HTTP_PORT,
     'script': os.path.join('mock_services', 'mock_dut_api.py')},
]

# 前端 Vite dev server
# 前端已复制到本项目 frontend/ 目录下。
# 端口：vite.config.ts 默认 6173；如要用 5173，通过环境变量 VITE_PORT 覆盖。
# 连后端：vite proxy 把 /api、/ws、/socket.io 转发到 VITE_API_TARGET（默认 6000=旧 Flask 网关）。
# 新 FastAPI 网关在 5000，必须在子进程环境里注入 VITE_API_TARGET=http://localhost:5000，
# 否则前端会连到旧项目 6000 端口。
FRONTEND_DIR = os.path.join(BASE_DIR, 'frontend')
FRONTEND_PORT = FRONTEND_DEV_PORT
# 新 FastAPI 网关地址，注入给 vite proxy
API_GATEWAY_URL = f"http://localhost:{services[0]['port']}"

processes = []


def _stream(proc, name):
    """实时读取子进程 stdout 并加上服务名前缀打印到主进程。

    打印失败（INT-102：磁盘/句柄异常等残余场景）只丢弃该行，
    绝不停止读管道——否则子进程 stdout PIPE 无人消化，塞满后
    服务卡死或日志调用抛 OSError 炸业务路径。
    """
    try:
        for line in iter(proc.stdout.readline, b''):
            if not line:
                break
            try:
                text = line.decode('utf-8', errors='replace').rstrip('\r\n')
            except Exception:
                text = repr(line)
            try:
                print(f"[{name}] {text}", flush=True)
            except Exception:
                pass
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
    """启动前检查并清理被占用的服务端口（HTTP + gRPC + 前端 + 可选 mock，不含 infra）。"""
    ports_to_check = {FRONTEND_PORT}
    for svc in services:
        if svc.get('port'):
            ports_to_check.add(svc['port'])
        if svc.get('grpc_port'):
            ports_to_check.add(svc['grpc_port'])
    if MOCK_SERVICES_ENABLED:
        ports_to_check.update(svc['port'] for svc in mock_services)

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
        # INT-81：服务运行日志按 logs/{service_name}/ 分目录，需显式传入服务名
        env['SERVICE_NAME'] = name
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
        # INT-81：gRPC-only 服务同样按服务名分目录落运行日志
        env['SERVICE_NAME'] = name
        if grpc_port:
            env['GRPC_PORT'] = str(grpc_port)
        cmd = [
            sys.executable, '-m', f"{svc['dir']}.interfaces.grpc.server",
        ]
        # INT-108：OS 音频栈楔死时（Audiosrv 卡 StartPending，真实 Pa_Initialize 无限挂起，
        # 服务卡死在 PyAudio 预初始化、50052 永不绑定），置 AUDIO_PYAUDIO_SHIM=1 以
        # INT-95 影子夹具启动 audio_service（无真实设备 I/O，API 链可用；E2E 物理链
        # 验收必须去掉该开关改用真实驱动）。
        if svc['name'] == 'audio_service' and os.environ.get('AUDIO_PYAUDIO_SHIM') == '1':
            shim_dir = os.path.join(BASE_DIR, 'tests', 'fixtures', 'pyaudio_shim')
            env['PYTHONPATH'] = shim_dir + os.pathsep + env['PYTHONPATH']
            print(f"[INFO] audio_service: AUDIO_PYAUDIO_SHIM=1, injecting shadow pyaudio fixture ({shim_dir})", flush=True)

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
        ready = _wait_port('localhost', grpc_port, name)
        if not ready and name == 'audio_service':
            # INT-108：audio_service 端口超时最常见的根因是 OS 音频栈楔死，
            # 进程卡死在 PyAudio 预初始化（日志停在 soft_delete_cleaner 两行），
            # 此后进程存活但不监听端口，HTTP 冒烟口径探测不到。
            print("[HINT] audio_service 未在超时内就绪。若 logs/audio_service/ 最新日志"
                  "停在「守护线程已启动」，即 OS 音频栈楔死（真实 Pa_Initialize 无限挂起）："
                  "设 AUDIO_PYAUDIO_SHIM=1 重新 run_all 以 INT-95 影子夹具启动"
                  "（tests/fixtures/pyaudio_shim/pyaudio.py，E2E 物理链验收除外）。", flush=True)


def start_redis():
    """本地直接启动 redis-server（Windows 下用 redis-server.exe）。"""
    if _is_port_open('localhost', REDIS_PORT):
        print(f"[INFO] redis already running on :{REDIS_PORT}", flush=True)
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
        print(f"[WARN] redis-server not found, please start redis manually on :{REDIS_PORT}", flush=True)
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
    _wait_port('localhost', REDIS_PORT, 'redis')


def start_postgres():
    """本地直接启动 Postgres（Windows 下用 pg_ctl start）。"""
    if _is_port_open('localhost', POSTGRESQL_PORT):
        print(f"[INFO] postgres already running on :{POSTGRESQL_PORT}", flush=True)
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
        print(f"[WARN] pg_ctl not found, please start postgres manually on :{POSTGRESQL_PORT}", flush=True)
        return
    data_dir = os.path.join(os.path.dirname(os.path.dirname(pg_ctl)), 'data')
    if not os.path.isdir(data_dir):
        print(f"[WARN] postgres data dir not found: {data_dir}", flush=True)
        return
    print(f"[START] postgres: {pg_ctl} (data: {data_dir})", flush=True)
    log_file = os.path.join(data_dir, 'pg_startup.log')
    try:
        # Windows 上 postgres 会继承 pg_ctl 的标准句柄：
        # 若用管道捕获输出，即使 pg_ctl 退出，postgres 仍持有管道写端，
        # communicate() 等不到 EOF 会永远阻塞（超时 kill 也无法解除）。
        # 因此输出直接丢弃（诊断信息见 pg_startup.log），仅用超时兜底。
        result = subprocess.run(
            [pg_ctl, 'start', '-D', data_dir, '-l', log_file, '-w', '-t', '15'],
            env=CHILD_ENV,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=20,
        )
        if result.returncode != 0:
            print(f"[WARN] pg_ctl start returned {result.returncode}, see {log_file}", flush=True)
    except subprocess.TimeoutExpired:
        print("[WARN] pg_ctl start timed out; checking PostgreSQL readiness instead", flush=True)
    except Exception as e:
        print(f"[WARN] postgres startup failed: {e}", flush=True)
    _wait_port('localhost', POSTGRESQL_PORT, 'postgres')


def start_rustfs():
    """本地直接启动 RustFS（S3 兼容对象存储，单节点模式：rustfs <data_dir>）。"""
    if _is_port_open('localhost', RUSTFS_PORT):
        print(f"[INFO] rustfs already running on :{RUSTFS_PORT}", flush=True)
        return
    candidates = []
    if os.name == 'nt':
        candidates = [
            r'C:\S2TT\environment\rustfs\rustfs.exe',
            r'D:\00_env\rustfs\rustfs.exe',
        ]
    else:
        candidates = ['rustfs']
    rustfs_bin = next((p for p in candidates if os.path.exists(p)), None)
    if not rustfs_bin:
        try:
            import shutil
            rustfs_bin = shutil.which('rustfs')
        except Exception:
            rustfs_bin = None
    if not rustfs_bin:
        print(f"[WARN] rustfs not found, please start rustfs manually on :{RUSTFS_PORT}", flush=True)
        return
    data_dir = CHILD_ENV.get('RUSTFS_DATA_DIR') or os.path.join(BASE_DIR, 'storage', 'rustfs')
    os.makedirs(data_dir, exist_ok=True)
    print(f"[START] rustfs: {rustfs_bin} (data: {data_dir})", flush=True)
    env = dict(CHILD_ENV)
    env['RUSTFS_ACCESS_KEY'] = CHILD_ENV.get('OSS_ACCESS_KEY', 'intelligent_audio_test')
    env['RUSTFS_SECRET_KEY'] = CHILD_ENV.get('OSS_SECRET_KEY', 'intelligent_audio_test666')
    env['RUSTFS_ADDRESS'] = f':{RUSTFS_PORT}'
    env['RUSTFS_CONSOLE_ADDRESS'] = f':{RUSTFS_CONSOLE_PORT}'
    env['RUSTFS_CONSOLE_ENABLE'] = 'true'
    proc = subprocess.Popen(
        [rustfs_bin, data_dir],
        cwd=os.path.dirname(rustfs_bin) or None,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=0,
    )
    t = threading.Thread(target=_stream, args=(proc, 'rustfs'), daemon=True)
    t.start()
    processes.append({'name': 'rustfs', 'proc': proc, 'thread': t})
    _wait_port('localhost', RUSTFS_PORT, 'rustfs')


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


def check_oss_connectivity():
    """启动时 OSS 连通性自检（INT-84）：一次性探测 S3 API 可达性。

    成功记一条 INFO；失败仅记一条 WARNING（含 endpoint 与排查提示），
    不阻塞启动 —— 各服务运行期按 STORAGE_FALLBACK_ENABLED 自动降级本地。
    """
    endpoint = CHILD_ENV.get('OSS_ENDPOINT') or 'http://localhost:9000'
    bucket = CHILD_ENV.get('OSS_BUCKET_NAME') or 'audios'
    try:
        from shared.clients.oss_client import OSSClient
        ok, reason = OSSClient().check_connectivity()
    except Exception as e:
        ok, reason = False, str(e)
    if ok:
        print(f"[OK] OSS connectivity check passed ({endpoint}, bucket={bucket})", flush=True)
    else:
        print(f"[WARN] OSS 连通性自检失败 endpoint={endpoint}: {reason}", flush=True)
        print("[WARN] 请核对 .env 的 OSS_ACCESS_KEY/OSS_SECRET_KEY 与 rustfs/S3 容器"
              "环境变量是否一致、endpoint 地址是否正确；未开启 STORAGE_FALLBACK_ENABLED"
              " 时将直接影响文件读写", flush=True)


def start_mock_services():
    """可选启动 mock 替身服务（MOCK_SERVICES_ENABLED=true，INT-137）。

    mock 服务独立可运行（脚本内自带 CLI/配置加载），此处仅负责拉起与就绪探测；
    端口取 service_ports 注册值，不进生产编排。
    """
    if not MOCK_SERVICES_ENABLED:
        return
    for svc in mock_services:
        if _is_port_open('localhost', svc['port']):
            print(f"[INFO] {svc['name']} already running on :{svc['port']}", flush=True)
            continue
        print(f"[START] {svc['name']} on port {svc['port']}...", flush=True)
        proc = subprocess.Popen(
            [sys.executable, svc['script'], '--port', str(svc['port'])],
            cwd=BASE_DIR,
            env=CHILD_ENV,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=0,
        )
        t = threading.Thread(target=_stream, args=(proc, svc['name']), daemon=True)
        t.start()
        processes.append({'name': svc['name'], 'proc': proc, 'thread': t})
        _wait_port('localhost', svc['port'], svc['name'])


def start_all():
    cleanup_occupied_ports()
    start_redis()
    start_postgres()
    start_rustfs()
    check_oss_connectivity()
    for svc in services:
        start_service(svc)
    start_mock_services()
    start_frontend()
    print(f"\n[OK] Started {len(processes)} processes (3 infra + 11 backend"
          f"{' + ' + str(len(mock_services)) + ' mock' if MOCK_SERVICES_ENABLED else ''}"
          f" + 1 frontend).", flush=True)
    print(f"[INFO] Frontend:            http://localhost:{FRONTEND_DEV_PORT}", flush=True)
    print(f"[INFO] API Gateway:        http://localhost:{API_GATEWAY_PORT}", flush=True)
    print(f"[INFO] Task Service:       http://localhost:{TASK_SERVICE_HTTP_PORT}", flush=True)
    print(f"[INFO] E2E Test Service:   http://localhost:{E2E_TEST_HTTP_PORT}", flush=True)
    print(f"[INFO] API Test Service:   http://localhost:{API_TEST_HTTP_PORT}", flush=True)
    print(f"[INFO] Evaluation Service: http://localhost:{EVALUATION_SERVICE_HTTP_PORT}", flush=True)
    print(f"[INFO] Report Service:     http://localhost:{REPORT_SERVICE_HTTP_PORT}", flush=True)
    print(f"[INFO] Algorithm Service:  http://localhost:{ALGORITHM_SERVICE_HTTP_PORT}", flush=True)
    print(f"[INFO] Auth Service:       http://localhost:{AUTH_SERVICE_HTTP_PORT}", flush=True)
    print(f"[INFO] Audio Service:      gRPC :{AUDIO_SERVICE_GRPC_PORT}", flush=True)
    print(f"[INFO] Device Service:     gRPC :{DEVICE_SERVICE_GRPC_PORT}", flush=True)
    print(f"[INFO] RustFS Console:     http://localhost:{RUSTFS_CONSOLE_PORT}", flush=True)
    if MOCK_SERVICES_ENABLED:
        print(f"[INFO] Mock ThirdPartyEval: http://localhost:{MOCK_THIRD_PARTY_EVAL_HTTP_PORT}"
              f" (/health, /__control)", flush=True)
        print(f"[INFO] Mock Realtime API:   ws://localhost:{MOCK_REALTIME_API_WS_PORT}", flush=True)
        print(f"[INFO] Mock EvalServerJudge: http://localhost:{MOCK_EVAL_SERVER_HTTP_PORT}"
              f" (/health, /__control)", flush=True)
    print("[INFO] Ctrl+C to stop all.", flush=True)


def _apply_test_db_override():
    """INT-246：--test-db 把整栈 DATABASE_URL 切到隔离测试库（幂等）。

    共享业务库只允许负责人手动操作与冒烟只读探测；实机链路回归 / 集成
    冒烟 / 验收一律 --test-db 起栈，冒烟后 scripts/reset_test_db.py 清库。
    凭据/主机取自当前 DATABASE_URL（.env），仅替换库名；隔离库不存在时
    自动创建（连接 postgres 管理库，幂等）。
    """
    from urllib.parse import urlsplit, urlunsplit
    from shared.constants.database import (
        ISOLATED_TEST_DB_NAME, database_name_of,
    )

    current = CHILD_ENV.get('DATABASE_URL', '')
    if database_name_of(current) == ISOLATED_TEST_DB_NAME:
        print("[TEST-DB] DATABASE_URL 已指向隔离测试库，无需切换。", flush=True)
        return

    parts = urlsplit(current)
    if not parts.scheme.startswith('postgres'):
        raise SystemExit(
            "[TEST-DB] 当前 DATABASE_URL 非 Postgres（无法安全推导隔离库连接串），"
            "请检查 .env。")
    isolated_url = urlunsplit((parts.scheme, parts.netloc, '/' + ISOLATED_TEST_DB_NAME, '', ''))
    admin_url = urlunsplit((parts.scheme, parts.netloc, '/postgres', '', ''))

    import psycopg2
    from psycopg2 import sql
    conn = psycopg2.connect(admin_url, connect_timeout=5)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL('CREATE DATABASE {}').format(sql.Identifier(ISOLATED_TEST_DB_NAME)))
            print(f"[TEST-DB] 已创建隔离测试库 {ISOLATED_TEST_DB_NAME}。", flush=True)
    except psycopg2.errors.DuplicateDatabase:
        print(f"[TEST-DB] 隔离测试库 {ISOLATED_TEST_DB_NAME} 已存在。", flush=True)
    finally:
        conn.close()

    CHILD_ENV['DATABASE_URL'] = isolated_url
    print(f"[TEST-DB] 整栈已切隔离测试库：{ISOLATED_TEST_DB_NAME}"
          "（共享业务库本栈不可见；冒烟后请运行 scripts/reset_test_db.py 清库）",
          flush=True)


def _assert_not_shared_db(allow_shared_db: bool = False):
    """INT-453：拒绝无 --test-db / --allow-shared-db 直连共享业务库（INT-246 同语义守卫）。

    run_all 只面向本地调试与验收；共享业务库（intelligent_audio_test）只允许
    负责人手动操作与冒烟只读探测，实机链路回归 / 集成冒烟 / 验收一律
    --test-db 起栈（流水线约定）。生效 DATABASE_URL 指向共享业务库且未显式
    --test-db / --allow-shared-db 时，启动即 RuntimeError、零进程零写入——
    与 tests/conftest.py 的 pytest 会话守卫同语义；隔离测试库
    （intelligent_audio_test_test）与非 Postgres URL（如 sqlite）均不受影响。

    INT-1190：真实库栈（常驻、连主库 intelligent_audio_test）是唯一被授权的
    例外——必须显式 --allow-shared-db（默认仍拒绝），由 real_stack.py 启动器
    使用；普通 run 不得直连共享业务库。
    """
    from shared.constants.database import (
        SHARED_BUSINESS_DB_NAME, ISOLATED_TEST_DB_NAME, database_name_of,
    )
    effective = database_name_of(CHILD_ENV.get('DATABASE_URL', ''))
    if effective == SHARED_BUSINESS_DB_NAME and not allow_shared_db:
        raise RuntimeError(
            "INT-453 启动守卫：当前 DATABASE_URL 指向共享业务库 "
            f"'{effective}' 且未显式 --test-db / --allow-shared-db，拒绝启动（零进程零写入）。"
            "共享业务库只允许负责人手动操作、冒烟只读探测与真实库栈"
            "（--allow-shared-db，INT-1190）；请带 --test-db"
            f" 起栈（自动切隔离测试库 {ISOLATED_TEST_DB_NAME}），"
            "或确认 DATABASE_URL 指向隔离库。")
    if effective == SHARED_BUSINESS_DB_NAME:
        print(
            f"[GUARD] INT-453 守卫已显式放行直连共享业务库 '{effective}'"
            "（--allow-shared-db，INT-1190 真实库栈专用；仅走查/设计/页面实测）。",
            flush=True)


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
    import argparse
    parser = argparse.ArgumentParser(description='一键启动所有微服务（FastAPI + DDD 版）')
    parser.add_argument(
        '--test-db', action='store_true',
        help='整栈切到隔离测试库（INT-246）：实机链路回归/集成冒烟/验收专用，'
             '共享业务库本栈不可见；冒烟后用 scripts/reset_test_db.py 清库')
    parser.add_argument(
        '--allow-shared-db', action='store_true',
        help='显式放行直连共享业务库（INT-1190 真实库栈专用，默认拒绝）：'
             '仅走查/设计/页面实测常驻真实库栈用；普通 run 不得使用')
    args = parser.parse_args()
    if args.test_db:
        _apply_test_db_override()
    _assert_not_shared_db(allow_shared_db=args.allow_shared_db)
    try:
        start_all()
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[INFO] Stopping all services...", flush=True)
        stop_all()
