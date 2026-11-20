# -*- coding: utf-8 -*-
"""T1 沙箱契约单测（INT-2455）——不需要 Docker。

覆盖：加固参数、挂载只读/可写边界、凭证拒收、路径穿越、失败不静默、产物
校验、结果映射与配置默认值。真实容器行为见 ``test_sandbox_execution.py``。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_service.application.sandbox_runner import (
    ContainerExecution,
    ContainerInvocation,
    ContainerLimits,
    SandboxArtifactPolicy,
    SandboxConfigurationError,
    SandboxFailureReason,
    SandboxOutcome,
    SandboxRequest,
    SandboxRunner,
)
from agent_service.domain.enums import SandboxTier
from agent_service.infrastructure.sandbox import docker_runner


# ── 假执行器：只记录请求并按剧本返回 ──────────────────────────


class FakeExecutor:
    def __init__(self, execution: ContainerExecution | None = None, limits: ContainerLimits | None = None):
        self.limits = limits or ContainerLimits()
        self.execution = execution or ContainerExecution(exit_code=0)
        self.invocations: list[ContainerInvocation] = []
        self.on_run = None

    def run(self, invocation: ContainerInvocation) -> ContainerExecution:
        self.invocations.append(invocation)
        if self.on_run is not None:
            return self.on_run(invocation)
        return self.execution


@pytest.fixture
def skill_root(tmp_path: Path) -> Path:
    root = tmp_path / 'skills' / 'demo'
    (root / 'scripts').mkdir(parents=True)
    (root / 'scripts' / 'main.py').write_text('print("hi")\n', encoding='utf-8')
    (root / 'SKILL.md').write_text('---\nname: demo\n---\n', encoding='utf-8')
    return root


def _run(skill_root: Path, executor: FakeExecutor, **kwargs) -> object:
    runner = SandboxRunner(executor, artifact_policy=kwargs.pop('policy', None))
    kwargs.setdefault('script', 'scripts/main.py')
    request = SandboxRequest(skill_name='demo', skill_root=skill_root, **kwargs)
    return runner.run_trusted_script(request)


# ── 容器加固参数（方案 §7 逐条） ──────────────────────────────


def _invocation(tmp_path: Path) -> ContainerInvocation:
    skill = tmp_path / 'skill'
    work = tmp_path / 'work'
    skill.mkdir()
    work.mkdir()
    return ContainerInvocation(
        name='agent-sandbox-t1-demo-abc',
        skill_root=str(skill),
        work_dir=str(work),
        script_relative_path='scripts/main.py',
    )


def _argv(invocation: ContainerInvocation) -> list[str]:
    return docker_runner.build_docker_run_argv(invocation, 'docker')


def _flag_value(argv: list[str], flag: str) -> list[str]:
    return [argv[i + 1] for i, token in enumerate(argv[:-1]) if token == flag]


def test_command_hardening_flags_match_spec(tmp_path: Path) -> None:
    argv = _argv(_invocation(tmp_path))
    assert argv[:2] == ['docker', 'run']
    assert _flag_value(argv, '--network') == ['none']
    assert '--read-only' in argv
    assert _flag_value(argv, '--cap-drop') == ['ALL']
    assert _flag_value(argv, '--security-opt') == ['no-new-privileges']
    assert _flag_value(argv, '--pids-limit') == ['128']
    assert _flag_value(argv, '--memory') == ['512m']
    assert _flag_value(argv, '--memory-swap') == ['512m']
    assert _flag_value(argv, '--cpus') == ['1.0']
    assert any(v.startswith('/tmp:') and 'size=64m' in v for v in _flag_value(argv, '--tmpfs'))
    user = _flag_value(argv, '--user')[0]
    assert user not in ('0', '0:0', 'root'), '沙箱容器必须以非 root 运行'
    assert '--privileged' not in argv
    assert '--pid=host' not in argv
    assert '--network=host' not in argv


def test_mounts_only_skill_readonly_and_work_writable(tmp_path: Path) -> None:
    invocation = _invocation(tmp_path)
    argv = _argv(invocation)
    mounts = _flag_value(argv, '--mount')
    skill_mount = [m for m in mounts if 'target=/skill' in m]
    work_mount = [m for m in mounts if 'target=/work' in m]
    assert len(skill_mount) == 1 and skill_mount[0].endswith(',readonly')
    assert len(work_mount) == 1 and not work_mount[0].endswith(',readonly')
    assert len(mounts) == 2, '除 Skill 与 /work 外不得有其它挂载'


def test_no_docker_socket_anywhere(tmp_path: Path) -> None:
    invocation = _invocation(tmp_path)
    argv = _argv(invocation)
    assert not any('docker.sock' in token for token in argv)
    assert not any('docker.sock' in mount for mount in _flag_value(argv, '--mount'))


def test_docker_socket_path_is_rejected(tmp_path: Path) -> None:
    skill = tmp_path / 'docker.sock'
    skill.mkdir()
    work = tmp_path / 'work'
    work.mkdir()
    invocation = ContainerInvocation(
        name='agent-sandbox-t1-demo-abc',
        skill_root=str(skill),
        work_dir=str(work),
        script_relative_path='scripts/main.py',
    )
    with pytest.raises(SandboxConfigurationError):
        docker_runner.validate_invocation(invocation)


def test_overlapping_mounts_rejected(tmp_path: Path) -> None:
    skill = tmp_path / 'skill'
    (skill / 'work').mkdir(parents=True)
    invocation = ContainerInvocation(
        name='agent-sandbox-t1-demo-abc',
        skill_root=str(skill),
        work_dir=str(skill / 'work'),
        script_relative_path='scripts/main.py',
    )
    with pytest.raises(SandboxConfigurationError):
        docker_runner.validate_invocation(invocation)


def test_container_env_never_inherits_host(tmp_path: Path) -> None:
    invocation = _invocation(tmp_path)
    argv = _argv(invocation)
    env_pairs = _flag_value(argv, '--env')
    env_names = [pair.split('=', 1)[0] for pair in env_pairs]
    assert set(env_names) == {
        'PYTHONUNBUFFERED', 'PYTHONDONTWRITEBYTECODE', 'HOME', 'TMPDIR',
    }
    for name in env_names:
        assert not _looks_credential(name)


def _looks_credential(name: str) -> bool:
    from agent_service.application.sandbox_runner import looks_like_credential

    return looks_like_credential(name)


# ── 凭证拒收 ────────────────────────────────────────────────


@pytest.mark.parametrize(
    'env',
    [
        {'DATABASE_URL': 'postgresql://u:p@db/x'},
        {'OSS_ACCESS_KEY': 'k'},
        {'LLM_API_KEY': 'sk-x'},
        {'deepseek_api_key': 'sk-x'},
        {'DOCKER_HOST': 'unix:///var/run/docker.sock'},
    ],
)
def test_credential_env_rejected(skill_root: Path, env: dict[str, str]) -> None:
    executor = FakeExecutor()
    result = _run(skill_root, executor, env=env)
    assert result.outcome is SandboxOutcome.FAILED
    assert result.reason is SandboxFailureReason.INVALID_INVOCATION
    assert not executor.invocations, '非法请求不得进入容器'


# ── 路径与层级校验 ──────────────────────────────────────────


@pytest.mark.parametrize('script', ['../outside.py', 'scripts/../../outside.py', 'C:/tmp/x.py', '/etc/passwd'])
def test_script_escape_rejected(skill_root: Path, script: str) -> None:
    executor = FakeExecutor()
    result = _run(skill_root, executor, script=script)
    assert result.outcome is SandboxOutcome.FAILED
    assert result.reason is SandboxFailureReason.SCRIPT_OUTSIDE_SKILL
    assert not executor.invocations


def test_script_outside_scripts_dir_rejected(skill_root: Path) -> None:
    (skill_root / 'other.py').write_text('print(1)', encoding='utf-8')
    executor = FakeExecutor()
    result = _run(skill_root, executor, script='other.py')
    assert result.reason is SandboxFailureReason.SCRIPT_OUTSIDE_SKILL
    assert not executor.invocations


def test_missing_script_is_failed_not_silent(skill_root: Path) -> None:
    executor = FakeExecutor()
    result = _run(skill_root, executor, script='scripts/nope.py')
    assert result.outcome is SandboxOutcome.FAILED
    assert result.reason is SandboxFailureReason.SCRIPT_NOT_FOUND


def test_t2_without_runtime_probe_reports_unavailable(skill_root: Path) -> None:
    """INT-2456 拍板#2：证明不了 T2 运行时可用就报 T2_RUNTIME_UNAVAILABLE，
    不得静默降级 T1（也不得误报成通用 UNSUPPORTED_TIER）。"""
    executor = FakeExecutor()
    result = _run(skill_root, executor, tier='T2_UNTRUSTED_CODE')
    assert result.outcome is SandboxOutcome.FAILED
    assert result.reason is SandboxFailureReason.T2_RUNTIME_UNAVAILABLE
    assert not executor.invocations


def test_t2_with_available_runtime_is_still_unsupported(skill_root: Path) -> None:
    """运行时在位也不冒充执行：T2 执行器未纳入 M0，仍拒绝且不调容器。"""
    executor = FakeExecutor()
    runner = SandboxRunner(
        executor, artifact_policy=None,
        t2_runtime_probe=lambda: (True, 'runsc version 20260101'),
    )
    result = runner.run_trusted_script(SandboxRequest(
        skill_name='demo', skill_root=skill_root, script='scripts/main.py',
        tier='T2_UNTRUSTED_CODE'))
    assert result.outcome is SandboxOutcome.FAILED
    assert result.reason is SandboxFailureReason.UNSUPPORTED_TIER
    assert not executor.invocations


def test_non_t2_non_t1_tier_rejected(skill_root: Path) -> None:
    executor = FakeExecutor()
    result = _run(skill_root, executor, tier='T0_NONE')
    assert result.outcome is SandboxOutcome.FAILED
    assert result.reason is SandboxFailureReason.UNSUPPORTED_TIER
    assert not executor.invocations


def test_default_tier_is_t1(skill_root: Path) -> None:
    executor = FakeExecutor()
    _run(skill_root, executor)
    request = SandboxRequest(skill_name='demo', skill_root=skill_root, script='scripts/main.py')
    assert request.tier is SandboxTier.T1_TRUSTED_SCRIPT


def test_tier_string_is_coerced_to_enum(skill_root: Path) -> None:
    """JSON 边界按 value 传入的字符串在构造时转成领域枚举。"""
    request = SandboxRequest(
        skill_name='demo', skill_root=skill_root, script='scripts/main.py',
        tier=SandboxTier.T1_TRUSTED_SCRIPT.value,
    )
    assert request.tier is SandboxTier.T1_TRUSTED_SCRIPT


# ── 结果映射：失败不得静默成功 ───────────────────────────────


def test_success_maps_to_succeeded(skill_root: Path) -> None:
    executor = FakeExecutor(ContainerExecution(exit_code=0, stdout='ok'))
    result = _run(skill_root, executor)
    assert result.outcome is SandboxOutcome.SUCCEEDED
    assert result.reason is SandboxFailureReason.NONE
    assert result.stdout == 'ok'


def test_nonzero_exit_maps_to_failed(skill_root: Path) -> None:
    executor = FakeExecutor(ContainerExecution(exit_code=3, stderr='boom'))
    result = _run(skill_root, executor)
    assert result.outcome is SandboxOutcome.FAILED
    assert result.reason is SandboxFailureReason.EXIT_CODE_NONZERO
    assert result.stderr == 'boom'


def test_timeout_maps_to_budget_exceeded(skill_root: Path) -> None:
    executor = FakeExecutor(ContainerExecution(exit_code=137, timed_out=True))
    result = _run(skill_root, executor)
    assert result.outcome is SandboxOutcome.BUDGET_EXCEEDED
    assert result.reason is SandboxFailureReason.TIMEOUT


def test_output_truncation_maps_to_budget_exceeded(skill_root: Path) -> None:
    executor = FakeExecutor(ContainerExecution(exit_code=137, output_truncated=True))
    result = _run(skill_root, executor)
    assert result.outcome is SandboxOutcome.BUDGET_EXCEEDED
    assert result.reason is SandboxFailureReason.OUTPUT_LIMIT_EXCEEDED


def test_oom_maps_to_budget_exceeded(skill_root: Path) -> None:
    executor = FakeExecutor(ContainerExecution(exit_code=137, oom_killed=True))
    result = _run(skill_root, executor)
    assert result.outcome is SandboxOutcome.BUDGET_EXCEEDED
    assert result.reason is SandboxFailureReason.MEMORY_LIMIT_EXCEEDED


def test_sigkill_maps_to_budget_exceeded(skill_root: Path) -> None:
    executor = FakeExecutor(ContainerExecution(exit_code=137))
    result = _run(skill_root, executor)
    assert result.outcome is SandboxOutcome.BUDGET_EXCEEDED
    assert result.reason is SandboxFailureReason.RESOURCE_LIMIT_EXCEEDED


def test_engine_error_maps_to_runner_error(skill_root: Path) -> None:
    executor = FakeExecutor(ContainerExecution(exit_code=-1, error='docker CLI 不可用'))
    result = _run(skill_root, executor)
    assert result.outcome is SandboxOutcome.FAILED
    assert result.reason is SandboxFailureReason.RUNNER_ERROR


def test_container_start_failure_maps_to_failed(skill_root: Path) -> None:
    executor = FakeExecutor(ContainerExecution(exit_code=125, error='no such image', start_failed=True))
    result = _run(skill_root, executor)
    assert result.outcome is SandboxOutcome.FAILED
    assert result.reason is SandboxFailureReason.CONTAINER_START_FAILED


# ── 产物回收只走 /work，且校验类型与大小 ──────────────────────


def _executor_writing(work_payload) -> FakeExecutor:
    executor = FakeExecutor()

    def _on_run(invocation: ContainerInvocation) -> ContainerExecution:
        work = Path(invocation.work_dir)
        work_payload(work)
        return ContainerExecution(exit_code=0)

    executor.on_run = _on_run
    return executor


def test_artifacts_collected_with_hash(skill_root: Path) -> None:
    executor = _executor_writing(lambda work: (work / 'result.json').write_text('{"a":1}', encoding='utf-8'))
    result = _run(skill_root, executor)
    assert result.outcome is SandboxOutcome.SUCCEEDED
    assert [a.relative_path for a in result.artifacts] == ['result.json']
    assert result.artifacts[0].size_bytes == 7
    assert len(result.artifacts[0].sha256) == 64


def test_files_outside_work_not_collected(skill_root: Path) -> None:
    executor = FakeExecutor()

    def _on_run(invocation: ContainerInvocation) -> ContainerExecution:
        (Path(invocation.skill_root) / 'leak.txt').write_text('x', encoding='utf-8')
        return ContainerExecution(exit_code=0)

    executor.on_run = _on_run
    result = _run(skill_root, executor)
    assert result.outcome is SandboxOutcome.SUCCEEDED
    assert result.artifacts == ()


def test_oversized_artifact_rejected(skill_root: Path) -> None:
    executor = _executor_writing(lambda work: (work / 'big.bin').write_bytes(b'0' * 4096))
    policy = SandboxArtifactPolicy(max_artifact_bytes=1024)
    result = _run(skill_root, executor, policy=policy)
    assert result.outcome is SandboxOutcome.FAILED
    assert result.reason is SandboxFailureReason.ARTIFACT_TOO_LARGE


def test_too_many_artifacts_rejected(skill_root: Path) -> None:
    def _payload(work: Path) -> None:
        for index in range(5):
            (work / f'f{index}.txt').write_text('x', encoding='utf-8')

    result = _run(
        skill_root,
        _executor_writing(_payload),
        policy=SandboxArtifactPolicy(max_artifacts=3),
    )
    assert result.outcome is SandboxOutcome.FAILED
    assert result.reason is SandboxFailureReason.ARTIFACT_TOO_LARGE


def test_work_dir_removed_after_run(skill_root: Path, tmp_path: Path) -> None:
    work_root = tmp_path / 'workroot'
    executor = FakeExecutor()

    captured: list[Path] = []

    def _on_run(invocation: ContainerInvocation) -> ContainerExecution:
        captured.append(Path(invocation.work_dir))
        return ContainerExecution(exit_code=0)

    executor.on_run = _on_run
    runner = SandboxRunner(executor, work_root=work_root)
    runner.run_trusted_script(SandboxRequest(skill_name='demo', skill_root=skill_root, script='scripts/main.py'))
    assert captured and not captured[0].exists(), '一次性 work 目录必须清理'


# ── 配置默认值 = 方案 §7 口径 ────────────────────────────────


def test_container_limits_defaults_match_spec() -> None:
    limits = ContainerLimits()
    assert limits.memory == '512m'
    assert limits.cpus == 1.0
    assert limits.pids_limit == 128
    assert limits.tmpfs_size == '64m'
    assert limits.timeout_seconds == 60
    assert limits.output_limit_bytes == 1024 * 1024


def test_limits_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('AGENT_SANDBOX_TIMEOUT_SECONDS', '7')
    monkeypatch.setenv('AGENT_SANDBOX_MEMORY', '256m')
    limits = docker_runner.build_limits_from_env()
    assert limits.timeout_seconds == 7
    assert limits.memory == '256m'


@pytest.mark.parametrize(
    'container_user', ['0', '000', '0:0', '0:65534', 'root', 'root:root', '-1', '65534:']
)
def test_root_or_non_numeric_container_user_rejected(container_user: str) -> None:
    """按数值判定：``000`` / ``0:65534`` 也是 uid 0，不能只比字面量。"""
    with pytest.raises(SandboxConfigurationError):
        ContainerLimits(container_user=container_user)


def test_non_root_numeric_container_user_accepted() -> None:
    assert ContainerLimits(container_user='65534:65534').container_user == '65534:65534'
    assert ContainerLimits(container_user='1000').container_user == '1000'


def test_container_entry_is_wrapped_with_timeout(tmp_path: Path) -> None:
    """容器内自限：宿主计时器消失时容器自己会死（P1-1 第三层）。"""
    argv = _argv(_invocation(tmp_path))
    image_index = argv.index('python:3.11-slim')
    assert argv[image_index + 1] == 'timeout'
    assert argv[image_index + 2] == '--kill-after'
    assert int(argv[image_index + 3]) > 0
    assert argv[image_index + 4] == '60'
    assert argv[image_index + 5] == 'python3'


def test_runner_url_must_be_http() -> None:
    for bad in ('', 'unix:///var/run/docker.sock', 'tcp://host:2375', 'http://x/docker.sock'):
        with pytest.raises(SandboxConfigurationError):
            docker_runner.validate_runner_url(bad)


def test_production_default_is_runner_http_fail_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv('AGENT_SANDBOX_EXECUTOR_MODE', raising=False)
    monkeypatch.delenv('AGENT_SANDBOX_RUNNER_URL', raising=False)
    config = docker_runner.DockerRunnerConfig.from_env()
    assert config.mode is docker_runner.DockerRunnerMode.RUNNER_HTTP
    with pytest.raises(SandboxConfigurationError):
        docker_runner.build_sandbox_executor(config)


def test_host_cli_mode_requires_explicit_opt_in(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('AGENT_SANDBOX_EXECUTOR_MODE', 'host_cli')
    config = docker_runner.DockerRunnerConfig.from_env()
    assert config.mode is docker_runner.DockerRunnerMode.HOST_CLI
    assert isinstance(
        docker_runner.build_sandbox_executor(config), docker_runner.HostCliDockerExecutor
    )


def test_invalid_executor_mode_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('AGENT_SANDBOX_EXECUTOR_MODE', 'docker_sock')
    with pytest.raises(SandboxConfigurationError):
        docker_runner.DockerRunnerConfig.from_env()
