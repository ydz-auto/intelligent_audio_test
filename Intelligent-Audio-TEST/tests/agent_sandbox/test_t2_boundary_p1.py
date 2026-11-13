# -*- coding: utf-8 -*-
"""T2 沙箱安全边界 P1 回归（INT-2518，来源 INT-2514 审计）。

审计结论是「runner 是唯一持有 Docker/runsc 的安全边界」，四条 P1 都出在边界
不校验、由调用方自律：

1. P1-1：runner 不复核 T2 payload 的限额与镜像 → 这里按 runner 配置复核；
2. P1-1b：T2 ``container_user`` 仍按字面量判 root → 改为数值解析；
3. P1-2：T2 argv 无容器内 ``timeout`` 自限、孤儿回收不覆盖 ``agent-sandbox=t2``
   → argv 包装 + 回收器双目标（阈值分层）；
4. P1-3：T2 ``/work`` 只有事后校验 → 运行中巡检超限即杀（BUDGET_EXCEEDED）；
5. P1-4：payload 可指定任意宿主目录 → 宿主目录允许根（``AGENT_SANDBOX_WORK_ROOT``）。

不需要 Docker 的用例直接跑；真实容器用例标记 ``docker_required``。本机 Docker
没有 gVisor ``runsc``：需要 T2 运行时的逃逸用例仍在 ``test_t2_escape.py`` 按
``T2_RUNTIME_UNAVAILABLE`` skip；这里用「去掉 ``--runtime`` 的 T2 argv」验证
共享执行路径（argv 形状 / timeout 自限 / /work 巡检），不冒充 gVisor 隔离。
"""

from __future__ import annotations

import json
import os
import subprocess
import time
import uuid
from dataclasses import replace
from pathlib import Path
from typing import Mapping

import pytest

from agent_service.application.sandbox_runner import (
    ContainerExecution,
    ContainerInvocation,
    ContainerLimits,
    SandboxConfigurationError,
    SandboxFailureReason,
    SandboxOutcome,
    SandboxRunner,
    SandboxRuntimeAvailability,
    T2ContainerInvocation,
    T2Phase,
    T2RunnerOptions,
    T2SandboxRequest,
)
from agent_service.infrastructure.sandbox.docker_runner import (
    HostCliDockerExecutor,
    ReaperTarget,
    SandboxContainerReaper,
    SandboxPolicy,
    build_docker_run_argv,
    execute_docker_container,
    execution_from_dict,
    execution_to_dict,
    validate_invocation,
)
from agent_service.infrastructure.sandbox.policy import T2Policy, load_t2_policy
from agent_service.infrastructure.sandbox.runner_service import SandboxRunnerServer
from agent_service.infrastructure.sandbox.t2_runner import (
    T2_RUNNER_API_PATH,
    T2DockerExecutor,
    build_t2_run_argv,
    t2_invocation_to_dict,
    validate_t2_invocation,
)
from tests.agent_sandbox._sandbox_support import docker_cli, sandbox_image

TEST_TOKEN = 'it-token-' + uuid.uuid4().hex[:12]
PHASE = ('python3', '-c', 'print(1)')


# ── 夹具 ───────────────────────────────────────────────────────


def _policy(tmp_path: Path, **overrides) -> T2Policy:
    """从 yaml 默认值构造策略；允许根固定在用例 tmp_path 下（不读宿主配置）。"""
    base = load_t2_policy(environ={})
    overrides.setdefault('work_roots', (str(tmp_path),))
    return replace(base, **overrides)


def _invocation(tmp_path: Path, **overrides) -> T2ContainerInvocation:
    input_root = tmp_path / 'input'
    work = tmp_path / 'work'
    input_root.mkdir(exist_ok=True)
    work.mkdir(exist_ok=True)
    payload = dict(
        name='agent-sandbox-t2-p1-abc',
        input_root=str(input_root),
        work_dir=str(work),
        command=PHASE,
        runtime='runsc',
        limits=ContainerLimits(),
    )
    payload.update(overrides)
    return T2ContainerInvocation(**payload)


