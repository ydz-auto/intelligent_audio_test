# -*- coding: utf-8 -*-
"""INT-2466 审批 REST 契约（agent_service，§11）。

| GET  | /api/v1/agent/runs/{id}/approvals |
| POST | /api/v1/agent/approvals/{id}/decision |

归属不符统一 404（不泄漏存在性）；并发 / 重复决策 409；过期 409 且不执行。
"""
import os

import pytest

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from fastapi.testclient import TestClient

from agent_service.app import create_app
from agent_service.domain.model.entities import ToolCallRequest
from tests.agent_write.helpers import (
    FakeLlm, FakeToolGateway, make_container, text_turn, tool_turn, write_tool,
)

OWNER = {'X-User-Id': '7', 'X-Tenant-Id': 't1',
         'X-User-Permissions': 'task:read,task:execute'}
OTHER = {'X-User-Id': '8', 'X-Tenant-Id': 't1',
         'X-User-Permissions': 'task:execute'}


def _client(tmp_path, *, name='approval_api.db'):
    call = ToolCallRequest(tool_call_id='c1', name='task_create',
                           arguments={'body': {'name': '审批任务'}})
    llm = FakeLlm([tool_turn([call]), text_turn('已完成')])
    gateway = FakeToolGateway(tools=[write_tool('task_create')])
    container, _engine, _sf = make_container(tmp_path, llm, gateway,
                                             name=name)
    return TestClient(create_app(container=container)), container


def _create_waiting_run(client, headers=OWNER):
    session = client.post('/api/v1/agent/sessions', json={'title': '审批'},
                          headers=headers)
    assert session.status_code == 201, session.text
    run = client.post(
        f"/api/v1/agent/sessions/{session.json()['id']}/runs",
        json={'message': '帮我创建任务'}, headers=headers)
    assert run.status_code == 201, run.text
    body = run.json()['run']
    assert body['status'] == 'WAITING_APPROVAL'
    return body['id']


def _approval_id(client, run_id, headers=OWNER):
    listing = client.get(f'/api/v1/agent/runs/{run_id}/approvals',
                         headers=headers)
    assert listing.status_code == 200, listing.text
    items = listing.json()['items']
    assert len(items) == 1
    return items[0]


def test_list_and_approve_via_api(tmp_path):
    client, container = _client(tmp_path)
    with client:
        run_id = _create_waiting_run(client)
        item = _approval_id(client, run_id)
        assert item['run_id'] == run_id
        assert item['tool_call_id'] == 'c1'
        assert item['status'] == 'PENDING'
        assert item['proposal']['tool'] == 'task_create'
        assert item['expires_at']

        resp = client.post(
            f"/api/v1/agent/approvals/{item['id']}/decision",
            json={'decision': 'APPROVE'}, headers=OWNER)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body['approval']['status'] == 'APPROVED'
        assert body['approval']['decided_by'] == 7
        assert body['run_status'] == 'WAITING_APPROVAL'

        # 决策后 run 已恢复并完成（Inline 执行器）
        assert client.get(f'/api/v1/agent/runs/{run_id}',
                          headers=OWNER).json()['status'] == 'SUCCEEDED'
        assert container.tool_gateway.executed[0][0] == 'c1'


def test_decision_by_other_user_404(tmp_path):
    client, container = _client(tmp_path)
    with client:
        run_id = _create_waiting_run(client)
        item = _approval_id(client, run_id)
        resp = client.post(
            f"/api/v1/agent/approvals/{item['id']}/decision",
            json={'decision': 'APPROVE'}, headers=OTHER)
        assert resp.status_code == 404
        assert resp.json() == {'detail': 'not found'}
        assert container.tool_gateway.executed == []


def test_invalid_decision_value_400(tmp_path):
    client, _container = _client(tmp_path)
    with client:
        run_id = _create_waiting_run(client)
        item = _approval_id(client, run_id)
        resp = client.post(
            f"/api/v1/agent/approvals/{item['id']}/decision",
            json={'decision': 'MAYBE'}, headers=OWNER)
        assert resp.status_code == 400
        assert 'APPROVE' in resp.json()['detail']


def test_second_decision_conflicts(tmp_path):
    client, container = _client(tmp_path)
    with client:
        run_id = _create_waiting_run(client)
        item = _approval_id(client, run_id)
        first = client.post(
            f"/api/v1/agent/approvals/{item['id']}/decision",
            json={'decision': 'REJECT'}, headers=OWNER)
        assert first.status_code == 200
        second = client.post(
            f"/api/v1/agent/approvals/{item['id']}/decision",
            json={'decision': 'APPROVE'}, headers=OWNER)
        assert second.status_code == 409
        assert container.tool_gateway.executed == []


def test_expired_decision_409_and_not_executed(tmp_path):
    from datetime import timedelta

    from agent_service.infrastructure.persistence.models.agent_models import (
        AgentApproval as AgentApprovalPO,
    )
    from shared.utils.time_utils import utcnow

    client, container = _client(tmp_path)
    with client:
        run_id = _create_waiting_run(client)
        item = _approval_id(client, run_id)
        repo = container.repositories['approvals']
        session = repo._session_factory()  # noqa: SLF001 - 测试夹具
        try:
            session.query(AgentApprovalPO).filter(
                AgentApprovalPO.id == item['id']).update(
                    {'expires_at': utcnow() - timedelta(seconds=1)},
                    synchronize_session=False)
            session.commit()
        finally:
            session.close()

        resp = client.post(
            f"/api/v1/agent/approvals/{item['id']}/decision",
            json={'decision': 'APPROVE'}, headers=OWNER)
        assert resp.status_code == 409
        assert resp.json()['code'] == 'APPROVAL_EXPIRED'
        assert container.tool_gateway.executed == []
        # 过期结果已回灌模型，run 继续收口（不是一直挂着）
        assert client.get(f'/api/v1/agent/runs/{run_id}',
                          headers=OWNER).json()['status'] == 'SUCCEEDED'
        result = container.repositories['tool_calls'].find(run_id, 'c1')
        assert result.result_code == 'APPROVAL_EXPIRED'
