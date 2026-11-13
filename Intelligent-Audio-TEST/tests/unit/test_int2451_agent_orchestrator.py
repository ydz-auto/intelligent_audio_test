# -*- coding: utf-8 -*-
"""INT-2451 唯一 Loop：事件序列 / 工具回灌 / 预算 / 取消 / 恢复。

验收锚点：
1. run_started / message_delta / run_finished 且 sequence 严格递增无空洞；
2. 工具按 tool_call_id 回灌；
3. 超预算 → BUDGET_EXCEEDED，已完成事件与产物保留；
4. 取消 → 当前模型调用中止，CANCELLED 落库；
5. 重启恢复 → 已完成的 tool_call 不重复执行。
"""
import os
import threading
import time
import uuid

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from agent_service.application.run_worker import (
    InlineRunExecutor, ThreadPoolRunExecutor,
)
from agent_service.domain.enums import (
    RunStatus, StepStatus, ToolCallStatus, ToolRisk,
)
from agent_service.domain.model.entities import AgentToolCall, ToolCallRequest
from agent_service.domain.ports.llm import LlmUsage
from tests.unit.int2451_agent_fakes import (
    FakeLlm, FakeToolGateway, Pause, build_stack, event_types, events_of,
    new_session, read_tool, server_budget, text_turn, tool_turn, wait_until,
    write_tool,
)
from shared.utils.time_utils import utcnow


def _submit(container, session, message='你好', owner_id=7, tenant_id='t1'):
    run, created = container.run_service.create_run(
        session.id, owner_id=owner_id, tenant_id=tenant_id, message=message)
    assert created
    container.executor.submit(run.id)
    return run


def _inline(orch):
    return InlineRunExecutor(orch)


def test_text_run_emits_ordered_events(tmp_path):
    llm = FakeLlm([text_turn('你', '好')])
    container, _engine, _sf = build_stack(
        tmp_path / 'a.db', llm, executor_factory=_inline)
    session = new_session(container)
    run = _submit(container, session)

    stored = container.repositories['runs'].get(run.id)
    assert stored.status is RunStatus.SUCCEEDED
    assert event_types(container, run.id) == [
        'run_started', 'message_delta', 'message_delta', 'run_finished']
    sequences = [e.sequence for e in events_of(container, run.id)]
    assert sequences == list(range(1, len(sequences) + 1))
    container.shutdown()


def test_tool_calls_are_fed_back_by_tool_call_id(tmp_path):
    call = ToolCallRequest(tool_call_id='call_1', name='task_query',
                           arguments={'task_id': 1})
    llm = FakeLlm([tool_turn([call]), text_turn('完成')])
    gateway = FakeToolGateway(tools=[read_tool('task_query')])
    container, _engine, _sf = build_stack(
        tmp_path / 'b.db', llm, gateway=gateway, executor_factory=_inline)
    session = new_session(container)
    run = _submit(container, session)

    stored = container.repositories['runs'].get(run.id)
    assert stored.status is RunStatus.SUCCEEDED
    assert [e[0] for e in gateway.executed] == ['call_1']
    assert event_types(container, run.id) == [
        'run_started', 'tool_call', 'tool_result', 'message_delta',
        'run_finished']
    tool_events = [e for e in events_of(container, run.id)
                   if e.type.value == 'tool_result']
    assert tool_events[0].payload['tool_call_id'] == 'call_1'
    assert tool_events[0].payload['ok'] is True
    # 第二轮模型消息里带上了 assistant tool_calls + tool 结果
    second = llm.requests[1]
    roles = [m.role for m in second.messages]
    assert 'assistant' in roles and 'tool' in roles
    tool_message = [m for m in second.messages if m.role == 'tool'][0]
    assert tool_message.tool_call_id == 'call_1'
    container.shutdown()


def test_write_tool_is_denied_in_m0(tmp_path):
    call = ToolCallRequest(tool_call_id='w1', name='task_run', arguments={})
    llm = FakeLlm([tool_turn([call]), text_turn('写操作被拒绝')])
    gateway = FakeToolGateway(tools=[write_tool('task_run')])
    container, _engine, _sf = build_stack(
        tmp_path / 'w.db', llm, gateway=gateway, executor_factory=_inline)
    session = new_session(container)
    run = _submit(container, session)

    assert gateway.executed == []
    call_row = container.repositories['tool_calls'].find(run.id, 'w1')
    assert call_row.status is ToolCallStatus.DENIED
    assert call_row.permission_decision == 'approval_required'
    container.shutdown()


