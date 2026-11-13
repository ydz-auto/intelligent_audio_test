# -*- coding: utf-8 -*-
"""runner 配置口径（INT-2494 打回项：启动回归 + Skill 根白名单 fail-closed）。

审计 / 复测打回的两个阻塞项：

1. 独立 runner 只带沙箱自身 env 启动即崩：``_configured_skills_root`` 回落到
   ``agent_service.config``，而 ``shared.BaseConfig`` 在类定义期就要求
   ``DATABASE_URL`` / ``OSS_*``。runner 是只持有 Docker 的 sidecar，不该被业务
   配置绑架。
2. Skill 根白名单存在 fail-open：允许根解析不出来时返回 ``None``，``validate_invocation``
   的 ``if policy.skills_root:`` 就整段跳过 —— 任意宿主路径都能被只读挂进容器。

两条断言：缺省时用本地默认 ``<项目根>/skills``；确定不了时按配置错误拒绝。
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path
from urllib import error as urlerror
from urllib import request as urlrequest

import pytest

from agent_service.application.sandbox_runner import (
    ContainerInvocation,
    ContainerLimits,
    SandboxConfigurationError,
)
from agent_service.infrastructure.sandbox.docker_runner import (
    DEFAULT_SKILLS_ROOT,
    HostCliDockerExecutor,
    SandboxPolicy,
    _configured_skills_root,
    validate_invocation,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
#: 启动子进程只给这些系统变量：与 ``DATABASE_URL`` / ``OSS_*`` / 沙箱 env 无关。
_OS_ENV_KEYS = (
    'PATH', 'SystemRoot', 'SYSTEMROOT', 'COMSPEC', 'PATHEXT', 'TEMP', 'TMP',
    'HOME', 'USERPROFILE', 'LOCALAPPDATA', 'APPDATA',
)
RUNNER_START_TIMEOUT_SECONDS = 60


def _bare_env(**overrides: str) -> dict[str, str]:
    """只带进程运行必需的系统变量，明确不给 DATABASE_URL / OSS_* / AGENT_SKILLS_ROOT。"""
    env = {key: value for key, value in os.environ.items() if key in _OS_ENV_KEYS}
    env['PYTHONPATH'] = str(PROJECT_ROOT)
    env.update(overrides)
    return env


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return int(sock.getsockname()[1])


# ── 阻塞项 1：裸 runner 启动 ───────────────────────────────────


def test_default_skills_root_needs_no_business_config() -> None:
    """不设 AGENT_SKILLS_ROOT、不给 DB/OSS 凭据：默认根可算，且不 import 业务配置。"""
    code = (
        'import sys\n'
        'from agent_service.infrastructure.sandbox.docker_runner import _configured_skills_root\n'
        'print(_configured_skills_root())\n'
        'assert "agent_service.config.config" not in sys.modules, "不应 import agent_service.config"\n'
    )
    result = subprocess.run(
        [sys.executable, '-c', code],
        cwd=str(PROJECT_ROOT),
        env=_bare_env(),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    assert Path(result.stdout.strip()) == PROJECT_ROOT / 'skills'
    assert Path(DEFAULT_SKILLS_ROOT) == PROJECT_ROOT / 'skills'


def test_runner_process_starts_with_only_sandbox_env() -> None:
    """复测命令的回归：只给沙箱 env，runner 必须能起来并响应 /healthz。"""
    port = _free_port()
    env = _bare_env(
        AGENT_SANDBOX_RUNNER_TOKEN='probe-' + uuid.uuid4().hex[:8],
        AGENT_SANDBOX_RUNNER_PORT=str(port),
        AGENT_SANDBOX_RUNNER_BIND='127.0.0.1',
        # 本机可能同时有别的沙箱测试在跑：把孤儿阈值拉到很大，启动回收不会误杀
        # 别人正在用的 agent-sandbox=t1 容器。
        AGENT_SANDBOX_TIMEOUT_SECONDS='3600',
        AGENT_SANDBOX_ORPHAN_GRACE_SECONDS='3600',
    )
    process = subprocess.Popen(
        [sys.executable, '-m', 'agent_service.infrastructure.sandbox.runner_service'],
        cwd=str(PROJECT_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    try:
        deadline = time.monotonic() + RUNNER_START_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            if process.poll() is not None:
                output = process.stdout.read().decode('utf-8', errors='replace') \
                    if process.stdout is not None else ''
                pytest.fail(f'runner 进程启动即退出（exit={process.returncode}）：{output[-2000:]}')
            try:
                with urlrequest.urlopen(
                    f'http://127.0.0.1:{port}/healthz', timeout=2
                ) as response:
                    if response.status == 200:
                        break
            except (urlerror.URLError, OSError):
                time.sleep(0.2)
        else:
            pytest.fail(f'runner 在 {RUNNER_START_TIMEOUT_SECONDS}s 内未就绪（/healthz 不通）')
    finally:
        if process.poll() is None:
            process.terminate()
        try:
            process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=30)
        if process.stdout is not None:
            process.stdout.close()


# ── 阻塞项 2：允许根 fail closed ───────────────────────────────


def test_host_cli_executor_defaults_to_project_skills_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv('AGENT_SKILLS_ROOT', raising=False)
    executor = HostCliDockerExecutor()
    assert Path(executor.policy.skills_root) == PROJECT_ROOT / 'skills'


def test_host_cli_executor_uses_absolute_env_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv('AGENT_SKILLS_ROOT', str(tmp_path))
    executor = HostCliDockerExecutor()
    assert Path(executor.policy.skills_root) == tmp_path.resolve()


def test_relative_skills_root_env_is_a_configuration_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """无法确定绝对根时明确失败，不返回 None 让白名单失效。"""
    monkeypatch.setenv('AGENT_SKILLS_ROOT', 'relative/skills')
    with pytest.raises(SandboxConfigurationError):
        _configured_skills_root()
    with pytest.raises(SandboxConfigurationError):
        SandboxPolicy.from_env()


def test_policy_rejects_missing_skills_root() -> None:
    """构造期就 fail closed：``skills_root=None`` 不得退化成「不校验」。"""
    with pytest.raises(SandboxConfigurationError):
        SandboxPolicy(
            limits=ContainerLimits(),
            allowed_images=frozenset({'python:3.11-slim'}),
            allowed_interpreters=frozenset({'python3'}),
            skills_root=None,  # type: ignore[arg-type]
        )


def test_default_root_still_enforces_skill_whitelist(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """缺省根走本地默认时，根外的 skill_root 仍被拒绝（不再跳过整段校验）。"""
    monkeypatch.delenv('AGENT_SKILLS_ROOT', raising=False)
    policy = SandboxPolicy.from_env()
    assert policy.skills_root == DEFAULT_SKILLS_ROOT

    skill = tmp_path / 'skills' / f'demo_{uuid.uuid4().hex[:6]}'
    (skill / 'scripts').mkdir(parents=True)
    work = tmp_path / 'work'
    work.mkdir()
    invocation = ContainerInvocation(
        name='agent-sandbox-t1-cfg-' + uuid.uuid4().hex[:8],
        skill_root=str(skill),
        work_dir=str(work),
        script_relative_path='scripts/main.py',
    )
    with pytest.raises(SandboxConfigurationError, match='skill_root'):
        validate_invocation(invocation, policy)
