# -*- coding: utf-8 -*-
"""INT-2495 T1 沙箱接入唯一 Loop：tier 分派 / run 级失败 / 产物回灌。

验收锚点（卡面「可测验收标准」）：
1. ``T1_TRUSTED_SCRIPT`` 的调用走 ``SandboxRunner``（不经过 ToolGateway），
   ``T0_NONE`` 行为不变；
2. 正常 / 超时 / 非零退出 / runner 不可达 / T2 拒绝 五条路径的 run 终态与
   原因码正确，``run_finished`` / ``error`` 事件带原因码，无静默成功；
3. runner 不可达 → run ``FAILED``，不抛裸异常；
4. 产物清单与截断后的输出摘要回灌到 ``tool_result``。
"""
import hashlib
import json
import os
import time

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from pathlib import Path

import pytest

from agent_service.application.run_worker import InlineRunExecutor
from agent_service.application.sandbox_dispatch import (
    SandboxScriptDispatcher, SkillScripts,
)
from agent_service.application.sandbox_runner import (
    ContainerExecution, ContainerLimits, SandboxArtifactPolicy,
    SandboxExecutor, SandboxOutcome, SandboxResult, SandboxRunner,
)
from agent_service.application.skill_registry import SkillRegistry
from agent_service.domain.enums import (
    RunStatus, SandboxTier, StepStatus, ToolCallStatus, ToolRisk,
)
from agent_service.domain.model.entities import AgentToolCall, ToolCallRequest
from agent_service.domain.ports.tool_gateway import ToolDescriptor
from agent_service.infrastructure.llm.credential_store import CredentialStore
from agent_service.infrastructure.sandbox.docker_runner import (
    HttpRunnerDockerExecutor,
)
from agent_service.infrastructure.wakeup import LocalRunWakeup
from agent_service.wiring import (
    build_container, build_sandbox_tool_executor,
)
from tests.unit.int2451_agent_fakes import (
    TEST_MASTER_KEY, FakeLlm, FakeProviderResolver, FakeToolGateway,
    events_of, make_engine, new_session, read_tool, text_turn, tool_turn,
)

SKILL_SCRIPT = 'scripts/main.py'
SKILL_BODY = '---\nname: demo\ndescription: 演示脚本\n---\n\n## Gotchas\n无\n\n## 验收\n通过\n'


# ------------------------------------------------------------------ helpers


class FakeExecutor(SandboxExecutor):
    """不起容器的执行器替身：可选地往 /work 写产物。"""

    def __init__(self, execution: ContainerExecution | None = None,
                 artifacts: dict | None = None,
                 delay_seconds: float = 0.0) -> None:
        self.execution = execution or ContainerExecution(exit_code=0)
        self.artifacts = artifacts or {}
        self.delay_seconds = delay_seconds
        self.invocations = []

    @property
    def limits(self) -> ContainerLimits:
        return ContainerLimits()

    def run(self, invocation):
        self.invocations.append(invocation)
        if self.delay_seconds:
            time.sleep(self.delay_seconds)
        for name, content in self.artifacts.items():
            path = Path(invocation.work_dir) / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding='utf-8')
        return self.execution


class RecordingRunner:
    """记录 SandboxRequest 的 runner 替身（用于 wiring 的 Skill 解析断言）。"""

    def __init__(self, result: SandboxResult | None = None) -> None:
        self.requests = []
        self.result = result or SandboxResult(outcome=SandboxOutcome.SUCCEEDED)

    def run_trusted_script(self, request):
        self.requests.append(request)
        return self.result


class ExplodingRunner:
    def run_trusted_script(self, request):
        raise RuntimeError('runner 崩了')


def sandbox_tool(name='script_tool',
                 tier=SandboxTier.T1_TRUSTED_SCRIPT) -> ToolDescriptor:
    return ToolDescriptor(
        name=name, description='T1 脚本执行', parameters={},
        risk=ToolRisk.READ, sandbox_tier=tier)


def make_skill_root(tmp_path: Path) -> Path:
    root = tmp_path / 'skills' / 'demo'
    (root / 'scripts').mkdir(parents=True)
    (root / 'SKILL.md').write_text(SKILL_BODY, encoding='utf-8')
    (root / 'scripts' / 'main.py').write_text('print("ok")\n', encoding='utf-8')
    return root


def skill_scripts(tmp_path: Path) -> SkillScripts:
    root = make_skill_root(tmp_path)
    return SkillScripts(skill_name='demo', root=root, scripts=(SKILL_SCRIPT,))


