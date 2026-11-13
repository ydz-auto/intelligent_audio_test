# -*- coding: utf-8 -*-
"""T2 不可信代码沙箱契约单测（INT-2489）——不需要 Docker / gVisor。

覆盖：T2 加固参数逐条断言、运行时选择与「绝不降级 T1」、运行时不可用原因码、
代码来源与 hash、出口白名单、输入/产物上限、阶段失败映射、产物落库、策略
配置（yaml + env）。真实 gVisor 行为见 ``test_t2_escape.py``。
"""

from __future__ import annotations

import hashlib
import subprocess
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from agent_service.application.sandbox_runner import (
    SANDBOX_TIER_T1,
    SANDBOX_TIER_T2,
    ContainerExecution,
    ContainerLimits,
    SandboxArtifactPolicy,
    SandboxConfigurationError,
    SandboxFailureReason,
    SandboxOutcome,
    SandboxRequest,
    SandboxRunner,
    SandboxRuntimeAvailability,
    T2ContainerInvocation,
    T2Phase,
    T2RunnerOptions,
    T2SandboxRequest,
    canonical_code_sha256,
    default_validation_phases,
)
from agent_service.infrastructure.sandbox import t2_runner
from agent_service.infrastructure.sandbox.policy import (
    T2ArtifactLimits,
    T2EgressPolicy,
    T2InputLimits,
    T2Policy,
    load_t2_policy,
)
from agent_service.infrastructure.sandbox.t2_runner import (
    T2DockerExecutor,
    build_t2_run_argv,
    probe_t2_runtime,
    validate_t2_invocation,
)

PHASE = T2Phase('import_compile', ('python3', '-c', 'print(1)'))
FILES = {'pkg/__init__.py': '', 'pkg/main.py': 'print("hi")\n'}


# ── 假执行器 ───────────────────────────────────────────────────


class FakeT2Executor:
    """记录 T2 调用并按剧本返回；可选择在 /work 里造产物。"""

    def __init__(
        self,
        availability: SandboxRuntimeAvailability | None = None,
        execution: ContainerExecution | None = None,
        on_run=None,
        policy: T2Policy | None = None,
    ) -> None:
        self._availability = availability or SandboxRuntimeAvailability(
            True, 'gvisor', 'runsc', 'ok'
        )
        self._execution = execution or ContainerExecution(exit_code=0)
        self._on_run = on_run
        self.policy = policy or load_t2_policy(environ={})
        self.invocations: list[T2ContainerInvocation] = []
        self.limits = ContainerLimits(timeout_seconds=30)

    @property
    def runtime(self) -> str:
        return 'gvisor'

    @property
    def runtime_name(self) -> str:
        return 'runsc'

    def availability(self) -> SandboxRuntimeAvailability:
        return self._availability

    def run(self, invocation: T2ContainerInvocation) -> ContainerExecution:
        self.invocations.append(invocation)
        if self._on_run is not None:
            return self._on_run(invocation)
        return self._execution


class RecordingT1Executor:
    """T1 执行器替身：T2 请求绝不应调用它。"""

    def __init__(self) -> None:
        self.limits = ContainerLimits()
        self.invocations = []

    def run(self, invocation):
        self.invocations.append(invocation)
        return ContainerExecution(exit_code=0)


def _request(**overrides) -> T2SandboxRequest:
    payload = dict(
        code_source='driver_propose:DEVICE_DRIVER',
        files=dict(FILES),
        phases=(PHASE,),
    )
    payload.update(overrides)
    return T2SandboxRequest(**payload)


def _runner(executor: FakeT2Executor, **kwargs) -> SandboxRunner:
    return SandboxRunner(untrusted_executor=executor, **kwargs)


def _invocation(tmp_path: Path, **overrides) -> T2ContainerInvocation:
    input_root = tmp_path / 'input'
    work = tmp_path / 'work'
    input_root.mkdir(exist_ok=True)
    work.mkdir(exist_ok=True)
    payload = dict(
        name='agent-sandbox-t2-demo-abc',
        input_root=str(input_root),
        work_dir=str(work),
        command=('python3', '-c', 'print(1)'),
        runtime='runsc',
        limits=ContainerLimits(),
    )
    payload.update(overrides)
    return T2ContainerInvocation(**payload)


def _flag_values(argv: list[str], flag: str) -> list[str]:
    return [argv[i + 1] for i, token in enumerate(argv[:-1]) if token == flag]


# ── 1. 容器加固参数（方案 §7 T2 行逐条）───────────────────────


