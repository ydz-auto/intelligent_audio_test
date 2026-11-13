# -*- coding: utf-8 -*-
"""INT-2466 并发 / 权限回收 / 重启恢复。

验收锚点：
1. 并发审批只有一个请求生效，写操作只执行一次；
2. 审批后权限被收回 → 执行失败（不是照旧执行）；
3. Worker 重启：等待审批的 run 不执行写；中断在写执行中的 run 不重放；
4. 同一 Idempotency-Key 重复投递不产生第二次副作用。
"""
import os
import threading

import pytest

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from agent_service.domain.enums import (
    ApprovalStatus, RunStatus, ToolCallStatus,
)
from agent_service.domain.exceptions import ApprovalConflict, ApprovalNotFound
from agent_service.domain.model.entities import ToolCallRequest
from shared.utils.time_utils import utcnow
from tests.agent_write.helpers import (
    FakeLlm, FakeToolGateway, approvals_of, decide, events_of_type,
    make_container, pending_approval, start_run, text_turn, tool_turn,
    write_tool,
)

OWNER = dict(owner_id=7, tenant_id='t1')


def _scenario(tmp_path, **kwargs):
    call = ToolCallRequest(tool_call_id='c1', name='task_create',
                           arguments={'body': {'name': '并发任务'}})
    llm = FakeLlm([tool_turn([call]), text_turn('完成')])
    gateway = FakeToolGateway(tools=[write_tool('task_create')])
    container, engine, sf = make_container(tmp_path, llm, gateway)
    run = start_run(container, **kwargs)
    return container, llm, gateway, run, engine, sf


# ---------------------------------------------------------------- 并发审批

