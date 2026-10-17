# -*- coding: utf-8 -*-
"""UI 专用并行隔离栈（INT-260）：端口整体偏移，隔离库 intelligent_audio_test_test。

背景：共享栈常被其它在途 run 占用（INT-261 UX 走查等），不可重启切换
--test-db；本启动器以全偏移端口并行起一套栈，DATABASE_URL 直指隔离库，
与共享栈互不干扰（端口/Redis DB/日志根全隔离）。

并发换段（INT-581）：同一端口段只能由一个栈占用（启动前逐端口探测，被占
即拒绝，绝不 kill 占用者）。并发 run（如 INT-569 前端回归日巡与功能卡验收
同时实测）经 --shift 显式换到空闲段，前端随段偏移（5273+shift）无需单独
指定；默认 shift=1000（网关 6000 / HTTP 6001-6010 / 前端 6273），向后兼容。
非默认段 PID/日志按 shift 分目录（_ui_stack<shift>.pid / logs/ui_stack/
shift<shift>），stop/status 需传相同 --shift（status 无参按 PID 文件记录段）。

端口表（shift=+1000）：网关 6000，HTTP 服务 6001-6010，gRPC 偏移后段，
前端 vite 6273（VITE_API_TARGET=http://127.0.0.1:6000）。

安全红线：
- 启动前逐端口探测，任一被占用即拒绝并退出，绝不 kill 占用者
  （run_all.py 的 cleanup_occupied_ports 行为在此禁止复刻）；
- DATABASE_URL 强制指向隔离库，启动后 /health database 字段复核。

用法（建议经 run_gate.py 以 WMI 脱离 agent 进程树启动；start 常驻监督）：
    python tests/ui/utils/parallel_stack.py start                           # 默认段（网关 6000/前端 6273）
    python tests/ui/utils/parallel_stack.py start --shift 2000              # 换段（网关 7000/前端 7273）
    python tests/ui/utils/parallel_stack.py start --shift 5000 --frontend-port 8273  # 显式前端（INT-553 变体）
    python tests/ui/utils/parallel_stack.py stop --shift 2000               # 停指定段（不带参数停默认段）
    python tests/ui/utils/parallel_stack.py status                          # 按 PID 文件记录段探测
    # 等价环境变量：UI_STACK_SHIFT / UI_STACK_FRONTEND_PORT（CLI 参数优先级更高）
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

# 端口偏移可配置（UI_STACK_SHIFT，默认 1000）：6000 段被并发 run 占用且其
# audio_service 带 INT-95 影子夹具（无法真机放音）时，可用 2000 起 7000 段
# 独立栈（真实音频驱动）互不干扰。PID/日志按偏移隔离，避免串栈清理。
# INT-401 验收：端口段可经 UI_STACK_SHIFT 覆盖（默认 1000 行为不变），
# 供并发多 run 共享 6000 段时错峰起本 run 独立栈（纪律 3：不复用别 run 的栈）。
# INT-528 验收：前端 vite 端口可经 UI_STACK_FRONTEND_PORT 覆盖（默认 6273）。
# INT-581：并发 run 经 --shift / --frontend-port 显式换段，configure() 按
# CLI > env > 默认 解析并重算派生项（服务 HTTP/gRPC/网关随偏移，前端默认
# 5273+shift）；非默认段 PID/日志按 shift 分目录，stop/status 各管各段。
SHIFT = int(os.environ.get('UI_STACK_SHIFT', '1000'))
_suffix = '' if SHIFT == 1000 else f'_{SHIFT}'

# INT-1195：显式放行连主库（生产副本 intelligent_audio_test）的验证场景。
# 默认仍强制隔离测试库（pytest / 冒烟用，INT-246 红线）；仅当显式设置
# UI_STACK_DATABASE_NAME 时才覆盖库名，用于「开认证验证真实库用户」类解阻卡，
# 用法：UI_STACK_DATABASE_NAME=intelligent_audio_test python .../parallel_stack.py start
DB_NAME = os.environ.get('UI_STACK_DATABASE_NAME', ISOLATED_TEST_DB_NAME)

GATEWAY_HTTP = 5000 + SHIFT
FRONTEND_PORT = int(os.environ.get('UI_STACK_FRONTEND_PORT', str(GATEWAY_HTTP + 273)))

PID_FILE = os.path.join(BASE_DIR, 'tests', 'ui', f'_ui_stack{_suffix}.pid')
LOG_DIR = os.path.join(BASE_DIR, 'logs', f'ui_stack{_suffix}')


def _env_int(key: str, default: int) -> int:
    """读环境变量整数；缺失/非法回退 default（并发 run 兼容 UI_STACK_* 历史口径）。"""
    raw = os.environ.get(key)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        print(f'[UI-STACK][WARN] {key}={raw!r} 非整数，使用默认 {default}', flush=True)
        return default


def configure(shift: int | None = None, frontend_port: int | None = None) -> None:
    """按显式参数配置端口段（并发 run 换段，避免争用）。

    优先级：CLI 参数 > UI_STACK_SHIFT / UI_STACK_FRONTEND_PORT 环境变量 > 默认。
    - shift 默认 1000（网关 6000 / 前端 6273，向后兼容）；前端默认随段偏移
      （5273+shift → 6273），显式 frontend_port 覆盖时以显式值为准。
    - 非默认段 PID/日志按 shift 分目录（_ui_stack<shift>.pid / logs/ui_stack/
      shift<shift>），并发多栈互不踩——stop 只停本段 launcher 进程树。
    """
    global SHIFT, GATEWAY_HTTP, FRONTEND_PORT, PID_FILE, LOG_DIR
    SHIFT = shift if shift is not None else _env_int('UI_STACK_SHIFT', 1000)
    fe = frontend_port if frontend_port is not None else _env_int('UI_STACK_FRONTEND_PORT', 0)
    GATEWAY_HTTP = 5000 + SHIFT
    FRONTEND_PORT = fe if fe else 5273 + SHIFT
    if SHIFT == 1000:
        PID_FILE = os.path.join(BASE_DIR, 'tests', 'ui', '_ui_stack.pid')
        LOG_DIR = os.path.join(BASE_DIR, 'logs', 'ui_stack')
    else:
        PID_FILE = os.path.join(BASE_DIR, 'tests', 'ui', f'_ui_stack{SHIFT}.pid')
        LOG_DIR = os.path.join(BASE_DIR, 'logs', 'ui_stack', f'shift{SHIFT}')


def _read_pid_cfg(path: str | None = None) -> dict:
    """读 PID 文件记录的 (pid, shift, frontend)；解析失败返回 {}。

    PID 文件首行为 launcher pid（历史兼容），次行起 shift=/frontend= 键值
    （INT-581 起写）；status 无参时据此探测对应端口段。
    """
    cfg: dict = {}
    path = path or PID_FILE
    if not os.path.exists(path):
        return cfg
    try:
        with open(path, encoding='ascii') as fh:
            first = True
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                if first:
                    if line.lstrip('-').isdigit():
                        cfg['pid'] = int(line)
                    first = False
                    continue
                k, _, v = line.partition('=')
                if k in ('shift', 'frontend') and v.lstrip('-').isdigit():
                    cfg[k] = int(v)
    except Exception:
        return {}
    return cfg

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

# INT-363：门禁默认认证模式。dev=本地 OAuth（表单登录），进程 env 是 vite
# env 优先级最高层，显式注入使 served VITE_AUTH_MODE 不再随
# frontend/.env.development（=off）与 .env.local（=dev）的文件级优先级
# 冲突漂移；前后端必须同值（AUTH_MODE/VITE_AUTH_MODE），否则路由守卫
# 弹登录页而后端不放 token（AuthModeMismatchBanner 会提示错位）。
AUTH_MODE = os.environ.get('UI_GATE_AUTH_MODE', 'dev')


def _shift(base: int) -> int:
    return base + SHIFT


def _base_env() -> dict:
    load_dotenv(os.path.join(BASE_DIR, '.env'))
    env = os.environ.copy()
    env['PYTHONUTF8'] = '1'
    env['AUTH_MODE'] = AUTH_MODE
    env['VITE_AUTH_MODE'] = AUTH_MODE
    # 库名：默认隔离库（强制）；UI_STACK_DATABASE_NAME 显式覆盖（INT-1195
    # 开认证验证真实库用户时指向主库）。从 .env DATABASE_URL 推导仅换库名
    parts = urlsplit(env.get('DATABASE_URL', ''))
    if not parts.scheme.startswith('postgres'):
        raise SystemExit('[UI-STACK] .env DATABASE_URL 非 Postgres，无法推导隔离库连接串')
    env['DATABASE_URL'] = urlunsplit(
        (parts.scheme, parts.netloc, '/' + DB_NAME, '', ''))
    # Redis 独立 DB index，避免与共享栈缓存互踩
    env['REDIS_URL'] = 'redis://localhost:6379/1'
    # 服务日志根随段偏移（logs/ui_stack/shift<shift>），并发多栈日志互不踩
    env['LOG_ROOT_DIR'] = (os.path.join('logs', 'ui_stack', f'shift{SHIFT}')
                           if SHIFT != 1000 else os.path.join('logs', 'ui_stack'))
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
        # 首行 launcher pid（stop 兼容旧单行文件）；次行起记录端口段供 status 无参探测
        fh.write(f'{os.getpid()}\nshift={SHIFT}\nfrontend={FRONTEND_PORT}\n')
    print(f'[UI-STACK] 已启动 {len(procs)} 个进程（launcher pid {os.getpid()}），'
          f'网关 :{GATEWAY_HTTP}，前端 :{FRONTEND_PORT}，日志 {LOG_DIR}', flush=True)

    try:
        wait_ready()
        stop_hint = '' if SHIFT == 1000 else f' --shift {SHIFT}'
        print(f'[UI-STACK] 监督中（stop: python tests/ui/utils/parallel_stack.py stop{stop_hint}）', flush=True)
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
                if body.get('database') != DB_NAME:
                    print('[UI-STACK][FATAL] 栈 database 字段非目标库，立即停止', flush=True)
                    return stop()
                _verify_auth_mode()
                return True
        except Exception:
            pass
        time.sleep(2)
    print(f'[UI-STACK][WARN] 网关就绪探测超时（详见 {LOG_DIR}/ui_stack.log）', flush=True)
    return False


def _verify_auth_mode():
    """INT-363：就绪后复核前后端认证模式一致（认证链路用例的前置条件自检）。

    后端读 /api/v1/auth/mode（网关 AUTH_MODE）；前端读 vite 模块图里
    实际注入的 served VITE_AUTH_MODE（与浏览器侧同源）。错位时守卫
    行为与登录跳转必然互相矛盾，在栈层显式 FAIL 而非留给 pytest 报
    模糊断言。
    """
    import httpx  # 懒加载：wait_ready 同款（模块级未导入，遗漏会 NameError 降级 WARN）

    try:
        r = httpx.get(f'http://127.0.0.1:{GATEWAY_HTTP}/api/v1/auth/mode',
                      timeout=3, trust_env=False)
        backend_mode = (r.json() or {}).get('auth_mode', '')
    except Exception as exc:
        print(f'[UI-STACK][WARN] auth mode 复核失败（后端不可达）: {exc}', flush=True)
        return
    served_mode = ''
    try:
        r = httpx.get(f'http://127.0.0.1:{FRONTEND_PORT}/src/domain/enums.ts',
                      timeout=5, trust_env=False)
        r.raise_for_status()
        for line in r.text.splitlines():
            if 'import.meta.env' in line and 'VITE_AUTH_MODE' in line:
                served_mode = line.split('"VITE_AUTH_MODE":')[1].split('"')[1]
                break
    except Exception as exc:
        print(f'[UI-STACK][WARN] served VITE_AUTH_MODE 读取失败: {exc}', flush=True)
        return
    if backend_mode != served_mode:
        raise SystemExit(
            f'[UI-STACK][FATAL] 前后端认证模式错位：后端 AUTH_MODE={backend_mode!r}，'
            f'served VITE_AUTH_MODE={served_mode!r}。门禁环境由本启动器统一注入 '
            f'AUTH_MODE/VITE_AUTH_MODE={AUTH_MODE!r}（进程 env 优先级最高，不受 '
            'frontend/.env* 文件漂移影响）；出现此报错说明注入被绕过，请排查。')
    print(f'[UI-STACK] 认证模式复核通过：两侧一致（{backend_mode!r}）', flush=True)


def stop():
    pid = _read_pid_cfg().get('pid')
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
    cfg = _read_pid_cfg()
    if not cfg:
        return 'pid-file=none'
    parts = [f"pid-file={cfg.get('pid', '?')}"]
    if 'shift' in cfg:
        parts.append(f'shift={cfg["shift"]}')
    if 'frontend' in cfg:
        parts.append(f'frontend={cfg["frontend"]}')
    return ' '.join(parts)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='UI 专用并行隔离栈（默认端口+1000：网关 6000/前端 6273，隔离库）；'
                    '并发 run 经 --shift 显式换段避免端口争用')
    parser.add_argument('action', choices=['start', 'stop', 'status'])
    parser.add_argument('--shift', type=int, default=None,
                        help='端口段偏移量（服务 HTTP/gRPC/网关随偏移，前端默认 5273+shift）；'
                             '默认 1000 向后兼容；优先级高于环境变量 UI_STACK_SHIFT')
    parser.add_argument('--frontend-port', type=int, default=None,
                        help='前端 vite 端口显式覆盖（默认随 shift 派生 5273+shift → 6273）；'
                             '优先级高于环境变量 UI_STACK_FRONTEND_PORT')
    args = parser.parse_args()

    if args.action == 'status':
        # status 无参时按 PID 文件记录的端口段探测（并发多栈各看各段）
        cfg = _read_pid_cfg()
        if args.shift is None and cfg.get('shift') is not None:
            args.shift = cfg['shift']
        if args.frontend_port is None and cfg.get('frontend') is not None:
            args.frontend_port = cfg['frontend']
    elif args.action == 'stop' and args.shift is None:
        # 无参 stop：默认段 PID 不存在时，若只剩一个偏移段则自动对准；多个则报错
        import glob as _glob
        candidates = _glob.glob(os.path.join(BASE_DIR, 'tests', 'ui', '_ui_stack*.pid'))
        if len(candidates) == 1:
            cfg = _read_pid_cfg(candidates[0])
            if cfg.get('shift') is not None:
                args.shift = cfg['shift']
        elif len(candidates) > 1:
            raise SystemExit('[UI-STACK] 多个端口段栈在跑，stop 请显式 --shift <段> 指定：'
                             + ', '.join(os.path.basename(p) for p in candidates))

    configure(args.shift, args.frontend_port)
    if args.action == 'start':
        start()
    elif args.action == 'stop':
        stop()
    else:
        status()