def test_tool_budget_exceeded_keeps_events_and_artifacts(tmp_path):
    calls = [ToolCallRequest(tool_call_id='c1', name='task_query', arguments={}),
             ToolCallRequest(tool_call_id='c2', name='task_query', arguments={})]
    llm = FakeLlm([tool_turn(calls), tool_turn(calls)])
    gateway = FakeToolGateway(tools=[read_tool('task_query')])
    container, _engine, _sf = build_stack(
        tmp_path / 'c.db', llm, gateway=gateway, executor_factory=_inline,
        budget_defaults=server_budget(max_tool_calls=2))
    session = new_session(container)
    run, _created = container.run_service.create_run(
        session.id, owner_id=7, tenant_id='t1', message='预算')
    from agent_service.domain.model.entities import AgentArtifact
    container.repositories['artifacts'].add(AgentArtifact(
        id=str(uuid.uuid4()), run_id=run.id, kind='export',
        uri='oss://a.pdf', size=10, metadata={}, created_at=utcnow()))
    container.executor.submit(run.id)

    stored = container.repositories['runs'].get(run.id)
    assert stored.status is RunStatus.BUDGET_EXCEEDED
    finished = [e for e in events_of(container, run.id)
                if e.type.value == 'run_finished'][0]
    assert finished.payload['reason'] == 'max_tool_calls'
    assert len(gateway.executed) == 2
    assert len(events_of(container, run.id)) >= 5  # 已完成事件保留
    assert len(container.repositories['artifacts'].list_by_run(run.id)) == 1
    container.shutdown()


def test_round_budget_exceeded(tmp_path):
    call = ToolCallRequest(tool_call_id='c1', name='task_query', arguments={})
    llm = FakeLlm([tool_turn([call]), tool_turn([call])])
    gateway = FakeToolGateway(tools=[read_tool('task_query')])
    container, _engine, _sf = build_stack(
        tmp_path / 'd.db', llm, gateway=gateway, executor_factory=_inline,
        budget_defaults=server_budget(max_rounds=1))
    session = new_session(container)
    run = _submit(container, session)

    stored = container.repositories['runs'].get(run.id)
    assert stored.status is RunStatus.BUDGET_EXCEEDED
    finished = [e for e in events_of(container, run.id)
                if e.type.value == 'run_finished'][0]
    assert finished.payload['reason'] == 'max_rounds'
    container.shutdown()


def test_token_budget_exceeded(tmp_path):
    from agent_service.domain.ports.llm import LlmFinished, LlmTextDelta
    llm = FakeLlm([[LlmTextDelta('a'),
                    LlmUsage(prompt_tokens=100, completion_tokens=1),
                    LlmFinished()]])
    container, _engine, _sf = build_stack(
        tmp_path / 'e.db', llm, executor_factory=_inline,
        budget_defaults=server_budget(max_tokens=10))
    session = new_session(container)
    run = _submit(container, session)
    stored = container.repositories['runs'].get(run.id)
    assert stored.status is RunStatus.BUDGET_EXCEEDED
    container.shutdown()


def test_cancel_aborts_current_stream(tmp_path):
    script = []
    for index in range(60):
        script.append(Pause(0.02))
        script.append(text_turn(f'chunk-{index}')[0])
    script.append(text_turn('end')[0])
    llm = FakeLlm([script])
    container, _engine, _sf = build_stack(
        tmp_path / 'f.db', llm, executor_factory=lambda orch:
        ThreadPoolRunExecutor(orch, 1))
    session = new_session(container)
    run = _submit(container, session)

    # 等到流式片段真的开始落库再取消（避免在 claim 之前取消，测不到「中止当前调用」）
    assert wait_until(lambda: any(
        e.type.value == 'message_delta'
        for e in events_of(container, run.id)), timeout=10)
    cancelled = container.run_service.cancel_run(
        run.id, owner_id=7, tenant_id='t1')
    assert cancelled.status is RunStatus.CANCELLED
    assert wait_until(lambda: llm.cancelled is True, timeout=10)
    emitted = [e for e in events_of(container, run.id)
               if e.type.value == 'message_delta']
    assert 0 < len(emitted) < 60
    container.shutdown()