def dispatcher_for(executor, tmp_path: Path, **kwargs) -> SandboxScriptDispatcher:
    skill = skill_scripts(tmp_path)
    runner = SandboxRunner(executor, SandboxArtifactPolicy())
    return SandboxScriptDispatcher(
        runner, lambda name: skill if name == 'demo' else None, **kwargs)


def script_call(tool_call_id='call_sandbox', **arguments) -> ToolCallRequest:
    payload = {'skill': 'demo', 'script': SKILL_SCRIPT}
    payload.update(arguments)
    return ToolCallRequest(tool_call_id=tool_call_id, name='script_tool',
                           arguments=payload)


def build_loop(tmp_path, dispatcher, *, tools=None, script=None,
               gateway=None, budget_defaults=None):
    """最小 Loop 装配：FakeLlm + FakeToolGateway + 注入的沙箱分派器。"""
    engine, session_factory = make_engine(tmp_path / 'int2495.db')
    llm = FakeLlm(script or [tool_turn([script_call()]), text_turn('完成')])
    tool_gateway = gateway or FakeToolGateway(
        tools=tools if tools is not None else [sandbox_tool()])
    container = build_container(
        session_factory,
        provider_resolver=FakeProviderResolver(llm),
        tool_gateway=tool_gateway,
        wakeup=LocalRunWakeup(),
        executor_factory=InlineRunExecutor,
        budget_defaults=budget_defaults,
        credential_store=CredentialStore.from_secret(TEST_MASTER_KEY),
        sandbox=dispatcher,
    )
    return container, llm, tool_gateway, session_factory


def run_once(container, message='跑脚本'):
    session = new_session(container)
    run, created = container.run_service.create_run(
        session.id, owner_id=7, tenant_id='t1', message=message)
    assert created
    container.executor.submit(run.id)
    return run


def finished_payload(container, run_id) -> dict:
    events = [e for e in events_of(container, run_id)
              if e.type.value == 'run_finished']
    assert len(events) == 1
    return events[0].payload


def error_codes(container, run_id):
    return [e.payload.get('code') for e in events_of(container, run_id)
            if e.type.value == 'error']


def step_statuses(session_factory, run_id):
    from agent_service.infrastructure.persistence.models.agent_models import (
        AgentStep,
    )
    db = session_factory()
    try:
        rows = (db.query(AgentStep)
                .filter(AgentStep.run_id == run_id)
                .order_by(AgentStep.index)
                .all())
        return [row.status for row in rows]
    finally:
        db.close()


# ------------------------------------------------------- dispatcher (unit)


def test_success_returns_artifact_manifest_and_summary(tmp_path):
    executor = FakeExecutor(
        ContainerExecution(exit_code=0, stdout='脚本输出' * 20,
                           container_id='abc123'),
        artifacts={'out.txt': 'hello'})
    dispatcher = dispatcher_for(executor, tmp_path,
                                output_summary_chars=20, max_result_chars=8000)

    result, failure = dispatcher.execute(
        script_call(args=['a', 'b'], env={'FOO': '1'}),
        SandboxTier.T1_TRUSTED_SCRIPT)

    assert failure is None
    assert result.ok is True
    payload = json.loads(result.content)
    assert payload['outcome'] == 'SUCCEEDED'
    assert payload['reason'] == 'NONE'
    assert payload['skill'] == 'demo'
    assert payload['script'] == SKILL_SCRIPT
    assert payload['stdout'].startswith('脚本输出')
    assert payload['stdout_truncated'] is True
    assert payload['artifact_count'] == 1
    artifact = payload['artifacts'][0]
    assert artifact['path'] == 'out.txt'
    assert artifact['bytes'] == len('hello')
    assert artifact['sha256'] == hashlib.sha256(b'hello').hexdigest()
    invocation = executor.invocations[0]
    assert invocation.args == ('a', 'b')
    assert invocation.env == {'FOO': '1'}
    assert invocation.script_relative_path == SKILL_SCRIPT


def test_timeout_maps_to_budget_exceeded(tmp_path):
    executor = FakeExecutor(ContainerExecution(exit_code=124, timed_out=True))
    dispatcher = dispatcher_for(executor, tmp_path)

    result, failure = dispatcher.execute(
        script_call(), SandboxTier.T1_TRUSTED_SCRIPT)

    assert result.ok is False
    assert result.error_code == 'TIMEOUT'
    assert failure is not None
    assert failure.outcome is SandboxOutcome.BUDGET_EXCEEDED
    assert failure.reason.value == 'TIMEOUT'
    assert json.loads(result.content)['timed_out'] is True


