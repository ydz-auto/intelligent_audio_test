# -*- coding: utf-8 -*-
"""INT-2466 写操作基线：提案 → 审批 → 幂等执行 → 审计。

验收锚点：
1. WRITE / DESTRUCTIVE 调用先生成 ``agent_approval`` 提案，审批前无副作用；
2. 批准后只执行一次；拒绝 / 过期不执行；
3. 审计行可还原「谁发起、谁批准、产生什么副作用」；
4. 取消：未决提案作废，不执行。
"""
import json
import os

import pytest

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from agent_service.domain.enums import (
    ApprovalStatus, RunStatus, ToolCallStatus,
)
from agent_service.domain.model.entities import ToolCallRequest
from tests.agent_write.helpers import (
    FakeLlm, FakeToolGateway, approvals_of, decide, destructive_tool,
    events_of, events_of_type, make_container, pending_approval, start_run,
    text_turn, tool_turn, write_tool,
)


def _write_scenario(tmp_path, *, gateway=None, tool=None, args=None,
                    followup='已完成'):
    tool = tool or write_tool('task_create')
    args = args or {'body': {'name': '接线任务'}}
    call = ToolCallRequest(tool_call_id='c1', name=tool.name, arguments=args)
    llm = FakeLlm([tool_turn([call]), text_turn(followup)])
    gateway = gateway or FakeToolGateway(tools=[tool])
    container, _engine, _sf = make_container(tmp_path, llm, gateway)
    run = start_run(container)
    return container, llm, gateway, run


# ---------------------------------------------------------------- 提案

def test_write_call_creates_pending_approval_without_side_effect(tmp_path):
    container, llm, gateway, run = _write_scenario(tmp_path)

    stored_run = container.repositories['runs'].get(run.id)
    assert stored_run.status is RunStatus.WAITING_APPROVAL
    # 写工具没有被执行，也没有 tool_result（写还没有结果）
    assert gateway.executed == []
    assert events_of_type(container, run.id, 'tool_result') == []
    assert events_of_type(container, run.id, 'approval_required')

    approval = pending_approval(container, run.id)
    assert approval.status is ApprovalStatus.PENDING
    assert approval.tool_call_id == 'c1'
    assert approval.expires_at is not None
    assert approval.proposal['tool'] == 'task_create'
    assert approval.proposal['risk'] == 'WRITE'
    assert approval.proposal['requested_by'] == 7
    assert approval.proposal['args_hash']
    assert approval.proposal['idempotency_key']

    record = container.repositories['tool_calls'].find(run.id, 'c1')
    assert record.status is ToolCallStatus.WAITING_APPROVAL
    assert record.result_code == 'APPROVAL_REQUIRED'
    assert record.permission_decision == 'approval_required'
    assert record.result['approval_id'] == approval.id
    # 提案不影响模型循环：只发过第一轮，第二段文本没有触发
    assert len(llm.requests) == 1


def test_destructive_tool_also_requires_single_approval(tmp_path):
    """DESTRUCTIVE：先提案（不执行）；批准时还要二次确认（INT-2467）。"""
    from agent_service.domain.exceptions import ApprovalConfirmationRequired

    container, _llm, gateway, run = _write_scenario(
        tmp_path, tool=destructive_tool('device_control'),
        args={'device_id': 3, 'action': 'reboot'})
    approval = pending_approval(container, run.id)
    assert approval.proposal['risk'] == 'DESTRUCTIVE'
    assert gateway.executed == []
    # 只发 APPROVE、不带 confirm → 决策被拒，仍未执行
    with pytest.raises(ApprovalConfirmationRequired):
        decide(container, approval.id, 'APPROVE',
               permissions=('device:control',))
    assert gateway.executed == []
    # 二次确认后才执行
    decide(container, approval.id, 'APPROVE',
           permissions=('device:control',), confirm=True)
    container.executor.submit(run.id)
    assert [item[0] for item in gateway.executed] == ['c1']


