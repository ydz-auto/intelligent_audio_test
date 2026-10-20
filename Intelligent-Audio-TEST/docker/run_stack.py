# -*- coding: utf-8 -*-
"""INT-272：全栈 Docker Compose 薄封装 —— agent 运行时唯一启动/停止入口。

根治口径（成员裁定）：服务生命周期归 Docker daemon，与一切 run 树解耦。
agent 运行时只做 `docker compose up/down` 与健康探测；禁止宿主机直起进程；
禁止启动期整树清场（遇宿主端口被占用，compose 报错退出，交执行者处置）。

用法（仓库根目录）：
    python docker/run_stack.py up        # 拉起全栈（infra + 引导 + 11 后端 + 前端）
    python docker/run_stack.py down      # 停止全栈（保留数据卷）
    python docker/run_stack.py down -v   # 停止全栈并删除数据卷（危险：清库）
    python docker/run_stack.py ps        # 容器状态
    python docker/run_stack.py health    # 13 端点健康探测（scripts/health_smoke.py 口径）
    python docker/run_stack.py logs [服务名] [-f]   # 跟踪日志

环境变量（读仓库根 .env，缺省值与宿主历史口径一致）：
    AUTH_MODE / VITE_AUTH_MODE  必填（off|dev|prod），compose 强制校验
    OSS_ACCESS_KEY / OSS_SECRET_KEY / JWT_SECRET / DEV_DEFAULT_*  可选
    POSTGRES_PORT / REDIS_PORT / RUSTFS_PORT / *_HTTP_PORT / *_GRPC_PORT  可选端口覆盖

安全边界：
    - 本脚本不 kill 任何进程、不清理任何端口；端口冲突由 compose 自行报错。
    - 本脚本自身可被 agent run 拉起：up 以 -d 分离模式执行，compose 客户端
      退出后容器由 daemon 托管，run 树收割不带走任何服务。
"""
import argparse
import os
import subprocess
import sys
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COMPOSE_FILE = os.path.join(BASE_DIR, 'docker', 'docker-compose.yml')

# 健康探测口径（与 scripts/health_smoke.py 一致）：10 个 HTTP /health
# + 前端 HTTP + 11 个 gRPC TCP + 3 个 infra TCP。api_test_service 不发布宿主
# 端口（UC-1001），探测在容器网络内经 compose exec 完成。
GRPC_PROBES = [
    # (服务名, 容器内端口)。宿主映射端口经 *_GRPC_PORT 环境变量覆盖（cmd_health 读取）；
    # api_test_service 宿主不发布端口（UC-1001），探测走 compose exec 容器内 TCP。
    ('e2e_test_service', 50051, 'E2E_TEST_GRPC_PORT'),
    ('audio_service', 50052, 'AUDIO_SERVICE_GRPC_PORT'),
    ('device_service', 50053, 'DEVICE_SERVICE_GRPC_PORT'),
    ('task_service', 51061, 'TASK_SERVICE_GRPC_PORT'),
    ('algorithm_service', 51067, 'ALGORITHM_SERVICE_GRPC_PORT'),
    ('report_service', 51068, 'REPORT_SERVICE_GRPC_PORT'),
    ('auth_service', 51069, 'AUTH_SERVICE_GRPC_PORT'),
    ('api_test_service', 51071, None),  # 容器网络内探测
    ('evaluation_service', 51091, 'EVALUATION_SERVICE_GRPC_PORT'),
    ('api_adapter_service', 51081, 'API_ADAPTER_SERVICE_GRPC_PORT'),
    ('transfer_agent', 51101, 'TRANSFER_AGENT_GRPC_PORT'),
]
HTTP_PROBES = [
    # (服务名, 容器内端口, 宿主端口环境变量)
    ('api_gateway', 5000, 'API_GATEWAY_PORT'),
    ('task_service', 5001, 'TASK_SERVICE_HTTP_PORT'),
    ('e2e_test_service', 5002, 'E2E_TEST_HTTP_PORT'),
    ('evaluation_service', 5004, 'EVALUATION_SERVICE_HTTP_PORT'),
    ('report_service', 5006, 'REPORT_SERVICE_HTTP_PORT'),
    ('algorithm_service', 5007, 'ALGORITHM_SERVICE_HTTP_PORT'),
    ('api_adapter_service', 5008, 'API_ADAPTER_SERVICE_HTTP_PORT'),
    ('auth_service', 5009, 'AUTH_SERVICE_HTTP_PORT'),
    ('transfer_agent', 5010, 'TRANSFER_AGENT_HTTP_PORT'),
]
FRONTEND_PORT = int(os.environ.get('FRONTEND_PORT', '5173'))
POSTGRES_PORT = int(os.environ.get('POSTGRES_PORT', '5432'))
REDIS_PORT = int(os.environ.get('REDIS_PORT', '6379'))
RUSTFS_PORT = int(os.environ.get('RUSTFS_PORT', '9000'))


