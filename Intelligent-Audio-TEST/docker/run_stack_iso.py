# -*- coding: utf-8 -*-
"""INT-597（INT-993 当前基线重交付）：多栈并行测试隔离封装 —— 起/停一套与现役栈
完全隔离的 docker compose 测试栈。

背景：宿主形态并行栈（tests/ui/utils/parallel_stack.py，6000 段）硬编码共享隔离库
intelligent_audio_test_test（SHIFT 写死、DATABASE_URL 指向共享宿主 Postgres），
多 run 并发起栈必踩踏同一库（INT-138 验收被 INT-288 在跑 run 占用 6000 栈阻塞，
负责人 2026-10-17 拍板「咱们不是有docker嘛」→ 本封装落地 docker 化隔离）。

与 parallel_stack.py 的关系：
  - parallel_stack.py = 宿主进程 UI 栈（vite + uvicorn），适用于单 run 独占 6000
    段的浏览器实测；不提供多栈并行隔离（共享库/端口段均写死）。
  - 本封装 = docker 容器化隔离栈，每栈一个独立 compose project：
      · 独立 postgres 容器 + 独立数据卷（docker volume 库隔离，零共享踩踏）；
      · 独立端口段（HTTP/gRPC/infra 整体偏移，与一切现役栈不重叠）；
      · 独立 redis / rustfs / 日志卷；
      · db_bootstrap 自举（69 表 + 幂等迁移 + RBAC 种子 + admin 引导用户，
        经 base compose 的 service_completed_successfully 门控）；
      · DATABASE_URL 指向本栈 postgres 内的 intelligent_audio_test_test
        （POSTGRES_DB 覆盖，base compose 参数化），验收 gate 口径
        （/health database==隔离库名）原样满足。
  - 适用范围：API 级验收/冒烟（登录→任务→用例→报告）与数据隔离验证；浏览器 UI
    实测仍用 parallel_stack.py（容器形态 device_service 无法触达宿主 USB 实机，
    真机 E2E 段保留宿主栈例外）。

运行纪律（INT-459 复用）：测完必 stop（down），起栈前探测端口段（本封装自动
逐端口探测，任一被占用即拒绝，绝不 kill 占用者）。

用法（仓库根目录 Intelligent-Audio-TEST/）：
    python docker/run_stack_iso.py up --name <project> [--offset N] [--auth-mode dev] [--no-build]
    python docker/run_stack_iso.py health --name <project>     # 全部端点健康探测
    python docker/run_stack_iso.py smoke --name <project> [--audio-dir <样例目录>]
    python docker/run_stack_iso.py env --name <project>        # 验收用例所需环境变量
    python docker/run_stack_iso.py ps [--name <project>]
    python docker/run_stack_iso.py down --name <project> [-v|--volumes] [--yes]

项目名规则：^[a-z0-9][a-z0-9-]*$（docker compose project 约束）。
端口段：默认自动探测第一个全空段（offset 2000→14000，步长 500）；
--offset N 显式指定时所有宿主端口 = base+N（HTTP 5000-5010/8080、gRPC 50051-51069、
infra 5432/6379/9000/9001；api_test_service 宿主不发布端口，容器网络内探测）。
栈计划（project/offset/auth/db/端口）持久化在 logs/iso_stacks/<project>.json，
health/smoke/env/down 从该计划恢复参数（logs/ 为 gitignored 运行产物）。
"""
import argparse
import json
import os
import socket
import subprocess
import sys
import time

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COMPOSE_FILE = os.path.join(PROJECT_ROOT, 'docker', 'docker-compose.yml')
ISO_OVERRIDE = os.path.join(PROJECT_ROOT, 'docker', 'docker-compose.iso.yml')
PLAN_DIR = os.path.join(PROJECT_ROOT, 'logs', 'iso_stacks')

ISOLATED_TEST_DB_NAME = 'intelligent_audio_test_test'
POSTGRES_USER = 'intelligent_audio_test'
POSTGRES_PASSWORD = 'intelligent_audio_test666'