def test_t2_hardening_flags_match_spec(tmp_path: Path) -> None:
    argv = build_t2_run_argv(_invocation(tmp_path))
    assert argv[:2] == ['docker', 'run']
    assert _flag_values(argv, '--runtime') == ['runsc'], 'T2 必须在 gVisor 里执行'
    assert _flag_values(argv, '--network') == ['none'], 'T2 默认完全禁网'
    assert '--read-only' in argv
    assert _flag_values(argv, '--cap-drop') == ['ALL']
    assert _flag_values(argv, '--security-opt') == ['no-new-privileges']
    assert _flag_values(argv, '--pids-limit') == ['128']
    assert _flag_values(argv, '--memory') == ['512m']
    assert _flag_values(argv, '--memory-swap') == ['512m']
    assert _flag_values(argv, '--cpus') == ['1.0']
    assert any(v.startswith('/tmp:') and 'size=64m' in v for v in _flag_values(argv, '--tmpfs'))
    user = _flag_values(argv, '--user')[0]
    assert user not in ('0', '0:0', 'root'), 'T2 必须非 root'
    assert _flag_values(argv, '--workdir') == ['/work']
    for forbidden in ('--privileged', '--pid=host', '--network=host', '--device'):
        assert forbidden not in argv


def test_t2_mounts_only_readonly_input_and_work(tmp_path: Path) -> None:
    argv = build_t2_run_argv(_invocation(tmp_path))
    mounts = _flag_values(argv, '--mount')
    input_mounts = [m for m in mounts if 'target=/input' in m]
    work_mounts = [m for m in mounts if 'target=/work' in m]
    assert len(input_mounts) == 1 and input_mounts[0].endswith(',readonly')
    assert len(work_mounts) == 1 and not work_mounts[0].endswith(',readonly')
    assert len(mounts) == 2, 'T2 只允许只读输入卷 + /work，不得有宿主目录挂载'
    assert not any('docker.sock' in token for token in argv)


def test_t2_container_env_has_no_credentials_and_fixed_home(tmp_path: Path) -> None:
    from agent_service.application.sandbox_runner import looks_like_credential

    argv = build_t2_run_argv(_invocation(tmp_path))
    env_pairs = _flag_values(argv, '--env')
    names = [pair.split('=', 1)[0] for pair in env_pairs]
    assert set(names) == {
        'PYTHONUNBUFFERED', 'PYTHONDONTWRITEBYTECODE', 'PYTHONPYCACHEPREFIX',
        'PYTHONPATH', 'HOME', 'TMPDIR',
    }
    assert 'HOME=/tmp' in env_pairs, '宿主 home 不可见'
    assert 'PYTHONPYCACHEPREFIX=/tmp/.pycache' in env_pairs, (
        '.pyc 必须写到 /tmp（tmpfs），不得进 /work 产物回收（审计 P1-1）'
    )
    assert not any(looks_like_credential(name) for name in names)


def test_t2_command_runs_after_image(tmp_path: Path) -> None:
    invocation = _invocation(tmp_path, command=('python3', '-m', 'compileall', '-q', '/input'))
    argv = build_t2_run_argv(invocation, container_kill_grace_seconds=5)
    image_index = argv.index(invocation.limits.image)
    # 镜像之后紧跟容器内自限：``timeout -k <grace> <timeout>``（逐 token 断言）。
    assert argv[image_index + 1:image_index + 5] == [
        'timeout', '--kill-after', '5', str(invocation.limits.timeout_seconds),
    ], 'T2 命令必须由 timeout 包装（INT-2518 P1-2）'
    assert argv[image_index + 5:] == ['python3', '-m', 'compileall', '-q', '/input']


# ── 2. 防降级：绝不回落到 runc/T1 ─────────────────────────────


def test_invocation_runtime_must_be_registered_runsc(tmp_path: Path) -> None:
    policy = load_t2_policy(environ={})
    with pytest.raises(SandboxConfigurationError):
        validate_t2_invocation(_invocation(tmp_path, runtime='runc'), policy)


def test_non_whitelisted_network_rejected(tmp_path: Path) -> None:
    policy = load_t2_policy(environ={})
    with pytest.raises(SandboxConfigurationError):
        validate_t2_invocation(_invocation(tmp_path, network='bridge'), policy)


def test_credential_env_rejected_before_container(tmp_path: Path) -> None:
    policy = load_t2_policy(environ={})
    invocation = _invocation(tmp_path, env={'AGENT_CREDENTIAL_MASTER_KEY': 'k'})
    with pytest.raises(SandboxConfigurationError):
        validate_t2_invocation(invocation, policy)


def test_t2_request_never_uses_t1_executor() -> None:
    t1 = RecordingT1Executor()
    runner = SandboxRunner(t1)
    result = runner.run_untrusted_code(_request())
    assert result.outcome is SandboxOutcome.FAILED
    assert result.reason is SandboxFailureReason.T2_RUNTIME_UNAVAILABLE
    assert t1.invocations == [], 'T2 请求不得落到 T1 通道'


def test_t1_channel_still_rejects_t2_request() -> None:
    t1 = RecordingT1Executor()
    runner = SandboxRunner(t1)
    result = runner.run_trusted_script(SimpleNamespace(
        tier=SANDBOX_TIER_T2, skill_name='x', skill_root=Path('.'), script='x',
    ))
    assert result.reason is SandboxFailureReason.UNSUPPORTED_TIER
    assert t1.invocations == []


