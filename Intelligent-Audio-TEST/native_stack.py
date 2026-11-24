# -*- coding: utf-8 -*-
"""V9.7.31 原生（无 Docker）后端全栈启动器。

背景：本机未安装 Docker，官方 stack.py 依赖 docker compose。本启动器按
real_stack.py 的成熟套路，用 uvicorn / gRPC 直接拉起 11 个后端服务，
并与 V9.7.10（占用 :5000 / :5173 / :5432）端口隔离：

    - 网关改到 :5700（其余 HTTP 服务保持 5001-5010 注册值）
    - 数据库用独立实例 D:\\00_env\\pgsql\\data_9731（:5433）
    - Redis :6379 / Minio(RustFS 兼容) :9000 均为本栈独占

安全红线（对齐 real_stack.py）：
    - 启动前逐端口探测，任一被占用即拒绝并退出，绝不 kill 占用者；
    - 必须经 WMI 脱离 agent 进程树启动（run 结束不回收）；
    - PID / 日志写 worktree 之外（D:\\00_env\\native_stack\\）。

用法：
    python native_stack.py start    # WMI 脱离启动 + 常驻监督
    python native_stack.py stop     # 停止整栈（按 launcher 进程树 kill）
    python native_stack.py status   # 端口 + 网关库名
    python native_stack.py verify   # /health 库名 + gRPC TCP 抽样
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

from shared.constants.database import database_name_of  # noqa: E402

BASE_DIR = PROJECT_ROOT
# PID / 日志根目录：默认 D:\00_env\native_stack\（可用 NATIVE_STACK_ROOT 覆盖）
STACK_ROOT = os.environ.get('NATIVE_STACK_ROOT') or r'D:\00_env\native_stack'
PID_FILE = os.path.join(STACK_ROOT, 'native_stack.pid')
LOG_DIR = os.path.join(STACK_ROOT, 'logs')

# name, dir, base_http_port(None=gRPC-only), base_grpc_port
# 网关 HTTP 5700 避开 V9.7.10 的 5000；其余端口与 service_ports.py 一致。
SERVICES = [
    ('api_gateway',        'api_gateway',        5700, None),
    ('task_service',       'task_service',       5001, 51061),
    ('e2e_test_service',   'e2e_test_service',   5002, 50051),
    ('api_test_service',   'api_test_service',   5003, 51071),
    ('evaluation_service', 'evaluation_service', 5004, 51091),
    ('report_service',     'report_service',     5006, 51068),
    ('algorithm_service',  'algorithm_service',  5007, 51067),
    ('auth_service',       'auth_service',       5009, 51069),
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
    'EVALUATION_SERVICE_GRPC_PORT': 51091,
    'TRANSFER_AGENT_GRPC_PORT': 51101,
}

GATEWAY_HTTP = 5700


def _base_env() -> dict:
    if load_dotenv is not None:
        load_dotenv(os.path.join(BASE_DIR, '.env'))
    env = os.environ.copy()
    env['PYTHONUTF8'] = '1'
    # 输出经 _tee 管道转发，必须关闭块缓冲，否则日志要攒满 8KB 才出现在窗口/文件里
    env['PYTHONUNBUFFERED'] = '1'
    # 服务发现：所有 *_HOST 指向本机；gRPC 端口取注册值（.env 已含，兜底补齐）
    for env_name, port in CLIENT_GRPC_ENVS.items():
        env[env_name] = str(port)
    for env_name in ('E2E_TEST_SERVICE_HOST', 'TASK_SERVICE_HOST',
                     'API_TEST_SERVICE_HOST', 'EVALUATION_SERVICE_HOST',
                     'AUDIO_SERVICE_HOST', 'DEVICE_SERVICE_HOST',
                     'ALGORITHM_SERVICE_HOST', 'REPORT_SERVICE_HOST',
                     'AUTH_SERVICE_HOST', 'TRANSFER_AGENT_SERVICE_HOST'):
        env[env_name] = '127.0.0.1'
    env.setdefault('API_TEST_SERVICE_PORT', '5003')
    env['LOG_ROOT_DIR'] = LOG_DIR
    # 认证：默认 off（与 .env 一致）；前端同值防错位
    env.setdefault('AUTH_MODE', 'off')
    env.setdefault('VITE_AUTH_MODE', env['AUTH_MODE'])
    proto_dir = os.path.join(BASE_DIR, 'shared', 'proto')
    env['PYTHONPATH'] = (BASE_DIR + os.pathsep + proto_dir + os.pathsep
                         + env.get('PYTHONPATH', ''))
    return env


def _service_cmd(name, svc_dir, http_port, grpc_port, env):
    if http_port is not None:
        env['PORT'] = str(http_port)
        if grpc_port:
            env['GRPC_PORT'] = str(grpc_port)
        cmd = [sys.executable, '-m', 'uvicorn', f'{svc_dir}.app:app',
               '--host', '0.0.0.0', '--port', str(http_port),
               '--workers', '1', '--log-level', 'info']
    else:
        env['GRPC_PORT'] = str(grpc_port)
        cmd = [sys.executable, '-c',
               'import logging; logging.basicConfig(level=logging.INFO); '
               f'from {svc_dir}.interfaces.grpc.server import start_grpc_server; '
               f's = start_grpc_server({grpc_port}); s.wait_for_termination()']
        if name == 'audio_service':
            shim = os.path.join(BASE_DIR, 'tests', 'fixtures', 'pyaudio_shim')
            env['PYTHONPATH'] = shim + os.pathsep + env['PYTHONPATH']
    env['SERVICE_NAME'] = name
    env['SERVICE_HOST'] = '127.0.0.1'
    return cmd


def _port_busy(host, port) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.6)
        return s.connect_ex((host, port)) == 0


def required_ports() -> list:
    ports = [p for _, _, _, p in SERVICES if p] + [GATEWAY_HTTP]
    ports += [p for _, _, p, _ in SERVICES if p]
    return sorted(set(ports))


def _refuse_if_busy():
    busy = [p for p in required_ports() if _port_busy('127.0.0.1', p)]
    if busy:
        raise SystemExit(
            f'[NATIVE-STACK] 拒绝启动：端口被占用 {busy}（本启动器绝不 kill 占用进程）')


def _roll_log(fh, log_path, day):
    """按天归档：把 <name>.log 改名为 <name>.log.YYYY-MM-DD，返回新句柄。"""
    fh.close()
    target = f'{log_path}.{day}'
    try:
        if os.path.exists(target):
            # 当天已有归档（进程当天重启过），合并而不是覆盖
            with open(target, 'ab') as dst, open(log_path, 'rb') as src:
                dst.write(src.read())
            os.remove(log_path)
        else:
            os.replace(log_path, target)
    except OSError:
        pass
    return open(log_path, 'ab', buffering=0)


def _tee(log_path, cmd):
    """窗口直显 + 落盘：读子进程输出，原样打到本控制台并追加到 log_path（按天分文件）。"""
    import ctypes
    import time
    try:
        ctypes.windll.kernel32.SetConsoleTitleW(
            'IAT ' + os.path.splitext(os.path.basename(log_path))[0])
    except Exception:
        pass
    os.makedirs(os.path.dirname(os.path.abspath(log_path)), exist_ok=True)
    day = time.strftime('%Y-%m-%d')
    fh = open(log_path, 'ab', buffering=0)
    proc = subprocess.Popen(cmd, cwd=BASE_DIR, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, bufsize=0)
    for line in iter(proc.stdout.readline, b''):
        today = time.strftime('%Y-%m-%d')
        if today != day:
            fh = _roll_log(fh, log_path, day)
            day = today
        fh.write(line)
        sys.stdout.buffer.write(line)
        sys.stdout.buffer.flush()
    fh.close()
    return proc.wait()


def _spawn(name, cmd, env, log):
    log.write(f'\n[START] {name}: {" ".join(cmd[:6])}...\n'.encode())
    log.flush()
    # 每个服务独占一个可见控制台窗口（标题 IAT <name>），由 _tee 把输出
    # 同时打到窗口和 LOG_DIR/<name>.log，窗口不再是空白也不丢文件记录。
    python = sys.executable
    if os.path.basename(python).lower() == 'pythonw.exe':
        python = os.path.join(os.path.dirname(python), 'python.exe')
    return (name, subprocess.Popen(
        [python, '-u', os.path.abspath(__file__), '_tee',
         os.path.join(LOG_DIR, f'{name}.log'), '--'] + cmd,
        cwd=BASE_DIR, env=env, creationflags=subprocess.CREATE_NEW_CONSOLE))


def start():
    _refuse_if_busy()
    os.makedirs(LOG_DIR, exist_ok=True)
    base_env = _base_env()
    log = open(os.path.join(LOG_DIR, 'native_stack.log'), 'ab')
    procs = []
    for name, svc_dir, http_port, grpc_port in SERVICES:
        env = dict(base_env)
        cmd = _service_cmd(name, svc_dir, http_port, grpc_port, env)
        procs.append(_spawn(name, cmd, env, log))
    with open(PID_FILE, 'w', encoding='ascii') as fh:
        fh.write(str(os.getpid()))
    print(f'[NATIVE-STACK] 已启动 {len(procs)} 个后端服务（launcher pid {os.getpid()}），'
          f'网关 :{GATEWAY_HTTP}，日志 {LOG_DIR}', flush=True)

    try:
        wait_ready()
        print('[NATIVE-STACK] 监督中（stop: python native_stack.py stop）', flush=True)
        while True:
            time.sleep(3)
            for name, p in procs:
                if p.poll() is not None:
                    print(f'[NATIVE-STACK] {name} 已退出（code {p.poll()}），停止整栈', flush=True)
                    return stop()
    except KeyboardInterrupt:
        stop()


def wait_ready(timeout: int = 120):
    import urllib.request
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(f'http://127.0.0.1:{GATEWAY_HTTP}/health', timeout=2) as resp:
                if resp.status == 200:
                    body = __import__('json').loads(resp.read().decode('utf-8'))
                    print(f"[NATIVE-STACK] 网关就绪：database={body.get('database')}",
                          flush=True)
                    return True
        except Exception:
            pass
        time.sleep(2)
    print('[NATIVE-STACK][WARN] 网关就绪探测超时（详见日志 native_stack.log）', flush=True)
    return False


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
        print(f'[NATIVE-STACK] 已停止（launcher pid {pid} 进程树）')
    else:
        print('[NATIVE-STACK] 无 PID 记录，未停止任何进程')


def status():
    up = [f'{p}:{"OPEN" if _port_busy("127.0.0.1", p) else "closed"}'
          for p in required_ports()]
    db = '?'
    try:
        import urllib.request
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(f'http://127.0.0.1:{GATEWAY_HTTP}/health', timeout=2) as resp:
            if resp.status == 200:
                db = __import__('json').loads(resp.read().decode('utf-8')).get('database', '?')
    except Exception:
        pass
    pid = open(PID_FILE, encoding='ascii').read().strip() if os.path.exists(PID_FILE) else 'none'
    print(f'[NATIVE-STACK] pid={pid} | gw-db={db}')
    print('  ' + ' '.join(up))


def verify():
    import urllib.request
    import json as _json
    print(f'[NATIVE-STACK] 核验 网关 :{GATEWAY_HTTP} ...')
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(f'http://127.0.0.1:{GATEWAY_HTTP}/health', timeout=5) as resp:
        body = _json.loads(resp.read().decode('utf-8'))
    print(f"  database={body.get('database')}（期望 intelligent_audio_test）")
    for name, port in (('task_service', 51061), ('algorithm_service', 51067),
                       ('evaluation_service', 51091), ('api_test_service', 51071)):
        print(f'  gRPC {name} :{port} open: {_port_busy("127.0.0.1", port)}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='V9.7.31 原生后端全栈启动器')
    # _tee 为内部用法：由 _spawn 在独立窗口里拉起，把服务输出同时打到窗口与日志文件。
    parser.add_argument('action',
                        choices=['start', 'stop', 'status', 'verify', '_tee'])
    parser.add_argument('rest', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    # argparse 只会吞掉出现在选项位置的那个 '--'，这里统一剔除分隔符
    rest = [a for a in args.rest if a != '--']
    if args.action == '_tee':
        sys.exit(_tee(rest[0], rest[1:]))
    elif args.action == 'start':
        start()
    elif args.action == 'stop':
        stop()
    elif args.action == 'verify':
        verify()
    else:
        status()