def _load_env_file():
    """把仓库根 .env 读进当前进程环境（子进程 compose 继承）。

    只注入 compose 需要的键；宿主 DATABASE_URL 等指向 localhost 的键不覆盖
    （compose 内置值按容器网络服务名寻址，见 docker-compose.yml）。
    """
    env_file = os.path.join(BASE_DIR, '.env')
    if not os.path.isfile(env_file):
        return
    try:
        from dotenv import load_dotenv
        load_dotenv(env_file)
        return
    except ImportError:
        pass
    # python-dotenv 缺席时的最小实现
    with open(env_file, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, _, val = line.partition('=')
            os.environ.setdefault(key.strip(), val.strip())


def _compose(*args):
    """执行 docker compose 子命令（继承当前环境；透传退出码）。"""
    cmd = ['docker', 'compose', '-f', COMPOSE_FILE, *args]
    print(f"[STACK] {' '.join(cmd)}", flush=True)
    result = subprocess.run(cmd, cwd=BASE_DIR)
    return result.returncode


def _require_auth_mode():
    """AUTH_MODE / VITE_AUTH_MODE 必填校验（INT-181 口径，失败立即退出）。"""
    auth_mode = os.environ.get('AUTH_MODE', '').strip()
    vite_auth_mode = os.environ.get('VITE_AUTH_MODE', '').strip()
    if not auth_mode and not vite_auth_mode:
        print(
            "[STACK] ERROR: AUTH_MODE / VITE_AUTH_MODE 均未设置。\n"
            "        认证模式必须显式注入（off|dev|prod），禁止静默默认 off（INT-181）。\n"
            "        示例：AUTH_MODE=dev VITE_AUTH_MODE=dev python docker/run_stack.py up\n"
            "        取值含义见 docs/oauth.md。",
            flush=True)
        sys.exit(2)
    # AUTH_MODE 侧有值而 VITE_AUTH_MODE 缺失时以前者补齐（同一认证态，避免双变量错位）
    if auth_mode and not vite_auth_mode:
        os.environ['VITE_AUTH_MODE'] = auth_mode
    if vite_auth_mode and not auth_mode:
        os.environ['AUTH_MODE'] = vite_auth_mode


def cmd_up(args):
    """拉起全栈（分离模式）：容器生命周期归 Docker daemon。"""
    _require_auth_mode()
    rc = _compose('up', '-d', '--build') if args.build else _compose('up', '-d')
    if rc != 0:
        print("[STACK] compose up 失败。常见原因：宿主端口被占用"
              "（本工具不清理端口，请处置占用方后重试）。", flush=True)
        return rc
    print("[STACK] 全栈已交 Docker daemon 托管。健康探测：python docker/run_stack.py health",
          flush=True)
    return 0


def cmd_down(args):
    """停止全栈。-v 时连同数据卷删除（清库，需显式确认）。"""
    if args.volumes and not args.yes:
        print("[STACK] down -v 将删除 postgres/redis/rustfs 数据卷（不可恢复）。"
              "确认请加 --yes。", flush=True)
        return 2
    extra = ['-v'] if args.volumes else []
    return _compose('down', *extra)


def cmd_ps(args):
    """容器状态一览。"""
    return _compose('ps', '--all' if args.all else '--all')


def cmd_logs(args):
    """跟踪服务日志。"""
    extra = ['--tail', str(args.tail)]
    if args.follow:
        extra.append('--follow')
    return _compose('logs', *extra, *args.services)


def _tcp_open(host, port, timeout=2.0):
    import socket
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def cmd_health(args):
    """13+ 端点健康探测（INT-272 验收口径）。

    HTTP /health 走宿主映射端口（含版本标记校验）；gRPC/infra TCP 探测；
    api_test_service 宿主不发布端口，经 compose exec 在容器网络内探测。
    """
    # compose 端口映射取实际值（端口覆盖时口径同步）
    def host_port(svc_port_env, default):
        return int(os.environ.get(svc_port_env, default))

    checks = []  # (名称, 探测函数)
    for name, container_port, host_env in HTTP_PROBES:
        host_p = host_port(host_env, container_port)
        checks.append((f"{name} :{host_p}", lambda p=host_p: _http_health(p)))
    checks.append((f"frontend :{host_port('FRONTEND_PORT', FRONTEND_PORT)}",
                   lambda: _http_ok(host_port('FRONTEND_PORT', FRONTEND_PORT), '/')))
    for name, container_port, host_env in GRPC_PROBES:
        if host_env is None:
            # api_test_service：宿主不发布端口，容器网络内 exec 探测
            checks.append((f"{name} gRPC :{container_port}(容器内)",
                           lambda s=name, p=container_port: _compose_exec_tcp(s, p)))
        else:
            host_p = host_port(host_env, container_port)
            checks.append((f"{name} gRPC :{host_p}",
                           lambda p=host_p: _tcp_open('127.0.0.1', p)))
    checks.append((f"postgres :{host_port('POSTGRES_PORT', POSTGRES_PORT)}",
                   lambda: _tcp_open('127.0.0.1', host_port('POSTGRES_PORT', POSTGRES_PORT))))
    checks.append((f"redis :{host_port('REDIS_PORT', REDIS_PORT)}",
                   lambda: _tcp_open('127.0.0.1', host_port('REDIS_PORT', REDIS_PORT))))
    checks.append((f"rustfs :{host_port('RUSTFS_PORT', RUSTFS_PORT)}",
                   lambda: _tcp_open('127.0.0.1', host_port('RUSTFS_PORT', RUSTFS_PORT))))

    passed, failed = 0, []
    for name, probe in checks:
        ok = False
        try:
            ok = probe()
        except Exception:
            ok = False
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}", flush=True)
        if ok:
            passed += 1
        else:
            failed.append(name)

    total = len(checks)
    print(f"\n[HEALTH] {passed}/{total} PASS" + ("" if not failed else
          f"；FAIL: {', '.join(failed)}"), flush=True)
    return 0 if not failed else 1


