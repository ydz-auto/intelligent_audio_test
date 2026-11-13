# -*- coding: utf-8 -*-
"""T1 沙箱容器生命周期（INT-2494 / INT-2485 审计 P1-1）——真实 Docker。

审计实测：kill 掉执行器进程后容器仍 ``Up``、无人回收。本文件回归三层防线：

1. 异常路径 ``try/finally``：执行器内部抛异常也必须 ``docker rm -f``；
2. 容器自限：``timeout -k`` 让容器在宿主计时器消失后自己结束；
3. 孤儿回收：``SandboxContainerReaper`` 按 label 回收超龄容器。
"""

from __future__ import annotations

import subprocess
import time
import uuid
from pathlib import Path

import pytest

from agent_service.application.sandbox_runner import (
    ContainerInvocation,
    ContainerLimits,
    SandboxArtifactPolicy,
    SandboxFailureReason,
    SandboxOutcome,
    SandboxRequest,
    SandboxRunner,
)
from agent_service.infrastructure.sandbox.docker_runner import (
    HostCliDockerExecutor,
    SandboxContainerReaper,
    SandboxPolicy,
    build_docker_run_argv,
)
from tests.agent_sandbox._sandbox_support import docker_cli, sandbox_image

pytestmark = pytest.mark.docker_required

SELF_TIMEOUT_SECONDS = 3
KILL_GRACE_SECONDS = 2


def _unique_name(prefix: str) -> str:
    return f'agent-sandbox-t1-{prefix}-{uuid.uuid4().hex[:10]}'


def _container_running(name: str) -> bool:
    result = docker_cli(
        'inspect', '--format', '{{.State.Running}}', name, timeout=30
    )
    return result.returncode == 0 and result.stdout.strip().lower() == 'true'


def _container_exists(name: str) -> bool:
    return docker_cli('container', 'inspect', '--format', '{{.Id}}', name, timeout=30).returncode == 0


def _container_exit_code(name: str) -> int | None:
    result = docker_cli('inspect', '--format', '{{.State.ExitCode}}', name, timeout=30)
    if result.returncode != 0:
        return None
    try:
        return int(result.stdout.strip())
    except ValueError:
        return None