def test_nonzero_exit_maps_to_failed(tmp_path):
    executor = FakeExecutor(ContainerExecution(exit_code=3, stdout='boom'))
    dispatcher = dispatcher_for(executor, tmp_path)

    result, failure = dispatcher.execute(
        script_call(), SandboxTier.T1_TRUSTED_SCRIPT)

    assert result.ok is False
    assert result.error_code == 'EXIT_CODE_NONZERO'
    assert failure.outcome is SandboxOutcome.FAILED
    assert failure.exit_code == 3


def test_runner_unreachable_maps_to_runner_error(tmp_path):
    skill = skill_scripts(tmp_path)
    runner = SandboxRunner(
        HttpRunnerDockerExecutor('http://127.0.0.1:1'),  # 无监听
        SandboxArtifactPolicy())
    dispatcher = SandboxScriptDispatcher(
        runner, lambda name: skill if name == 'demo' else None)

    result, failure = dispatcher.execute(
        script_call(), SandboxTier.T1_TRUSTED_SCRIPT)

    assert result.ok is False
    assert failure.outcome is SandboxOutcome.FAILED
    assert failure.reason.value == 'RUNNER_ERROR'
    assert '不可达' in failure.detail or 'runner' in failure.detail


def test_t2_tier_is_rejected_without_execution(tmp_path):
    executor = FakeExecutor()
    dispatcher = dispatcher_for(executor, tmp_path)

    result, failure = dispatcher.execute(
        script_call(), SandboxTier.T2_UNTRUSTED_CODE)

    assert executor.invocations == []
    assert result.ok is False
    assert failure.outcome is SandboxOutcome.FAILED
    assert failure.reason.value == 'UNSUPPORTED_TIER'
    assert result.error_code == 'UNSUPPORTED_TIER'


def test_unknown_skill_or_unregistered_script_is_rejected(tmp_path):
    executor = FakeExecutor()
    dispatcher = dispatcher_for(executor, tmp_path)

    _result, failure = dispatcher.execute(
        ToolCallRequest('c1', 'script_tool',
                        {'skill': 'nope', 'script': SKILL_SCRIPT}),
        SandboxTier.T1_TRUSTED_SCRIPT)
    assert failure.reason.value == 'INVALID_INVOCATION'

    _result, failure = dispatcher.execute(
        script_call(script='scripts/other.py'), SandboxTier.T1_TRUSTED_SCRIPT)
    assert failure.reason.value == 'SCRIPT_NOT_FOUND'

    _result, failure = dispatcher.execute(
        ToolCallRequest('c2', 'script_tool', {'skill': 'demo'}),
        SandboxTier.T1_TRUSTED_SCRIPT)
    assert failure.reason.value == 'INVALID_INVOCATION'
    assert executor.invocations == []


def test_runner_exception_is_contained(tmp_path):
    skill = skill_scripts(tmp_path)
    dispatcher = SandboxScriptDispatcher(
        ExplodingRunner(), lambda name: skill if name == 'demo' else None)

    result, failure = dispatcher.execute(
        script_call(), SandboxTier.T1_TRUSTED_SCRIPT)

    assert result.ok is False
    assert failure.reason.value == 'RUNNER_ERROR'


def test_unavailable_executor_fails_closed(tmp_path):
    dispatcher = SandboxScriptDispatcher.unavailable(
        configuration_error='AGENT_SANDBOX_RUNNER_URL 未配置')

    result, failure = dispatcher.execute(
        script_call(), SandboxTier.T1_TRUSTED_SCRIPT)

    assert result.ok is False
    assert failure.reason.value == 'RUNNER_ERROR'
    assert '未配置' in failure.detail


# ------------------------------------------------------- loop (run level)