def _http_ok(port, path='/', timeout=3.0):
    import urllib.request
    # trust_env 规避：urllib 读系统代理会劫持 localhost（INT-102 教训）
    proxy_handler = urllib.request.ProxyHandler({})
    opener = urllib.request.build_opener(proxy_handler)
    with opener.open(f'http://127.0.0.1:{port}{path}', timeout=timeout) as resp:
        return resp.status == 200


def _http_health(port, timeout=3.0):
    """HTTP /health 探测。

    api_gateway 的 /health 带 version 标记（区分同端口异版本，tests/api 同口径）；
    其余服务 /health 仅返回 status/service——任一服务 200 即视为健康。
    """
    import json
    import urllib.request
    proxy_handler = urllib.request.ProxyHandler({})
    opener = urllib.request.build_opener(proxy_handler)
    with opener.open(f'http://127.0.0.1:{port}/health', timeout=timeout) as resp:
        body = json.loads(resp.read().decode('utf-8'))
    if resp.status != 200:
        return False
    # version 字段存在时校验（仅 api_gateway 有），防误连同端口异版本进程
    if 'version' in body:
        return body.get('version') in ('V9.7.31', 'V9.7.10')
    return body.get('status') in ('ok', 'healthy')


def _compose_exec_tcp(service, port, timeout=5.0):
    """在容器网络内探测服务 TCP 端口（api_test_service 宿主不发布端口）。

    compose 栈未运行 / 服务未起时探测失败返回 False（不算异常崩溃）。
    exec 不经 build 插值——用 --no-interpolate 规避宿主未设 AUTH_MODE 等
    构建期变量时的插值报错（exec 本身只需要运行中的容器）。
    """
    result = subprocess.run(
        ['docker', 'compose', '-f', COMPOSE_FILE, 'exec', '-T', service,
         'python', '-c',
         f"import socket; s=socket.create_connection(('127.0.0.1',{port}),{timeout}); s.close()"],
        capture_output=True, timeout=timeout + 10,
        env={**os.environ, 'AUTH_MODE': os.environ.get('AUTH_MODE', 'off'),
             'VITE_AUTH_MODE': os.environ.get('VITE_AUTH_MODE', 'off')})
    return result.returncode == 0


def cmd_wait(args):
    """等待全栈健康（up 后验收探测用；超时非零退出）。"""
    deadline = time.time() + args.timeout
    while time.time() < deadline:
        rc = _compose('ps', '--format', 'json')
        # 逐项探测，全绿即返回
        if cmd_health(argparse.Namespace()) == 0:
            print("[STACK] 全栈健康。", flush=True)
            return 0
        time.sleep(args.interval)
    print("[STACK] 等待健康超时。排查：python docker/run_stack.py logs", flush=True)
    return 1


def main():
    parser = argparse.ArgumentParser(description='全栈 Docker Compose 薄封装（INT-272）')
    sub = parser.add_subparsers(dest='command', required=True)

    p_up = sub.add_parser('up', help='拉起全栈（分离模式，容器归 daemon 托管）')
    p_up.add_argument('--build', action='store_true', help='up 前重新构建镜像')
    p_up.set_defaults(func=cmd_up)

    p_down = sub.add_parser('down', help='停止全栈（保留数据卷）')
    p_down.add_argument('-v', '--volumes', action='store_true',
                        help='同时删除数据卷（清库）')
    p_down.add_argument('--yes', action='store_true', help='确认 -v 危险操作')
    p_down.set_defaults(func=cmd_down)

    p_ps = sub.add_parser('ps', help='容器状态')
    p_ps.add_argument('-a', '--all', action='store_true')
    p_ps.set_defaults(func=cmd_ps)

    p_logs = sub.add_parser('logs', help='服务日志')
    p_logs.add_argument('services', nargs='*', help='服务名（缺省全部）')
    p_logs.add_argument('-f', '--follow', action='store_true')
    p_logs.add_argument('--tail', type=int, default=100)
    p_logs.set_defaults(func=cmd_logs)

    p_health = sub.add_parser('health', help='13+ 端点健康探测')
    p_health.set_defaults(func=cmd_health)

    p_wait = sub.add_parser('wait', help='等待全栈健康')
    p_wait.add_argument('--timeout', type=int, default=300)
    p_wait.add_argument('--interval', type=int, default=5)
    p_wait.set_defaults(func=cmd_wait)

    args = parser.parse_args()
    _load_env_file()
    sys.exit(args.func(args))


if __name__ == '__main__':
    main()