def _wait_gone(name: str, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not _container_exists(name):
            return True
        time.sleep(0.2)
    return not _container_exists(name)


def _make_invocation(tmp_path: Path, skill: Path, limits: ContainerLimits) -> ContainerInvocation:
    work = tmp_path / f'work_{uuid.uuid4().hex[:8]}'
    work.mkdir()
    return ContainerInvocation(
        name=_unique_name('lifecycle'),
        skill_root=str(skill),
        work_dir=str(work),
        script_relative_path='scripts/main.py',
        limits=limits,
    )


# ── 1. 异常路径也回收容器 ────────────────────────────────────


def test_cleanup_runs_on_inspect_exception(make_skill, tmp_path: Path, docker_available) -> None:
    """执行器在收尾阶段抛异常时，finally 仍必须 ``docker rm -f``。"""
    from agent_service.infrastructure.sandbox.docker_runner import HostCliDockerExecutor

    skill = make_skill({'main.py': 'print("done")\n'})
    invocation = _make_invocation(tmp_path, skill, ContainerLimits(timeout_seconds=30))

    class _ExplodingInspectExecutor(HostCliDockerExecutor):
        def _inspect_state(self, name: str):
            raise RuntimeError('inspect 爆炸（模拟收尾阶段异常）')

    executor = _ExplodingInspectExecutor(limits=ContainerLimits(timeout_seconds=30))
    try:
        with pytest.raises(RuntimeError):
            executor.run(invocation)
    finally:
        docker_cli('rm', '--force', invocation.name, timeout=30)
    assert not _container_exists(invocation.name), '异常路径也必须回收容器'


# ── 2. 容器自限：宿主执行器被杀后容器自己结束 ────────────────


def test_container_stops_itself_after_executor_killed(
    make_skill, tmp_path: Path, docker_available
) -> None:
    skill = make_skill({'main.py': 'import time\ntime.sleep(300)\nprint("never")\n'})
    invocation = _make_invocation(
        tmp_path, skill, ContainerLimits(timeout_seconds=SELF_TIMEOUT_SECONDS)
    )
    argv = build_docker_run_argv(
        invocation, 'docker', container_kill_grace_seconds=KILL_GRACE_SECONDS
    )
    process = subprocess.Popen(
        argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline and not _container_running(invocation.name):
            if process.poll() is not None:
                break
            time.sleep(0.2)
        assert _container_running(invocation.name), '容器未起来，用例前提不成立'

        # 模拟 runner / agent_service 崩溃：执行器进程被杀，容器留在 daemon 里。
        process.kill()
        process.wait(timeout=30)
        killed_at = time.monotonic()

        deadline = killed_at + SELF_TIMEOUT_SECONDS + KILL_GRACE_SECONDS + 30
        while time.monotonic() < deadline and _container_running(invocation.name):
            time.sleep(0.2)
        elapsed = time.monotonic() - killed_at
        assert not _container_running(invocation.name), (
            f'执行器被杀后容器仍在运行（{elapsed:.1f}s）'
        )
        # GNU timeout 自限退出码 124；-k 兜底可能是 137。两者都应判超时。
        assert _container_exit_code(invocation.name) in (124, 137), (
            f'容器自限退出码异常：{_container_exit_code(invocation.name)}'
        )
    finally:
        docker_cli('rm', '--force', invocation.name, timeout=30)
    assert _wait_gone(invocation.name, 30)


def test_self_timeout_maps_to_budget_exceeded(make_skill, run_script) -> None:
    """runner 存活时，容器自限退出（124）仍按超时判 BUDGET_EXCEEDED。"""
    skill = make_skill({'main.py': 'import time\ntime.sleep(300)\n'})
    result = run_script(skill, limits=ContainerLimits(timeout_seconds=SELF_TIMEOUT_SECONDS))
    assert result.outcome is SandboxOutcome.BUDGET_EXCEEDED, result.detail
    assert result.reason in (SandboxFailureReason.TIMEOUT,)
    assert result.timed_out is True
    assert result.container_id, '超时路径也必须记录 container_id（P3-1）'


# ── 3. 孤儿容器回收 ─────────────────────────────────────────


def test_reaper_removes_stale_container(docker_available) -> None:
    """按 label 回收创建时间超过阈值的容器，并记录日志。"""
    selector_key = f'agent-sandbox-reaper-{uuid.uuid4().hex[:8]}'
    name = _unique_name('reaper')
    created = docker_cli(
        'run', '--name', name,
        '--label', 'agent-sandbox=t1',
        '--label', f'{selector_key}=1',
        '--network', 'none',
        '--user', '65534:65534',
        sandbox_image(), 'true',
        timeout=120,
    )
    assert created.returncode == 0, created.stderr
    try:
        assert _container_exists(name), '被回收的容器必须先在 docker ps -a 里'
        reaper = SandboxContainerReaper(
            timeout_seconds=0, grace_seconds=0, interval_seconds=1,
            label_selector=f'{selector_key}=1',
        )
        reaped = reaper.reap_once()
        assert name in reaped, f'孤儿容器未被回收：{reaped}'
        assert not _container_exists(name), '回收后容器必须从 docker ps -a 消失'
    finally:
        docker_cli('rm', '--force', name, timeout=30)


def test_reaper_keeps_young_container(docker_available) -> None:
    """未超龄的容器不能被回收（在跑的容器不会被误杀）。"""
    selector_key = f'agent-sandbox-reaper-{uuid.uuid4().hex[:8]}'
    name = _unique_name('young')
    created = docker_cli(
        'run', '--detach', '--name', name,
        '--label', 'agent-sandbox=t1',
        '--label', f'{selector_key}=1',
        '--network', 'none',
        '--user', '65534:65534',
        docker_available, 'sleep', '300',
        timeout=120,
    )
    assert created.returncode == 0, created.stderr
    try:
        reaper = SandboxContainerReaper(
            timeout_seconds=60, grace_seconds=60, interval_seconds=1,
            label_selector=f'{selector_key}=1',
        )
        assert reaper.reap_once() == [], '未超龄容器被误回收'
        assert _container_running(name)
    finally:
        docker_cli('rm', '--force', name, timeout=30)


# ── 4. 正常规格的生效限额 = runner 配置（单一口径） ────────────


def test_default_spec_effective_limits(make_skill, tmp_path: Path, docker_available) -> None:
    """正常规格进容器后，实际生效的加固参数与限额必须与 runner 配置一致。"""
    skill = make_skill({'main.py': 'import time\ntime.sleep(60)\n'})
    invocation = _make_invocation(tmp_path, skill, ContainerLimits())
    argv = build_docker_run_argv(
        invocation, 'docker', container_kill_grace_seconds=5
    )
    process = subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline and not _container_running(invocation.name):
            if process.poll() is not None:
                break
            time.sleep(0.2)
        assert _container_running(invocation.name), '容器未起来，用例前提不成立'
        inspected = docker_cli(
            'inspect', '--format',
            '{{.Config.User}}|{{.HostConfig.NetworkMode}}|{{.HostConfig.ReadonlyRootfs}}'
            '|{{.HostConfig.Memory}}|{{.HostConfig.NanoCpus}}|{{.HostConfig.PidsLimit}}'
            '|{{.HostConfig.CapDrop}}',
            invocation.name, timeout=30,
        )
        assert inspected.returncode == 0, inspected.stderr
        user, network, readonly, memory, nano_cpus, pids, cap_drop = (
            inspected.stdout.strip().split('|')
        )
        assert user == '65534:65534'
        assert network == 'none'
        assert readonly == 'true'
        assert int(memory) == 512 * 1024 * 1024
        assert int(nano_cpus) == 1_000_000_000
        assert int(pids) == 128
        assert 'ALL' in cap_drop
    finally:
        process.kill()
        process.wait(timeout=30)
        docker_cli('rm', '--force', invocation.name, timeout=30)


# ── 5. 运行中 /work 容量巡检（P2-3） ────────────────────────


WORK_FLOOD_SCRIPT = r'''
import pathlib, time
path = pathlib.Path('/work/big.bin')
with path.open('wb') as handle:
    end = time.time() + 30
    while time.time() < end:
        handle.write(b'x' * 65536)
        handle.flush()
        time.sleep(0.01)
'''


def test_work_dir_limit_terminates_container(make_skill, tmp_path: Path) -> None:
    """运行中 /work 超限即 terminate，并按资源超限收口（不等容器自己结束）。"""
    skill = make_skill({'main.py': WORK_FLOOD_SCRIPT})
    limits = ContainerLimits(timeout_seconds=60)
    policy = SandboxPolicy(
        limits=limits,
        allowed_images=frozenset({sandbox_image()}),
        allowed_interpreters=frozenset({'python3'}),
        skills_root=str(tmp_path),
        work_limit_bytes=1024 * 1024,
    )
    executor = HostCliDockerExecutor(limits=limits, policy=policy)
    runner = SandboxRunner(
        executor,
        artifact_policy=SandboxArtifactPolicy(),
        work_root=tmp_path / 'workroot',
    )
    started = time.monotonic()
    result = runner.run_trusted_script(
        SandboxRequest(
            skill_name='work-limit', skill_root=skill, script='scripts/main.py'
        )
    )
    elapsed = time.monotonic() - started
    assert result.outcome is SandboxOutcome.BUDGET_EXCEEDED, result.detail
    assert result.reason is SandboxFailureReason.RESOURCE_LIMIT_EXCEEDED
    assert elapsed < 30, f'/work 超限未被运行中巡检拦住：{elapsed:.1f}s'
    assert result.container_id, '容量超限路径也要记录 container_id'