def test_t1_tool_runs_in_sandbox_and_feeds_manifest_back(tmp_path):
    executor = FakeExecutor(
        ContainerExecution(exit_code=0, stdout='done', container_id='c-1'),
        artifacts={'report.json': '{"ok": true}'})
    container, llm, gateway, _engine = build_loop(
        tmp_path, dispatcher_for(executor, tmp_path))

    run = run_once(container)

    stored = container.repositories['runs'].get(run.id)
    assert stored.status is RunStatus.SUCCEEDED
    # 脚本类调用不在 ToolGateway 里执行（§7 硬规则 1）
    assert gateway.executed == []
    assert len(executor.invocations) == 1
    call_row = container.repositories['tool_calls'].find(run.id, 'call_sandbox')
    assert call_row.status is ToolCallStatus.COMPLETED
    assert call_row.result_code == 'OK'

    tool_message = [m for m in llm.requests[1].messages if m.role == 'tool'][0]
    payload = json.loads(tool_message.content)
    assert payload['outcome'] == 'SUCCEEDED'
    assert payload['artifacts'][0]['path'] == 'report.json'
    assert 'done' in payload['stdout']
    container.shutdown()


def test_t1_timeout_finishes_run_as_budget_exceeded(tmp_path):
    executor = FakeExecutor(ContainerExecution(exit_code=124, timed_out=True))
    container, llm, gateway, session_factory = build_loop(
        tmp_path, dispatcher_for(executor, tmp_path))

    run = run_once(container)

    stored = container.repositories['runs'].get(run.id)
    assert stored.status is RunStatus.BUDGET_EXCEEDED
    finished = finished_payload(container, run.id)
    assert finished['reason'] == 'TIMEOUT'
    assert finished['reason_code'] == 'TIMEOUT'
    assert finished['status'] == 'BUDGET_EXCEEDED'
    assert 'TIMEOUT' in error_codes(container, run.id)
    assert step_statuses(session_factory, run.id)[-1] == StepStatus.FAILED.value
    call_row = container.repositories['tool_calls'].find(run.id, 'call_sandbox')
    assert call_row.status is ToolCallStatus.FAILED
    assert call_row.result_code == 'TIMEOUT'
    assert call_row.result['sandbox_outcome'] == 'BUDGET_EXCEEDED'
    # 失败后不再发起第二轮模型调用：没有「失败当成功继续」
    assert len(llm.requests) == 1
    container.shutdown()


def test_t1_nonzero_exit_finishes_run_as_failed(tmp_path):
    executor = FakeExecutor(ContainerExecution(exit_code=2, stderr='bad'))
    container, llm, _gateway, _engine = build_loop(
        tmp_path, dispatcher_for(executor, tmp_path))

    run = run_once(container)

    stored = container.repositories['runs'].get(run.id)
    assert stored.status is RunStatus.FAILED
    finished = finished_payload(container, run.id)
    assert finished['reason'] == 'EXIT_CODE_NONZERO'
    assert 'EXIT_CODE_NONZERO' in error_codes(container, run.id)
    assert len(llm.requests) == 1
    container.shutdown()


def test_t1_runner_unreachable_finishes_run_as_failed(tmp_path):
    skill = skill_scripts(tmp_path)
    runner = SandboxRunner(
        HttpRunnerDockerExecutor('http://127.0.0.1:1'),
        SandboxArtifactPolicy())
    dispatcher = SandboxScriptDispatcher(
        runner, lambda name: skill if name == 'demo' else None)
    container, llm, _gateway, _engine = build_loop(tmp_path, dispatcher)

    run = run_once(container)

    stored = container.repositories['runs'].get(run.id)
    assert stored.status is RunStatus.FAILED
    finished = finished_payload(container, run.id)
    assert finished['reason'] == 'RUNNER_ERROR'
    assert 'RUNNER_ERROR' in error_codes(container, run.id)
    assert len(llm.requests) == 1
    container.shutdown()


def test_t2_tool_is_rejected_and_fails_run(tmp_path):
    executor = FakeExecutor()
    dispatcher = dispatcher_for(executor, tmp_path)
    container, llm, _gateway, _engine = build_loop(
        tmp_path, dispatcher,
        tools=[sandbox_tool(tier=SandboxTier.T2_UNTRUSTED_CODE)])

    run = run_once(container)

    stored = container.repositories['runs'].get(run.id)
    assert stored.status is RunStatus.FAILED
    finished = finished_payload(container, run.id)
    assert finished['reason'] == 'UNSUPPORTED_TIER'
    assert executor.invocations == []
    assert len(llm.requests) == 1
    container.shutdown()