# base 端口（与 docker/docker-compose.yml 发布映射 / shared/config/service_ports.py 一致）
# 宿主可覆盖的 HTTP 端口环境变量 → base 端口
HTTP_PORTS = {
    'API_GATEWAY_PORT': 5000,
    'TASK_SERVICE_HTTP_PORT': 5001,
    'E2E_TEST_HTTP_PORT': 5002,
    'EVALUATION_SERVICE_HTTP_PORT': 5004,
    'REPORT_SERVICE_HTTP_PORT': 5006,
    'ALGORITHM_SERVICE_HTTP_PORT': 5007,
    'AUTH_SERVICE_HTTP_PORT': 5009,
    'FRONTEND_PORT': 8080,
}
# 宿主可覆盖的 gRPC 端口环境变量 → base 端口
GRPC_PORTS = {
    'E2E_TEST_GRPC_PORT': 50051,
    'AUDIO_SERVICE_GRPC_PORT': 50052,
    'DEVICE_SERVICE_GRPC_PORT': 50053,
    'TASK_SERVICE_GRPC_PORT': 50061,
    'ALGORITHM_SERVICE_GRPC_PORT': 50067,
    'REPORT_SERVICE_GRPC_PORT': 51068,
    'AUTH_SERVICE_GRPC_PORT': 51069,
    'EVALUATION_SERVICE_GRPC_PORT': 50091,
    'API_TEST_SERVICE_GRPC_PORT': 50071,  # api_test_service 宿主不发布端口（UC-1001）
}
# infra
INFRA_PORTS = {
    'POSTGRES_PORT': 5432,
    'REDIS_PORT': 6379,
    'RUSTFS_PORT': 9000,
    'RUSTFS_CONSOLE_PORT': 9001,
}
# api_test_service 宿主不发布端口，探测走 compose exec 容器内 TCP
API_TEST_CONTAINER_GRPC_PORT = 50071
# 最大 host base 端口（gRPC 51069），偏移上限保证 base+offset <= 65535
MAX_BASE_PORT = max([*HTTP_PORTS.values(), *GRPC_PORTS.values(), *INFRA_PORTS.values()])


def _validate_project(name: str):
    import re
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]*', name):
        sys.exit(f'[ISO-STACK] 非法项目名 {name!r}（须 ^[a-z0-9][a-z0-9-]*$）')


