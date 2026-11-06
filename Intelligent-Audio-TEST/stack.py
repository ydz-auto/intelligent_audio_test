#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""唯一启动入口：Docker 栈 + 宿主 audio/device 服务。

历史上有两套并存的启动链（stack_ctl.ps1 → run_all.py 宿主全栈；docker 时代又一套
run_stack.py + 三个 audio 启动 .cmd），端口/库地址多处手抄导致漂移（宿主
audio_service 曾连到测试库）。本入口统一为一条命令：

    python stack.py up                    # compose 起栈 + 宿主 device/audio
    python stack.py up --audio-mode shim  # Windows 音频栈楔死时用影子 pyaudio
    python stack.py status                # 容器 + 宿主服务状态
    python stack.py health                # HTTP /health + gRPC/基础设施 TCP 探测
    python stack.py down                  # 优雅停宿主服务 → compose down
    python stack.py restart host|audio|device|all
    python stack.py logs [服务名] [-f]    # 容器日志；audio/device 看宿主日志
    python stack.py build [服务名...]     # 构建镜像（委托 docker/build_stack.py）

端口口径不在本文件硬编码：compose 发布端口由 docker compose config 解析，
宿主服务环境见 scripts/host_services/control.py。
"""
from __future__ import annotations

import argparse
import socket
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO))

from scripts.host_services import control  # noqa: E402
from shared.constants.database import ISOLATED_TEST_DB_NAME  # noqa: E402

RUN_STACK = REPO / 'docker' / 'run_stack.py'
BUILD_STACK = REPO / 'docker' / 'build_stack.py'

# compose 容器内端口 → (服务名, 探测方式)
HTTP_PROBES = {
    5000: 'api_gateway', 5001: 'task_service', 5002: 'e2e_test_service',
    5004: 'evaluation_service', 5006: 'report_service', 5007: 'algorithm_service',
    5009: 'auth_service', 5010: 'transfer_agent',
}
TCP_PROBES = {
    50051: 'e2e_test_service', 51061: 'task_service', 51067: 'algorithm_service',
    51068: 'report_service', 51069: 'auth_service', 51091: 'evaluation_service',
    5432: 'postgres', 6379: 'redis', 9000: 'rustfs',
}
HOST_LOGS = {'audio': 'audio_service.log', 'audio_shim': 'audio_service_shim.log',
             'device': 'device_service.log'}


def _docker(args: list[str]) -> int:
    return subprocess.run([sys.executable, str(RUN_STACK), *args], cwd=str(REPO)).returncode


def _print(msg: str) -> None:
    print(msg, flush=True)


# ---------------------------------------------------------------- up / down

def cmd_up(args) -> int:
    if args.test_db:
        # 整栈切隔离测试库（pytest 实机链路/验收口径）：compose 用它拼各服务 DATABASE_URL
        os.environ['POSTGRES_DB'] = ISOLATED_TEST_DB_NAME
        _print(f'[stack] 整栈数据源 = {ISOLATED_TEST_DB_NAME}（隔离测试库）')
    if not args.no_docker:
        extra = ['--build'] if args.build else []
        rc = _docker(['up', *extra])
        if rc != 0:
            return rc
    if args.no_host:
        return 0
    ok, msg = control.start_device()
    _print(msg)
    if not ok:
        return 1
    ok, msg = control.start_audio(mode=args.audio_mode, check_timeout=args.check_timeout)
    _print(msg)
    return 0 if ok else 1


def cmd_down(args) -> int:
    rc = 0
    if not args.no_host:
        ok, msg = control.stop_audio()
        _print(msg)
        rc |= 0 if ok else 1
        ok, msg = control.stop_device()
        _print(msg)
        rc |= 0 if ok else 1
    if not args.no_docker:
        if args.volumes and not args.yes:
            _print('[abort] down -v 会删除 postgres/redis/rustfs 数据卷（不可恢复），'
                   '确认请加 --yes')
            return 2
        extra = ['--volumes'] if args.volumes else []
        if args.volumes:
            extra.append('--yes')
        rc |= _docker(['down', *extra])
    return rc


def cmd_restart(args) -> int:
    target = args.target
    if target in ('host', 'all', 'audio'):
        ok, msg = control.stop_audio()
        _print(msg)
        if not ok:
            return 1
    if target in ('host', 'all', 'device'):
        ok, msg = control.stop_device()
        _print(msg)
        if not ok:
            return 1
    if target == 'all':
        rc = _docker(['down'])
        if rc != 0:
            return rc
        return cmd_up(argparse.Namespace(
            no_docker=False, no_host=False, build=False, test_db=args.test_db,
            audio_mode=args.audio_mode, check_timeout=args.check_timeout))
    if target in ('host', 'all', 'device'):
        ok, msg = control.start_device()
        _print(msg)
        if not ok:
            return 1
    if target in ('host', 'all', 'audio'):
        ok, msg = control.start_audio(mode=args.audio_mode,
                                      check_timeout=args.check_timeout)
        _print(msg)
        if not ok:
            return 1
    return 0


# ---------------------------------------------------------------- status / health

def cmd_status(args) -> int:
    rc = _docker(['ps'])
    _print('\n宿主服务:')
    for name, port, pid in control.status():
        state = f'UP pid={pid}' if pid else 'DOWN'
        _print(f'  {name:<16} :{port}  {state}')
    return rc


def _http_health(port: int) -> bool:
    try:
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/health', timeout=3) as resp:
            return 200 <= resp.status < 300
    except (urllib.error.URLError, OSError, ValueError):
        return False


def _tcp_health(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(2)
        try:
            sock.connect(('127.0.0.1', port))
            return True
        except OSError:
            return False


def cmd_health(args) -> int:
    try:
        ports = control.published_ports()
    except RuntimeError as exc:
        _print(f'[fail] {exc}')
        return 1

    checks: list[tuple[str, int, bool]] = []
    for container_port, name in HTTP_PROBES.items():
        if container_port in ports:
            checks.append((name, ports[container_port], _http_health(ports[container_port])))
    for container_port, name in TCP_PROBES.items():
        if container_port in ports:
            checks.append((name, ports[container_port], _tcp_health(ports[container_port])))
    for name, port, _pid in control.status():
        checks.append((name, port, _tcp_health(port)))

    failed = 0
    for name, port, ok in checks:
        _print(f'  [{"PASS" if ok else "FAIL"}] {name:<20} :{port}')
        failed += 0 if ok else 1
    _print(f'\n{len(checks) - failed}/{len(checks)} PASS')
    return 0 if failed == 0 else 1


# ---------------------------------------------------------------- logs / build

def cmd_logs(args) -> int:
    if args.services and args.services[0] in HOST_LOGS:
        path = control.LOG_DIR / HOST_LOGS[args.services[0]]
        _print(f'# {path}')
        if not path.is_file():
            return 1
        tail = f'-Tail {args.tail}'
        follow = '-Wait' if args.follow else ''
        return subprocess.run(
            ['powershell', '-NoProfile', '-Command',
             f'Get-Content -Path "{path}" {tail} {follow}'],
            cwd=str(REPO)).returncode
    extra = ['--tail', str(args.tail)]
    if args.follow:
        extra.append('-f')
    return _docker(['logs', *extra, *args.services])


def cmd_build(args) -> int:
    return subprocess.run([sys.executable, str(BUILD_STACK), *args.services],
                          cwd=str(REPO)).returncode


# ---------------------------------------------------------------- CLI

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='唯一启动入口：Docker 栈 + 宿主 audio/device')
    sub = parser.add_subparsers(dest='command', required=True)

    p_up = sub.add_parser('up', help='起 Docker 栈 + 宿主服务')
    p_up.add_argument('--build', action='store_true', help='up 前重建镜像')
    p_up.add_argument('--no-docker', action='store_true', help='只起宿主服务')
    p_up.add_argument('--no-host', action='store_true', help='只起 Docker 栈')
    p_up.add_argument('--audio-mode', choices=('real', 'shim'), default='real',
                      help='real=真实声卡；shim=Windows 音频栈异常时的影子模块')
    p_up.add_argument('--test-db', action='store_true',
                      help='整栈切隔离测试库 intelligent_audio_test_test（pytest/验收）')
    p_up.add_argument('--check-timeout', type=float, default=60.0,
                      help='real 模式 pyaudio 自检超时秒数（超时即失败，不重试）')
    p_up.set_defaults(func=cmd_up)

    p_down = sub.add_parser('down', help='停宿主服务 + Docker 栈（保留数据卷）')
    p_down.add_argument('-v', '--volumes', action='store_true', help='同时删除数据卷（清库）')
    p_down.add_argument('--yes', action='store_true', help='确认 -v 危险操作')
    p_down.add_argument('--no-docker', action='store_true')
    p_down.add_argument('--no-host', action='store_true')
    p_down.set_defaults(func=cmd_down)

    p_restart = sub.add_parser('restart', help='重启宿主服务或全栈')
    p_restart.add_argument('target', choices=('audio', 'device', 'host', 'all'))
    p_restart.add_argument('--audio-mode', choices=('real', 'shim'), default='real')
    p_restart.add_argument('--test-db', action='store_true')
    p_restart.add_argument('--check-timeout', type=float, default=60.0)
    p_restart.set_defaults(func=cmd_restart)

    p_status = sub.add_parser('status', help='容器 + 宿主服务状态')
    p_status.set_defaults(func=cmd_status)

    p_health = sub.add_parser('health', help='HTTP /health + gRPC/基础设施 TCP 探测')
    p_health.set_defaults(func=cmd_health)

    p_logs = sub.add_parser('logs', help='容器日志；audio/device/audio_shim 看宿主日志')
    p_logs.add_argument('services', nargs='*', help='服务名（缺省全部容器）')
    p_logs.add_argument('-f', '--follow', action='store_true')
    p_logs.add_argument('--tail', type=int, default=100)
    p_logs.set_defaults(func=cmd_logs)

    p_build = sub.add_parser('build', help='构建镜像（委托 docker/build_stack.py）')
    p_build.add_argument('services', nargs='*', help='服务名（缺省全部）')
    p_build.set_defaults(func=cmd_build)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == '__main__':
    sys.exit(main())