class FakeT2Executor:
    """记录调用并返回成功：只验证应用侧编排与契约，不起容器。"""

    def __init__(self, policy: T2Policy) -> None:
        self.policy = policy
        self.limits = policy.container_limits
        self.invocations: list[T2ContainerInvocation] = []

    @property
    def runtime(self) -> str:
        return 'gvisor'

    @property
    def runtime_name(self) -> str:
        return 'runsc'

    def availability(self) -> SandboxRuntimeAvailability:
        return SandboxRuntimeAvailability(True, 'gvisor', 'runsc', 'ok')

    def run(self, invocation: T2ContainerInvocation) -> ContainerExecution:
        self.invocations.append(invocation)
        return ContainerExecution(exit_code=0)


def _request(**overrides) -> T2SandboxRequest:
    payload = dict(
        code_source='driver_propose:DEVICE_DRIVER',
        files={'pkg/__init__.py': '', 'pkg/main.py': 'print(1)\n'},
        phases=(T2Phase('import_compile', PHASE),),
    )
    payload.update(overrides)
    return T2SandboxRequest(**payload)


# ── P1-1：runner 复核 T2 payload 的限额与镜像 ──────────────────


@pytest.mark.parametrize(
    'limits',
    [
        dict(memory='64g'),
        dict(memory_swap='64g'),
        dict(cpus=100.0),
        dict(pids_limit=100000),
        dict(tmpfs_size='8g'),
        dict(timeout_seconds=99999),
        dict(output_limit_bytes=64 * 1024 * 1024),
    ],
    ids=['memory', 'memory_swap', 'cpus', 'pids', 'tmpfs', 'timeout', 'output'],
)
def test_t2_payload_limits_may_only_tighten(tmp_path: Path, limits: Mapping) -> None:
    """payload 放大任一限额都要 400（audit 实测 6 类构造），不静默 clamp。"""
    invocation = _invocation(tmp_path, limits=replace(ContainerLimits(), **dict(limits)))
    with pytest.raises(SandboxConfigurationError):
        validate_t2_invocation(invocation, _policy(tmp_path))


def test_t2_payload_image_must_be_allowed(tmp_path: Path) -> None:
    policy = _policy(tmp_path)
    for image in ('evil/attacker:latest', 'alpine:3.20', '--privileged', 'bad image'):
        invocation = _invocation(tmp_path, limits=replace(ContainerLimits(), image=image))
        with pytest.raises(SandboxConfigurationError):
            validate_t2_invocation(invocation, policy)


def test_t2_allowed_images_come_from_config(tmp_path: Path) -> None:
    """白名单可由配置放开（第二个镜像显式加入后才允许）。"""
    policy = _policy(
        tmp_path,
        container_limits=replace(ContainerLimits(), image='python:3.11-slim'),
        allowed_images=('python:3.11-slim', 'python:3.11'),
    )
    validate_t2_invocation(
        _invocation(tmp_path, limits=replace(ContainerLimits(), image='python:3.11')),
        policy,
    )


def test_t2_phase_timeout_may_not_exceed_runner(tmp_path: Path) -> None:
    policy = _policy(tmp_path)
    with pytest.raises(SandboxConfigurationError):
        validate_t2_invocation(
            _invocation(tmp_path, timeout_seconds=99999), policy
        )
    # 正常规格（≤ 单阶段上限）不受影响
    validate_t2_invocation(
        _invocation(tmp_path, timeout_seconds=policy.container_limits.timeout_seconds),
        policy,
    )


def test_t2_normal_spec_is_accepted(tmp_path: Path) -> None:
    """审计要求的正常规格：512m/1cpu/128pids/64m/120s/python:3.11-slim/65534:65534。"""
    policy = _policy(tmp_path)
    validate_t2_invocation(_invocation(tmp_path), policy)


# ── P1-1b：container_user 按数值判定非 root ────────────────────


@pytest.mark.parametrize('user', ['0', '0:0', '000', '0:65534', '00:00'])
def test_t2_container_user_numeric_root_rejected(tmp_path: Path, user: str) -> None:
    """``000`` / ``0:65534`` 这类字面量绕不过数值判定（与 T1 INT-2494 同口径）。"""
    limits = ContainerLimits()
    # 绕过构造期校验，模拟「payload 直接落到边界」的情形：边界自己必须再判。
    object.__setattr__(limits, 'container_user', user)
    with pytest.raises(SandboxConfigurationError):
        validate_t2_invocation(_invocation(tmp_path, limits=limits), _policy(tmp_path))


def test_t2_policy_rejects_literal_root_user() -> None:
    limits = ContainerLimits()
    object.__setattr__(limits, 'container_user', '000')
    with pytest.raises(SandboxConfigurationError):
        T2Policy(container_limits=limits)