def test_unavailable_runtime_returns_explicit_reason() -> None:
    executor = FakeT2Executor(
        availability=SandboxRuntimeAvailability(
            False, 'gvisor', 'runsc', 'T2_RUNTIME_UNAVAILABLE: docker 未注册 runsc'
        )
    )
    result = _runner(executor).run_untrusted_code(_request())
    assert result.outcome is SandboxOutcome.FAILED
    assert result.reason is SandboxFailureReason.T2_RUNTIME_UNAVAILABLE
    assert 'runsc' in result.detail
    assert executor.invocations == [], '运行时不可用时不得尝试执行'


def test_executor_runtime_unavailable_is_mapped(tmp_path: Path) -> None:
    """docker 125（runtime 缺失）→ T2_RUNTIME_UNAVAILABLE，而不是代码失败。"""
    executor = FakeT2Executor(execution=ContainerExecution(
        exit_code=-1, error='T2_RUNTIME_UNAVAILABLE: runtime runsc 不可用',
        runtime='gvisor', runtime_unavailable=True,
    ))
    result = _runner(executor).run_untrusted_code(_request())
    assert result.outcome is SandboxOutcome.FAILED
    assert result.reason is SandboxFailureReason.T2_RUNTIME_UNAVAILABLE
    assert result.phases[0].reason is SandboxFailureReason.T2_RUNTIME_UNAVAILABLE


# ── 3. 运行时探测 ──────────────────────────────────────────────


def _docker_info(runtimes: dict) -> subprocess.CompletedProcess:
    import json

    return subprocess.CompletedProcess(
        args=['docker'], returncode=0, stdout=json.dumps(runtimes), stderr=''
    )


def test_probe_reports_unavailable_when_runsc_missing(monkeypatch) -> None:
    monkeypatch.setattr(
        t2_runner, 'run_docker_admin',
        lambda *a, **k: _docker_info({'runc': {'path': 'runc'}}),
    )
    availability = probe_t2_runtime(load_t2_policy(environ={}))
    assert availability.available is False
    assert 'T2_RUNTIME_UNAVAILABLE' in availability.detail
    assert 'runsc' in availability.detail


def test_probe_reports_available_when_runsc_registered(monkeypatch) -> None:
    monkeypatch.setattr(
        t2_runner, 'run_docker_admin',
        lambda *a, **k: _docker_info({'runsc': {'path': '/usr/local/bin/runsc'}}),
    )
    availability = probe_t2_runtime(load_t2_policy(environ={}))
    assert availability.available is True
    assert availability.runtime_name == 'runsc'


def test_probe_reports_daemon_failure(monkeypatch) -> None:
    monkeypatch.setattr(t2_runner, 'run_docker_admin', lambda *a, **k: None)
    availability = probe_t2_runtime(load_t2_policy(environ={}))
    assert availability.available is False
    assert 'docker' in availability.detail.lower()


def test_firecracker_switch_is_explicitly_unavailable() -> None:
    policy = load_t2_policy(
        environ={}, )
    policy = replace(policy, runtime='firecracker', firecracker_enabled=True)
    availability = probe_t2_runtime(policy)
    assert availability.available is False
    assert 'Firecracker' in availability.detail
    assert '未实现' in availability.detail


def test_docker_125_runtime_hint_maps_to_unavailable(monkeypatch, tmp_path: Path) -> None:
    policy = load_t2_policy(environ={})
    executor = T2DockerExecutor(
        policy,
        availability=SandboxRuntimeAvailability(True, 'gvisor', 'runsc', 'ok'),
    )
    monkeypatch.setattr(
        t2_runner, 'execute_docker_container',
        lambda *a, **k: ContainerExecution(
            exit_code=125,
            error='docker: Error response from daemon: unknown or invalid runtime name: runsc',
            start_failed=True,
        ),
    )
    execution = executor.run(_invocation(tmp_path))
    assert execution.runtime_unavailable is True
    assert 'T2_RUNTIME_UNAVAILABLE' in execution.error


# ── 4. 代码来源与 hash ─────────────────────────────────────────


def test_code_source_required() -> None:
    result = _runner(FakeT2Executor()).run_untrusted_code(_request(code_source='  '))
    assert result.reason is SandboxFailureReason.CODE_PROVENANCE_MISSING


def test_code_hash_is_recomputed_and_recorded() -> None:
    executor = FakeT2Executor()
    result = _runner(executor).run_untrusted_code(_request())
    expected = canonical_code_sha256(FILES)
    assert result.code_sha256 == expected
    assert result.code_source == 'driver_propose:DEVICE_DRIVER'
    assert result.tier == SANDBOX_TIER_T2
    assert result.runtime == 'gvisor'


def test_declared_hash_mismatch_rejected() -> None:
    executor = FakeT2Executor()
    result = _runner(executor).run_untrusted_code(_request(code_sha256='deadbeef'))
    assert result.reason is SandboxFailureReason.CODE_PROVENANCE_MISMATCH
    assert executor.invocations == []


def test_declared_hash_match_accepted() -> None:
    executor = FakeT2Executor()
    result = _runner(executor).run_untrusted_code(
        _request(code_sha256=canonical_code_sha256(FILES))
    )
    assert result.outcome is SandboxOutcome.SUCCEEDED


# ── 5. 出口代理白名单 ──────────────────────────────────────────


