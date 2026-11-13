# -*- coding: utf-8 -*-
"""INT-2466 审批过期的命令侧结算与唤醒（P2-1 回归）。

审计打回 P2-1 的根因：列表查询把到点单写库成 EXPIRED（CQRS 违规），
随后决策命中「非 PENDING → 409 APPROVAL_ALREADY_DECIDED」，且这条分支
不唤醒 run —— 「先查列表再决策」会让 run 永久停在 WAITING_APPROVAL。

本文件锚定三条不变量：

1. ``GET /runs/{id}/approvals`` 只读：到点但未结算的单仍如实返回 PENDING；
2. 过期单决策 → 409 ``APPROVAL_EXPIRED``，run 收到 ``APPROVAL_EXPIRED`` 结果
   继续收口（不是挂死）；
3. 无人决策时由周期扫描结算并提交 run（``run_once``）。
"""
import os
import threading
from datetime import timedelta

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from fastapi.testclient import TestClient

from agent_service.app import create_app
from agent_service.application.approval_expiry import ApprovalExpiryScanner
from agent_service.domain.enums import ApprovalStatus, RunStatus
from agent_service.domain.model.entities import ToolCallRequest
from agent_service.infrastructure.persistence.models.agent_models import (
    AgentApproval as AgentApprovalPO,
)
from shared.utils.time_utils import utcnow
from tests.agent_write.helpers import (
    FakeLlm, FakeToolGateway, approvals_of, make_container, pending_approval,
    start_run, text_turn, tool_turn, write_tool,
)

OWNER = {'X-User-Id': '7', 'X-Tenant-Id': 't1',
         'X-User-Permissions': 'task:read,task:execute'}


def _expire_in_db(container, approval_id: str) -> None:
    """把审批单的 expires_at 改到过去（等价 TTL 到点，不动 status）。"""
    repo = container.repositories['approvals']
    session = repo._session_factory()  # noqa: SLF001 - 测试夹具
    try:
        session.query(AgentApprovalPO).filter(
            AgentApprovalPO.id == approval_id).update(
                {'expires_at': utcnow() - timedelta(seconds=1)},
                synchronize_session=False)
        session.commit()
    finally:
        session.close()


def _api_client(tmp_path, *, name='approval_expiry_api.db'):
    call = ToolCallRequest(tool_call_id='c1', name='task_create',
                           arguments={'body': {'name': '过期任务'}})
    llm = FakeLlm([tool_turn([call]), text_turn('已完成')])
    gateway = FakeToolGateway(tools=[write_tool('task_create')])
    container, _engine, _sf = make_container(tmp_path, llm, gateway,
                                             name=name)
    return TestClient(create_app(container=container)), container


def _waiting_run(client) -> str:
    session = client.post('/api/v1/agent/sessions', json={'title': '过期'},
                          headers=OWNER)
    assert session.status_code == 201, session.text
    run = client.post(
        f"/api/v1/agent/sessions/{session.json()['id']}/runs",
        json={'message': '帮我创建任务'}, headers=OWNER)
    assert run.status_code == 201, run.text
    body = run.json()['run']
    assert body['status'] == 'WAITING_APPROVAL'
    return body['id']


def _only_approval(client, run_id) -> dict:
    listing = client.get(f'/api/v1/agent/runs/{run_id}/approvals',
                         headers=OWNER)
    assert listing.status_code == 200, listing.text
    items = listing.json()['items']
    assert len(items) == 1
    return items[0]


# ---------------------------------------------------------------- 查询只读

def test_list_does_not_settle_expired_approval(tmp_path):
    """§3.1 CQRS：列表只读，到点单在查询侧不得被写库成 EXPIRED。"""
    client, container = _api_client(tmp_path)
    with client:
        run_id = _waiting_run(client)
        approval = _only_approval(client, run_id)
        _expire_in_db(container, approval['id'])

        item = _only_approval(client, run_id)
        assert item['status'] == 'PENDING'
        assert container.repositories['approvals'].get(
            approval['id']).status is ApprovalStatus.PENDING
        # 查询不产生副作用：run 仍停在等待审批
        assert client.get(f'/api/v1/agent/runs/{run_id}',
                          headers=OWNER).json()['status'] == 'WAITING_APPROVAL'
        assert container.tool_gateway.executed == []


# ---------------------------------------------------------------- 列表后决策