def test_consecutive_tool_failures_stop_the_loop(tmp_path):
    turns = [tool_turn([ToolCallRequest(tool_call_id=f'f{i}',
                                        name='task_query', arguments={})])
             for i in range(1, 4)]
    llm = FakeLlm(turns + [text_turn('never')])
    gateway = FakeToolGateway(tools=[read_tool('task_query')], fail=True)
    container, _engine, _sf = build_stack(
        tmp_path / 'g.db', llm, gateway=gateway, executor_factory=_inline)
    session = new_session(container)
    run = _submit(container, session)

    stored = container.repositories['runs'].get(run.id)
    assert stored.status is RunStatus.FAILED
    assert stored.error == 'CONSECUTIVE_TOOL_FAILURES'
    assert len(gateway.executed) == 3
    container.shutdown()


def _seed_interrupted_run(container, session):
    """构造「上一进程跑到一半被 kill」的持久化状态。"""
    run, _created = container.run_service.create_run(
        session.id, owner_id=7, tenant_id='t1', message='继续')
    repos = container.repositories
    repos['runs'].transition_if(run.id, {RunStatus.QUEUED}, RunStatus.RUNNING)
    step = repos['steps'].create(run.id, 0)
    from agent_service.domain.enums import EventType
    repos['events'].append(run.id, EventType.TOOL_CALL, {
        'tool_call_id': 'done_1', 'tool': 'task_query',
        'arguments': {'task_id': 1}, 'risk': 'READ', 'turn': 0})
    repos['events'].append(run.id, EventType.TOOL_RESULT, {
        'tool_call_id': 'done_1', 'tool': 'task_query', 'ok': True,
        'content': 'ok:done', 'error_code': None, 'turn': 0})
    now = utcnow()
    repos['tool_calls'].create(AgentToolCall(
        id=str(uuid.uuid4()), run_id=run.id, step_id=step.id,
        tool_call_id='done_1', tool='task_query', arguments={'task_id': 1},
        args_hash='h', risk=ToolRisk.READ,
        status=ToolCallStatus.COMPLETED,
        result={'ok': True, 'content': 'ok:done', 'error_code': None},
        idempotency_key=f'{run.id}:{step.id}:task_query:h',
        created_at=now, updated_at=now))
    return run, step


def test_recovery_resumes_without_reexecuting_completed_tool(tmp_path):
    llm = FakeLlm([text_turn('恢复后继续')])
    gateway = FakeToolGateway(tools=[read_tool('task_query')])
    container, _engine, _sf = build_stack(
        tmp_path / 'h.db', llm, gateway=gateway, executor_factory=_inline)
    session = new_session(container)
    run, _step = _seed_interrupted_run(container, session)

    resumable = container.recovery.recover()
    assert resumable == [run.id]
    # 中断的 step 已被标记 FAILED
    container.executor.submit(run.id)
    stored = container.repositories['runs'].get(run.id)
    assert stored.status is RunStatus.SUCCEEDED
    assert gateway.executed == []  # 已完成 tool_call 不重复执行
    tool_results = [e for e in events_of(container, run.id)
                    if e.type.value == 'tool_result'
                    and e.payload.get('tool_call_id') == 'done_1']
    assert len(tool_results) == 1
    container.shutdown()


def test_recovery_refuses_to_replay_inflight_write(tmp_path):
    llm = FakeLlm([text_turn('never')])
    container, _engine, _sf = build_stack(
        tmp_path / 'i.db', llm, executor_factory=_inline)
    session = new_session(container)
    run, created = container.run_service.create_run(
        session.id, owner_id=7, tenant_id='t1', message='写')
    repos = container.repositories
    repos['runs'].transition_if(run.id, {RunStatus.QUEUED}, RunStatus.RUNNING)
    now = utcnow()
    repos['tool_calls'].create(AgentToolCall(
        id=str(uuid.uuid4()), run_id=run.id, step_id=None,
        tool_call_id='w1', tool='task_run', arguments={}, args_hash='h',
        risk=ToolRisk.WRITE, status=ToolCallStatus.RUNNING,
        idempotency_key=f'{run.id}:s:task_run:h', created_at=now,
        updated_at=now))

    assert container.recovery.recover() == []
    stored = container.repositories['runs'].get(run.id)
    assert stored.status is RunStatus.FAILED
    call = repos['tool_calls'].find(run.id, 'w1')
    assert call.status is ToolCallStatus.FAILED
    assert call.permission_decision == 'restart_write_unverified'
    container.shutdown()


