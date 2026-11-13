# -*- coding: utf-8 -*-
"""INT-2453 ToolGateway：权限 / Schema / 未启用 / 越权文案 / audit 决策。

验收锚点（卡面可测标准 3、4）：
3. tool_search 返回 Schema 可直接调用；权限不满足的工具不返回；
4. 越权调用返回普通拒绝文本（不抛内部异常、不泄漏资源存在性），
   agent_tool_call 审计行字段齐全（在 test_int2453_tool_audit.py 覆盖）。
"""
import json
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from agent_service.application.tool_gateway import (
    INVALID_ARGUMENTS, PERMISSION_DENIED, RESOURCE_NOT_FOUND,
    SharedToolGateway, TOOL_NOT_ENABLED, UNKNOWN_TOOL, UPSTREAM_ERROR,
    UPSTREAM_UNAVAILABLE,
)
from agent_service.domain.model.entities import ToolCallRequest
from agent_service.domain.ports.tool_gateway import ToolInvocationContext
from agent_service.infrastructure.tools.registry_bridge import (
    RestResult, RunCredentialRegistry, SharedToolRegistryBridge,
)


class FakeRestClient:
    """记录回源请求，返回脚本化响应。"""

    def __init__(self, status=200, payload=None):
        self.status = status
        self.payload = payload if payload is not None else {'ok': True}
        self.calls = []

    def call(self, tool, arguments, **kwargs):
        self.calls.append({'tool': tool, 'arguments': arguments, **kwargs})
        if isinstance(self.status, Exception):
            return RestResult(status=0, error=str(self.status))
        text = json.dumps(self.payload, ensure_ascii=False)
        return RestResult(status=self.status, payload=self.payload, text=text)


def make_gateway(rest=None, credentials=None):
    return SharedToolGateway(
        bridge=SharedToolRegistryBridge(),
        rest=rest or FakeRestClient(),
        credentials=credentials or RunCredentialRegistry(),
    )


def ctx(permissions=('*',), run_id='r1', owner_id=7, tenant='t1'):
    return ToolInvocationContext(
        run_id=run_id, session_id='s1', owner_id=owner_id, tenant_id=tenant,
        step_id='step1', permissions=tuple(permissions), idempotency_key='k')


def call(name, arguments=None):
    return ToolCallRequest(tool_call_id='call-1', name=name,
                          arguments=arguments or {})


# ---------------------------------------------------------------- catalog

def test_all_tools_exposes_31_intent_tools():
    gateway = make_gateway()
    assert len(gateway.all_tools()) == 31
    names = {d.name for d in gateway.all_tools()}
    assert 'platform_contract' in names and 'tool_search' in names
    assert gateway.risk_of('memory_search').value == 'READ'
    assert gateway.risk_of('ui_action').value == 'WRITE'
    assert gateway.risk_of('task_create').value == 'WRITE'   # MCP POST
    assert gateway.risk_of('task_get').value == 'READ'       # MCP GET
    # 两份注册表都查不到 → None（fail-closed，INT-2500；不降级成 READ）
    assert gateway.risk_of('no_such_tool') is None


# ---------------------------------------------------------------- local tools

def test_tool_search_local_and_permission_filtered():
    gateway = make_gateway()
    result = gateway.execute(call('tool_search', {'query': '报告'}),
                             ctx(permissions=('task:read',)))
    assert result.ok and result.error_code == 'OK'
    payload = json.loads(result.content)
    assert all(t['name'].startswith('report') is False for t in payload['tools'])

    admin = gateway.execute(call('tool_search', {'query': '报告'}),
                            ctx(permissions=('*',)))
    assert any(t['name'].startswith('report')
               for t in json.loads(admin.content)['tools'])


def test_platform_contract_local():
    gateway = make_gateway()
    result = gateway.execute(call('platform_contract', {'query': '报告类型'}),
                             ctx(permissions=()))
    assert result.ok
    payload = json.loads(result.content)
    assert payload['enums']


# ---------------------------------------------------------------- 权限 / 未启用

def test_permission_denied_returns_plain_text_without_leak():
    gateway = make_gateway()
    result = gateway.execute(call('report_query', {'action': 'list'}),
                             ctx(permissions=('task:read',)))
    assert not result.ok
    assert result.error_code == PERMISSION_DENIED
    assert '无权访问' in result.content
    assert 'report' not in result.content  # 不泄漏资源是否存在


