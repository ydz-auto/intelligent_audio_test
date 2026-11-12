# -*- coding: utf-8 -*-
"""T1 沙箱测试夹具（INT-2455）。

docker 相关用例在本机无 Docker / 缺沙箱镜像时 skip（并给出原因）；CI 与 M3
门禁必须预置 Docker + 镜像后再跑，命令见 ``tests/agent_sandbox/README.md``。
"""

from __future__ import annotations

import shutil
import subprocess
import uuid
from pathlib import Path

import pytest

from agent_service.application.sandbox_runner import (
    ContainerLimits,
    SandboxArtifactPolicy,
    SandboxRequest,
    SandboxResult,
    SandboxRunner,
)
from tests.agent_sandbox._sandbox_support import RecordingDockerExecutor, docker_cli

SANDBOX_IMAGE = 'python:3.11-slim'
DEFAULT_TEST_TIMEOUT_SECONDS = 30


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        'markers', 'docker_required: 需要 Docker daemon 与本地沙箱镜像（CI/M3 门禁）'
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
