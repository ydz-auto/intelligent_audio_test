# -*- coding: utf-8 -*-
"""INT-2500 回归：tool_search 命中的长尾 MCP 工具经 Loop 不再被判未注册。

根因：Loop 执行前的注册判定只看意图注册表（31 个），205 个 MCP 工具全部
落进 ``TOOL_NOT_REGISTERED``。修复后两份注册表任一命中即按已注册处理，风险
由网关按 HTTP 方法推导（GET=READ、其余=WRITE）；两份都查不到才拒绝
（fail-closed），写操作仍被 M0 只读门禁拦下。
"""
import json
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from agent_service.application.run_worker import InlineRunExecutor
from agent_service.application.tool_gateway import SharedToolGateway
from agent_service.domain.enums import ToolCallStatus, ToolRisk
from agent_service.domain.model.entities import ToolCallRequest
from agent_service.infrastructure.tools.registry_bridge import (
    RestResult, RunCredentialRegistry, SharedToolRegistryBridge,
)
from tests.unit.int2451_agent_fakes import (
    FakeLlm, build_stack, text_turn, tool_turn,
)


class FakeRestClient:
    """记录回源请求，返回 200（MCP 工具应真的发到网关 REST）。"""

    def __init__(self):
        self.calls = []

    def call(self, tool, arguments, **kwargs):
        self.calls.append({'tool': tool, 'arguments': arguments, **kwargs})
        payload = {'items': [], 'total': 0, 'echo_tool': tool['name']}
        return RestResult(status=200, payload=payload,
                          text=json.dumps(payload, ensure_ascii=False))


def _gateway(rest):
    return SharedToolGateway(
        bridge=SharedToolRegistryBridge(), rest=rest,
        credentials=RunCredentialRegistry())


def _stack(tmp_path, llm, rest):
    return build_stack(
        tmp_path / 'agent.db', llm,
        gateway=_gateway(rest),
        executor_factory=lambda orch: InlineRunExecutor(orch))


def _run(container, *, permissions=('*',), active_skill=None):
    session = container.run_service.create_session(
        owner_id=7, tenant_id='t1', title='t', active_skill=active_skill,
        permissions=list(permissions))
    run, created = container.run_service.create_run(
        session.id, owner_id=7, tenant_id='t1', message='查任务',
        permissions=list(permissions), active_skill=active_skill)
    assert created
    container.executor.submit(run.id)
    return container.repositories['runs'].get(run.id)


def _tool_results(container, run_id):
    return [e for e in container.repositories['events'].list_after(
                run_id, 0, 10000)
            if e.type.value == 'tool_result']


# ---------------------------------------------------------------- 长尾 MCP 工具

def test_tool_search_discovered_mcp_tool_executes(tmp_path):
    """声明了 tool_search 的 Skill：task_list（MCP GET）正常回源执行。"""
    llm = FakeLlm([
        tool_turn([ToolCallRequest('c1', 'task_list', {'page': 1})]),
        text_turn('查到了'),
    ])
    rest = FakeRestClient()
    container, _, _ = _stack(tmp_path, llm, rest)
    run = _run(container, permissions=['*'],
               active_skill='platform-reference')

    # 网关真的被调用（不再在 Loop 层被判未注册）
    assert len(rest.calls) == 1
    assert rest.calls[0]['tool']['name'] == 'task_list'

    record = container.repositories['tool_calls'].find(run.id, 'c1')
    assert record.status is ToolCallStatus.COMPLETED
    assert record.result_code == 'OK'
    assert record.risk is ToolRisk.READ       # MCP GET → READ
    assert record.permission_decision == 'allow'

    results = _tool_results(container, run.id)
    assert len(results) == 1
    assert results[0].payload['ok'] is True
    assert results[0].payload['error_code'] == 'OK'
    assert container.repositories['runs'].get(run.id).status.value == 'SUCCEEDED'


def test_mcp_write_tool_still_blocked_by_m0_gate(tmp_path):
    """MCP POST（task_create）风险=WRITE：M2 起只生成提案，审批前不回源。"""
    llm = FakeLlm([
        tool_turn([ToolCallRequest(
            'c2', 'task_create', {'body': {'name': '接线测试_任务'}})]),
        text_turn('需要审批'),
    ])
    rest = FakeRestClient()
    container, _, _ = _stack(tmp_path, llm, rest)
    run = _run(container, permissions=['*'],
               active_skill='platform-reference')

    assert rest.calls == []                    # 写操作没有回源
    record = container.repositories['tool_calls'].find(run.id, 'c2')
    assert record.status is ToolCallStatus.WAITING_APPROVAL
    assert record.result_code == 'APPROVAL_REQUIRED'
    assert record.risk is ToolRisk.WRITE
    assert container.repositories['runs'].get(run.id).status.value == \
        'WAITING_APPROVAL'


# ---------------------------------------------------------------- fail-closed

def test_unknown_tool_in_neither_registry_is_rejected(tmp_path):
    """两份注册表都查不到 → 仍是 TOOL_NOT_REGISTERED，且无副作用。"""
    llm = FakeLlm([
        tool_turn([ToolCallRequest('c3', 'no_such_tool_xyz', {'all': True})]),
        text_turn('该工具不可用'),
    ])
    rest = FakeRestClient()
    container, _, _ = _stack(tmp_path, llm, rest)
    run = _run(container, permissions=['*'],
               active_skill='platform-reference')

    assert rest.calls == []
    record = container.repositories['tool_calls'].find(run.id, 'c3')
    assert record.status is ToolCallStatus.DENIED
    assert record.permission_decision == 'tool_not_registered'
    assert (record.result or {}).get('error_code') == 'TOOL_NOT_REGISTERED'
    assert record.risk is ToolRisk.DESTRUCTIVE   # 未知工具按最高风险记账

    results = _tool_results(container, run.id)
    assert results[0].payload['error_code'] == 'TOOL_NOT_REGISTERED'


def test_gateway_risk_of_returns_none_for_unknown():
    """网关 risk_of 不再把未知工具降级成 READ（fail-closed 的依据）。"""
    gateway = _gateway(FakeRestClient())
    assert gateway.risk_of('task_list') is ToolRisk.READ
    assert gateway.risk_of('task_create') is ToolRisk.WRITE
    assert gateway.risk_of('no_such_tool_xyz') is None
