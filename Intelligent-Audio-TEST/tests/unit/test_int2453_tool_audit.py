# -*- coding: utf-8 -*-
"""INT-2453 Loop 集成：allowed-tools 交集 / 执行期拒绝 / audit / 并行回灌。

验收锚点（卡面可测标准 5 + §6.3）：
5. 3 个只读调用并行执行，结果按 tool_call_id 回灌顺序正确；
§6.3：Skill 声明的工具集 ∩ 用户权限，未声明的工具运行时不装配；
审计：agent_tool_call 行含 run_id / tool / args_hash / decision / latency / result_code。
"""
import json
import os
import time

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from agent_service.application.run_worker import InlineRunExecutor
from agent_service.application.tool_gateway import (
    PERMISSION_DENIED, SharedToolGateway,
)
from agent_service.app import create_app
from agent_service.domain.enums import ToolCallStatus
from agent_service.domain.model.entities import ToolCallRequest
from agent_service.infrastructure.tools.registry_bridge import (
    RestResult, RunCredentialRegistry, SharedToolRegistryBridge,
)
from agent_service.wiring import build_container
from tests.unit.int2451_agent_fakes import (
    FakeLlm, FakeProviderResolver, build_stack, make_engine, text_turn,
    tool_turn,
)


class FakeRestClient:
    def __init__(self, delay_by_call=None):
        self.calls = []
        self.delay_by_call = delay_by_call or {}

    def call(self, tool, arguments, **kwargs):
        self.calls.append({'tool': tool, 'arguments': arguments, **kwargs})
        delay = self.delay_by_call.get(arguments.get('task_id'), 0)
        if delay:
            time.sleep(delay)
        return RestResult(
            status=200,
            payload={'echo_tool': tool['name'], 'args': arguments},
            text=json.dumps({'echo_tool': tool['name'], 'args': arguments},
                            ensure_ascii=False))


def _gateway(rest, credentials=None):
    return SharedToolGateway(
        bridge=SharedToolRegistryBridge(), rest=rest,
        credentials=credentials or RunCredentialRegistry())


def _stack(tmp_path, llm, rest, credentials=None):
    return build_stack(
        tmp_path / 'agent.db', llm,
        gateway=_gateway(rest, credentials),
        executor_factory=lambda orch: InlineRunExecutor(orch))


def _run(container, *, permissions, active_skill=None, message='你好'):
    session = container.run_service.create_session(
        owner_id=7, tenant_id='t1', title='t', active_skill=active_skill,
        permissions=permissions)
    run, created = container.run_service.create_run(
        session.id, owner_id=7, tenant_id='t1', message=message,
        permissions=permissions, active_skill=active_skill)
    assert created
    container.executor.submit(run.id)
    return container.repositories['runs'].get(run.id)


def _tool_names(request):
    return [t['function']['name'] for t in request.tools]


def _tool_calls_by_id(container, run_id):
    events = container.repositories['events'].list_after(run_id, 0, 10000)
    return [e for e in events if e.type.value == 'tool_result']


# ---------------------------------------------------------------- exposure

def test_active_skill_only_exposes_declared_tools(tmp_path):
    llm = FakeLlm([text_turn('好')])
    container, _, _ = _stack(tmp_path, llm, FakeRestClient())
    _run(container, permissions=['*'], active_skill='platform-reference')
    names = _tool_names(llm.requests[0])
    assert names == ['platform_contract', 'tool_search']


def test_no_skill_exposes_tools_intersect_permissions(tmp_path):
    llm = FakeLlm([text_turn('好')])
    container, _, _ = _stack(tmp_path, llm, FakeRestClient())
    _run(container, permissions=['task:read'])
    names = set(_tool_names(llm.requests[0]))
    assert 'task_query' in names
    assert 'report_query' not in names       # 权限不足
    assert 'memory_search' in names          # 预留但无权限要求 → 装配

    llm2 = FakeLlm([text_turn('好')])
    (tmp_path / 'second').mkdir()
    container2, _, _ = _stack(tmp_path / 'second', llm2, FakeRestClient())
    _run(container2, permissions=['*'])
    assert len(_tool_names(llm2.requests[0])) == 31


# ---------------------------------------------------------------- execution scope

def test_undeclared_tool_is_denied_at_execution(tmp_path):
    llm = FakeLlm([
        tool_turn([ToolCallRequest('c1', 'task_query',
                                   {'action': 'list', 'page': 1})]),
        text_turn('好的'),
    ])
    rest = FakeRestClient()
    container, _, _ = _stack(tmp_path, llm, rest)
    run = _run(container, permissions=['*'], active_skill='platform-reference')

    record = container.repositories['tool_calls'].find(run.id, 'c1')
    assert record.status is ToolCallStatus.DENIED
    assert record.permission_decision == 'deny'
    assert record.result_code == 'SKILL_TOOL_DENIED'
    assert rest.calls == []  # 未开放的工具没有回源

    results = _tool_calls_by_id(container, run.id)
    assert '未对当前激活 Skill 开放' in results[0].payload['content']


# ---------------------------------------------------------------- audit rows

def test_audit_row_fields_complete_on_success(tmp_path):
    llm = FakeLlm([
        tool_turn([ToolCallRequest('c1', 'task_query',
                                   {'action': 'detail', 'task_id': 9})]),
        text_turn('完成'),
    ])
    rest = FakeRestClient()
    container, _, _ = _stack(tmp_path, llm, rest)
    run = _run(container, permissions=['task:read'])

    record = container.repositories['tool_calls'].find(run.id, 'c1')
    assert record.run_id == run.id
    assert record.tool == 'task_query'
    assert len(record.args_hash) == 64
    assert record.permission_decision == 'allow'
    assert record.result_code == 'OK'
    assert record.latency_ms is not None
    assert record.status is ToolCallStatus.COMPLETED
    assert rest.calls[0]['tool']['name'] == 'task_get'


