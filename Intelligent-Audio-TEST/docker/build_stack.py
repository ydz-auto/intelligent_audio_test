# -*- coding: utf-8 -*-
"""INT-1820：构建链路守卫 —— `docker compose build` 的安全入口。

背景（INT-1754 发版受阻，2026-10-24）：两次常规 `docker compose build` 失败——
① deb.debian.org 返回 502，apt 层直接打红；② 构建期 Docker 引擎崩溃（WSL VM 重启 /
Docker Desktop 进程消失），**全部容器 Exited 255**。Dockerfile 侧已改（镜像源 + digest
钉版 + 层内重试，见各 `docker/Dockerfile.*` 顶部注释）；本脚本负责「构建这件事本身」的可重复与可观测：

  - 构建前体检：引擎是否真的可用（区分「没连上」与「连上了但 500」）；
  - 目标项目对齐：构建写进哪个 compose 项目决定镜像 tag（`<project>-<svc>:latest`），
    写错项目会产出「构建成功但栈不用它」的孤儿镜像；
  - 构建前后对照：**本项目的**容器 StartedAt + VM uptime —— 区分「引擎真崩了」与
    「只是别的 run 在动容器」；
  - 目标镜像真的换新了吗：失败时不留下"看起来是新镜像"的半成品 tag；
  - 重试：失败层有缓存，重试只重跑失败层；引擎已死时不重试（白等）。

用法（仓库根目录）：
    python docker/build_stack.py                        # 构建全部 11 个后端服务
    python docker/build_stack.py api_gateway task_service evaluation_service
    python docker/build_stack.py --buildkit 0 api_gateway   # 旧 builder（BuildKit 打崩引擎时）
    python docker/build_stack.py --project int1820-verify api_gateway   # 隔离验证，不动现役镜像
    python docker/build_stack.py --no-cache --retries 2 e2e_test_service
    python docker/build_stack.py --check                # 只体检，不构建

退出码：
    0 构建成功且引擎全程健康
    2 参数/前置错误（未开始构建）
    3 引擎不健康（构建前体检失败，或构建期间 VM/引擎重启）
    4 构建失败（重试耗尽；目标镜像保持构建前身份，没有半成品）
"""
import argparse
import json
import os
import subprocess
import sys
import time

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COMPOSE_FILE = os.path.join(BASE_DIR, 'docker', 'docker-compose.yml')

# 缺省 compose 项目名：现役栈的镜像 tag 前缀就是它（intelligent-audio-test-api_gateway:latest）。
# 用 -p 不显式指定时 compose 会按 compose 文件父目录名推导（= "docker"），产出的镜像
# 现役栈根本不会用——INT-1820 实测踩到过。非部署场景请用 --project 指定隔离名字。
DEFAULT_PROJECT = 'intelligent-audio-test'

# 构建目标：compose 里带 build: 段的全部后端服务（frontend 需显式点名，见 _require_vite_mode）
BACKEND_SERVICES = [
    'db_bootstrap',
    'api_gateway',
    'task_service',
    'evaluation_service',
    'e2e_test_service',
    'report_service',
    'algorithm_service',
    'auth_service',
    'api_test_service',
    'audio_service',
    'device_service',
]

PROBE_TIMEOUT = 20          # 单次引擎探测上限（秒）；引擎「半死」时 docker CLI 会挂到 45s+
BUILD_TIMEOUT = 3600        # 单次构建上限（秒）


def _log(msg):
    print(f"[BUILD] {msg}", flush=True)


def _run(cmd, timeout=PROBE_TIMEOUT, env=None):
    """跑一条外部命令，返回 (returncode, stdout, stderr)。超时按不可用处理。"""
    try:
        p = subprocess.run(cmd, cwd=BASE_DIR, timeout=timeout, capture_output=True,
                           text=True, encoding='utf-8', errors='replace', env=env)
        return p.returncode, (p.stdout or '').strip(), (p.stderr or '').strip()
    except subprocess.TimeoutExpired:
        return 124, '', f'timeout after {timeout}s'
    except FileNotFoundError:
        return 127, '', f'{cmd[0]} not found'