# ---------------------------------------------------------------- 返工回归
# 审计 P1：上下文必须取「最近」N 个 run（正序取最早 N 个会丢掉最近对话）

def test_context_uses_most_recent_runs(tmp_path):
    container, _engine, _sf = build_stack(
        tmp_path / 'j.db', FakeLlm([]), executor_factory=_inline)
    session = new_session(container)
    runs = []
    for index in range(25):
        run, created = container.run_service.create_run(
            session.id, owner_id=7, tenant_id='t1', message=f'msg-{index}')
        assert created
        runs.append(run)

    messages = container.assembler.assemble(session.id, runs[-1])
    users = [m.content for m in messages if m.role == 'user']
    assert users[-1] == 'msg-24'
    assert users == [f'msg-{index}' for index in range(5, 25)], users
    assert 'msg-4' not in users  # 窗口外的更早轮次被挤出，而不是挤掉最近的

    recent = container.repositories['runs'].list_session_runs(session.id, 20)
    assert [runs_item.id for runs_item in recent] == [
        run.id for run in runs[-20:]]
    assert recent[-1].id == runs[-1].id  # 末位仍是 latest
    container.shutdown()


# 审计 P3：PENDING 表示「落库后尚未执行」，必须执行，不能拿空结果复用

def test_pending_tool_call_is_executed(tmp_path):
    call = ToolCallRequest(tool_call_id='p1', name='task_query', arguments={})
    llm = FakeLlm([tool_turn([call]), text_turn('完成')])
    gateway = FakeToolGateway(tools=[read_tool('task_query')])
    container, _engine, _sf = build_stack(
        tmp_path / 'k.db', llm, gateway=gateway, executor_factory=_inline)
    session = new_session(container)
    run, _created = container.run_service.create_run(
        session.id, owner_id=7, tenant_id='t1', message='pending')
    now = utcnow()
    container.repositories['tool_calls'].create(AgentToolCall(
        id=str(uuid.uuid4()), run_id=run.id, step_id=None,
        tool_call_id='p1', tool='task_query', arguments={}, args_hash='h',
        risk=ToolRisk.READ, status=ToolCallStatus.PENDING,
        idempotency_key=f'{run.id}:preset:p1:h',
        created_at=now, updated_at=now))
    container.executor.submit(run.id)

    assert [entry[0] for entry in gateway.executed] == ['p1']
    stored = container.repositories['tool_calls'].find(run.id, 'p1')
    assert stored.status is ToolCallStatus.COMPLETED
    assert (stored.result or {}).get('content') == 'ok:task_query'
    results = [e for e in events_of(container, run.id)
               if e.type.value == 'tool_result'
               and e.payload.get('tool_call_id') == 'p1']
    assert len(results) == 1
    container.shutdown()


# ---------------------------------------------------------------- INT-2487 修复回归
# P1-1：未知工具的默认风险曾是 READ → 审批门禁 fail-open（§5.2 硬规则 5）