def test_t0_tool_still_uses_tool_gateway(tmp_path):
    gateway = FakeToolGateway(tools=[read_tool('task_query')])
    executor = FakeExecutor()
    script = [tool_turn([ToolCallRequest('c0', 'task_query',
                                         {'task_id': 1})]),
              text_turn('完成')]
    container, llm, gateway, _engine = build_loop(
        tmp_path, dispatcher_for(executor, tmp_path),
        tools=[read_tool('task_query')], script=script, gateway=gateway)

    run = run_once(container)

    stored = container.repositories['runs'].get(run.id)
    assert stored.status is RunStatus.SUCCEEDED
    assert [item[0] for item in gateway.executed] == ['c0']
    assert executor.invocations == []
    assert len(llm.requests) == 2
    container.shutdown()


def test_sandbox_calls_count_against_tool_budget(tmp_path):
    from tests.unit.int2451_agent_fakes import server_budget

    executor = FakeExecutor(ContainerExecution(exit_code=0))
    first = script_call(tool_call_id='c1')
    second = script_call(tool_call_id='c2')
    script = [tool_turn([first]), tool_turn([second]), text_turn('完成')]
    container, llm, _gateway, _session_factory = build_loop(
        tmp_path, dispatcher_for(executor, tmp_path), script=script,
        budget_defaults=server_budget(max_tool_calls=1))

    run = run_once(container)

    # 第一轮沙箱调用计入工具预算；第二轮在模型返回后被预算拦下
    stored = container.repositories['runs'].get(run.id)
    assert stored.status is RunStatus.BUDGET_EXCEEDED
    assert finished_payload(container, run.id)['reason'] == 'max_tool_calls'
    assert len(executor.invocations) == 1
    assert len(llm.requests) == 2
    container.shutdown()


def test_sandbox_duration_counts_against_run_duration_budget(tmp_path):
    from tests.unit.int2451_agent_fakes import server_budget

    executor = FakeExecutor(ContainerExecution(exit_code=0),
                            delay_seconds=2.2)
    container, llm, _gateway, _session_factory = build_loop(
        tmp_path, dispatcher_for(executor, tmp_path),
        budget_defaults=server_budget(max_duration_seconds=2))

    run = run_once(container)

    stored = container.repositories['runs'].get(run.id)
    assert stored.status is RunStatus.BUDGET_EXCEEDED
    assert finished_payload(container, run.id)['reason'] == 'max_duration_seconds'
    # 一轮容器执行就把时长预算吃满，收口后不再发起模型调用
    assert len(executor.invocations) == 1
    assert len(llm.requests) == 1
    container.shutdown()


def test_recorded_sandbox_failure_is_replayed_on_recovery(tmp_path):
    """崩溃在「沙箱失败落库」与「run 收口」之间：恢复时仍按失败收口。"""
    container, _llm, gateway, _engine = build_loop(
        tmp_path, dispatcher_for(FakeExecutor(), tmp_path))
    session = new_session(container)
    run, _created = container.run_service.create_run(
        session.id, owner_id=7, tenant_id='t1', message='恢复')
    engine_run = container.repositories['runs'].get(run.id)
    step = container.repositories['steps'].create(run.id, 0)
    container.repositories['tool_calls'].create(AgentToolCall(
        id='tc-1', run_id=run.id, step_id=step.id, tool_call_id='call_sandbox',
        tool='script_tool', args_hash='x', risk=ToolRisk.READ,
        status=ToolCallStatus.FAILED,
        result={'ok': False, 'error_code': 'TIMEOUT',
                'sandbox_outcome': 'BUDGET_EXCEEDED',
                'sandbox_reason': 'TIMEOUT'},
        result_code='TIMEOUT', error='TIMEOUT: 超时终止',
        idempotency_key='k-replay'))
    descriptors = {d.name: d for d in gateway.all_tools()}

    from agent_service.application.sandbox_dispatch import SandboxFailureLog
    failures = SandboxFailureLog()
    container.orchestrator._execute_one(
        engine_run, step.id, script_call(), 0, set(), descriptors, failures)

    winner = failures.winner()
    assert winner is not None
    assert winner.reason.value == 'TIMEOUT'
    assert winner.outcome is SandboxOutcome.BUDGET_EXCEEDED
    container.shutdown()


def _create_run(container, message='恢复'):
    session = new_session(container)
    run, _created = container.run_service.create_run(
        session.id, owner_id=7, tenant_id='t1', message=message)
    return run


def _crash_before_sandbox_finish(container, run):
    """模拟「沙箱失败已落库、run 收口前」进程崩溃：不执行收口函数。"""
    original = container.orchestrator._finish_sandbox_failure
    container.orchestrator._finish_sandbox_failure = lambda *a, **k: None
    try:
        container.executor.submit(run.id)
    finally:
        container.orchestrator._finish_sandbox_failure = original