def test_reserved_tool_returns_not_enabled():
    for name, args in [
        ('memory_search', {'query': 'x'}),
        ('memory_write', {'content': 'x', 'kind': 'preference'}),
        ('ui_tree', {'device_id': 1}),
        ('ui_action', {'device_id': 1, 'action': 'tap'}),
        ('api_spec', {'source': 'url'}),
    ]:
        result = make_gateway().execute(call(name, args), ctx())
        assert result.error_code == TOOL_NOT_ENABLED, name
        assert '未启用' in result.content


def test_unknown_tool_is_ordinary_failure():
    result = make_gateway().execute(call('nope'), ctx())
    assert result.error_code == UNKNOWN_TOOL
    assert not result.ok


def test_invalid_arguments_before_rest_call():
    rest = FakeRestClient()
    gateway = make_gateway(rest)
    result = gateway.execute(call('task_query', {'action': 'detail'}), ctx())
    assert result.error_code == INVALID_ARGUMENTS
    assert '缺少必填参数' in result.content
    assert rest.calls == []


def test_write_tool_denied_at_gateway_layer():
    rest = FakeRestClient()
    result = make_gateway(rest).execute(
        call('task_create', {'body': {'name': 'x'}}), ctx())
    assert result.error_code == 'APPROVAL_REQUIRED'
    assert rest.calls == []


# ---------------------------------------------------------------- REST 回源

def test_task_query_maps_action_and_passes_credentials():
    rest = FakeRestClient(payload={'data': {'id': 9}})
    credentials = RunCredentialRegistry()
    credentials.put('r1', 'Bearer user-token')
    gateway = make_gateway(rest, credentials)

    result = gateway.execute(call('task_query', {'action': 'detail',
                                                 'task_id': 9}), ctx())
    assert result.ok
    assert json.loads(result.content) == {'data': {'id': 9}}
    sent = rest.calls[0]
    assert sent['tool']['name'] == 'task_get'
    assert sent['arguments'] == {'task_id': 9}
    assert sent['authorization'] == 'Bearer user-token'
    assert sent['user_id'] == 7 and sent['tenant_id'] == 't1'
    assert sent['permissions'] == ('*',)


def test_report_query_rest_success():
    rest = FakeRestClient(payload={'items': [], 'total': 0})
    gateway = make_gateway(rest)
    result = gateway.execute(call('report_query', {'action': 'list',
                                                   'page': 1}), ctx())
    assert result.ok
    assert rest.calls[0]['tool']['name'] == 'report_list'


@pytest.mark.parametrize('status,code,needle', [
    (403, PERMISSION_DENIED, '无权访问'),
    (401, PERMISSION_DENIED, '无权访问'),
    (404, RESOURCE_NOT_FOUND, '不存在或无权访问'),
    (422, INVALID_ARGUMENTS, '参数校验失败'),
    (500, UPSTREAM_ERROR, '目标接口返回 500'),
])
def test_rest_error_classification(status, code, needle):
    gateway = make_gateway(FakeRestClient(status=status, payload={'detail': 'x'}))
    result = gateway.execute(call('report_query', {'action': 'list'}), ctx())
    assert not result.ok
    assert result.error_code == code
    assert needle in result.content


def test_rest_network_error_is_plain_text():
    gateway = make_gateway(FakeRestClient(status=RuntimeError('down')))
    result = gateway.execute(call('report_query', {'action': 'list'}), ctx())
    assert result.error_code == UPSTREAM_UNAVAILABLE
    assert '不可用' in result.content


def test_mcp_tool_direct_call_is_permission_checked():
    rest = FakeRestClient(payload={'items': []})
    gateway = make_gateway(rest)
    denied = gateway.execute(call('task_list'), ctx(permissions=('report:read',)))
    assert denied.error_code == PERMISSION_DENIED and rest.calls == []

    allowed = gateway.execute(call('task_list', {'page': 1}),
                              ctx(permissions=('task:read',)))
    assert allowed.ok
    assert rest.calls[0]['tool']['name'] == 'task_list'