def test_t2_non_root_user_accepted(tmp_path: Path) -> None:
    validate_t2_invocation(
        _invocation(tmp_path, limits=replace(ContainerLimits(), container_user='65534:65534')),
        _policy(tmp_path),
    )


# ── P1-2：容器内 timeout 自限 ─────────────────────────────────


def test_t2_argv_timeout_wraps_command_with_effective_timeout(tmp_path: Path) -> None:
    invocation = _invocation(tmp_path, timeout_seconds=30)
    argv = build_t2_run_argv(invocation, container_kill_grace_seconds=7)
    image_index = argv.index(invocation.limits.image)
    assert argv[image_index + 1:image_index + 5] == ['timeout', '--kill-after', '7', '30']
    assert argv[image_index + 5:] == list(PHASE)


def test_t2_timeout_exit_code_maps_to_budget_exceeded() -> None:
    """容器内 timeout 到点退出 124 → BUDGET_EXCEEDED/TIMEOUT，不是普通非零退出。"""
    runner = SandboxRunner(untrusted_executor=None)
    result = runner._map_t2_execution(
        T2Phase('import_compile', PHASE),
        ContainerExecution(exit_code=124, timed_out=False),
        limits=ContainerLimits(),
        timeout_seconds=120,
        duration_fallback_ms=1,
    )
    assert result.outcome is SandboxOutcome.BUDGET_EXCEEDED
    assert result.reason is SandboxFailureReason.TIMEOUT


def test_t2_work_limit_maps_to_budget_exceeded() -> None:
    """运行中 /work 超限（标记随 HTTP 契约传输）→ BUDGET_EXCEEDED/资源超限。"""
    execution = execution_from_dict(execution_to_dict(
        ContainerExecution(exit_code=137, work_limit_exceeded=True, killed_by_runner=True)
    ))
    assert execution.work_limit_exceeded, 'work_limit_exceeded 必须能跨 runner HTTP 契约传输'
    result = SandboxRunner(untrusted_executor=None)._map_t2_execution(
        T2Phase('import_compile', PHASE), execution,
        limits=ContainerLimits(), timeout_seconds=120, duration_fallback_ms=1,
    )
    assert result.outcome is SandboxOutcome.BUDGET_EXCEEDED
    assert result.reason is SandboxFailureReason.RESOURCE_LIMIT_EXCEEDED


def test_reaper_targets_have_layered_thresholds() -> None:
    """回收器按标签给不同阈值：T2 必须比 T1 宽（否则跨阶段容器被误杀）。"""
    reaper = SandboxContainerReaper(targets=(
        ReaperTarget('agent-sandbox=t1', 60, 30),
        ReaperTarget('agent-sandbox=t2', 300, 30),
    ))
    assert reaper.target_thresholds == {
        'agent-sandbox=t1': 90.0, 'agent-sandbox=t2': 330.0,
    }


# ── P1-3：T2 的 /work 运行中容量门禁（应用层编排） ─────────────


def test_t2_work_limit_comes_from_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('AGENT_SANDBOX_T2_WORK_LIMIT_BYTES', str(48 * 1024 * 1024))
    policy = load_t2_policy(path=Path('config-does-not-exist.yaml'))
    assert policy.work_limit_bytes == 48 * 1024 * 1024


def test_t2_work_limit_may_not_under_cut_artifacts(tmp_path: Path) -> None:
    """工作区上限不得小于产物总量上限，否则合法产物会被运行中巡检误杀。"""
    with pytest.raises(SandboxConfigurationError):
        _policy(
            tmp_path,
            work_limit_bytes=1024,
            artifacts=replace(load_t2_policy(environ={}).artifacts, max_total_bytes=4096),
        )


# ── P1-4：宿主目录允许根 ─────────────────────────────────────


def test_t2_rejects_paths_outside_allowed_root(tmp_path: Path) -> None:
    outside = tmp_path.parent / f'outside_{uuid.uuid4().hex[:8]}'
    outside.mkdir()
    work = tmp_path / 'work'
    work.mkdir(exist_ok=True)
    policy = _policy(tmp_path)
    with pytest.raises(SandboxConfigurationError, match='input_root'):
        validate_t2_invocation(
            _invocation(tmp_path, input_root=str(outside), work_dir=str(work)), policy
        )
    with pytest.raises(SandboxConfigurationError, match='work_dir'):
        validate_t2_invocation(
            _invocation(tmp_path, input_root=str(tmp_path / 'input'), work_dir=str(outside)),
            policy,
        )