def test_unregistered_tool_is_rejected_without_side_effects(tmp_path):
    call = ToolCallRequest(tool_call_id='x1', name='task_delete_all',
                           arguments={'all': True})
    llm = FakeLlm([tool_turn([call]), text_turn('该工具不可用')])
    # 注册表里只有只读的 task_query；模型却调了一个没注册的工具
    gateway = FakeToolGateway(tools=[read_tool('task_query')])
    container, _engine, _sf = build_stack(
        tmp_path / 'l.db', llm, gateway=gateway, executor_factory=_inline)
    session = new_session(container)
    run = _submit(container, session)

    assert gateway.executed == []  # 未执行、无副作用
    row = container.repositories['tool_calls'].find(run.id, 'x1')
    assert row.status is ToolCallStatus.DENIED
    assert row.permission_decision == 'tool_not_registered'
    assert row.risk is ToolRisk.DESTRUCTIVE  # 未知工具按最高风险记账（fail-closed）
    results = [e for e in events_of(container, run.id)
               if e.type.value == 'tool_result'
               and e.payload.get('tool_call_id') == 'x1']
    assert len(results) == 1
    assert results[0].payload['ok'] is False
    assert results[0].payload['error_code'] == 'TOOL_NOT_REGISTERED'
    # 拒绝结果回灌模型，run 正常收尾而不是卡死
    assert container.repositories['runs'].get(run.id).status is RunStatus.SUCCEEDED
    container.shutdown()


def test_registry_failure_rejects_entire_batch(tmp_path):
    class BrokenRegistryGateway(FakeToolGateway):
        def all_tools(self):
            raise RuntimeError('tool registry unavailable')

    calls = [ToolCallRequest(tool_call_id='r1', name='task_query', arguments={}),
             ToolCallRequest(tool_call_id='r2', name='task_query', arguments={})]
    llm = FakeLlm([tool_turn(calls), text_turn('注册表不可用')])
    gateway = BrokenRegistryGateway(tools=[read_tool('task_query')])
    container, _engine, _sf = build_stack(
        tmp_path / 'n.db', llm, gateway=gateway, executor_factory=_inline)
    session = new_session(container)
    run = _submit(container, session)

    # 注册表读取异常 → 整批拒绝，绝不降级为 READ 自动执行
    assert gateway.executed == []
    for call_id in ('r1', 'r2'):
        row = container.repositories['tool_calls'].find(run.id, call_id)
        assert row.status is ToolCallStatus.FAILED
        assert row.permission_decision == 'tool_registry_unavailable'
        assert row.risk is ToolRisk.DESTRUCTIVE
    results = [e for e in events_of(container, run.id)
               if e.type.value == 'tool_result']
    assert {e.payload['tool_call_id'] for e in results} == {'r1', 'r2'}
    assert all(e.payload['error_code'] == 'TOOL_REGISTRY_UNAVAILABLE'
               for e in results)
    container.shutdown()


def test_registered_read_tool_still_executes(tmp_path):
    call = ToolCallRequest(tool_call_id='s1', name='task_query',
                           arguments={'task_id': 2})
    llm = FakeLlm([tool_turn([call]), text_turn('完成')])
    gateway = FakeToolGateway(tools=[read_tool('task_query')])
    container, _engine, _sf = build_stack(
        tmp_path / 'o.db', llm, gateway=gateway, executor_factory=_inline)
    session = new_session(container)
    run = _submit(container, session)

    assert gateway.executed == [('s1', 'task_query', {'task_id': 2})]
    row = container.repositories['tool_calls'].find(run.id, 's1')
    assert row.status is ToolCallStatus.COMPLETED
    assert row.risk is ToolRisk.READ
    assert container.repositories['runs'].get(run.id).status is RunStatus.SUCCEEDED
    container.shutdown()


# P2-3：tool call 落库异常曾按 except Exception 吞掉 → 记录不存在但工具照常执行

def test_persistence_error_fails_run_instead_of_executing(tmp_path, monkeypatch):
    from sqlalchemy.exc import OperationalError

    call = ToolCallRequest(tool_call_id='d1', name='task_query', arguments={})
    llm = FakeLlm([tool_turn([call]), text_turn('never')])
    gateway = FakeToolGateway(tools=[read_tool('task_query')])
    container, _engine, _sf = build_stack(
        tmp_path / 'p.db', llm, gateway=gateway, executor_factory=_inline)

    def boom(_record):
        raise OperationalError('INSERT INTO agent_tool_call', {},
                               Exception('db down'))

    monkeypatch.setattr(container.repositories['tool_calls'], 'create', boom)
    session = new_session(container)
    run = _submit(container, session)

    stored = container.repositories['runs'].get(run.id)
    assert stored.status is RunStatus.FAILED
    assert (stored.error or '').startswith('WORKER_CRASH')
    assert gateway.executed == []  # 记录没落库 → 绝不执行工具
    container.shutdown()