def _docker(*args, **kw):
    return _run(['docker', *args], **kw)


def _compose(project, *args, **kw):
    return _docker('compose', '-p', project, '-f', COMPOSE_FILE, *args, **kw)


def engine_probe():
    """有界探测引擎。返回 (ok, server_version, detail)。"""
    rc, out, err = _docker('version', '--format', '{{.Server.Version}}', timeout=PROBE_TIMEOUT)
    if rc == 0 and out:
        return True, out, ''
    if rc == 124:
        return False, '', f'docker CLI 超时 {PROBE_TIMEOUT}s（引擎半死：管道在但 API 不应答）'
    if 'cannot find the file specified' in err or 'pipe' in err.lower():
        return False, '', 'Docker 引擎管道不存在（Docker Desktop 进程不在）'
    if '500' in err:
        return False, '', f'引擎返回 500：{err[-200:]}'
    return False, '', (err or f'rc={rc}')[-200:]


def vm_uptime():
    """docker-desktop VM 的 uptime（秒）。拿不到返回 None（非 Windows / 非 WSL 后端时跳过）。

    这是判定「构建期引擎是否真重启」最硬的信号：容器 StartedAt 会被别的 run 的
    启停打扰，VM uptime 只会在引擎重启时才归零。
    """
    # wsl.exe 偶发返回非零（本地代理提示、发行版切换竞态），重试一次再放弃
    for _ in range(2):
        rc, out, _ = _run(['wsl', '-d', 'docker-desktop', '-u', 'root', '-e', 'cat', '/proc/uptime'],
                          timeout=PROBE_TIMEOUT)
        if rc == 0 and out:
            try:
                return float(out.split()[0])
            except (ValueError, IndexError):
                return None
    return None


def container_snapshot(project):
    """本项目容器身份快照：{容器ID: StartedAt}。

    只取 `com.docker.compose.project=<project>` 的容器——同一台宿主上并行着别的 run 的栈，
    全量 `docker ps` 会把它们的启停算成「引擎崩过」。StartedAt 是唯一能区分「一直在跑」与
    「崩过、restart 策略又拉起来」的字段；ID 集合一致但 StartedAt 全变 = 引擎重启过。
    处于 created 状态的容器 StartedAt 是零值，单独标出来，避免被当成「刚重启」。
    """
    rc, out, _ = _docker('ps', '-aq', '--filter', f'label=com.docker.compose.project={project}')
    if rc != 0:
        return None
    ids = out.split() if out else []
    if not ids:
        return {}
    rc2, started, _ = _docker('inspect', '-f', '{{.Id}} {{.State.StartedAt}}', *ids,
                              timeout=PROBE_TIMEOUT)
    if rc2 != 0:
        return None
    snap = {}
    for line in started.splitlines():
        parts = line.split()
        if len(parts) == 2:
            snap[parts[0]] = parts[1]
    return snap


def _is_unstarted(started_at):
    return not started_at or started_at.startswith('0001-')


def image_identity(project, services):
    """目标镜像身份：{compose 镜像名: image id}（未构建过则为 None）。"""
    idents = {}
    for svc in services:
        image = f"{project}-{svc}:latest"
        rc, out, _ = _docker('image', 'inspect', '-f', '{{.Id}}', image)
        idents[svc] = out if rc == 0 and out else None
    return idents


def _require_vite_mode(services):
    """compose 文件里 frontend 的 VITE_AUTH_MODE 是必填插值（INT-181），缺它会解析失败。

    只构建后端时不涉及前端 bundle，缺省补 off 仅用于通过 compose 插值；一旦目标里
    包含 frontend，则拒绝替用户决定认证态。
    """
    vite = os.environ.get('VITE_AUTH_MODE', '').strip()
    if 'frontend' in services:
        if not vite:
            _log('ERROR: 目标含 frontend，但 VITE_AUTH_MODE 未设置。'
                 '前端构建期认证态必须显式注入（off|dev|prod），本脚本不代填。')
            sys.exit(2)
        return
    if not vite:
        os.environ['VITE_AUTH_MODE'] = os.environ.get('AUTH_MODE', '').strip() or 'off'
        _log(f'注：未设置 VITE_AUTH_MODE，仅用于 compose 插值，本次补 {os.environ["VITE_AUTH_MODE"]}'
             '（不构建 frontend，不进任何镜像）。')