def test_t2_rejects_dotdot_escape(tmp_path: Path) -> None:
    """``..`` 拼出来的路径在 resolve 后落在根外 → 400（不是按字符串前缀放行）。"""
    escaping = f'{tmp_path}/..'
    with pytest.raises(SandboxConfigurationError):
        validate_t2_invocation(
            _invocation(
                tmp_path,
                input_root=escaping,
                work_dir=str(tmp_path / 'work'),
            ),
            _policy(tmp_path),
        )


def test_t2_rejects_symlink_escape(tmp_path: Path) -> None:
    outside = tmp_path.parent / f'link_outside_{uuid.uuid4().hex[:8]}'
    outside.mkdir()
    link = tmp_path / 'linked'
    try:
        os.symlink(outside, link, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:  # pragma: no cover - 平台相关
        pytest.skip(f'本机不支持目录符号链接（{exc}）：需 Windows 开发者模式/管理员权限')
    with pytest.raises(SandboxConfigurationError):
        validate_t2_invocation(
            _invocation(
                tmp_path,
                input_root=str(link),
                work_dir=str(tmp_path / 'work'),
            ),
            _policy(tmp_path),
        )


def _t1_invocation(tmp_path: Path, work_dir: Path) -> ContainerInvocation:
    skill = tmp_path / 'skills' / 'demo'
    (skill / 'scripts').mkdir(parents=True, exist_ok=True)
    (skill / 'scripts' / 'main.py').write_text('print("hi")\n', encoding='utf-8')
    return ContainerInvocation(
        name='agent-sandbox-t1-p1-ok',
        skill_root=str(skill),
        work_dir=str(work_dir),
        script_relative_path='scripts/main.py',
    )


def test_t1_work_dir_must_be_inside_allowed_root(tmp_path: Path) -> None:
    work = tmp_path / 'work'
    work.mkdir()
    policy = SandboxPolicy(
        limits=ContainerLimits(),
        allowed_images=frozenset({sandbox_image()}),
        allowed_interpreters=frozenset({'python3'}),
        skills_root=str(tmp_path / 'skills'),
        work_roots=(str(tmp_path),),
    )
    validate_invocation(_t1_invocation(tmp_path, work), policy)  # 根内通过

    outside = tmp_path.parent / f't1_outside_{uuid.uuid4().hex[:8]}'
    outside.mkdir()
    with pytest.raises(SandboxConfigurationError, match='work_dir'):
        validate_invocation(_t1_invocation(tmp_path, outside), policy)


def test_t1_build_argv_does_not_bypass_root(tmp_path: Path) -> None:
    """纵深防御：argv 构造不校验允许根，但 runner 的 validate 一定拦住根外目录。"""
    outside = tmp_path.parent / f't1_outside_{uuid.uuid4().hex[:8]}'
    outside.mkdir()
    invocation = _t1_invocation(tmp_path, outside)
    # argv 只做格式构造，允许根由 runner.validate（上面那条用例）负责。
    build_docker_run_argv(invocation, 'docker')


def test_sandbox_runner_creates_dirs_under_allowed_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """应用侧一次性目录建在 ``AGENT_SANDBOX_WORK_ROOT`` 之下（不是宿主真实目录）。"""
    from agent_service.application.sandbox_runner import T2Phase

    root = tmp_path / 'runner-work-root'
    monkeypatch.setenv('AGENT_SANDBOX_WORK_ROOT', str(root))
    executor = FakeT2Executor(_policy(tmp_path))
    runner = SandboxRunner(
        untrusted_executor=executor,
        t2_options=T2RunnerOptions(total_timeout_seconds=60),
    )
    result = runner.run_untrusted_code(T2SandboxRequest(
        code_source='test',
        files={'main.py': 'print(1)\n'},
        phases=(T2Phase('import_compile', PHASE),),
    ))
    assert result.outcome is SandboxOutcome.SUCCEEDED, result.detail
    invocation = executor.invocations[0]
    resolved_root = root.resolve()
    assert Path(invocation.input_root).resolve().is_relative_to(resolved_root)
    assert Path(invocation.work_dir).resolve().is_relative_to(resolved_root)


# ── runner HTTP 端点：真实 400（进程内，无需 Docker / gVisor） ──


class _RecordOnlyT2Executor(T2DockerExecutor):
    """只做校验/记录、不碰 Docker 的 T2 执行器：区分「400 拒绝」与「200 放行」。"""

    def __init__(self, policy: T2Policy) -> None:
        super().__init__(policy)
        self.seen: list[str] = []

    def run(self, invocation: T2ContainerInvocation) -> ContainerExecution:
        self.seen.append(invocation.name)
        return ContainerExecution(exit_code=0, runtime='gvisor')


@pytest.fixture
def t2_sidecar(tmp_path: Path):
    policy = _policy(tmp_path)
    server = SandboxRunnerServer(
        executor=HostCliDockerExecutor(policy=SandboxPolicy(
            limits=ContainerLimits(),
            allowed_images=frozenset({sandbox_image()}),
            allowed_interpreters=frozenset({'python3'}),
            skills_root=str(tmp_path),
            work_roots=(str(tmp_path),),
        )),
        token=TEST_TOKEN,
        bind_host='127.0.0.1',
        port=0,
        t2_executor=_RecordOnlyT2Executor(policy),
    ).start_background()
    yield server
    server.stop()


def _t2_payload(tmp_path: Path, *, limits: Mapping | None = None, **overrides) -> bytes:
    data = t2_invocation_to_dict(_invocation(tmp_path))
    data['limits'].update(dict(limits or {}))
    data.update(overrides)
    return json.dumps({'protocol_version': 1, 'invocation': data}).encode('utf-8')


def _post_t2(url: str, body: bytes):
    from urllib import error as urlerror
    from urllib import request as urlrequest

    request = urlrequest.Request(
        url + T2_RUNNER_API_PATH,
        data=body,
        headers={'Content-Type': 'application/json', 'X-Sandbox-Runner-Token': TEST_TOKEN},
        method='POST',
    )
    try:
        with urlrequest.urlopen(request, timeout=15) as response:
            return response.status, response.read()
    except urlerror.HTTPError as exc:
        return exc.code, exc.read()


@pytest.mark.parametrize(
    'limits',
    [
        dict(memory='64g'),
        dict(cpus=100.0),
        dict(pids_limit=100000),
        dict(tmpfs_size='8g'),
        dict(timeout_seconds=99999),
        dict(image='evil/attacker:latest'),
        dict(container_user='000'),
        dict(container_user='0:65534'),
        dict(container_user='root'),
    ],
    ids=['memory', 'cpus', 'pids', 'tmpfs', 'timeout', 'image', 'user-000',
         'user-0:65534', 'user-root'],
)
def test_runner_returns_400_for_illegal_t2_payload(
    t2_sidecar, tmp_path: Path, limits: Mapping
) -> None:
    """验收标准 1：七类放大/非法构造在 runner HTTP 边界全部 400。"""
    status, body = _post_t2(t2_sidecar.url, _t2_payload(tmp_path, limits=limits))
    assert status == 400, body
    assert b'error' in body


def test_runner_returns_400_for_outside_root(t2_sidecar, tmp_path: Path) -> None:
    outside = tmp_path.parent / f'outside_{uuid.uuid4().hex[:8]}'
    outside.mkdir()
    status, body = _post_t2(
        t2_sidecar.url, _t2_payload(tmp_path, input_root=str(outside))
    )
    assert status == 400, body


def test_runner_accepts_normal_t2_payload(t2_sidecar, tmp_path: Path) -> None:
    """正常规格通过校验并进入执行（200），不受新校验影响。"""
    status, body = _post_t2(t2_sidecar.url, _t2_payload(tmp_path))
    assert status == 200, body


# ── 真实 Docker：timeout 自限、/work 巡检、t2 标签回收 ──────────


FLOOD_SCRIPT = (
    'import pathlib, time\n'
    'p = pathlib.Path("/work/big.bin")\n'
    'h = p.open("wb")\n'
    'end = time.time() + 30\n'
    'while time.time() < end:\n'
    '    h.write(b"x" * 65536); h.flush(); time.sleep(0.01)\n'
)


def _t2_like_argv(tmp_path: Path, name: str, command: tuple[str, ...],
                  work_dir: Path, *, timeout_seconds: int = 10,
                  extra_labels: tuple[str, ...] = ()) -> list[str]:
    """T2 的 argv（去掉 ``--runtime``，本机无 runsc）：同一套加固/挂载/timeout。"""
    invocation = T2ContainerInvocation(
        name=name,
        input_root=str(tmp_path / 'input'),
        work_dir=str(work_dir),
        command=command,
        runtime='runsc',
        limits=ContainerLimits(timeout_seconds=timeout_seconds),
    )
    argv = build_t2_run_argv(invocation, container_kill_grace_seconds=2)
    index = argv.index('--runtime')
    del argv[index:index + 2]
    if extra_labels:
        # 在 t2 标签之后追加用例自己的隔离标签（回收器按它精确选择）。
        insert_at = argv.index('--label') + 2
        for label in extra_labels:
            argv[insert_at:insert_at] = ['--label', label]
            insert_at += 2
    return argv


def _container_exists(name: str) -> bool:
    return docker_cli('container', 'inspect', '--format', '{{.Id}}', name, timeout=30).returncode == 0


def _container_running(name: str) -> bool:
    result = docker_cli('inspect', '--format', '{{.State.Running}}', name, timeout=30)
    return result.returncode == 0 and result.stdout.strip().lower() == 'true'


def _container_exit_code(name: str) -> int | None:
    result = docker_cli('inspect', '--format', '{{.State.ExitCode}}', name, timeout=30)
    if result.returncode != 0:
        return None
    try:
        return int(result.stdout.strip())
    except ValueError:
        return None


def test_t2_image_ships_timeout_binary(docker_available: str) -> None:
    """容器内自限依赖镜像里的 ``/usr/bin/timeout``：在测试里断言，不假设。"""
    image = (os.environ.get('AGENT_SANDBOX_T2_IMAGE') or '').strip() or docker_available
    result = docker_cli(
        'run', '--rm', '--network', 'none', '--user', '65534:65534',
        image, 'timeout', '--version', timeout=120,
    )
    assert result.returncode == 0, result.stderr
    assert 'timeout' in (result.stdout or '').lower()


@pytest.mark.docker_required
def test_t2_container_stops_itself_after_runner_killed(
    docker_available: str, tmp_path: Path
) -> None:
    """runner 进程消失后 T2 容器靠容器内 ``timeout`` 到点自己退出（124/137）。"""
    (tmp_path / 'input').mkdir()
    work = tmp_path / 'work'
    work.mkdir()
    name = f'agent-sandbox-t2-self-{uuid.uuid4().hex[:8]}'
    argv = _t2_like_argv(
        tmp_path, name, ('python3', '-c', 'import time; time.sleep(300)'), work
    )
    process = subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline and not _container_running(name):
            if process.poll() is not None:
                break
            time.sleep(0.2)
        assert _container_running(name), '容器未起来，用例前提不成立'

        process.kill()  # 模拟 runner 崩溃：附着的 docker CLI 随死
        process.wait(timeout=30)
        killed_at = time.monotonic()
        deadline = killed_at + 10 + 2 + 30
        while time.monotonic() < deadline and _container_running(name):
            time.sleep(0.2)
        assert not _container_running(name), 'T2 容器没有容器内自限'
        assert _container_exit_code(name) in (124, 137)
    finally:
        docker_cli('rm', '--force', name, timeout=30)


@pytest.mark.docker_required
def test_reaper_reclaims_container_left_by_killed_runner(
    docker_available: str, tmp_path: Path
) -> None:
    """runner（附着的 docker CLI）被杀后留下的 T2 容器，由回收器按标签清掉。"""
    (tmp_path / 'input').mkdir()
    work = tmp_path / 'work'
    work.mkdir()
    selector = f'agent-sandbox-reaper-{uuid.uuid4().hex[:8]}'
    name = f'agent-sandbox-t2-killed-{uuid.uuid4().hex[:8]}'
    argv = _t2_like_argv(
        tmp_path, name, ('python3', '-c', 'import time; time.sleep(300)'), work,
        timeout_seconds=600, extra_labels=(f'{selector}=1',),
    )
    process = subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline and not _container_running(name):
            if process.poll() is not None:
                break
            time.sleep(0.2)
        assert _container_running(name), '容器未起来，用例前提不成立'
        process.kill()
        process.wait(timeout=30)

        reaper = SandboxContainerReaper(
            targets=(ReaperTarget(f'{selector}=1', 0, 0),), interval_seconds=1,
        )
        our = [c for c in _wait_listed(reaper, f'{selector}=1', name) if c.name == name]
        assert our, '回收器按标签没发现 runner 遗留的 T2 容器'
        reaped = reaper.reap_once()
        assert name in reaped, f'runner 异常退出后的 T2 容器未被回收：{reaped}'
        assert not _container_exists(name)
    finally:
        docker_cli('rm', '--force', name, timeout=30)


@pytest.mark.docker_required
def test_t2_work_dir_limit_kills_container(docker_available: str, tmp_path: Path) -> None:
    """运行中 /work 超限 → terminate（与 T1 同一套巡检，T2 自己的阈值）。"""
    (tmp_path / 'input').mkdir()
    work = tmp_path / 'work'
    work.mkdir()
    name = f'agent-sandbox-t2-work-{uuid.uuid4().hex[:8]}'
    argv = _t2_like_argv(
        tmp_path, name, ('python3', '-c', FLOOD_SCRIPT), work, timeout_seconds=60
    )
    started = time.monotonic()
    execution = execute_docker_container(
        argv,
        name,
        ContainerLimits(timeout_seconds=60),
        work_dir=str(work),
        work_limit_bytes=1024 * 1024,
    )
    elapsed = time.monotonic() - started
    assert execution.work_limit_exceeded is True, execution.error
    assert execution.killed_by_runner is True
    assert elapsed < 30, f'/work 超限未被运行中巡检拦住：{elapsed:.1f}s'
    assert not _container_exists(name), '超限终止后必须回收容器'


def _wait_running(name: str, timeout: float = 15.0) -> bool:
    """等 ``docker inspect`` 报运行中（daemon 偶发慢时重试，避免误判）。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _container_running(name):
            return True
        time.sleep(0.3)
    return False


def _wait_listed(reaper: SandboxContainerReaper, selector: str, name: str,
                 timeout: float = 30.0) -> list:
    """等容器出现在 ``docker ps`` 列表里（加载中的 daemon 偶发慢，重试而非硬断言）。"""
    deadline = time.monotonic() + timeout
    containers: list = []
    while time.monotonic() < deadline:
        containers = reaper.list_containers(selector)
        if any(c.name == name for c in containers):
            return containers
        time.sleep(0.5)
    return containers


@pytest.mark.docker_required
def test_reaper_reclaims_orphan_t2_container(docker_available: str) -> None:
    """``agent-sandbox=t2`` 孤儿容器在阈值外被回收、阈值内不被误杀。

    除真实 t2 标签外另打一个唯一标签做删除选择器：同一 docker daemon 上可能有
    别的会话的 t2 容器，用例只删自己造的那个（同时断言 t2 标签能列出本容器）。
    """
    selector = f'agent-sandbox-reaper-{uuid.uuid4().hex[:8]}'
    name = f'agent-sandbox-t2-orphan-{uuid.uuid4().hex[:8]}'
    created = docker_cli(
        'run', '--detach', '--name', name,
        '--label', 'agent-sandbox=t2',
        '--label', f'{selector}=1',
        '--network', 'none',
        '--user', '65534:65534',
        docker_available, 'sleep', '300',
        timeout=120,
    )
    assert created.returncode == 0, created.stderr
    try:
        lister = SandboxContainerReaper(
            targets=(ReaperTarget('agent-sandbox=t2', 300, 30),), interval_seconds=1,
        )
        # t2 标签确实能列出本容器（回收器按标签发现的路径）。
        listed = [c.name for c in _wait_listed(lister, 'agent-sandbox=t2', name)]
        assert name in listed, 'agent-sandbox=t2 标签没能列出 T2 容器'

        target = ReaperTarget(f'{selector}=1', 300, 30)
        tagged = SandboxContainerReaper(targets=(target,), interval_seconds=1)
        our = [c for c in _wait_listed(tagged, f'{selector}=1', name) if c.name == name]
        assert our, '唯一标签没能列出本容器'
        created_at = our[0].created_at

        # 阈值内：不回收（模拟跨阶段仍在合法运行）
        assert tagged.reap_once(now=created_at + target.threshold_seconds - 5) == []
        assert _wait_running(name), '阈值内的容器被误杀'
        # 阈值外：回收
        reaped = tagged.reap_once(now=created_at + target.threshold_seconds + 1)
        assert name in reaped, f'孤儿 T2 容器未被回收：{reaped}'
        assert not _container_exists(name)
    finally:
        docker_cli('rm', '--force', name, timeout=30)