def _egress_options() -> T2RunnerOptions:
    return T2RunnerOptions(
        egress_enabled=True,
        egress_network='agent-sandbox-egress',
        egress_proxy_url='http://proxy.internal:3128',
        egress_allowed_hosts=('api.vendor.example',),
    )


def test_egress_denied_when_whitelist_disabled() -> None:
    executor = FakeT2Executor()
    result = _runner(executor).run_untrusted_code(
        _request(egress_hosts=('api.vendor.example',))
    )
    assert result.reason is SandboxFailureReason.EGRESS_DENIED
    assert executor.invocations == [], '非白名单联网必须在进容器前拒绝'


def test_egress_denied_for_host_outside_whitelist() -> None:
    executor = FakeT2Executor()
    result = _runner(executor, t2_options=_egress_options()).run_untrusted_code(
        _request(egress_hosts=('evil.example',))
    )
    assert result.reason is SandboxFailureReason.EGRESS_DENIED
    assert executor.invocations == []


def test_whitelisted_egress_uses_internal_network_and_records_source() -> None:
    executor = FakeT2Executor()
    result = _runner(executor, t2_options=_egress_options()).run_untrusted_code(
        _request(egress_hosts=('api.vendor.example',))
    )
    assert result.outcome is SandboxOutcome.SUCCEEDED, result.detail
    invocation = executor.invocations[0]
    assert invocation.network == 'agent-sandbox-egress'
    assert invocation.env['HTTPS_PROXY'] == 'http://proxy.internal:3128'
    assert result.code_source == 'driver_propose:DEVICE_DRIVER'
    assert result.code_sha256 == canonical_code_sha256(FILES)


# ── 6. 输入校验 ────────────────────────────────────────────────


@pytest.mark.parametrize('bad_path', [
    '/etc/passwd', 'C:/windows/x.py', '../escape.py', 'pkg/../../x.py', './a.py',
])
def test_input_paths_must_be_relative_and_contained(bad_path: str) -> None:
    executor = FakeT2Executor()
    result = _runner(executor).run_untrusted_code(_request(files={bad_path: 'x'}))
    assert result.reason is SandboxFailureReason.INPUT_INVALID
    assert executor.invocations == []


def test_input_file_count_limit() -> None:
    options = T2RunnerOptions(max_input_files=2)
    files = {f'f{i}.py': '' for i in range(3)}
    result = _runner(FakeT2Executor(), t2_options=options).run_untrusted_code(
        _request(files=files)
    )
    assert result.reason is SandboxFailureReason.INPUT_INVALID


def test_input_file_size_limit() -> None:
    options = T2RunnerOptions(max_input_file_bytes=16)
    result = _runner(FakeT2Executor(), t2_options=options).run_untrusted_code(
        _request(files={'big.py': 'x' * 64})
    )
    assert result.reason is SandboxFailureReason.INPUT_INVALID


def test_empty_files_rejected() -> None:
    result = _runner(FakeT2Executor()).run_untrusted_code(_request(files={}))
    assert result.reason is SandboxFailureReason.INPUT_INVALID


def test_env_credentials_rejected() -> None:
    executor = FakeT2Executor()
    result = _runner(executor).run_untrusted_code(
        _request(env={'AGENT_CREDENTIAL_MASTER_KEY': 'secret'})
    )
    assert result.reason is SandboxFailureReason.INPUT_INVALID
    assert executor.invocations == []


def test_phase_shape_validation() -> None:
    with pytest.raises(SandboxConfigurationError):
        T2Phase('bad name', ('python3',))
    with pytest.raises(SandboxConfigurationError):
        T2Phase('..', ('python3',))
    with pytest.raises(SandboxConfigurationError):
        T2Phase('sub/phase', ('python3',))
    with pytest.raises(SandboxConfigurationError):
        T2Phase('ok', ())
    result = _runner(FakeT2Executor()).run_untrusted_code(_request(phases=()))
    assert result.reason is SandboxFailureReason.INPUT_INVALID


def test_unsafe_run_id_rejected_before_container() -> None:
    """run_id 是产物落盘路径分量，字符集非法即拒绝（审计 P3-3）。"""
    executor = FakeT2Executor()
    result = _runner(executor).run_untrusted_code(_request(run_id='..'))
    assert result.outcome is SandboxOutcome.FAILED
    assert result.reason is SandboxFailureReason.INPUT_INVALID
    assert executor.invocations == []


def test_executor_exception_is_mapped_to_runner_error() -> None:
    """执行器抛异常时 run 不得抛异常，映射为 RUNNER_ERROR（审计 P3-3）。"""
    def _raise(_invocation):
        raise FileNotFoundError('docker 不存在')

    executor = FakeT2Executor(on_run=_raise)
    result = _runner(executor).run_untrusted_code(_request())
    assert result.outcome is SandboxOutcome.FAILED
    assert result.reason is SandboxFailureReason.RUNNER_ERROR
    assert '执行器异常' in result.detail


# ── 7. 阶段失败映射（失败不静默）───────────────────────────────