def test_concurrent_approval_only_one_wins(tmp_path):
    container, _llm, gateway, run, _engine, _sf = _scenario(tmp_path)
    approval = pending_approval(container, run.id)

    barrier = threading.Barrier(2)
    outcomes = []
    lock = threading.Lock()

    def attempt():
        barrier.wait()
        try:
            decide(container, approval.id, 'APPROVE',
                   permissions=('task:execute',))
            result = 'approved'
        except ApprovalConflict:
            result = 'conflict'
        with lock:
            outcomes.append(result)

    threads = [threading.Thread(target=attempt) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert sorted(outcomes) == ['approved', 'conflict']
    # 决策只落一次；执行只发生一次
    container.executor.submit(run.id)
    assert len(gateway.executed) == 1
    stored = container.repositories['approvals'].get(approval.id)
    assert stored.status is ApprovalStatus.APPROVED


def test_repeated_settle_executes_write_only_once(tmp_path):
    container, _llm, gateway, run, _engine, _sf = _scenario(tmp_path)
    approval = pending_approval(container, run.id)
    decide(container, approval.id, 'APPROVE', permissions=('task:execute',))
    # 直接把 run 拉回 RUNNING（等价于恢复进入 Loop），重复结算两次
    container.repositories['runs'].transition_if(
        run.id, {RunStatus.WAITING_APPROVAL}, RunStatus.RUNNING)
    assert container.orchestrator._settle_approvals(run.id) is False
    assert container.orchestrator._settle_approvals(run.id) is False
    assert len(gateway.executed) == 1
    record = container.repositories['tool_calls'].find(run.id, 'c1')
    assert record.status is ToolCallStatus.COMPLETED


# ---------------------------------------------------------------- 权限回收

def test_permission_revoked_after_approval_blocks_execution(tmp_path):
    container, llm, gateway, run, _engine, _sf = _scenario(tmp_path)
    approval = pending_approval(container, run.id)

    # 审批时权限已被收回（决策请求携带的实时权限为空）
    stored, _run = decide(container, approval.id, 'APPROVE', permissions=())
    assert stored['status'] == 'APPROVED'
    container.executor.submit(run.id)

    assert gateway.executed == []
    record = container.repositories['tool_calls'].find(run.id, 'c1')
    assert record.status is ToolCallStatus.FAILED
    assert record.result_code == 'PERMISSION_DENIED'
    assert record.result['error_code'] == 'PERMISSION_DENIED'
    errors = events_of_type(container, run.id, 'error')
    assert errors and errors[-1].payload['code'] == 'APPROVAL_EXECUTION_DENIED'
    assert container.repositories['runs'].get(run.id).status is RunStatus.FAILED
    # 权限失败不产生模型轮次：直接收口，不让模型「重试」绕过
    assert len(llm.requests) == 1


def test_approval_of_another_user_is_not_found(tmp_path):
    container, _llm, _gateway, run, _engine, _sf = _scenario(tmp_path)
    approval = pending_approval(container, run.id)
    with pytest.raises(ApprovalNotFound):
        decide(container, approval.id, 'APPROVE',
               owner_id=8, tenant_id='t1', permissions=('*',))
    # 单子仍是 PENDING，未被越权请求改掉
    assert container.repositories['approvals'].get(
        approval.id).status is ApprovalStatus.PENDING


# ---------------------------------------------------------------- 重启恢复

def test_restart_with_pending_approval_never_executes_write(tmp_path):
    container, llm, gateway, run, _engine, _sf = _scenario(tmp_path)
    resumable = container.recovery.recover()
    assert run.id in resumable
    for run_id in resumable:
        container.executor.submit(run_id)

    assert gateway.executed == []
    assert container.repositories['runs'].get(run.id).status is \
        RunStatus.WAITING_APPROVAL
    assert len(llm.requests) == 1
    assert container.repositories['approvals'].get(
        pending_approval(container, run.id).id).status is ApprovalStatus.PENDING


def test_restart_during_write_execution_marks_unverified_and_never_replays(
        tmp_path):
    container, _llm, gateway, run, _engine, _sf = _scenario(tmp_path)
    approval = pending_approval(container, run.id)
    decide(container, approval.id, 'APPROVE', permissions=('task:execute',))

    # 模拟「已进入写执行（RUNNING）后进程被杀」：恢复必须判人工确认
    container.repositories['runs'].transition_if(
        run.id, {RunStatus.WAITING_APPROVAL}, RunStatus.RUNNING)
    container.repositories['tool_calls'].update(
        'c1', run.id, status=ToolCallStatus.RUNNING)

    resumable = container.recovery.recover()
    assert run.id not in resumable
    assert gateway.executed == []
    stored = container.repositories['runs'].get(run.id)
    assert stored.status is RunStatus.FAILED
    assert 'RESTART_WRITE_UNVERIFIED' in (stored.error or '')
    record = container.repositories['tool_calls'].find(run.id, 'c1')
    assert record.status is ToolCallStatus.FAILED
    assert record.permission_decision == 'restart_write_unverified'


def test_missing_approval_is_reproposed_on_resume(tmp_path):
    """崩溃在「写调用落库 / 提案落库」之间：恢复时按记录重建提案（幂等）。"""
    from agent_service.infrastructure.persistence.models.agent_models import (
        AgentApproval as AgentApprovalPO,
    )

    container, llm, gateway, run, _engine, _sf = _scenario(tmp_path)
    approval = pending_approval(container, run.id)
    session = container.repositories['approvals']._session_factory()  # noqa: SLF001
    try:
        session.query(AgentApprovalPO).filter(
            AgentApprovalPO.id == approval.id).delete(synchronize_session=False)
        session.commit()
    finally:
        session.close()
    assert approvals_of(container, run.id) == []

    container.orchestrator.execute(run.id)
    items = approvals_of(container, run.id)
    assert len(items) == 1
    assert items[0].status is ApprovalStatus.PENDING
    assert items[0].proposal['tool'] == 'task_create'
    assert container.repositories['runs'].get(run.id).status is \
        RunStatus.WAITING_APPROVAL
    assert gateway.executed == []
    assert len(llm.requests) == 1


def test_startup_expiry_sweep_marks_due_approvals(tmp_path):
    container, _llm, gateway, run, _engine, _sf = _scenario(tmp_path)
    approval = pending_approval(container, run.id)
    from datetime import timedelta
    from agent_service.infrastructure.persistence.models.agent_models import (
        AgentApproval as AgentApprovalPO,
    )
    repo = container.repositories['approvals']
    session = repo._session_factory()  # noqa: SLF001 - 测试夹具
    try:
        session.query(AgentApprovalPO).filter(
            AgentApprovalPO.id == approval.id).update(
                {'expires_at': utcnow() - timedelta(seconds=1)},
                synchronize_session=False)
        session.commit()
    finally:
        session.close()

    assert container.approval_service.expire_due() == 1
    assert container.repositories['approvals'].get(
        approval.id).status is ApprovalStatus.EXPIRED
    assert gateway.executed == []


# ---------------------------------------------------------------- 幂等键

def test_same_tool_call_reuses_single_record_and_approval(tmp_path):
    """同一 tool_call_id 重复投递：只有一条 tool call、一张提案。"""
    container, _llm, gateway, run, _engine, _sf = _scenario(tmp_path)
    approval = pending_approval(container, run.id)
    record = container.repositories['tool_calls'].find(run.id, 'c1')

    # 重复进入提案路径（模拟重复投递 / 崩溃恢复）
    container.orchestrator.execute(run.id)
    records = [item for item in
               container.repositories['tool_calls'].list_by_run(run.id)
               if item.tool_call_id == 'c1']
    assert len(records) == 1
    assert records[0].idempotency_key == record.idempotency_key
    assert len(approvals_of(container, run.id)) == 1
    assert gateway.executed == []
    assert container.repositories['approvals'].get(
        approval.id).status is ApprovalStatus.PENDING