def test_proposal_is_idempotent_and_reuses_single_row(tmp_path):
    """同一 tool call 重复进入提案路径：只保留一张单、一条事件。"""
    container, llm, gateway, run = _write_scenario(tmp_path)
    approval = pending_approval(container, run.id)
    # 模拟重复投递 / 恢复：再次执行同一 run（仍在等待审批）
    container.orchestrator.execute(run.id)
    items = approvals_of(container, run.id)
    assert len(items) == 1 and items[0].id == approval.id
    assert len(events_of_type(container, run.id, 'approval_required')) == 1
    assert gateway.executed == []
    assert container.repositories['runs'].get(run.id).status is \
        RunStatus.WAITING_APPROVAL
    assert len(llm.requests) == 1


# ---------------------------------------------------------------- 批准执行

def test_approve_executes_write_once_and_resumes_run(tmp_path):
    container, llm, gateway, run = _write_scenario(tmp_path)
    approval = pending_approval(container, run.id)

    stored, decision_run = decide(container, approval.id, 'APPROVE',
                                  permissions=('task:execute',))
    assert stored['status'] == 'APPROVED'
    assert decision_run.id == run.id
    container.executor.submit(run.id)

    # 恰好执行一次，run 继续模型循环并正常结束
    assert [item[0] for item in gateway.executed] == ['c1']
    assert container.repositories['runs'].get(run.id).status is \
        RunStatus.SUCCEEDED
    assert len(llm.requests) == 2

    record = container.repositories['tool_calls'].find(run.id, 'c1')
    assert record.status is ToolCallStatus.COMPLETED
    assert record.permission_decision == 'approved'
    assert record.result_code == 'OK'
    results = events_of_type(container, run.id, 'tool_result')
    assert len(results) == 1
    assert results[0].payload['ok'] is True

    # 恢复执行不会再次执行（幂等）：重复结算 / 重复投递
    container.orchestrator.execute(run.id)
    container.orchestrator.execute(run.id)
    assert len(gateway.executed) == 1


def test_audit_row_reconstructs_who_approved_and_side_effect(tmp_path):
    container, _llm, _gateway, run = _write_scenario(tmp_path)
    approval = pending_approval(container, run.id)
    decide(container, approval.id, 'APPROVE',
           permissions=('task:execute',))
    container.executor.submit(run.id)

    stored = container.repositories['approvals'].get(approval.id)
    assert stored.decided_by == 7
    assert stored.decided_at is not None
    assert stored.decision_permissions == ['task:execute']

    record = container.repositories['tool_calls'].find(run.id, 'c1')
    audit = (record.result or {}).get('approval') or {}
    assert audit['approval_id'] == approval.id
    assert audit['decided_by'] == 7
    assert audit['decided_at']
    # 谁发起 = run.owner_id；谁批准 = decided_by；副作用 = result_code + result
    assert container.repositories['runs'].get(run.id).owner_id == 7
    assert record.result_code == 'OK'
    assert record.result['ok'] is True


# ---------------------------------------------------------------- 拒绝 / 过期

def test_reject_marks_denied_and_never_executes(tmp_path):
    container, llm, gateway, run = _write_scenario(
        tmp_path, followup='写操作未获批准')
    approval = pending_approval(container, run.id)
    stored, _run = decide(container, approval.id, 'REJECT',
                          permissions=('task:execute',))
    assert stored['status'] == 'REJECTED'
    container.executor.submit(run.id)

    assert gateway.executed == []
    record = container.repositories['tool_calls'].find(run.id, 'c1')
    assert record.status is ToolCallStatus.DENIED
    assert record.result_code == 'APPROVAL_REJECTED'
    results = events_of_type(container, run.id, 'tool_result')
    assert [item.payload['error_code'] for item in results] == [
        'APPROVAL_REJECTED']
    # 拒绝是「可回灌」的结果：模型继续并解释，而不是静默成功
    assert container.repositories['runs'].get(run.id).status is \
        RunStatus.SUCCEEDED
    assert len(llm.requests) == 2