def _with_execution(execution: ContainerExecution) -> SandboxResult:
    return _runner(FakeT2Executor(execution=execution)).run_untrusted_code(_request())


def test_nonzero_exit_is_failed_with_phase() -> None:
    result = _with_execution(ContainerExecution(exit_code=2, stderr='SyntaxError'))
    assert result.outcome is SandboxOutcome.FAILED
    assert result.reason is SandboxFailureReason.EXIT_CODE_NONZERO
    assert 'import_compile' in result.detail
    assert result.phases[-1].reason is SandboxFailureReason.EXIT_CODE_NONZERO


def test_timeout_is_budget_exceeded() -> None:
    result = _with_execution(ContainerExecution(exit_code=-1, timed_out=True))
    assert result.outcome is SandboxOutcome.BUDGET_EXCEEDED
    assert result.reason is SandboxFailureReason.TIMEOUT
    assert result.timed_out is True


def test_output_limit_is_budget_exceeded() -> None:
    result = _with_execution(ContainerExecution(exit_code=-1, output_truncated=True))
    assert result.outcome is SandboxOutcome.BUDGET_EXCEEDED
    assert result.reason is SandboxFailureReason.OUTPUT_LIMIT_EXCEEDED


def test_oom_is_budget_exceeded() -> None:
    result = _with_execution(ContainerExecution(exit_code=137, oom_killed=True))
    assert result.outcome is SandboxOutcome.BUDGET_EXCEEDED
    assert result.reason is SandboxFailureReason.MEMORY_LIMIT_EXCEEDED


def test_sigkill_is_resource_budget() -> None:
    result = _with_execution(ContainerExecution(exit_code=137))
    assert result.outcome is SandboxOutcome.BUDGET_EXCEEDED
    assert result.reason is SandboxFailureReason.RESOURCE_LIMIT_EXCEEDED


def test_start_failed_is_failed() -> None:
    result = _with_execution(
        ContainerExecution(exit_code=125, start_failed=True, error='start failed')
    )
    assert result.outcome is SandboxOutcome.FAILED
    assert result.reason is SandboxFailureReason.CONTAINER_START_FAILED


def test_plan_stops_at_first_failing_phase() -> None:
    executor = FakeT2Executor(on_run=lambda inv: ContainerExecution(exit_code=3))
    phases = (
        T2Phase('unit_test', ('python3', '-m', 'unittest')),
        T2Phase('mock_contract', ('python3', '-m', 'unittest')),
    )
    result = _runner(executor).run_untrusted_code(_request(phases=phases))
    assert result.outcome is SandboxOutcome.FAILED
    assert len(executor.invocations) == 1, '失败阶段之后的阶段不得执行'
    assert [p.name for p in result.phases] == ['unit_test']


def test_sandbox_failed_event_contains_reason() -> None:
    result = _with_execution(ContainerExecution(exit_code=2))
    event = result.to_sandbox_event()
    assert event['event'] == 'sandbox_failed'
    assert event['reason'] == SandboxFailureReason.EXIT_CODE_NONZERO.value
    assert event['tier'] == SANDBOX_TIER_T2
    assert event['code_sha256']


def test_success_event_name() -> None:
    result = _runner(FakeT2Executor()).run_untrusted_code(_request())
    assert result.to_sandbox_event()['event'] == 'sandbox_succeeded'


# ── 8. 产物：只从 /work 收、上限、落库 ─────────────────────────


def _write_work(files: dict[str, bytes]):
    def _on_run(invocation: T2ContainerInvocation) -> ContainerExecution:
        for relative, content in files.items():
            target = Path(invocation.work_dir) / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        return ContainerExecution(exit_code=0)

    return _on_run


def test_artifacts_collected_with_sha256_and_phase() -> None:
    executor = FakeT2Executor(on_run=_write_work({'report.json': b'{"ok":true}'}))
    result = _runner(executor).run_untrusted_code(_request())
    assert result.outcome is SandboxOutcome.SUCCEEDED
    artifact = result.artifacts[0]
    assert artifact.relative_path == 'report.json'
    assert artifact.phase == 'import_compile'
    assert artifact.sha256 == hashlib.sha256(b'{"ok":true}').hexdigest()


def test_too_many_artifacts_is_budget_exceeded() -> None:
    executor = FakeT2Executor(on_run=_write_work({'a.txt': b'a', 'b.txt': b'b'}))
    runner = _runner(executor, t2_options=T2RunnerOptions(max_artifacts=1))
    result = runner.run_untrusted_code(_request())
    assert result.outcome is SandboxOutcome.BUDGET_EXCEEDED
    assert result.reason is SandboxFailureReason.ARTIFACT_TOO_MANY


def test_oversized_artifact_is_budget_exceeded() -> None:
    executor = FakeT2Executor(on_run=_write_work({'big.bin': b'0' * 2048}))
    runner = _runner(
        executor, t2_options=T2RunnerOptions(max_artifact_bytes=1024)
    )
    result = runner.run_untrusted_code(_request())
    assert result.outcome is SandboxOutcome.BUDGET_EXCEEDED
    assert result.reason is SandboxFailureReason.ARTIFACT_TOO_LARGE


