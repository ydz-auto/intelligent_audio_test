# -*- coding: utf-8 -*-
"""INT-2463 报告对比（report_compare）：只读组合、不写报告。

验收锚点（卡面可测标准 1、2、4）：
1. 对比 4 条任务走通（多报告并排 / 二次对比 / 趋势）；
2. 并排数值与 Report Service 逐字段一致（原样搬运，不重算、不四舍五入）；
4. 每个数字可回溯到 REST 返回字段（对比结果只包含详情里的原文数值）。

补充硬约束（INT-2463 卡面「对比产物落 artifact，不写报告」）：工具层**不得**
调用 ``POST /reports/compare`` / ``POST /reports/secondary-compare``——它们会
落库生成新报告，属写操作。本文件的 FakeRest 会记录所有回源，逐条断言只读。
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
from shared.agent_tools.intent_tools import REPORT_COMPARE_ACTIONS
from tests.agent_eval.domains.report import fixtures

COMPARE_TASKS = [task for task in fixtures.DOMAIN_TASKS
                 if task['tool'] == 'report_compare']

_REPORTS = {
    426: fixtures.DETAIL,
    425: dict(fixtures.DETAIL, id=425, name='另一份任务报告',
              summary=dict(fixtures.SUMMARY, pass_rate=93.68,
                           failed_cases=2, completed_cases=2)),
    395: fixtures.COMPARISON_DETAIL,
    424: fixtures.SECONDARY_DETAIL,
}

# 绝不应该是 Agent 侧对比工具回源的目标（写接口）
_WRITE_TOOLS = {'report_compare', 'report_secondary_compare'}
_WRITE_PATHS = {'/api/v1/reports/compare', '/api/v1/reports/secondary-compare'}


class FakeCompareRest:
    def __init__(self, statuses=None):
        self.calls = []
        self._statuses = statuses or {}

    def call(self, tool, arguments, **kwargs):
        self.calls.append({'tool': tool, 'arguments': dict(arguments), **kwargs})
        name = tool['name']
        if name == 'report_statistics_trend':
            payload = fixtures.ok(fixtures.TREND)
        elif name == 'report_get':
            report_id = arguments.get('report_id')
            status = self._statuses.get(report_id, 200)
            if status != 200:
                return _error(status, 'report not found')
            data = _REPORTS.get(report_id)
            if data is None:
                return _error(404, 'report not found')
            payload = fixtures.ok(data)
        else:  # pragma: no cover - 只读组合只应命中上面两种工具
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
        rest=rest or FakeCompareRest(),
        credentials=credentials or RunCredentialRegistry(),
    )


def ctx(permissions=('report:compare', 'report:read'), run_id='r1'):
    return ToolInvocationContext(
        run_id=run_id, session_id='s1', owner_id=7, tenant_id='t1',
        step_id='step1', permissions=tuple(permissions), idempotency_key='k')


def call(arguments):
    return ToolCallRequest(tool_call_id='call-1', name='report_compare',
                           arguments=arguments)


def _assert_readonly_calls(rest):
    assert rest.calls, '没有回源记录'
    for sent in rest.calls:
        assert sent['tool']['name'] not in _WRITE_TOOLS, sent['tool']['name']
        assert sent['tool']['path'] not in _WRITE_PATHS, sent['tool']['path']
        assert sent['tool']['method'] == 'GET', sent['tool']['name']


# ---------------------------------------------------------------- 注册口径

def test_report_compare_is_enabled_readonly_local():
    tool = intent_tools.INTENT_TOOL_BY_NAME['report_compare']
    assert tool.enabled is True
    assert tool.risk == 'READ'
    assert tool.kind == 'local'
    assert tool.permissions == ('report:compare',)
    assert 'report_compare' in intent_tools.ENABLED_TOOLS
    assert set(tool.parameters['properties']['action']['enum']) == set(
        REPORT_COMPARE_ACTIONS)


def test_tool_search_index_prefers_local_readonly_tool():
    """同名 MCP 写工具（POST /reports/compare）不能盖住 Agent 侧的只读工具。"""
    entry = intent_tools.TOOL_INDEX_BY_NAME['report_compare']
    assert entry['kind'] == 'local'
    assert entry['risk'] == 'READ'
    names = [t['name'] for t in intent_tools.TOOL_INDEX]
    assert names.count('report_compare') == 1


def test_local_tool_never_resolves_to_mcp_write_tool():
    tool, merged, error = intent_tools.resolve_rest_call(
        'report_compare', {'action': 'compare', 'report_ids': [1, 2]})
    assert tool is None and merged is None
    assert error and '本地实现' in error
    # MCP 注册表里的 1:1 写工具仍在（外部 MCP 契约不变），只是不走 Agent 通道
    mcp = mcp_registry.get_tool('report_compare')
    assert mcp is not None and mcp['method'] == 'POST'


# ---------------------------------------------------------------- 10 条域任务（对比 4 条）

@pytest.mark.parametrize('task', COMPARE_TASKS,
                         ids=[t['name'] for t in COMPARE_TASKS])
def test_compare_task_runs_through_gateway(task):
    rest = FakeCompareRest()
    result = make_gateway(rest).execute(call(dict(task['arguments'])), ctx())
    assert result.ok, result.content
    payload = json.loads(result.content)
    # compare / secondary_compare 是工具层组合对象；trend 直接透传 REST 信封
    data = payload.get('data') if isinstance(payload.get('data'), dict) else payload
    for field in task['checks']:
        assert field in data, f"{task['name']} 缺少 {field}"
    _assert_readonly_calls(rest)


def test_compare_two_reports_returns_side_by_side_facts():
    rest = FakeCompareRest()
    result = make_gateway(rest).execute(
        call({'action': 'compare', 'report_ids': [426, 425]}), ctx())
    assert result.ok, result.content
    payload = json.loads(result.content)
    assert payload['action'] == 'compare'
    assert payload['report_count'] == 2
    assert payload['missing'] == []
    first, second = payload['reports']
    assert first['report_id'] == 426 and second['report_id'] == 425
    # 数值原样来自 GET /reports/{id}：不重算、不四舍五入
    assert first['summary'] == {'total_cases': 2, 'completed_cases': 2,
                               'failed_cases': 0, 'pass_rate': 100.0}
    assert second['summary']['pass_rate'] == 93.68
    assert first['metric_data'][0]['metrics'][1] == {
        'id': 88, 'metric': '接管内容平均分', 'value': 0.85}
    assert first['device_stats'][0]['metrics']['接管内容平均分'] == 0.85
    assert first['case_type_stats'][0]['group_name'] == '话轮接管'
    # 体量大的逐用例原始值不随对比下发（需要时走 report_query.cases）
    assert 'raw_data' not in first
    _assert_readonly_calls(rest)


def test_compare_projection_is_subset_of_detail_fields():
    """并排结果的每个顶层字段都来自详情原文（或工具层固定元字段）。"""
    result = make_gateway().execute(
        call({'action': 'compare', 'report_ids': [426, 395]}), ctx())
    payload = json.loads(result.content)
    meta = {'report_id', 'type', 'task_id', 'task_name', 'created_at',
            'visibility', 'source_task_ids'}
    summary_source = set(fixtures.SUMMARY)
    for report in payload['reports']:
        for key in report:
            if key in meta or key in ('name', 'status'):
                continue
            if key == 'summary':
                assert set(report[key]) <= summary_source
                continue
            assert key in summary_source, key


def test_compare_partial_missing_reports_still_returns_others():
    rest = FakeCompareRest()
    result = make_gateway(rest).execute(
        call({'action': 'compare', 'report_ids': [426, 999999]}), ctx())
    assert result.ok, result.content
    payload = json.loads(result.content)
    assert payload['report_count'] == 1
    assert [r['report_id'] for r in payload['reports']] == [426]
    assert payload['missing'] == [{'report_id': 999999, 'status': 404,
                                   'message': '资源不存在或无权访问。'}]


def test_compare_all_missing_fails_without_empty_payload():
    rest = FakeCompareRest()
    result = make_gateway(rest).execute(
        call({'action': 'compare', 'report_ids': [999998, 999999]}), ctx())
    assert not result.ok
    assert result.error_code == RESOURCE_NOT_FOUND
    assert '不存在或无权访问' in result.content


def test_compare_all_forbidden_reports_to_permission_denied():
    rest = FakeCompareRest(statuses={426: 403, 425: 403})
    result = make_gateway(rest).execute(
        call({'action': 'compare', 'report_ids': [426, 425]}), ctx())
    assert not result.ok
    assert result.error_code == PERMISSION_DENIED
    assert '无权访问' in result.content


def test_secondary_compare_rejects_task_reports():
    rest = FakeCompareRest()
    result = make_gateway(rest).execute(
        call({'action': 'secondary_compare', 'report_ids': [426, 395]}), ctx())
    assert not result.ok
    assert result.error_code == INVALID_ARGUMENTS
    assert '426' in result.content and 'compare' in result.content


def test_secondary_compare_accepts_comparison_reports_and_carries_source_tasks():
    rest = FakeCompareRest()
    result = make_gateway(rest).execute(
        call({'action': 'secondary_compare', 'report_ids': [424, 395]}), ctx())
    assert result.ok, result.content
    payload = json.loads(result.content)
    assert payload['action'] == 'secondary_compare'
    assert {r['report_id'] for r in payload['reports']} == {424, 395}
    for report in payload['reports']:
        assert report['type'] in ('comparison', 'secondary_comparison')
        assert report['source_task_ids'] == [402, 407]


def test_trend_action_returns_interface_payload_verbatim():
    rest = FakeCompareRest()
    result = make_gateway(rest).execute(
        call({'action': 'trend', 'trend_type': 'time', 'metric': 'pass_rate',
              'start_time': '2026-10-01'}), ctx())
    assert result.ok, result.content
    payload = json.loads(result.content)
    assert payload['data'] == fixtures.TREND
    sent = rest.calls[0]
    assert sent['tool']['name'] == 'report_statistics_trend'
    assert sent['arguments'] == {'trend_type': 'time', 'metric': 'pass_rate',
                                 'start_time': '2026-10-01'}


# ---------------------------------------------------------------- 参数护栏

@pytest.mark.parametrize('arguments', [
    {'action': 'compare', 'report_ids': [426]},
    {'action': 'compare', 'report_ids': [426, 426]},
    {'action': 'compare', 'report_ids': [426, '425']},
    {'action': 'compare', 'report_ids': [426, 0]},
    {'action': 'compare', 'report_ids': list(range(1, 12))},
    {'action': 'compare', 'report_ids': [426, 425], 'metric': 'pass_rate'},
    {'action': 'trend', 'report_ids': [426, 425]},
    {'action': 'nope', 'report_ids': [426, 425]},
])
def test_invalid_arguments_rejected_before_rest(arguments):
    rest = FakeCompareRest()
    result = make_gateway(rest).execute(call(arguments), ctx())
    assert result.error_code == INVALID_ARGUMENTS, arguments
    assert rest.calls == []


def test_missing_permission_denied_before_rest():
    rest = FakeCompareRest()
    result = make_gateway(rest).execute(
        call({'action': 'compare', 'report_ids': [426, 425]}),
        ctx(permissions=('report:read',)))
    assert result.error_code == PERMISSION_DENIED
    assert rest.calls == []


def test_gateway_exposes_report_compare_as_read():
    gateway = make_gateway()
    assert gateway.risk_of('report_compare') is ToolRisk.READ
    descriptor = gateway.describe(['report_compare'])[0]
    assert descriptor.enabled is True
    assert descriptor.permissions == ('report:compare',)
