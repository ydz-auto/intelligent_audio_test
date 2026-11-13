# -*- coding: utf-8 -*-
"""INT-2463 报告域只读意图工具（report_query）。

验收锚点（卡面可测标准 1、2、4）：
1. 该域 10 条任务全部走通（取数 6 条 → report_query，对比 4 条 → report_compare）；
2. 字段 / 参数与 Report Service 真实口径逐字段一致（参数名、路径、响应信封）；
4. 无编造数值：本文件只验证「工具把接口原文透传」，数值解释在 Skill 层约束。
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
from shared.agent_tools.intent_tools import REPORT_QUERY_ACTIONS, REPORT_QUERY_PARAMS
from tests.agent_eval.domains.report import fixtures

FETCH_TASKS = [task for task in fixtures.DOMAIN_TASKS
               if task['tool'] == 'report_query']


class FakeReportRest:
    """按工具名返回实测形状的响应，并记录回源参数。"""

    def __init__(self):
        self.calls = []

    def call(self, tool, arguments, **kwargs):
        self.calls.append({'tool': tool, 'arguments': dict(arguments), **kwargs})
        name = tool['name']
        if name == 'report_get':
            if arguments.get('report_id') != 426:
                return _error(404, 'report not found')
            payload = fixtures.ok(fixtures.DETAIL)
        elif name == 'report_by_task':
            if arguments.get('task_id') != 460:
                return _error(404, 'report not found')
            payload = fixtures.ok(fixtures.DETAIL)
        elif name == 'report_list':
            payload = fixtures.REPORT_LIST
        elif name == 'report_tab_counts':
            payload = fixtures.ok(fixtures.TAB_COUNTS)
        elif name == 'report_statistics':
            payload = fixtures.ok(fixtures.STATISTICS)
        elif name == 'report_statistics_trend':
            payload = fixtures.ok(fixtures.TREND)
        elif name in ('report_cases', 'report_cases_search'):
            payload = fixtures.CASES_PAGE
        elif name == 'report_case_averages':
            payload = fixtures.ok(fixtures.CASE_AVERAGES)
        elif name == 'report_progress':
            payload = fixtures.ok(fixtures.PROGRESS)
        else:  # pragma: no cover - 用例只走报告工具
            payload = fixtures.ok({})
        return RestResult(status=200, payload=payload,
                          text=json.dumps(payload, ensure_ascii=False))


def _error(status, message):
    payload = {'success': False, 'code': status, 'message': message}
    return RestResult(status=status, payload=payload,
                      text=json.dumps(payload, ensure_ascii=False))


def make_gateway(rest=None, credentials=None):
    return SharedToolGateway(
        bridge=SharedToolRegistryBridge(),
        rest=rest or FakeReportRest(),
        credentials=credentials or RunCredentialRegistry(),
    )


def ctx(permissions=('report:read',), run_id='r1'):
    return ToolInvocationContext(
        run_id=run_id, session_id='s1', owner_id=7, tenant_id='t1',
        step_id='step1', permissions=tuple(permissions), idempotency_key='k')


def call(arguments):
    return ToolCallRequest(tool_call_id='call-1', name='report_query',
                           arguments=arguments)


# ---------------------------------------------------------------- 注册口径

def test_report_query_is_enabled_readonly():
    tool = intent_tools.INTENT_TOOL_BY_NAME['report_query']
    assert tool.enabled is True
    assert tool.risk == 'READ'
    assert tool.kind == 'intent_rest'
    assert tool.permissions == ('report:read',)
    assert 'report_query' in intent_tools.ENABLED_TOOLS
    assert set(tool.parameters['properties']['action']['enum']) == set(
        REPORT_QUERY_ACTIONS)


def test_actions_map_to_existing_readonly_mcp_tools():
    for action, mcp_name in REPORT_QUERY_ACTIONS.items():
        mcp = mcp_registry.get_tool(mcp_name)
        assert mcp is not None, f'{action} -> {mcp_name} 不存在'
        # 只读语义：GET，或 POST 但只要求读权限（case-averages / cases/search 取数）
        assert mcp['method'] == 'GET' or mcp['permissions'] == ['report:read'], \
            mcp_name
        assert mcp['permissions'] == ['report:read'], mcp_name
        assert mcp['path'].startswith('/api/v1/reports'), mcp_name


def test_every_action_targets_a_registered_gateway_route():
    """动作 → MCP 路径必须能在网关 report 路由表里找到同方法与同路径的路由。"""
    from api_gateway.routes.report_bp import router

    registered = set()
    for route in router.routes:
        for method in route.methods or ():
            registered.add((_normalize(route.path), method))

    for action, mcp_name in REPORT_QUERY_ACTIONS.items():
        mcp = mcp_registry.get_tool(mcp_name)
        # 网关 router 以 /api/v1/reports 为前缀注册，路由表里是相对路径
        # （列表路由注册为 ''，其它为 '/tab-counts' 等）
        relative = mcp['path'][len('/api/v1/reports'):]
        assert (_normalize(relative), mcp['method']) in registered, (
            f'{action} -> {mcp_name} 的 {mcp["method"]} {mcp["path"]} 在网关上没有路由')


def _normalize(path):
    import re
    return re.sub(r'\{[^}]+\}', '{}', path)


def test_declared_params_match_schema_and_cover_every_property():
    """每个动作的参数都在 Schema 里声明；Schema 里也没有谁都不用的死参数。"""
    properties = set(intent_tools.INTENT_TOOL_BY_NAME[
        'report_query'].parameters['properties'])
    used = {'action'}
    for action, params in REPORT_QUERY_PARAMS.items():
        assert action in REPORT_QUERY_ACTIONS, action
        for name in params:
            assert name in properties, f'{action} 声明了未定义参数 {name}'
        used |= set(params)
    # report_id / task_id 只在动作必填里出现，也要算「被用到的参数」
    for action in REPORT_QUERY_ACTIONS:
        used |= set(intent_tools.required_for_action('report_query', action))
    assert properties - used == set(), sorted(properties - used)


def test_trend_and_binary_actions_are_not_in_report_query():
    """趋势归 report_compare；导出 / 统计报表是二进制通道，都不挂在 report_query。"""
    assert 'statistics_trend' not in REPORT_QUERY_ACTIONS
    assert 'statistics_report' not in REPORT_QUERY_ACTIONS
    assert 'export' not in REPORT_QUERY_ACTIONS
    # MCP 侧仍保留这两个只读/写工具给外部 MCP 客户端（1:1 契约不变）
    assert mcp_registry.get_tool('report_statistics_trend') is not None
    assert mcp_registry.get_tool('report_statistics_report') is not None


# ---------------------------------------------------------------- 10 条域任务

@pytest.mark.parametrize('task', FETCH_TASKS, ids=[t['name'] for t in FETCH_TASKS])
def test_fetch_task_runs_through_gateway(task):
    rest = FakeReportRest()
    gateway = make_gateway(rest)
    result = gateway.execute(call(dict(task['arguments'])), ctx())
    assert result.ok, result.content

    sent = rest.calls[0]
    assert sent['tool']['name'] == task['mcp']
    assert sent['arguments'] == task['merged']
    assert sent['authorization'] is None  # 未注入凭证时不伪造身份头

    payload = json.loads(result.content)
    assert payload['success'] is True
    data = payload['data']
    for field in task['checks']:
        assert field in data, f"{task['name']} 缺少 {field}"


def test_domain_has_six_fetch_and_four_compare_tasks():
    """卡面可测标准 1：取数 6 条 + 对比 4 条 = 10 条。"""
    compare = [t for t in fixtures.DOMAIN_TASKS if t['tool'] == 'report_compare']
    assert len(FETCH_TASKS) == 6
    assert len(compare) == 4
    assert len({t['name'] for t in fixtures.DOMAIN_TASKS}) == 10


def test_cases_search_and_case_averages_and_progress_also_work():
    """六条 golden 之外的三个取数动作同样走通（参数逐字对齐 REST）。"""
    rest = FakeReportRest()
    gateway = make_gateway(rest)

    result = gateway.execute(call({
        'action': 'cases_search', 'report_id': 426,
        'categories': ['话轮接管'], 'tags': ['打断用例'],
        'metrics': ['接管率占比'], 'sort_by': 'metric',
        'sort_metric': '接管率占比', 'sort_order': 'desc',
        'page': 1, 'per_page': 20}), ctx())
    assert result.ok, result.content
    sent = rest.calls[-1]
    assert sent['tool']['name'] == 'report_cases_search'
    assert sent['arguments'] == {
        'report_id': 426, 'categories': ['话轮接管'], 'tags': ['打断用例'],
        'metrics': ['接管率占比'], 'sort_by': 'metric',
        'sort_metric': '接管率占比', 'sort_order': 'desc',
        'page': 1, 'per_page': 20}

    result = gateway.execute(call({'action': 'case_averages',
                                   'task_id': 460, 'category': '话轮接管'}),
                             ctx())
    assert result.ok, result.content
    sent = rest.calls[-1]
    assert sent['tool']['name'] == 'report_case_averages'
    assert sent['arguments'] == {'task_id': 460, 'category': '话轮接管'}

    result = gateway.execute(call({'action': 'progress', 'report_id': 426}), ctx())
    assert result.ok, result.content
    assert rest.calls[-1]['tool']['name'] == 'report_progress'


# ---------------------------------------------------------------- 参数护栏

def test_unsupported_param_rejected_before_rest():
    rest = FakeReportRest()
    result = make_gateway(rest).execute(
        call({'action': 'list', 'keyword': 'x', 'bogus': 1}), ctx())
    assert result.error_code == INVALID_ARGUMENTS
    assert 'bogus' in result.content
    assert rest.calls == []


def test_tags_rejected_on_get_cases():
    """GET cases 的 tags 在网关恒 400（查询串是字符串，pydantic 要 List[str]）。"""
    rest = FakeReportRest()
    result = make_gateway(rest).execute(
        call({'action': 'cases', 'report_id': 426, 'tags': ['话轮接管']}), ctx())
    assert result.error_code == INVALID_ARGUMENTS
    assert 'tags' in result.content
    assert rest.calls == []


def test_page_and_per_page_bounds():
    rest = FakeReportRest()
    gateway = make_gateway(rest)
    for arguments in ({'action': 'list', 'page': 0},
                      {'action': 'list', 'per_page': 0},
                      {'action': 'list', 'per_page': 1000},
                      {'action': 'cases', 'report_id': 426, 'page': -1}):
        result = gateway.execute(call(arguments), ctx())
        assert result.error_code == INVALID_ARGUMENTS, arguments
    assert rest.calls == []


def test_case_averages_requires_exactly_one_of_report_or_task():
    rest = FakeReportRest()
    gateway = make_gateway(rest)
    missing = gateway.execute(call({'action': 'case_averages'}), ctx())
    assert missing.error_code == INVALID_ARGUMENTS
    assert 'report_id' in missing.content and 'task_id' in missing.content

    both = gateway.execute(call({'action': 'case_averages', 'report_id': 426,
                                 'task_id': 460}), ctx())
    assert both.error_code == INVALID_ARGUMENTS
    assert rest.calls == []


def test_report_actions_require_ids_before_rest():
    rest = FakeReportRest()
    gateway = make_gateway(rest)
    for action, missing_name in (('detail', 'report_id'),
                                 ('progress', 'report_id'),
                                 ('cases', 'report_id'),
                                 ('cases_search', 'report_id'),
                                 ('by_task', 'task_id')):
        result = gateway.execute(call({'action': action}), ctx())
        assert result.error_code == INVALID_ARGUMENTS, action
        assert missing_name in result.content, action
    assert rest.calls == []


def test_missing_report_collapses_to_plain_not_found():
    result = make_gateway().execute(
        call({'action': 'detail', 'report_id': 999999}), ctx())
    assert not result.ok
    assert result.error_code == RESOURCE_NOT_FOUND
    assert '不存在或无权访问' in result.content


def test_missing_report_permission_denied():
    rest = FakeReportRest()
    result = make_gateway(rest).execute(
        call({'action': 'list'}), ctx(permissions=('task:read',)))
    assert result.error_code == PERMISSION_DENIED
    assert '无权访问' in result.content
    assert rest.calls == []


def test_gateway_exposes_report_query_as_read():
    gateway = make_gateway()
    assert gateway.risk_of('report_query') is ToolRisk.READ
    descriptor = gateway.describe(['report_query'])[0]
    assert descriptor.enabled is True
    assert descriptor.permissions == ('report:read',)


# ---------------------------------------------------------------- 字段一致性

# 网关 report_bp 是 BFF 透传（report_service 的 JSON 不按 schema 重建），
# 实测列表项 / 详情会多带这些 schema 里没有的键；它们是真实下发字段，
# 样例可以包含，但两者之外的字段一律视为样例编造。
_LIVE_ONLY_FIELDS = {
    'report_type', 'config', 'analysis', 'conclusion', 'summaries',
    'cases', 'metric_stats', 'raw_data',
    # 列表项字段（ReportListItem），详情 schema 里没有但列表/详情共用同一聚合载荷
    'is_favorite',
}


def test_list_item_fixture_has_no_invented_fields():
    """样例字段必须 ⊆ 网关 Schema ∪ 实测透传字段；`algorithm_type` / `updated_at`
    是可选字段，这份任务报告上接口没下发（None 不序列化），因此样例里可以没有。"""
    from api_gateway.schemas.report import ReportListItem

    allowed = set(ReportListItem.model_fields) | _LIVE_ONLY_FIELDS
    assert set(fixtures.LIST_ITEM) <= allowed, sorted(
        set(fixtures.LIST_ITEM) - allowed)
    for field in ('id', 'name', 'type', 'status', 'task_name', 'created_at',
                  'summary', 'visibility', 'is_favorite'):
        assert field in fixtures.LIST_ITEM, field


def test_detail_fixture_has_no_invented_fields():
    from api_gateway.schemas.report import ReportDetailData

    allowed = set(ReportDetailData.model_fields) | _LIVE_ONLY_FIELDS
    assert set(fixtures.DETAIL) <= allowed, sorted(
        set(fixtures.DETAIL) - allowed)
    for field in ('id', 'name', 'type', 'status', 'task_name', 'summary',
                  'analysis', 'conclusion', 'created_at'):
        assert field in fixtures.DETAIL, field
    # summary 里必须带上指标解释依赖的字段
    for field in ('all_metrics', 'metric_data', 'tag_metric_data',
                  'case_type_stats', 'device_stats', 'api_stats',
                  'resources', 'resource_headers', 'pass_rate',
                  'total_cases', 'completed_cases', 'failed_cases'):
        assert field in fixtures.SUMMARY, field


def test_metric_fields_come_from_all_metrics_definition():
    """指标解释依赖 all_metrics 的定义字段（单位 / 小数位 / 统计方式 / 层级）。"""
    from shared.agent_tools import contract

    for metric in fixtures.ALL_METRICS:
        for field in ('id', 'name', 'unit', 'decimal_places',
                      'statistic_method', 'agg_denominator',
                      'dimension_type', 'parent_dimension_id'):
            assert field in metric, field
        assert metric['dimension_type'] in ('main', 'sub')
    assert set(contract.REPORT_TYPE_VALUES) == {
        'task', 'comparison', 'secondary_comparison', 'benchmark'}
    assert set(contract.REPORT_STATUS_VALUES) == {'draft', 'published'}


def test_action_enum_values_are_used_by_reference():
    """report_type / status / dimension 的枚举值取自 contract，不写字面量。"""
    from shared.agent_tools import contract

    properties = intent_tools.INTENT_TOOL_BY_NAME[
        'report_query'].parameters['properties']
    assert properties['report_type']['enum'] == list(contract.REPORT_TYPE_VALUES)
    assert properties['status']['enum'] == list(contract.REPORT_STATUS_VALUES)
    assert properties['dimension']['enum'] == list(
        contract.REPORT_STATISTICS_DIMENSIONS)