def test_decide_after_list_on_expired_approval_resumes_run(tmp_path):
    """P2-1 回归：先查列表、再决策过期单 → 409 且 run 收到过期结果继续。"""
    client, container = _api_client(tmp_path)
    with client:
        run_id = _waiting_run(client)
        approval = _only_approval(client, run_id)
        _expire_in_db(container, approval['id'])

        # 复现路径第 3 步：先看列表（只读，不再把单据写死成 EXPIRED）
        assert _only_approval(client, run_id)['status'] == 'PENDING'

        # 第 4 步：过期单决策 → 409 APPROVAL_EXPIRED（不是 APPROVAL_ALREADY_DECIDED）
        resp = client.post(
            f"/api/v1/agent/approvals/{approval['id']}/decision",
            json={'decision': 'APPROVE'}, headers=OWNER)
        assert resp.status_code == 409, resp.text
        assert resp.json()['code'] == 'APPROVAL_EXPIRED'

        # 不执行、不挂死：过期结果回灌模型，run 继续收口
        assert container.tool_gateway.executed == []
        assert client.get(f'/api/v1/agent/runs/{run_id}',
                          headers=OWNER).json()['status'] == 'SUCCEEDED'
        result = container.repositories['tool_calls'].find(run_id, 'c1')
        assert result.result_code == 'APPROVAL_EXPIRED'
        assert container.repositories['approvals'].get(
            approval['id']).status is ApprovalStatus.EXPIRED


def test_decide_on_already_settled_expired_approval_is_expired_not_conflict(
        tmp_path):
    """已被命令侧结算成 EXPIRED 后再决策：仍是 409 APPROVAL_EXPIRED。"""
    client, container = _api_client(tmp_path)
    with client:
        run_id = _waiting_run(client)
        approval = _only_approval(client, run_id)
        _expire_in_db(container, approval['id'])

        # 命令侧扫描先结算
        assert container.approval_service.expire_due() == [run_id]
        resp = client.post(
            f"/api/v1/agent/approvals/{approval['id']}/decision",
            json={'decision': 'APPROVE'}, headers=OWNER)
        assert resp.status_code == 409, resp.text
        assert resp.json()['code'] == 'APPROVAL_EXPIRED'
        assert container.tool_gateway.executed == []


# ---------------------------------------------------------------- 周期扫描

def test_periodic_scanner_expires_and_wakes_run(tmp_path):
    """无人决策：周期扫描结算 EXPIRED 并提交 run，run 收下过期结果收口。"""
    call = ToolCallRequest(tool_call_id='c1', name='task_create',
                           arguments={'body': {'name': '耗时任务'}})
    llm = FakeLlm([tool_turn([call]), text_turn('已完成')])
    gateway = FakeToolGateway(tools=[write_tool('task_create')])
    container, _engine, _sf = make_container(tmp_path, llm, gateway,
                                             name='approval_expiry_scan.db')
    run = start_run(container)
    approval = pending_approval(container, run.id)
    _expire_in_db(container, approval.id)

    scanner = ApprovalExpiryScanner(
        approvals=container.approval_service,
        wake_run=container.executor.submit, interval_seconds=30)

    assert scanner.run_once() == [run.id]
    # 幂等：再扫一轮没有新过期单
    assert scanner.run_once() == []

    assert container.repositories['approvals'].get(
        approval.id).status is ApprovalStatus.EXPIRED
    assert container.repositories['runs'].get(run.id).status is \
        RunStatus.SUCCEEDED
    result = container.repositories['tool_calls'].find(run.id, 'c1')
    assert result.result_code == 'APPROVAL_EXPIRED'
    assert gateway.executed == []
    assert len(approvals_of(container, run.id)) == 1


def test_scanner_does_not_touch_pending_within_ttl(tmp_path):
    """未到点的待审批单不被扫描误伤。"""
    call = ToolCallRequest(tool_call_id='c1', name='task_create',
                           arguments={'body': {'name': '正常等待'}})
    llm = FakeLlm([tool_turn([call]), text_turn('已完成')])
    gateway = FakeToolGateway(tools=[write_tool('task_create')])
    container, _engine, _sf = make_container(tmp_path, llm, gateway,
                                             name='approval_expiry_keep.db')
    run = start_run(container)
    approval = pending_approval(container, run.id)

    scanner = ApprovalExpiryScanner(
        approvals=container.approval_service,
        wake_run=container.executor.submit, interval_seconds=30)

    assert scanner.run_once() == []
    assert container.repositories['approvals'].get(
        approval.id).status is ApprovalStatus.PENDING
    assert container.repositories['runs'].get(run.id).status is \
        RunStatus.WAITING_APPROVAL
    assert gateway.executed == []


# ---------------------------------------------------------------- 生命周期

def test_lifespan_starts_and_stops_expiry_scanner(tmp_path, monkeypatch):
    """总开关开启时随应用启停扫描线程；关闭时不产生后台扫描。"""
    from agent_service.config.config import Config

    name = 'agent-approval-expiry'
    monkeypatch.setattr(Config, 'AGENT_ENABLED', True)
    monkeypatch.setattr(Config, 'APPROVAL_EXPIRY_SCAN_INTERVAL_SECONDS', 3600.0)
    client, _container = _api_client(tmp_path, name='approval_expiry_life.db')
    with client:
        assert name in [thread.name for thread in threading.enumerate()]
    assert name not in [thread.name for thread in threading.enumerate()]

    # 关闭态：即使配了间隔也不启动
    monkeypatch.setattr(Config, 'AGENT_ENABLED', False)
    client, _container = _api_client(tmp_path, name='approval_expiry_off.db')
    with client:
        assert name not in [thread.name for thread in threading.enumerate()]