def test_bytecode_cache_is_not_collected_as_artifact() -> None:
    """编译期的 .pyc / __pycache__ 不是交付产物（审计 P1-1 回归）。"""
    executor = FakeT2Executor(on_run=_write_work({
        'report.json': b'{"ok":true}',
        '.pycache/pkg/main.cpython-311.pyc': b'\x00' * 64,
        'pkg/__pycache__/driver.cpython-311.pyc': b'\x00' * 64,
        'pkg/driver.pyc': b'\x00' * 64,
    }))
    # 数量上限 1：只有 report.json 计入，字节码不得触发 ARTIFACT_TOO_MANY。
    runner = _runner(executor, t2_options=T2RunnerOptions(max_artifacts=1))
    result = runner.run_untrusted_code(_request())
    assert result.outcome is SandboxOutcome.SUCCEEDED, result.detail
    assert [a.relative_path for a in result.artifacts] == ['report.json']


def test_t2_artifact_limits_come_from_config(monkeypatch) -> None:
    """``AGENT_SANDBOX_T2_MAX_ARTIFACTS`` 必须真的改变判定（审计 P2-2）。"""
    from agent_service.infrastructure.sandbox.policy import load_t2_policy

    policy = load_t2_policy(environ={'AGENT_SANDBOX_T2_MAX_ARTIFACTS': '2'})
    executor = FakeT2Executor(on_run=_write_work({
        f'out_{index}.txt': b'x' for index in range(10)
    }))
    runner = _runner(executor, t2_options=policy.to_runner_options())
    result = runner.run_untrusted_code(_request())
    assert result.outcome is SandboxOutcome.BUDGET_EXCEEDED
    assert result.reason is SandboxFailureReason.ARTIFACT_TOO_MANY
    assert '2' in result.detail
    assert '上限 2' in result.detail


def test_invalid_artifact_is_failed(monkeypatch) -> None:
    from agent_service.application import sandbox_runner as runner_module

    def _raise(*args, **kwargs):
        from agent_service.application.sandbox_runner import SandboxArtifactError

        raise SandboxArtifactError('产物禁止符号链接')

    monkeypatch.setattr(runner_module, 'collect_artifacts', _raise)
    executor = FakeT2Executor(on_run=_write_work({'x.txt': b'x'}))
    result = _runner(executor).run_untrusted_code(_request())
    assert result.outcome is SandboxOutcome.FAILED
    assert result.reason is SandboxFailureReason.ARTIFACT_INVALID


class FakeArtifactRepository:
    def __init__(self) -> None:
        self.rows = []

    def add(self, artifact):
        self.rows.append(artifact)
        return artifact


def test_artifacts_written_to_agent_artifact_with_provenance(tmp_path: Path) -> None:
    repository = FakeArtifactRepository()
    artifact_root = tmp_path / 'artifacts'
    executor = FakeT2Executor(on_run=_write_work({'report.json': b'payload'}))
    runner = _runner(executor, artifact_repository=repository, artifact_root=artifact_root)
    result = runner.run_untrusted_code(_request(run_id='run-123'))
    assert result.outcome is SandboxOutcome.SUCCEEDED
    assert len(repository.rows) == 1
    row = repository.rows[0]
    assert row.run_id == 'run-123'
    assert row.kind == 'sandbox_artifact'
    assert row.metadata['sha256'] == hashlib.sha256(b'payload').hexdigest()
    assert row.metadata['code_source'] == 'driver_propose:DEVICE_DRIVER'
    assert row.metadata['code_sha256'] == result.code_sha256
    assert Path(row.uri).read_bytes() == b'payload'


# ── 9. 通道分派 ────────────────────────────────────────────────


def test_run_by_tier_dispatches_t2() -> None:
    executor = FakeT2Executor()
    result = _runner(executor).run_by_tier(_request())
    assert result.tier == SANDBOX_TIER_T2
    assert len(executor.invocations) == 1


def test_run_by_tier_rejects_t0() -> None:
    result = _runner(FakeT2Executor()).run_by_tier(SimpleNamespace(tier='T0_NONE'))
    assert result.reason is SandboxFailureReason.UNSUPPORTED_TIER


def test_t1_request_still_routes_to_t1_channel(tmp_path: Path) -> None:
    skill = tmp_path / 'skills' / 'demo'
    (skill / 'scripts').mkdir(parents=True)
    (skill / 'scripts' / 'main.py').write_text('print(1)\n', encoding='utf-8')
    t1 = RecordingT1Executor()
    result = _runner(FakeT2Executor(), artifact_policy=SandboxArtifactPolicy()).run_by_tier(
        SandboxRequest(skill_name='demo', skill_root=skill, script='scripts/main.py')
    )
    assert result.tier == SANDBOX_TIER_T1