def _tcp_open(host: str, port: int, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _http_ok(port: int, path: str = '/', timeout: float = 3.0) -> bool:
    import urllib.request
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(f'http://127.0.0.1:{port}{path}', timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


def _http_health(port: int, timeout: float = 3.0) -> bool:
    """HTTP /health 探测：网关带 version 标记，其余服务仅 status 字段。"""
    import json as _json
    import urllib.request
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(f'http://127.0.0.1:{port}/health', timeout=timeout) as resp:
            body = _json.loads(resp.read().decode('utf-8'))
    except Exception:
        return False
    if resp.status != 200:
        return False
    if 'version' in body:
        return body.get('version') in ('V9.7.31', 'V9.7.10')
    return body.get('status') in ('ok', 'healthy')


def _required_host_ports(offset: int) -> list:
    ports = [b + offset for b in HTTP_PORTS.values()]
    ports += [b + offset for b in GRPC_PORTS.values()
              if b != 50071]  # api_test_service 宿主不发布端口
    ports += [b + offset for b in INFRA_PORTS.values()]
    return sorted(set(ports))


def _find_free_offset(start: int = 2000, step: int = 500, limit: int = 14000):
    """逐段探测全空端口段；全部必需端口空闲即返回，否则 None。

    start=2000：跳过宿主已约定端口段——offset 0（docker base 5000 段，int-472
    等现役栈）与 offset 1000（parallel_stack.py 宿主 6000 段，HTTP 6000-6273 /
    gRPC 51051-51101）。若从 1000 起测，6000 段宿主机未跑时会被误判为空段，
    起出的隔离栈即与 6000 段约定段冲突（INT-597 实测：隔离栈曾被起在 offset
    1000 占住 :6000）。2000 起测已高于 6000 段全端口上限。
    """
    for off in range(start, limit + 1, step):
        if off > 65535 - MAX_BASE_PORT:
            break
        busy = [p for p in _required_host_ports(off) if _tcp_open('127.0.0.1', p)]
        if not busy:
            return off
    return None


def _stack_env(project: str, offset: int, auth_mode: str, db: str) -> dict:
    env = dict(os.environ)
    env['PYTHONUTF8'] = '1'
    env['AUTH_MODE'] = auth_mode
    env['VITE_AUTH_MODE'] = auth_mode
    env['ISO_STACK_NAME'] = project
    env['POSTGRES_DB'] = db
    env['POSTGRES_USER'] = POSTGRES_USER
    env['POSTGRES_PASSWORD'] = POSTGRES_PASSWORD
    # 隔离栈为测试用途：api_test_service 单副本即可，减小资源占用
    env['API_TEST_REPLICAS'] = '1'
    for var, base in HTTP_PORTS.items():
        env[var] = str(base + offset)
    for var, base in GRPC_PORTS.items():
        env[var] = str(base + offset)
    for var, base in INFRA_PORTS.items():
        env[var] = str(base + offset)
    return env


def _compose(project: str, args: list, env: dict) -> int:
    cmd = ['docker', 'compose', '-p', project,
           '-f', COMPOSE_FILE, '-f', ISO_OVERRIDE] + args
    print(f'[ISO-STACK] {" ".join(cmd)}', flush=True)
    return subprocess.run(cmd, env=env).returncode


def _plan_path(project: str) -> str:
    return os.path.join(PLAN_DIR, f'{project}.json')


def _save_plan(project, offset, auth_mode, db, gateway_http, frontend, postgres):
    os.makedirs(PLAN_DIR, exist_ok=True)
    plan = {
        'project': project,
        'offset': offset,
        'auth_mode': auth_mode,
        'db': db,
        'gateway_http': gateway_http,
        'frontend': frontend,
        'postgres': postgres,
        'created_at': time.strftime('%Y-%m-%dT%H:%M:%S'),
    }
    with open(_plan_path(project), 'w', encoding='utf-8') as fh:
        json.dump(plan, fh, ensure_ascii=False, indent=1)


def _load_plan(project: str) -> dict:
    path = _plan_path(project)
    if not os.path.isfile(path):
        sys.exit(f'[ISO-STACK] 无 {project} 栈计划（先 python docker/run_stack_iso.py up --name {project}）')
    with open(path, encoding='utf-8') as fh:
        return json.load(fh)


def _remove_plan(project: str):
    try:
        os.remove(_plan_path(project))
    except OSError:
        pass


def _env_from_plan(plan: dict) -> dict:
    return _stack_env(plan['project'], plan['offset'], plan['auth_mode'], plan['db'])


def _compose_exec_tcp(project: str, service: str, port: int, env: dict, timeout: float = 8.0) -> bool:
    result = subprocess.run(
        ['docker', 'compose', '-p', project, '-f', COMPOSE_FILE, '-f', ISO_OVERRIDE,
         'exec', '-T', service, 'python', '-c',
         f"import socket; s=socket.create_connection(('127.0.0.1',{port}),{timeout}); s.close()"],
        capture_output=True, timeout=timeout + 10, env=env)
    return result.returncode == 0


def _project_containers(project: str) -> list:
    """该项目已有的容器名（含 stopped）。引擎异常时返回 []（调用方按全新起栈兜底）。"""
    r = subprocess.run(
        ['docker', 'ps', '-a', '--filter', f'label=com.docker.compose.project={project}',
         '--format', '{{.Names}}'],
        capture_output=True, text=True, timeout=60)
    if r.returncode != 0:
        return []
    return [n for n in r.stdout.splitlines() if n]


def _existing_offset(project: str) -> int:
    """从 api_gateway 容器宿主发布端口推导既有 offset（5000 宿主端口 - base 5000）。"""
    r = subprocess.run(
        ['docker', 'inspect', f'{project}-api_gateway-1',
         '--format', '{{(index (index .NetworkSettings.Ports "5000/tcp") 0).HostPort}}'],
        capture_output=True, text=True, timeout=60)
    try:
        return int(r.stdout.strip()) - 5000
    except Exception:
        sys.exit(f'[ISO-STACK] 无法从 {project}-api_gateway-1 推导既有 offset（{r.stdout.strip()!r}）')


def cmd_up(args):
    project = args.name
    _validate_project(project)
    existing = _project_containers(project)
    if existing:
        # 复用模式（INT-459 起栈前探测复用）：栈已在跑/已建容器，沿用其既有
        # 端口段（绝不自动漂移），跳过端口占用拒绝（本栈自己的端口本就占用）。
        offset = args.offset if args.offset is not None else _existing_offset(project)
        print(f'[ISO-STACK] 复用既有栈 {project}（{len(existing)} 容器），offset={offset}，'
              f'gateway=:{(5000 + offset)}', flush=True)
    else:
        offset = args.offset if args.offset is not None else _find_free_offset()
        if offset is None:
            sys.exit('[ISO-STACK] 无空闲端口段（2000-14000 全部被占），请 --offset 指定后人工确认')
        busy = [p for p in _required_host_ports(offset) if _tcp_open('127.0.0.1', p)]
        if busy:
            sys.exit(f'[ISO-STACK] 拒绝起栈：端口被占用 {busy}（INT-459 起栈前探测；绝不 kill 占用者）')
    env = _stack_env(project, offset, args.auth_mode, ISOLATED_TEST_DB_NAME)
    print(f'[ISO-STACK] 起栈计划 project={project} offset={offset} '
          f'gateway=:{5000 + offset} frontend=:{8080 + offset} '
          f'postgres=:{5432 + offset} db={ISOLATED_TEST_DB_NAME} auth={args.auth_mode}',
          flush=True)
    build_args = [] if args.no_build else ['--build']
    rc = _compose(project, ['up', '-d'] + build_args, env)
    if rc != 0:
        sys.exit('[ISO-STACK] compose up 失败（见上；端口冲突不清理、交执行者处置）')
    _save_plan(project, offset, args.auth_mode, ISOLATED_TEST_DB_NAME,
               5000 + offset, 8080 + offset, 5432 + offset)
    deadline = time.time() + args.wait
    while time.time() < deadline:
        if _health_check(project, env, quiet=True):
            print('[ISO-STACK] 全栈健康（网关 /health database='
                  f"{ISOLATED_TEST_DB_NAME}'）", flush=True)
            _print_acceptance_env(project, env)
            return 0
        time.sleep(args.interval)
    print('[ISO-STACK] 等待健康超时，最近探测如下：', flush=True)
    _health_check(project, env, quiet=False)
    return 1


def cmd_health(args):
    plan = _load_plan(args.name)
    env = _env_from_plan(plan)
    ok = _health_check(plan['project'], env, quiet=False)
    return 0 if ok else 1


def _health_check(project: str, env: dict, quiet: bool = False) -> bool:
    checks = []
    for var, base in HTTP_PORTS.items():
        if var == 'FRONTEND_PORT':
            continue
        host = int(env[var])
        checks.append((f'{var} :{host}', lambda p=host: _http_health(p)))
    checks.append((f'frontend :{int(env["FRONTEND_PORT"])}',
                   lambda p=int(env['FRONTEND_PORT']): _http_ok(p)))
    for var, base in GRPC_PORTS.items():
        if var == 'API_TEST_SERVICE_GRPC_PORT':
            continue
        host = int(env[var])
        checks.append((f'{var} :{host}', lambda p=host: _tcp_open('127.0.0.1', p)))
    checks.append((f'api_test gRPC :{API_TEST_CONTAINER_GRPC_PORT}(容器内)',
                   lambda: _compose_exec_tcp(project, 'api_test_service',
                                             API_TEST_CONTAINER_GRPC_PORT, env)))
    for var, base in INFRA_PORTS.items():
        host = int(env[var])
        checks.append((f'{var} :{host}', lambda p=host: _tcp_open('127.0.0.1', p)))
    passed, failed = 0, []
    for name, probe in checks:
        try:
            ok = probe()
        except Exception:
            ok = False
        if not quiet:
            print(f"  [{'PASS' if ok else 'FAIL'}] {name}", flush=True)
        if ok:
            passed += 1
        else:
            failed.append(name)
    if not quiet:
        print(f'[ISO-STACK] {passed}/{len(checks)} PASS'
              + ('' if not failed else f'；FAIL: {", ".join(failed)}'), flush=True)
    return not failed


def _print_acceptance_env(project: str, env: dict):
    gw = env['API_GATEWAY_PORT']
    pg = env['POSTGRES_PORT']
    db_url = (f'postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}'
              f'@127.0.0.1:{pg}/{ISOLATED_TEST_DB_NAME}')
    print('\n[ISO-STACK] 验收用例环境变量（直接注入/导出即可）：', flush=True)
    print(f'  API_BASE_URL=http://127.0.0.1:{gw}/api/v1', flush=True)
    print(f'  HEALTH_URL=http://127.0.0.1:{gw}/health', flush=True)
    print(f'  DATABASE_URL={db_url}', flush=True)
    print(f'  UI_API_BASE=http://127.0.0.1:{gw}', flush=True)
    print(f'  UI_FRONTEND_BASE=http://127.0.0.1:{env["FRONTEND_PORT"]}', flush=True)
    print(f'  AUTH_MODE={env["AUTH_MODE"]}  VITE_AUTH_MODE={env["VITE_AUTH_MODE"]}', flush=True)


def cmd_env(args):
    plan = _load_plan(args.name)
    env = _env_from_plan(plan)
    _print_acceptance_env(args.name, env)


def cmd_smoke(args):
    plan = _load_plan(args.name)
    env = _env_from_plan(plan)
    image = f"{plan['project']}-api_gateway:latest"
    network = f"{plan['project']}_default"
    smoke_script = os.path.join(PROJECT_ROOT, 'tools', 'iso_stack_smoke.py')
    if not os.path.isfile(smoke_script):
        sys.exit(f'[ISO-STACK] 缺冒烟脚本 {smoke_script}')
    audio_dir = args.audio_dir or os.path.join(PROJECT_ROOT, 'doc', 'voice_llm', '样例')
    if not os.path.isdir(audio_dir):
        sys.exit(f'[ISO-STACK] 样例音频目录不存在: {audio_dir}')
    # Windows 路径转 Docker 挂载可用形态（C:/...）
    def _win(p):
        return os.path.abspath(p).replace('\\', '/')
    cmd = [
        'docker', 'run', '--rm',
        f'--network={network}',
        f'-v{_win(smoke_script)}:/smoke.py:ro',
        f'-v{_win(audio_dir)}:/data:ro',
        '--entrypoint', 'python',
        image,
        '/smoke.py',
        '--api-base', 'http://api_gateway:5000/api/v1',
        '--health-url', 'http://api_gateway:5000/health',
        '--dut-url', 'http://mock_dut_api:5096',
        '--audio-dir', '/data',
    ]
    if args.username:
        cmd += ['--username', args.username]
    if args.password:
        cmd += ['--password', args.password]
    print(f'[ISO-STACK] 冒烟容器：{image} @ {network}', flush=True)
    rc = subprocess.run(cmd, env=env).returncode
    if rc != 0:
        print('[ISO-STACK] 冒烟失败（exit %d）' % rc, flush=True)
    return rc


def cmd_ps(args):
    plan = _load_plan(args.name)
    return _compose(args.name, ['ps'], _env_from_plan(plan))


def cmd_down(args):
    plan = _load_plan(args.name)
    if args.volumes and not args.yes:
        print('[ISO-STACK] down -v 将删除本栈 postgres/rustfs/redis 数据卷（不可恢复）。'
              '确认请加 --yes。', flush=True)
        return 2
    extra = ['-v'] if args.volumes else []
    rc = _compose(args.name, ['down'] + extra, _env_from_plan(plan))
    if rc == 0:
        _remove_plan(args.name)
        print(f'[ISO-STACK] 栈 {args.name} 已停止（INT-459：测完必 stop）', flush=True)
    return rc


def main():
    parser = argparse.ArgumentParser(description='多栈并行测试隔离 docker 封装（INT-597）')
    sub = parser.add_subparsers(dest='command', required=True)

    p_up = sub.add_parser('up', help='起一套隔离栈（默认自动探测空闲端口段并 --build）')
    p_up.add_argument('--name', required=True, help='compose project 名（^[a-z0-9][a-z0-9-]*$）')
    p_up.add_argument('--offset', type=int, default=None, help='端口段整体偏移（缺省自动探测）')
    p_up.add_argument('--auth-mode', default='dev', choices=['off', 'dev'],
                      help='认证模式（dev=表单登录，off=免认证）；缺省 dev')
    p_up.add_argument('--no-build', action='store_true',
                      help='复用已存在镜像（不构建；代码非当前分支时慎用）')
    p_up.add_argument('--wait', type=int, default=420, help='等健康超时秒数')
    p_up.add_argument('--interval', type=int, default=5)
    p_up.set_defaults(func=cmd_up)

    p_health = sub.add_parser('health', help='全栈端点健康探测')
    p_health.add_argument('--name', required=True)
    p_health.set_defaults(func=cmd_health)

    p_smoke = sub.add_parser('smoke', help='栈内跑验收冒烟（登录→用例→任务→报告，API 链）')
    p_smoke.add_argument('--name', required=True)
    p_smoke.add_argument('--audio-dir', default=None, help='样例音频目录（缺省仓库 doc/voice_llm/样例）')
    p_smoke.add_argument('--username', default='dev_user')
    p_smoke.add_argument('--password', default='dev_password')
    p_smoke.set_defaults(func=cmd_smoke)

    p_env = sub.add_parser('env', help='打印验收用例所需环境变量')
    p_env.add_argument('--name', required=True)
    p_env.set_defaults(func=cmd_env)

    p_ps = sub.add_parser('ps', help='容器状态')
    p_ps.add_argument('--name', required=True)
    p_ps.set_defaults(func=cmd_ps)

    p_down = sub.add_parser('down', help='停止并移除隔离栈（INT-459：测完必 stop）')
    p_down.add_argument('--name', required=True)
    p_down.add_argument('-v', '--volumes', action='store_true', help='同时删除数据卷（清库）')
    p_down.add_argument('--yes', action='store_true', help='确认 -v 危险操作')
    p_down.set_defaults(func=cmd_down)

    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == '__main__':
    sys.exit(main())