def test_expired_proposal_is_not_executed(tmp_path):
    container, llm, gateway, run = _write_scenario(tmp_path)
    approval = pending_approval(container, run.id)
    # 把过期时间前移到过去（模拟 TTL 到点，不 sleep）
    _expire_now(container, approval.id)

    with pytest.raises(Exception) as exc:
        decide(container, approval.id, 'APPROVE',
               permissions=('task:execute',))
    assert 'EXPIRED' in str(getattr(exc.value, 'code', '')) or \
        type(exc.value).__name__ == 'ApprovalExpired'

    container.executor.submit(run.id)
    assert gateway.executed == []
    record = container.repositories['tool_calls'].find(run.id, 'c1')
    assert record.status is ToolCallStatus.DENIED
    assert record.result_code == 'APPROVAL_EXPIRED'
    assert events_of_type(container, run.id, 'tool_result')[0].payload[
        'error_code'] == 'APPROVAL_EXPIRED'
    # 过期结果回灌模型：模型基于「未执行」继续作答（不会假装写成功）
    assert len(llm.requests) == 2
    assert container.repositories['runs'].get(run.id).status is \
        RunStatus.SUCCEEDED


def _expire_now(container, approval_id):
    """把审批单过期时间改到过去（等价于 TTL 到点，避免测试 sleep）。"""
    from datetime import timedelta

    from agent_service.infrastructure.persistence.models.agent_models import (
        AgentApproval as AgentApprovalPO,
    )
    from shared.utils.time_utils import utcnow

    repo = container.repositories['approvals']
    session = repo._session_factory()  # noqa: SLF001 - 测试夹具
    try:
        hit = session.query(AgentApprovalPO).filter(
            AgentApprovalPO.id == approval_id).update(
                {'expires_at': utcnow() - timedelta(seconds=5)},
                synchronize_session=False)
        session.commit()
        assert hit == 1
    finally:
        session.close()


# ---------------------------------------------------------------- 取消

def test_approval_wait_does_not_consume_duration_budget(tmp_path):
    """等待人工审批的时间不计入 §9.3 执行时长预算。"""
    from datetime import timedelta

    from agent_service.infrastructure.persistence.models.agent_models import (
        AgentApproval as AgentApprovalPO,
        AgentRun as AgentRunPO,
    )
    from shared.utils.time_utils import utcnow
    from tests.unit.int2451_agent_fakes import server_budget

    call = ToolCallRequest(tool_call_id='c1', name='task_create',
                           arguments={'body': {'name': '接线任务'}})
    llm = FakeLlm([tool_turn([call]), text_turn('已完成')])
    gateway = FakeToolGateway(tools=[write_tool('task_create')])
    container, _engine, _sf = make_container(
        tmp_path, llm, gateway,
        budget_defaults=server_budget(max_duration_seconds=10))
    run = start_run(container)
    approval = pending_approval(container, run.id)

    # 模拟「run 已跑 30s、其中 29s 在等审批」：执行时长只剩 1s
    now = utcnow()
    session = container.repositories['approvals']._session_factory()  # noqa: SLF001
    try:
        session.query(AgentRunPO).filter(AgentRunPO.id == run.id).update(
            {'started_at': now - timedelta(seconds=30)},
            synchronize_session=False)
        session.query(AgentApprovalPO).filter(
            AgentApprovalPO.id == approval.id).update(
                {'created_at': now - timedelta(seconds=29)},
                synchronize_session=False)
        session.commit()
    finally:
        session.close()

    decide(container, approval.id, 'APPROVE', permissions=('task:execute',))
    container.executor.submit(run.id)
    stored = container.repositories['runs'].get(run.id)
    assert stored.status is RunStatus.SUCCEEDED, stored.error
    assert len(gateway.executed) == 1


def test_cancel_while_waiting_voids_pending_approval(tmp_path):
    container, _llm, gateway, run = _write_scenario(tmp_path)
    approval = pending_approval(container, run.id)
    stored = container.run_service.cancel_run(
        run.id, owner_id=7, tenant_id='t1')
    assert stored.status is RunStatus.CANCELLED

    latest = container.repositories['approvals'].get(approval.id)
    assert latest.status is ApprovalStatus.REJECTED
    assert latest.decided_by == 7
    assert gateway.executed == []
    # 已取消的 run 决策不生效
    with pytest.raises(Exception):
        decide(container, approval.id, 'APPROVE',
               permissions=('task:execute',))
    assert gateway.executed == []