def test_t1_request_with_tier_dispatch_uses_t1_executor(tmp_path: Path) -> None:
    skill = tmp_path / 'skills' / 'demo'
    (skill / 'scripts').mkdir(parents=True)
    (skill / 'scripts' / 'main.py').write_text('print(1)\n', encoding='utf-8')
    t1 = RecordingT1Executor()
    runner = SandboxRunner(t1, artifact_policy=SandboxArtifactPolicy())
    result = runner.run_by_tier(
        SandboxRequest(skill_name='demo', skill_root=skill, script='scripts/main.py')
    )
    assert result.outcome is SandboxOutcome.SUCCEEDED
    assert len(t1.invocations) == 1


# ── 10. 策略配置（yaml + env）──────────────────────────────────


def test_yaml_defaults_are_applied() -> None:
    policy = load_t2_policy(environ={})
    assert policy.runtime == 'gvisor'
    assert policy.runtime_name == 'runsc'
    assert policy.container_limits.image == 'python:3.11-slim'
    assert policy.container_limits.memory == '512m'
    assert policy.container_limits.pids_limit == 128
    assert policy.container_limits.timeout_seconds == 120
    assert policy.total_timeout_seconds == 300
    assert policy.artifacts.max_artifact_bytes == 8 * 1024 * 1024
    assert policy.input.max_total_bytes == 2 * 1024 * 1024
    assert policy.egress.enabled is False


def test_env_overrides_yaml() -> None:
    policy = load_t2_policy(environ={
        'AGENT_SANDBOX_T2_MEMORY': '256m',
        'AGENT_SANDBOX_T2_PIDS_LIMIT': '32',
        'AGENT_SANDBOX_T2_TIMEOUT_SECONDS': '5',
        'AGENT_SANDBOX_T2_TOTAL_TIMEOUT_SECONDS': '30',
        'AGENT_SANDBOX_T2_IMAGE': 'sandbox:test',
    })
    assert policy.container_limits.memory == '256m'
    assert policy.container_limits.pids_limit == 32
    assert policy.container_limits.timeout_seconds == 5
    assert policy.total_timeout_seconds == 30
    assert policy.container_limits.image == 'sandbox:test'


def test_missing_config_file_falls_back_to_safe_defaults(tmp_path: Path) -> None:
    policy = load_t2_policy(path=tmp_path / 'missing.yaml', environ={})
    assert policy.runtime == 'gvisor'
    assert policy.container_limits.container_user != '0:0'


def test_config_validation_rejects_unsafe_values() -> None:
    with pytest.raises(SandboxConfigurationError):
        T2Policy(runtime='runc')
    with pytest.raises(SandboxConfigurationError):
        T2Policy(container_limits=ContainerLimits(container_user='0:0'))
    with pytest.raises(SandboxConfigurationError):
        T2Policy(container_limits=ContainerLimits(timeout_seconds=60),
                 total_timeout_seconds=30)
    with pytest.raises(SandboxConfigurationError):
        T2EgressPolicy(enabled=True, network='', proxy_url='http://p:1',
                       allowed_hosts=('a.example',))
    with pytest.raises(SandboxConfigurationError):
        T2ArtifactLimits(max_artifacts=0)
    with pytest.raises(SandboxConfigurationError):
        T2InputLimits(max_files=0)


def test_policy_to_runner_options_includes_egress() -> None:
    policy = T2Policy(egress=T2EgressPolicy(
        enabled=True,
        network='agent-sandbox-egress',
        proxy_url='http://proxy:3128',
        allowed_hosts=('api.vendor.example',),
    ))
    options = policy.to_runner_options()
    assert options.egress_enabled is True
    assert options.egress_allowed_hosts == ('api.vendor.example',)
    assert options.require_code_provenance is True


def test_policy_to_runner_options_carries_artifact_limits() -> None:
    policy = T2Policy(artifacts=T2ArtifactLimits(
        max_artifacts=7,
        max_artifact_bytes=1024,
        max_total_bytes=4096,
    ))
    options = policy.to_runner_options()
    assert (options.max_artifacts, options.max_artifact_bytes,
            options.max_total_bytes) == (7, 1024, 4096)
    artifact_policy = options.artifact_policy()
    assert artifact_policy.max_artifacts == 7
    assert artifact_policy.max_artifact_bytes == 1024
    assert artifact_policy.max_total_bytes == 4096


def test_runtime_constants_single_source_is_domain_enum() -> None:
    """运行时取值只认 domain 枚举，不在 policy 另造一份（审计 P3-4）。"""
    from agent_service.domain.enums import SandboxRuntime
    from agent_service.infrastructure.sandbox import policy as policy_module

    assert policy_module.RUNTIME_GVISOR == SandboxRuntime.GVISOR.value
    assert policy_module.RUNTIME_FIRECRACKER == SandboxRuntime.FIRECRACKER.value


def test_collect_artifacts_bytecode_flag(tmp_path: Path) -> None:
    """T2 忽略字节码；T1 默认口径不变（不改既有 T1 行为）。"""
    from agent_service.application.sandbox_runner import collect_artifacts

    work = tmp_path / 'work'
    (work / 'pkg' / '__pycache__').mkdir(parents=True)
    (work / 'pkg' / 'mod.pyc').write_bytes(b'\x00')
    (work / 'pkg' / '__pycache__' / 'mod.cpython-311.pyc').write_bytes(b'\x00')
    (work / 'report.json').write_text('{}', encoding='utf-8')

    t1_names = sorted(a.relative_path for a in collect_artifacts(work, SandboxArtifactPolicy()))
    assert 'pkg/mod.pyc' in t1_names, 'T1 默认行为不变（仍按常规文件收集）'

    t2_names = sorted(
        a.relative_path
        for a in collect_artifacts(work, SandboxArtifactPolicy(), ignore_bytecode=True)
    )
    assert t2_names == ['report.json']


