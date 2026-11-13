# -*- coding: utf-8 -*-
"""INT-2462 评估域只读意图工具（evaluation_query）。

验收锚点（卡面可测标准 1、2）：
1. 该域 10 条任务全部走通（动作 → MCP 只读工具 → REST 参数透传）；
2. 维度字段 / 分类与真实网关契约逐字段一致（参数名、路径、响应信封）。
"""
import json

import pytest

from agent_service.application.tool_gateway import (
    INVALID_ARGUMENTS, PERMISSION_DENIED, RESOURCE_NOT_FOUND, SharedToolGateway,
)
from agent_service.domain.enums import ToolRisk
from agent_service.domain.model.entities import ToolCallRequest
from agent_service.domain.ports.tool_gateway import ToolInvocationContext
from agent_service.infrastructure.tools.registry_bridge import (
    RestResult, RunCredentialRegistry, SharedToolRegistryBridge,
)
from shared.agent_tools import intent_tools, mcp_registry
from shared.agent_tools.intent_tools import EVALUATION_QUERY_ACTIONS
from tests.agent_eval.domains.evaluation import fixtures


class FakeEvaluationRest:
    """按工具名返回实测形状的响应，并记录回源参数。"""

    def __init__(self):
        self.calls = []

    def call(self, tool, arguments, **kwargs):
        self.calls.append({'tool': tool, 'arguments': dict(arguments), **kwargs})
        name = tool['name']
        if name == 'evaluation_dimension_get':
            if arguments.get('dim_id') != 121:
                return RestResult(status=404,
                                  payload={'success': False, 'code': 404,
                                           'message': '未找到评估维度'},
                                  text=json.dumps({'success': False,
                                                   'message': '未找到评估维度'},
                                                  ensure_ascii=False))
            payload = fixtures.DIMENSION_DETAIL_ENVELOPE
        elif name == 'evaluation_category_list':
            payload = fixtures.CATEGORY_LIST
        elif name == 'evaluation_dimension_list':
            page = arguments.get('page', 1)
            per_page = arguments.get('per_page', 10)
            items = []
            if arguments.get('search') in (None, '', '拒识'):
                items = [fixtures.DIMENSION_ITEM]
            if arguments.get('category_id') not in (None, 3):
                items = []
            payload = fixtures.enveloped(items, page=page, per_page=per_page)
        else:  # pragma: no cover - 用例只走评估工具
            payload = {'success': True, 'data': {}}
        return RestResult(status=200, payload=payload,
                          text=json.dumps(payload, ensure_ascii=False))


def make_gateway(rest=None, credentials=None):
    return SharedToolGateway(
        bridge=SharedToolRegistryBridge(),
        rest=rest or FakeEvaluationRest(),
        credentials=credentials or RunCredentialRegistry(),
    )


def ctx(permissions=('evaluation:read',), run_id='r1'):
    return ToolInvocationContext(
        run_id=run_id, session_id='s1', owner_id=7, tenant_id='t1',
        step_id='step1', permissions=tuple(permissions), idempotency_key='k')


def call(arguments):
    return ToolCallRequest(tool_call_id='call-1', name='evaluation_query',
                           arguments=arguments)


# ---------------------------------------------------------------- 注册口径

def test_evaluation_query_is_enabled_readonly():
    tool = intent_tools.INTENT_TOOL_BY_NAME['evaluation_query']
    assert tool.enabled is True
    assert tool.risk == 'READ'
    assert tool.kind == 'intent_rest'
    assert tool.permissions == ('evaluation:read',)
    assert 'evaluation_query' in intent_tools.ENABLED_TOOLS
    assert set(tool.parameters['properties']['action']['enum']) == {
        'dimensions', 'dimension', 'categories'}


def test_actions_map_to_existing_readonly_mcp_tools():
    for action, mcp_name in EVALUATION_QUERY_ACTIONS.items():
        mcp = mcp_registry.get_tool(mcp_name)
        assert mcp is not None, f'{action} -> {mcp_name} 不存在'
        assert mcp['method'] == 'GET', mcp_name
        assert mcp['permissions'] == ['evaluation:read'], mcp_name
        assert mcp['path'].startswith('/api/v1/evaluation'), mcp_name


def test_dimension_list_schema_matches_gateway_query():
    """参数名对齐 DimensionListQuery：category_id/page/per_page/search。"""
    mcp = mcp_registry.get_tool('evaluation_dimension_list')
    assert mcp['path'] == '/api/v1/evaluation/dimensions'
    assert set(mcp['inputSchema']['properties']) == {
        'category_id', 'page', 'per_page', 'search'}
    assert set(mcp['query_params']) == {
        'category_id', 'page', 'per_page', 'search'}
    assert 'keyword' not in mcp['inputSchema']['properties']