def _normalize_services(names):
    if not names:
        return list(BACKEND_SERVICES)
    bad = [n for n in names if n not in BACKEND_SERVICES and n != 'frontend']
    if bad:
        _log(f'ERROR: 未知服务 {bad}；可选：{", ".join(BACKEND_SERVICES + ["frontend"])}')
        sys.exit(2)
    # 去重保序
    return list(dict.fromkeys(names))


def _build_once(project, services, buildkit, no_cache):
    env = os.environ.copy()
    if buildkit is not None:
        env['DOCKER_BUILDKIT'] = '1' if buildkit else '0'
    args = ['build']
    if no_cache:
        args.append('--no-cache')
    args += services
    _log(f'docker compose -p {project} -f {COMPOSE_FILE} ' + ' '.join(args)
         + f"   [DOCKER_BUILDKIT={env.get('DOCKER_BUILDKIT', '<默认>')}]")
    started = time.time()
    try:
        rc = subprocess.run(['docker', 'compose', '-p', project, '-f', COMPOSE_FILE, *args],
                            cwd=BASE_DIR, env=env, timeout=BUILD_TIMEOUT).returncode
    except subprocess.TimeoutExpired:
        _log(f'构建超时（>{BUILD_TIMEOUT}s）')
        return 124, time.time() - started
    return rc, time.time() - started


def cmd_check():
    ok, ver, detail = engine_probe()
    if ok:
        _log(f'引擎健康：server={ver}')
    else:
        _log(f'引擎不健康：{detail}')
    up = vm_uptime()
    if up is None:
        _log('VM uptime：取不到（非 Windows/WSL 后端，或 docker-desktop 发行版不可用）')
    else:
        _log(f'VM uptime：{up / 3600:.1f}h（引擎重启会让它归零，构建前后用它判定是否真重启）')
    snap = container_snapshot(DEFAULT_PROJECT)
    if snap is not None:
        _log(f'项目 {DEFAULT_PROJECT} 的容器 {len(snap)} 个')
    return 0 if ok else 3