def test_default_validation_phases_cover_driver_propose_chain() -> None:
    names = [phase.name for phase in default_validation_phases()]
    assert names == ['import_compile', 'unit_test', 'mock_contract', 'registry_resolve']


# ── 11. 生产 HTTP 通道（agent_service 不碰 docker.sock）──────────


def _start_runner(t2_executor, token: str = 'runner-token'):
    from agent_service.infrastructure.sandbox.runner_service import (
        SandboxRunnerServer,
    )

    server = SandboxRunnerServer(
        executor=RecordingT1Executor(),
        token=token,
        bind_host='127.0.0.1',
        port=0,
        t2_executor=t2_executor,
    )
    return server.start_background()


def _http_executor(server, token: str = 'runner-token'):
    from agent_service.infrastructure.sandbox.t2_runner import HttpRunnerT2Executor

    return HttpRunnerT2Executor(
        server.url, load_t2_policy(environ={}), runner_token=token
    )


def test_http_t2_roundtrip_and_runtime_probe(tmp_path: Path) -> None:
    fake = FakeT2Executor(on_run=_write_work({'report.json': b'payload'}))
    server = _start_runner(fake)
    try:
        executor = _http_executor(server)
        availability = executor.availability()
        assert availability.available is True
        assert availability.runtime_name == 'runsc'

        result = SandboxRunner(untrusted_executor=executor,
                               t2_options=T2RunnerOptions()).run_untrusted_code(_request())
        assert result.outcome is SandboxOutcome.SUCCEEDED, result.detail
        assert [a.relative_path for a in result.artifacts] == ['report.json']
        assert len(fake.invocations) == 1
        invocation = fake.invocations[0]
        assert invocation.runtime == 'runsc'
        assert invocation.network == 'none'
        assert invocation.command == PHASE.argv
    finally:
        server.stop()


def test_http_t2_reports_unavailable_runtime(tmp_path: Path) -> None:
    fake = FakeT2Executor(availability=SandboxRuntimeAvailability(
        False, 'gvisor', 'runsc', 'T2_RUNTIME_UNAVAILABLE: 未注册 runsc'
    ))
    server = _start_runner(fake)
    try:
        executor = _http_executor(server)
        assert executor.availability().available is False
        result = SandboxRunner(untrusted_executor=executor).run_untrusted_code(_request())
        assert result.outcome is SandboxOutcome.FAILED
        assert result.reason is SandboxFailureReason.T2_RUNTIME_UNAVAILABLE
        assert fake.invocations == []
    finally:
        server.stop()


def test_http_t2_rejects_bad_token(tmp_path: Path) -> None:
    fake = FakeT2Executor()
    server = _start_runner(fake)
    try:
        executor = _http_executor(server, token='wrong-token')
        availability = executor.availability()
        assert availability.available is False
        assert '401' in availability.detail
    finally:
        server.stop()


def test_http_t2_not_assembled_is_explicitly_unavailable(tmp_path: Path) -> None:
    server = _start_runner(None)
    try:
        executor = _http_executor(server)
        availability = executor.availability()
        assert availability.available is False
        assert 'T2_RUNTIME_UNAVAILABLE' in availability.detail
    finally:
        server.stop()


def test_build_t2_executor_defaults_to_runner_http(monkeypatch) -> None:
    from agent_service.infrastructure.sandbox.t2_runner import build_t2_executor
    from agent_service.infrastructure.sandbox.t2_runner import HttpRunnerT2Executor

    monkeypatch.delenv('AGENT_SANDBOX_EXECUTOR_MODE', raising=False)
    executor = build_t2_executor(
        load_t2_policy(environ={}),
        runner_url='http://runner.internal:5012',
        runner_token='t',
    )
    assert isinstance(executor, HttpRunnerT2Executor)


def test_build_t2_executor_runner_http_without_url_fails_closed(monkeypatch) -> None:
    from agent_service.infrastructure.sandbox.t2_runner import build_t2_executor

    monkeypatch.delenv('AGENT_SANDBOX_EXECUTOR_MODE', raising=False)
    monkeypatch.delenv('AGENT_SANDBOX_RUNNER_URL', raising=False)
    with pytest.raises(SandboxConfigurationError):
        build_t2_executor(load_t2_policy(environ={}))


def test_build_t2_executor_host_cli_mode() -> None:
    from agent_service.infrastructure.sandbox.t2_runner import (
        T2DockerExecutor,
        build_t2_executor,
    )

    executor = build_t2_executor(load_t2_policy(environ={}), mode='host_cli')
    assert isinstance(executor, T2DockerExecutor)