def test_crash_before_sandbox_finish_closes_run_on_real_recovery(tmp_path):
    """P1 打回：崩溃在「沙箱失败落库」与「run 收口」之间。

    走真实恢复链路（``recovery.recover()`` + 重新投递），而不是直接调
    ``_execute_one``：重启后 Loop 会开新 step，模型新一轮给出的是新的
    tool_call_id，落库的失败调用不会再进 ``_execute_one``。必须在发起模型
    轮次前按落库原因码收口，否则模型回一段文本就会把 run 判 SUCCEEDED。
    """
    executor = FakeExecutor(ContainerExecution(exit_code=3, stdout='boom'))
    container, llm, _gateway, _session_factory = build_loop(
        tmp_path, dispatcher_for(executor, tmp_path))
    run = _create_run(container)

    _crash_before_sandbox_finish(container, run)
    crashed = container.repositories['runs'].get(run.id)
    assert crashed.status is RunStatus.RUNNING
    persisted = container.repositories['tool_calls'].list_by_run(run.id)
    assert [row.result['sandbox_reason'] for row in persisted] == [
        'EXIT_CODE_NONZERO']

    assert run.id in container.recovery.recover()
    container.executor.submit(run.id)

    stored = container.repositories['runs'].get(run.id)
    assert stored.status is RunStatus.FAILED
    finished = finished_payload(container, run.id)
    assert finished['reason'] == 'EXIT_CODE_NONZERO'
    assert finished['reason_code'] == 'EXIT_CODE_NONZERO'
    assert 'EXIT_CODE_NONZERO' in error_codes(container, run.id)
    # 恢复后不再发起模型轮次：模型没有机会用一段文本把失败「洗」成成功
    assert len(llm.requests) == 1
    container.shutdown()


def test_crash_before_sandbox_finish_closes_run_as_budget_exceeded(tmp_path):
    """同一条恢复口子对预算类失败（超时）必须收口 BUDGET_EXCEEDED。"""
    executor = FakeExecutor(ContainerExecution(exit_code=124, timed_out=True))
    container, llm, _gateway, _session_factory = build_loop(
        tmp_path, dispatcher_for(executor, tmp_path))
    run = _create_run(container)

    _crash_before_sandbox_finish(container, run)
    assert container.repositories['runs'].get(run.id).status is RunStatus.RUNNING

    assert run.id in container.recovery.recover()
    container.executor.submit(run.id)

    stored = container.repositories['runs'].get(run.id)
    assert stored.status is RunStatus.BUDGET_EXCEEDED
    finished = finished_payload(container, run.id)
    assert finished['reason'] == 'TIMEOUT'
    assert finished['reason_code'] == 'TIMEOUT'
    assert 'TIMEOUT' in error_codes(container, run.id)
    assert len(llm.requests) == 1
    container.shutdown()


# ------------------------------------------------------------- wiring


def test_wiring_builds_sandbox_dispatcher_with_registered_scripts(tmp_path):
    from agent_service.wiring import build_skill_registry
    from tests.unit.int2451_agent_fakes import FakeToolGateway

    make_skill_root(tmp_path)
    skills_root = tmp_path / 'skills'
    registry = build_skill_registry(
        FakeToolGateway(tools=[sandbox_tool()]), str(skills_root))
    assert isinstance(registry, SkillRegistry)
    assert registry.get('demo') is not None

    runner = RecordingRunner()
    dispatcher = build_sandbox_tool_executor(registry, runner=runner)
    result, failure = dispatcher.execute(script_call(),
                                         SandboxTier.T1_TRUSTED_SCRIPT)

    assert failure is None
    assert result.ok is True
    request = runner.requests[0]
    assert request.skill_name == 'demo'
    assert Path(request.skill_root).name == 'demo'
    assert request.script == SKILL_SCRIPT


def test_wiring_without_runner_config_fails_closed(monkeypatch):
    monkeypatch.setattr('agent_service.config.config.Config.SANDBOX_RUNNER_URL', '')
    monkeypatch.setattr('agent_service.config.config.Config.SANDBOX_EXECUTOR_MODE',
                        'runner_http')

    dispatcher = build_sandbox_tool_executor(None)

    result, failure = dispatcher.execute(script_call(),
                                         SandboxTier.T1_TRUSTED_SCRIPT)
    assert result.ok is False
    assert failure.reason.value == 'RUNNER_ERROR'