def test_audit_row_marks_permission_denial(tmp_path):
    llm = FakeLlm([
        tool_turn([ToolCallRequest('c1', 'task_query',
                                   {'action': 'list', 'page': 1})]),
        text_turn('无权'),
    ])
    rest = FakeRestClient()
    container, _, _ = _stack(tmp_path, llm, rest)
    # report:read 用户看不到 task_query（不装配），但模型仍可能硬调 → 网关拒绝
    run = _run(container, permissions=['report:read'])

    record = container.repositories['tool_calls'].find(run.id, 'c1')
    assert record.status is ToolCallStatus.DENIED
    assert record.permission_decision == 'deny'
    assert record.result_code == PERMISSION_DENIED
    assert rest.calls == []


# ---------------------------------------------------------------- parallel

def test_three_parallel_reads_replay_by_tool_call_id(tmp_path):
    calls = [
        ToolCallRequest('c-slow', 'task_query', {'action': 'detail', 'task_id': 1}),
        ToolCallRequest('c-mid', 'task_query', {'action': 'detail', 'task_id': 2}),
        ToolCallRequest('c-fast', 'task_query', {'action': 'detail', 'task_id': 3}),
    ]
    llm = FakeLlm([tool_turn(calls), text_turn('汇总完成')])
    # 完成顺序：3 最快、2 次之、1 最慢 —— 回灌必须按 tool_call_id 而不是完成顺序
    rest = FakeRestClient(delay_by_call={1: 0.15, 2: 0.07, 3: 0.0})
    container, _, _ = _stack(tmp_path, llm, rest)
    run = _run(container, permissions=['task:read'])

    assert len(rest.calls) == 3
    # 第二轮模型请求里，每个 tool 消息的内容与自己的 tool_call_id 配对
    second = llm.requests[1]
    tool_messages = {m.tool_call_id: m.content for m in second.messages
                     if m.role == 'tool'}
    assert set(tool_messages) == {'c-slow', 'c-mid', 'c-fast'}
    assert '"task_id": 1' in tool_messages['c-slow']
    assert '"task_id": 2' in tool_messages['c-mid']
    assert '"task_id": 3' in tool_messages['c-fast']

    run_final = container.repositories['runs'].get(run.id)
    assert run_final.status.value == 'SUCCEEDED'


def test_credentials_forwarded_from_run_registry(tmp_path):
    llm = FakeLlm([
        tool_turn([ToolCallRequest('c1', 'task_query',
                                   {'action': 'list', 'page': 1})]),
        text_turn('好'),
    ])
    rest = FakeRestClient()
    credentials = RunCredentialRegistry()
    container, _, _ = _stack(tmp_path, llm, rest, credentials)
    session = container.run_service.create_session(
        owner_id=7, tenant_id='t1', title='t')
    run, _ = container.run_service.create_run(
        session.id, owner_id=7, tenant_id='t1', message='hi',
        permissions=['task:read'])
    credentials.put(run.id, 'Bearer abc')
    container.executor.submit(run.id)

    assert rest.calls[0]['authorization'] == 'Bearer abc'


# ---------------------------------------------------------------- REST /skills

def test_skills_endpoint_lists_31_tools_without_duplicates(tmp_path):
    from fastapi.testclient import TestClient
    from agent_service.infrastructure.wakeup import LocalRunWakeup

    engine, session_factory = make_engine(tmp_path / 'skills.db')
    container = build_container(
        session_factory,
        provider_resolver=FakeProviderResolver(FakeLlm([text_turn('x')])),
        wakeup=LocalRunWakeup(),
        executor_factory=lambda orch: InlineRunExecutor(orch))
    with TestClient(create_app(container=container)) as client:
        admin = client.get('/api/v1/agent/skills',
                           headers={'X-User-Id': '7', 'X-Tenant-Id': 't1',
                                    'X-User-Permissions': '*'})
        assert admin.status_code == 200, admin.text
        body = admin.json()
        names = [t['name'] for t in body['tools']]
        assert len(names) == 31 and len(names) == len(set(names))
        assert body['tools_count'] == 31
        enabled = {t['name'] for t in body['tools'] if t['enabled']}
        # M0 四项常驻；M1 各域卡按域追加
        # （INT-2458 audio_query / INT-2462 evaluation_query / INT-2464 algorithm_query /
        #   INT-2460 testcase_query + testcase_generate）
        # 精确等值：新增启用工具必须在本卡同步更新该集合，避免无意多启用。
        assert enabled == {'platform_contract', 'tool_search', 'task_query',
                           'report_query', 'audio_query', 'evaluation_query',
                           'algorithm_query', 'testcase_query',
                           'testcase_generate'}

        low = client.get('/api/v1/agent/skills',
                         headers={'X-User-Id': '8', 'X-Tenant-Id': 't1',
                                  'X-User-Permissions': 'task:read'})
        low_names = {t['name'] for t in low.json()['tools']}
        assert 'task_query' in low_names
        assert 'report_query' not in low_names
        assert 'tool_search' in low_names


def test_reserved_tool_returns_not_enabled_through_loop(tmp_path):
    llm = FakeLlm([
        tool_turn([ToolCallRequest('c1', 'memory_search', {'query': 'x'})]),
        text_turn('未启用'),
    ])
    container, _, _ = _stack(tmp_path, llm, FakeRestClient())
    run = _run(container, permissions=['*'])
    record = container.repositories['tool_calls'].find(run.id, 'c1')
    assert record.status is ToolCallStatus.DENIED
    assert record.permission_decision == 'not_enabled'
    assert record.result_code == 'TOOL_NOT_ENABLED'