def cmd_build(args):
    services = _normalize_services(args.services)
    _require_vite_mode(services)
    project = args.project

    # ---- 构建前体检 ----
    ok, ver, detail = engine_probe()
    if not ok:
        _log(f'引擎不健康，不开始构建：{detail}')
        _log('恢复见 docker/README.md「引擎崩溃后的恢复清单」。')
        return 3
    _log(f'引擎健康：server={ver}；目标项目：{project}（镜像 tag 前缀 {project}-）')

    before_snap = container_snapshot(project) or {}
    before_imgs = image_identity(project, services)
    before_uptime = vm_uptime()

    # ---- 构建（失败重试；引擎已死时不重试）----
    rc, elapsed = 0, 0.0
    for attempt in range(1, args.retries + 1):
        rc, elapsed = _build_once(project, services, args.buildkit, args.no_cache)
        if rc == 0:
            break
        alive, _ver, why = engine_probe()
        if not alive:
            _log(f'第 {attempt}/{args.retries} 次构建失败，且引擎已不可用：{why}')
            _log('判定为「构建期引擎崩溃」——继续重试没有意义。'
                 '恢复引擎后重跑本命令；重试会命中已完成层的缓存。')
            return 3
        _log(f'第 {attempt}/{args.retries} 次构建失败（rc={rc}，{elapsed:.0f}s），引擎仍在；'
             '重试将只重跑失败层。')
        if args.no_cache:
            _log('提示：--no-cache 下重试要全量重来，耗时可能数倍。')

    # ---- 构建后对照 ----
    alive, ver_after, why = engine_probe()
    after_snap = container_snapshot(project) or {}
    after_imgs = image_identity(project, services)
    after_uptime = vm_uptime()

    vm_restarted = (before_uptime is not None and after_uptime is not None
                    and after_uptime < before_uptime)

    restarted, new, gone = [], [], []
    for cid, started in after_snap.items():
        if cid not in before_snap:
            new.append(cid)
        elif (not _is_unstarted(before_snap[cid]) and before_snap[cid] != started):
            restarted.append(cid)
    gone = [c for c in before_snap if c not in after_snap]

    _log('---- 构建后对照 ----')
    _log(f'引擎：{"健康 server=" + str(ver_after) if alive else "不可用：" + why}')
    if before_uptime is not None and after_uptime is not None:
        _log(f'VM uptime：{before_uptime / 3600:.2f}h → {after_uptime / 3600:.2f}h'
             + ('（缩短 = VM 重启过）' if vm_restarted else '（连续，VM 未重启）'))
    _log(f'项目 {project} 容器：{len(before_snap)} → {len(after_snap)}'
         f'；重启 {len(restarted)}，新增 {len(new)}，消失 {len(gone)}')
    for svc, new_id in after_imgs.items():
        old_id = before_imgs.get(svc)
        if rc == 0:
            tag = '新镜像' if old_id != new_id else '未变化（层全部命中缓存，镜像 ID 不变）'
            _log(f'{svc}: {tag} {new_id}')
        elif old_id == new_id:
            _log(f'{svc}: 保持构建前镜像 {new_id}（构建失败未留下半成品 tag）')
        else:
            _log(f'{svc}: WARN 构建失败但镜像已变化 {old_id} → {new_id}')

    if not alive:
        _log('构建结束时引擎已不可用：验收不通过（卡片口径要求构建全过程引擎不重启）。')
        return 3
    if vm_restarted:
        _log('VM uptime 变短：构建期间引擎/VM 重启过 —— 按 INT-1820 验收口径记为不稳定，'
             '改用 --buildkit 0 单服务串行复测。')
        return 3
    if restarted:
        _log('WARN: 构建期间本项目有容器被重启（StartedAt 变化），但 VM uptime 连续、'
             '引擎未重启——多半是并行的其他 run 在动容器，不计入引擎崩溃。')
    if rc != 0:
        _log(f'构建失败（rc={rc}，累计 {elapsed:.0f}s）。')
        return 4
    _log(f'构建成功（{elapsed:.0f}s），引擎全程健康、VM 未重启、本项目容器集合未丢失。')
    _log('下一步不自动 up（避免打断现役栈）：需要发布时按发版流程执行，'
         '只验构建则到此为止。')
    return 0


def main():
    ap = argparse.ArgumentParser(
        description='INT-1820 构建守卫：带引擎体检与容器/VM 对照的 docker compose build')
    ap.add_argument('services', nargs='*', help='compose 服务名（缺省全部后端）')
    ap.add_argument('--project', default=os.environ.get('COMPOSE_PROJECT_NAME') or DEFAULT_PROJECT,
                    help=f'compose 项目名，决定镜像 tag 前缀（缺省 {DEFAULT_PROJECT}）。'
                         '非发布场景建议用独立名字（如 int1820-verify）避免覆盖现役镜像。')
    ap.add_argument('--buildkit', choices=['auto', '1', '0'], default='auto',
                    help='DOCKER_BUILDKIT：auto=用引擎默认（当前为 BuildKit）；'
                         '0=旧 builder（BuildKit 打崩引擎时的绕行）')
    ap.add_argument('--no-cache', action='store_true', help='全量重建（不命中层缓存）')
    ap.add_argument('--retries', type=int, default=2,
                    help='单次构建最多尝试次数（缺省 2；失败层有缓存，重试代价小）')
    ap.add_argument('--check', action='store_true', help='只做构建前体检')
    args = ap.parse_args()

    if args.check:
        return cmd_check()
    if args.retries < 1:
        _log('--retries 至少为 1')
        return 2
    args.buildkit = None if args.buildkit == 'auto' else int(args.buildkit)
    return cmd_build(args)


if __name__ == '__main__':
    sys.exit(main())