def test_dimension_detail_and_category_contract():
    detail = mcp_registry.get_tool('evaluation_dimension_get')
    assert detail['path'] == '/api/v1/evaluation/dimensions/{dim_id}'
    assert detail['path_params'] == ['dim_id']
    assert detail['inputSchema']['required'] == ['dim_id']

    categories = mcp_registry.get_tool('evaluation_category_list')
    assert categories['path'] == '/api/v1/evaluation/categories'
    assert categories['permissions'] == ['evaluation:read']


# ---------------------------------------------------------------- 10 条域任务

@pytest.mark.parametrize('task', fixtures.DOMAIN_TASKS,
                         ids=[t['name'] for t in fixtures.DOMAIN_TASKS])
def test_domain_task_runs_through_gateway(task):
    rest = FakeEvaluationRest()
    gateway = make_gateway(rest)
    result = gateway.execute(call(dict(task['arguments'])), ctx())
    assert result.ok, result.content

    sent = rest.calls[0]
    assert sent['tool']['name'] == task['tool']
    assert sent['arguments'] == task['merged']
    assert sent['authorization'] is None  # 未注入凭证时不伪造身份头

    payload = json.loads(result.content)
    assert payload['success'] is True
    data = payload['data']
    for field in task['checks']:
        assert field in data, f"{task['name']} 缺少 {field}"
    if task['arguments']['action'] == 'dimensions':
        assert set(data) == {'items', 'total', 'page', 'per_page', 'pages'}
        for item in data['items']:
            assert set(item) <= set(fixtures.DIMENSION_ITEM)


def test_ten_domain_tasks_are_distinct():
    assert len(fixtures.DOMAIN_TASKS) == 10
    assert len({t['name'] for t in fixtures.DOMAIN_TASKS}) == 10


# ---------------------------------------------------------------- 校验 / 权限

def test_dimension_action_requires_dim_id_before_rest():
    rest = FakeEvaluationRest()
    result = make_gateway(rest).execute(
        call({'action': 'dimension'}), ctx())
    assert result.error_code == INVALID_ARGUMENTS
    assert 'dim_id' in result.content
    assert rest.calls == []


def test_invalid_action_rejected_before_rest():
    rest = FakeEvaluationRest()
    result = make_gateway(rest).execute(
        call({'action': 'delete'}), ctx())
    assert result.error_code == INVALID_ARGUMENTS
    assert rest.calls == []


def test_missing_evaluation_read_permission_denied():
    rest = FakeEvaluationRest()
    result = make_gateway(rest).execute(
        call({'action': 'dimensions'}), ctx(permissions=('task:read',)))
    assert result.error_code == PERMISSION_DENIED
    assert '无权访问' in result.content
    assert rest.calls == []


def test_private_or_missing_dimension_collapses_to_plain_not_found():
    result = make_gateway().execute(
        call({'action': 'dimension', 'dim_id': 999999}), ctx())
    assert not result.ok
    assert result.error_code == RESOURCE_NOT_FOUND
    assert '不存在或无权访问' in result.content


def test_gateway_exposes_evaluation_query_as_read():
    gateway = make_gateway()
    assert gateway.risk_of('evaluation_query') is ToolRisk.READ
    descriptor = gateway.describe(['evaluation_query'])[0]
    assert descriptor.enabled is True
    assert descriptor.permissions == ('evaluation:read',)


# ---------------------------------------------------------------- 字段一致性

def test_dimension_fields_cover_gateway_schema():
    """文档/样例字段覆盖 api_gateway DimensionItem 全字段（逐字段一致）。"""
    from api_gateway.schemas.evaluation import CategoryItem, DimensionItem

    documented = set(fixtures.DIMENSION_DETAIL)
    expected = set(DimensionItem.model_fields)
    assert expected <= documented, sorted(expected - documented)

    category_expected = set(CategoryItem.model_fields)
    assert category_expected <= set(fixtures.CATEGORY_ITEM)


def test_skill_documents_every_dimension_field():
    """Skill 的字段表必须覆盖接口字段，避免模型按缺字段的说明回答。"""
    from api_gateway.schemas.evaluation import DimensionItem
    from tests.agent_eval.domains.evaluation.skill_support import skill_body

    body = skill_body()
    missing = [name for name in DimensionItem.model_fields if name not in body]
    assert missing == [], missing
