# -*- coding: utf-8 -*-
"""T1 沙箱规格白名单（INT-2494 / INT-2485 审计 P1-2）——不需要 Docker。

审计实测的四类绕过都在这里回归：

1. ``container_user='0:65534'`` / ``'000'`` / ``'root'`` → 容器内 uid=0；
2. ``image='--privileged'`` → 参数注入成 docker 全局参数；
3. ``script_relative_path='../../bin/sh'`` → 逃出 skill；
4. payload 的 memory/cpus/pids 把限额拉大（一个进程两套口径）。

判据是 runner 侧（``SandboxRunnerServer``）返回 400，而不是透传给 docker。
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Mapping

import pytest

from agent_service.application.sandbox_runner import (
    ContainerInvocation,
    ContainerLimits,
    SandboxConfigurationError,
)
from agent_service.infrastructure.sandbox.docker_runner import (
    RUNNER_API_PATH,
    HostCliDockerExecutor,
    SandboxContainerReaper,
    SandboxPolicy,
    build_docker_run_argv,
    parse_memory_bytes,
    validate_limits_within,
    validate_script_relative_path,
)
from agent_service.infrastructure.sandbox.runner_service import SandboxRunnerServer

TEST_TOKEN = 'it-token-' + uuid.uuid4().hex[:12]
DEFAULT_IMAGE = 'python:3.11-slim'


class _NeverRunExecutor(HostCliDockerExecutor):
    """只做校验的 runner 执行器：走到 run 说明规格没被拦住，直接判失败。"""

    def run(self, invocation: ContainerInvocation):  # pragma: no cover - 不该到这里
        raise AssertionError(f'非法规格竟然进入执行：{invocation.name}')


@pytest.fixture
def sidecar(tmp_path: Path):
    server = SandboxRunnerServer(
        executor=_NeverRunExecutor(policy=SandboxPolicy(
            limits=ContainerLimits(),
            allowed_images=frozenset({DEFAULT_IMAGE}),
            allowed_interpreters=frozenset({'python3'}),
            skills_root=str(tmp_path),
        )),
        token=TEST_TOKEN,
        bind_host='127.0.0.1',
        port=0,
    ).start_background()
    yield server
    server.stop()


@pytest.fixture
def skill_work(tmp_path: Path) -> tuple[Path, Path]:
    skill = tmp_path / 'skills' / f'demo_{uuid.uuid4().hex[:6]}'
    (skill / 'scripts').mkdir(parents=True)
    (skill / 'scripts' / 'main.py').write_text('print("hi")\n', encoding='utf-8')
    work = tmp_path / 'work'
    work.mkdir()
    return skill, work


def _payload(skill: Path, work: Path, **overrides) -> bytes:
    invocation: dict = {
        'name': 'agent-sandbox-t1-spec-' + uuid.uuid4().hex[:8],
        'skill_root': str(skill),
        'work_dir': str(work),
        'script_relative_path': 'scripts/main.py',
        'args': [],
        'env': {},
        'limits': {},
    }
    invocation.update(overrides)
    return json.dumps({'protocol_version': 1, 'invocation': invocation}).encode('utf-8')


def _post(url: str, body: bytes):
    from urllib import error as urlerror
    from urllib import request as urlrequest

    request = urlrequest.Request(
        url + RUNNER_API_PATH,
        data=body,
        headers={'Content-Type': 'application/json', 'X-Sandbox-Runner-Token': TEST_TOKEN},
        method='POST',
    )
    try:
        with urlrequest.urlopen(request, timeout=10) as response:
            return response.status, response.read()
    except urlerror.HTTPError as exc:
        return exc.code, exc.read()


@pytest.mark.parametrize(
    'limits',
    [
        {'container_user': '0:65534'},
        {'container_user': '000'},
        {'container_user': '0'},
        {'container_user': 'root'},
        {'image': '--privileged'},
        {'image': 'alpine:3.20'},
        {'interpreter': '/bin/sh'},
        {'interpreter': '--help'},
        {'memory': '2g', 'memory_swap': '2g'},
        {'cpus': 2.0},
        {'pids_limit': 512},
        {'tmpfs_size': '512m'},
        {'timeout_seconds': 600},
        {'output_limit_bytes': 64 * 1024 * 1024},
    ],
)
def test_runner_rejects_illegal_limits(sidecar, skill_work, limits: Mapping) -> None:
    skill, work = skill_work
    status, body = _post(sidecar.url, _payload(skill, work, limits=dict(limits)))
    assert status == 400, body
    assert b'error' in body


@pytest.mark.parametrize(
    'script',
    ['../../bin/sh', '/bin/sh', 'C:/Windows/system32/cmd.exe', 'scripts/../../bin/sh',
     'other/main.py', 'scripts/..', '', 'scripts//../x.py'],
)
def test_runner_rejects_illegal_script_path(sidecar, skill_work, script: str) -> None:
    skill, work = skill_work
    status, body = _post(sidecar.url, _payload(skill, work, script_relative_path=script))
    assert status == 400, body


def test_runner_rejects_skill_root_outside_allowed(sidecar, tmp_path: Path) -> None:
    outside = tmp_path.parent / f'outside_{uuid.uuid4().hex[:6]}'
    (outside / 'scripts').mkdir(parents=True)
    (outside / 'scripts' / 'main.py').write_text('print(1)\n', encoding='utf-8')
    work = tmp_path / 'work_outside'
    work.mkdir()
    status, body = _post(sidecar.url, _payload(outside, work))
    assert status == 400, body
    assert b'skill_root' in body


def test_runner_accepts_spec_within_limits(skill_work) -> None:
    """白名单内的更严格规格可以通过校验（真正执行由 docker 用例覆盖）。"""
    skill, work = skill_work
    invocation = ContainerInvocation(
        name='agent-sandbox-t1-spec-ok',
        skill_root=str(skill),
        work_dir=str(work),
        script_relative_path='scripts/main.py',
        limits=ContainerLimits(
            memory='256m', memory_swap='256m', cpus=0.5, pids_limit=32,
            timeout_seconds=10, output_limit_bytes=64 * 1024,
        ),
    )
    # 不抛异常即通过
    _NeverRunExecutor(policy=SandboxPolicy(
        limits=ContainerLimits(),
        allowed_images=frozenset({DEFAULT_IMAGE}),
        allowed_interpreters=frozenset({'python3'}),
        skills_root=str(skill.parent),
    )).validate(invocation)


# ── 纯函数级回归（无需 sidecar） ─────────────────────────────


@pytest.mark.parametrize(
    ('text', 'expected'),
    [('512m', 512 * 1024 * 1024), ('2g', 2 * 1024 ** 3), ('1024k', 1024 * 1024),
     ('100', 100), ('1.5g', int(1.5 * 1024 ** 3)), ('64MiB', 64 * 1024 * 1024)],
)
def test_parse_memory_bytes(text: str, expected: int) -> None:
    assert parse_memory_bytes(text) == expected


@pytest.mark.parametrize('bad', ['', 'abc', '512x', '-1m', '1,5g'])
def test_parse_memory_bytes_rejects_garbage(bad: str) -> None:
    with pytest.raises(SandboxConfigurationError):
        parse_memory_bytes(bad)


def test_limits_may_only_tighten() -> None:
    runner_limits = ContainerLimits(memory='512m', cpus=1.0, pids_limit=128)
    validate_limits_within(
        runner_limits,
        ContainerLimits(memory='256m', memory_swap='256m', cpus=0.5, pids_limit=32),
    )
    with pytest.raises(SandboxConfigurationError):
        validate_limits_within(runner_limits, ContainerLimits(memory='2g'))
    with pytest.raises(SandboxConfigurationError):
        validate_limits_within(runner_limits, ContainerLimits(cpus=2.0))
    with pytest.raises(SandboxConfigurationError):
        validate_limits_within(runner_limits, ContainerLimits(pids_limit=512))


def test_build_argv_revalidates_script_path(tmp_path: Path) -> None:
    """纵深防御：即使应用层被绕过，argv 构造也拒绝 ``../../bin/sh``。"""
    skill = tmp_path / 'skills' / 'demo'
    (skill / 'scripts').mkdir(parents=True)
    work = tmp_path / 'work'
    work.mkdir()
    invocation = ContainerInvocation(
        name='agent-sandbox-t1-inject',
        skill_root=str(skill),
        work_dir=str(work),
        script_relative_path='../../bin/sh',
    )
    with pytest.raises(SandboxConfigurationError):
        build_docker_run_argv(invocation, 'docker')
    with pytest.raises(SandboxConfigurationError):
        validate_script_relative_path('../../bin/sh')


def test_reaper_default_selector_is_t1_label() -> None:
    reaper = SandboxContainerReaper(timeout_seconds=60, grace_seconds=30, interval_seconds=30)
    assert reaper.label_selector == 'agent-sandbox=t1'
    assert reaper.threshold_seconds == 90


def test_reaper_threshold_and_interval_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('AGENT_SANDBOX_ORPHAN_GRACE_SECONDS', '7')
    monkeypatch.setenv('AGENT_SANDBOX_REAPER_INTERVAL_SECONDS', '3')
    reaper = SandboxContainerReaper(timeout_seconds=10)
    assert reaper.threshold_seconds == 17
    assert reaper.interval_seconds == 3
