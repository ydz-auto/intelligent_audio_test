# -*- coding: utf-8 -*-
"""沙箱测试夹具：T1（INT-2455）+ T2（INT-2489）。

docker 相关用例在本机无 Docker / 缺沙箱镜像 / 缺 gVisor ``runsc`` 时 skip 并
给出原因与手工执行命令（门禁脚本把 skip 判为失败，见 ``scripts/sandbox_gate.py``）。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import uuid
from dataclasses import replace
from pathlib import Path

import pytest

from agent_service.application.sandbox_runner import (
    ContainerLimits,
    SandboxArtifactPolicy,
    SandboxRequest,
    SandboxResult,
    SandboxRunner,
    SandboxRuntimeAvailability,
    T2RunnerOptions,
    T2SandboxRequest,
)
from agent_service.infrastructure.sandbox.policy import T2Policy, load_t2_policy
from agent_service.infrastructure.sandbox.t2_runner import probe_t2_runtime
from tests.agent_sandbox._sandbox_support import (
    RecordingDockerExecutor,
    RecordingT2Executor,
    docker_cli,
)

SANDBOX_IMAGE = 'python:3.11-slim'
DEFAULT_TEST_TIMEOUT_SECONDS = 30

#: T2 镜像（含 pytest 的镜像可由 AGENT_SANDBOX_T2_IMAGE 覆盖；测试只用 stdlib）。
T2_SANDBOX_IMAGE = os.environ.get('AGENT_SANDBOX_T2_IMAGE', SANDBOX_IMAGE)

#: T2 用例在无 runsc 时的手工执行命令（skip 原因里必须给出，不许静默跳过）。
T2_MANUAL_COMMAND = (
    'python -m pytest tests/agent_sandbox/test_t2_escape.py -q '
    '# 需 Linux 宿主 + Docker + 已注册 runsc（gVisor），'
    '或在 CI 用 docker-in-docker 预置 gVisor 后执行'
)


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        'markers', 'docker_required: 需要 Docker daemon 与本地沙箱镜像（CI/M3 门禁）'
    )
    config.addinivalue_line(
        'markers',
        't2_required: 需要 Docker 且已注册 gVisor runsc（无 runsc 时 skip 并给出手工命令）',
    )


@pytest.fixture(scope='session')
def docker_available() -> str:
    """docker daemon 可用且沙箱镜像在本地；否则 skip 并说明原因。"""
    if shutil.which('docker') is None:
        pytest.skip('未找到 docker CLI：T1 沙箱用例需要 Docker Desktop（Linux 容器）')
    try:
        info = docker_cli('info', '--format', '{{.ServerVersion}}', timeout=30)
    except (OSError, subprocess.TimeoutExpired) as exc:
        pytest.skip(f'docker daemon 不可用：{exc}')
    if info.returncode != 0:
        pytest.skip(f'docker daemon 不可用：{info.stderr.strip()[:200]}')
    image = docker_cli('image', 'inspect', '--format', '{{.Id}}', SANDBOX_IMAGE, timeout=30)
    if image.returncode != 0:
        pytest.skip(
            f'沙箱镜像 {SANDBOX_IMAGE} 不在本地（门禁需先 `docker pull {SANDBOX_IMAGE}`）'
        )
    return SANDBOX_IMAGE


def _t2_policy(**overrides) -> T2Policy:
    """T2 测试策略：yaml 默认值（不读宿主 AGENT_SANDBOX_T2_*）+ 用例覆盖。"""
    base = load_t2_policy(environ={})
    return replace(base, **overrides)


@pytest.fixture(scope='session')
def t2_runtime() -> SandboxRuntimeAvailability:
    """真实探测 gVisor：缺 docker / 缺 runsc 时 skip 并给出明确原因与手工命令。"""
    if shutil.which('docker') is None:
        pytest.skip(f'未找到 docker CLI；T2 需要 Docker + gVisor。手工执行：{T2_MANUAL_COMMAND}')
    try:
        availability = probe_t2_runtime(_t2_policy())
    except (OSError, subprocess.TimeoutExpired) as exc:
        pytest.skip(f'docker 探测失败：{exc}。手工执行：{T2_MANUAL_COMMAND}')
    if not availability.available:
        pytest.skip(f'{availability.detail}。手工执行：{T2_MANUAL_COMMAND}')
    return availability


@pytest.fixture
def t2_executor(t2_runtime: SandboxRuntimeAvailability) -> RecordingT2Executor:
    """真实 T2 执行器（容器超时 30s）+ 用例结束后的「容器用完即毁」断言。"""
    limits = ContainerLimits(
        image=T2_SANDBOX_IMAGE,
        timeout_seconds=DEFAULT_TEST_TIMEOUT_SECONDS,
    )
    executor = RecordingT2Executor(
        _t2_policy(container_limits=limits, total_timeout_seconds=180),
    )
    yield executor
    for name in executor.container_names:
        inspect = docker_cli('container', 'inspect', '--format', '{{.Name}}', name, timeout=30)
        assert inspect.returncode != 0, f'T2 沙箱容器未销毁：{name}'


@pytest.fixture
def make_t2_executor(t2_runtime: SandboxRuntimeAvailability):
    """按用例资源上限构造 T2 执行器（内存/PID 等需要缩小的资源用例）。"""
    created: list[RecordingT2Executor] = []

    def _make(limits: ContainerLimits | None = None) -> RecordingT2Executor:
        executor = RecordingT2Executor(_t2_policy(
            container_limits=limits or ContainerLimits(
                image=T2_SANDBOX_IMAGE, timeout_seconds=DEFAULT_TEST_TIMEOUT_SECONDS
            ),
            total_timeout_seconds=180,
        ))
        created.append(executor)
        return executor

    yield _make
    for executor in created:
        for name in executor.container_names:
            inspect = docker_cli(
                'container', 'inspect', '--format', '{{.Name}}', name, timeout=30
            )
            assert inspect.returncode != 0, f'T2 沙箱容器未销毁：{name}'


@pytest.fixture
def run_t2(tmp_path: Path, t2_executor: RecordingT2Executor):
    """通过真实 gVisor 沙箱执行一份代码包 + 阶段计划，返回 ``SandboxResult``。"""

    def _run(
        files: dict[str, str],
        phases: tuple,
        *,
        code_source: str = 'test:driver_propose',
        options: T2RunnerOptions | None = None,
        artifact_policy: SandboxArtifactPolicy | None = None,
        artifact_repository=None,
        artifact_root: Path | None = None,
        executor: RecordingT2Executor | None = None,
        **request_kwargs,
    ) -> SandboxResult:
        runner = SandboxRunner(
            untrusted_executor=executor or t2_executor,
            artifact_policy=artifact_policy or SandboxArtifactPolicy(),
            work_root=tmp_path / 'workroot',
            t2_options=options or T2RunnerOptions(total_timeout_seconds=180),
            artifact_repository=artifact_repository,
            artifact_root=artifact_root,
        )
        return runner.run_untrusted_code(T2SandboxRequest(
            code_source=code_source,
            files=files,
            phases=phases,
            **request_kwargs,
        ))

    return _run


@pytest.fixture
def recorded_executor(docker_available: str):
    """测试用执行器 + 用例结束后的「容器用完即毁」断言。"""
    executor = RecordingDockerExecutor(
        limits=ContainerLimits(timeout_seconds=DEFAULT_TEST_TIMEOUT_SECONDS)
    )
    yield executor
    for name in executor.container_names:
        inspect = docker_cli('container', 'inspect', '--format', '{{.Name}}', name, timeout=30)
        assert inspect.returncode != 0, f'沙箱容器未销毁：{name}'


@pytest.fixture
def make_skill(tmp_path: Path):
    """在临时目录里造一个 Skill（scripts/ 下写脚本），返回 Skill 根目录。"""

    def _make(scripts: dict[str, str], name: str | None = None) -> Path:
        skill_name = name or f'skill_{uuid.uuid4().hex[:8]}'
        skill_root = tmp_path / 'skills' / skill_name
        scripts_dir = skill_root / 'scripts'
        scripts_dir.mkdir(parents=True)
        for filename, source in scripts.items():
            target = scripts_dir / filename
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(source, encoding='utf-8')
        return skill_root

    return _make


@pytest.fixture
def run_script(tmp_path: Path, recorded_executor: RecordingDockerExecutor):
    """通过真实 Docker 执行一次 T1 脚本，返回 ``SandboxResult``。"""

    def _run(
        skill_root: Path,
        script: str = 'scripts/main.py',
        *,
        limits: ContainerLimits | None = None,
        args: tuple[str, ...] = (),
        env: dict[str, str] | None = None,
        policy: SandboxArtifactPolicy | None = None,
        work_root: Path | None = None,
    ) -> SandboxResult:
        executor = recorded_executor
        if limits is not None:
            executor = RecordingDockerExecutor(limits=limits)
            # 复用同一个容器名校验集合
            executor.container_names = recorded_executor.container_names
        runner = SandboxRunner(
            executor,
            artifact_policy=policy or SandboxArtifactPolicy(),
            work_root=work_root or (tmp_path / 'workroot'),
        )
        return runner.run_trusted_script(
            SandboxRequest(
                skill_name=f'skill_{uuid.uuid4().hex[:8]}',
                skill_root=skill_root,
                script=script,
                args=tuple(args),
                env=dict(env or {}),
            )
        )

    return _run
