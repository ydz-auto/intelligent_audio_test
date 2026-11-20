# -*- coding: utf-8 -*-
"""INT-2466 通用写路径：tool_search 命中的长尾 MCP 写工具（POST/PUT/DELETE）。

验收锚点：写工具在审批前不回源；批准后按原参数回源执行一次，
执行前重新校验权限与实时注册状态。
"""
import json
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from agent_service.application.run_worker import InlineRunExecutor
from agent_service.application.tool_gateway import SharedToolGateway
from agent_service.domain.enums import RunStatus, ToolCallStatus
from agent_service.domain.model.entities import ToolCallRequest
from agent_service.infrastructure.tools.registry_bridge import (
    RestResult, RunCredentialRegistry, SharedToolRegistryBridge,
)
from tests.agent_write.helpers import (
    FakeLlm, approvals_of, decide, events_of_type, pending_approval,
    text_turn, tool_turn,
)
from tests.unit.int2451_agent_fakes import build_stack


class FakeRestClient:
    def __init__(self):
        self.calls = []

    def call(self, tool, arguments, **kwargs):
        self.calls.append({'tool': tool, 'arguments': arguments, **kwargs})
        payload = {'data': {'id': 99}}
        return RestResult(status=200, payload=payload,
                          text=json.dumps(payload, ensure_ascii=False))


def _stack(tmp_path, llm, rest):
    gateway = SharedToolGateway(
        bridge=SharedToolRegistryBridge(), rest=rest,
        credentials=RunCredentialRegistry())
    return build_stack(
        tmp_path / 'generic_write.db', llm, gateway=gateway,
        executor_factory=lambda orch: InlineRunExecutor(orch))


def _start(container):
    session = container.run_service.create_session(
        owner_id=7, tenant_id='t1', title='通用写', permissions=['*'])
    run, created = container.run_service.create_run(
        session.id, owner_id=7, tenant_id='t1', message='创建任务',
        permissions=['*'])
    assert created
    container.executor.submit(run.id)
    return run


def test_mcp_post_write_proposes_then_executes_after_approval(tmp_path):
    call = ToolCallRequest(tool_call_id='c1', name='task_create',
                           arguments={'body': {'name': '接线测试_任务'}})
    llm = FakeLlm([tool_turn([call]), text_turn('任务已创建')])
    rest = FakeRestClient()
    container, _engine, _sf = _stack(tmp_path, llm, rest)
    run = _start(container)

    # 审批前：不回源、无副作用
    assert rest.calls == []
    approval = pending_approval(container, run.id)
    assert approval.proposal['risk'] == 'WRITE'
    assert approval.proposal['arguments'] == {'body': {'name': '接线测试_任务'}}
    # 审批人可见的请求预览（REST 写工具的通用 diff）
    assert approval.diff['method'] == 'POST'
    assert approval.diff['path'] == '/api/v1/tasks'
    assert approval.diff['arguments'] == {'body': {'name': '接线测试_任务'}}
    record = container.repositories['tool_calls'].find(run.id, 'c1')
    assert record.status is ToolCallStatus.WAITING_APPROVAL

    # 批准：按原参数回源一次（POST /api/v1/tasks）
    decide(container, approval.id, 'APPROVE', permissions=['*'])
    container.executor.submit(run.id)
    assert len(rest.calls) == 1
    sent = rest.calls[0]
    assert sent['tool']['name'] == 'task_create'
    assert sent['tool']['method'] == 'POST'
    assert sent['arguments'] == {'body': {'name': '接线测试_任务'}}
    assert container.repositories['runs'].get(run.id).status is \
        RunStatus.SUCCEEDED
    record = container.repositories['tool_calls'].find(run.id, 'c1')
    assert record.status is ToolCallStatus.COMPLETED
    assert record.result_code == 'OK'
    assert events_of_type(container, run.id, 'tool_result')[0].payload[
        'ok'] is True


def test_mcp_write_permission_revoked_does_not_reach_rest(tmp_path):
    call = ToolCallRequest(tool_call_id='c1', name='task_create',
                           arguments={'body': {'name': '接线测试_任务'}})
    llm = FakeLlm([tool_turn([call]), text_turn('未执行')])
    rest = FakeRestClient()
    container, _engine, _sf = _stack(tmp_path, llm, rest)
    run = _start(container)
    approval = pending_approval(container, run.id)
    # 审批时只保留只读权限：task:create 已被收回
    decide(container, approval.id, 'APPROVE', permissions=['task:read'])
    container.executor.submit(run.id)

    assert rest.calls == []
    record = container.repositories['tool_calls'].find(run.id, 'c1')
    assert record.result_code == 'PERMISSION_DENIED'
    assert container.repositories['runs'].get(run.id).status is RunStatus.FAILED
