# -*- coding: utf-8 -*-
"""INT-2460 用例域只读意图工具（testcase_query）。

验收锚点（卡面可测标准 1、2、4）：
1. 该域 10 条任务全部走通（动作 → 工具 → 网关真实路由 + 查询串）；
2. 轮次 / 维度字段与真实用例详情逐字段一致（列表项 / 详情 / 轮次配置契约）；
4. 不编造用例 ID / 轮次数：动作参数只做透传，不补 ID、不猜轮次。
"""
import json
import re
import urllib.parse

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
from shared.agent_tools import intent_tools, mcp_registry, testcase_tools
from shared.agent_tools.intent_tools import TESTCASE_QUERY_ACTIONS, TOOL_INDEX
from tests.agent_eval.domains.testcase import fixtures


class FakeTestcaseRest:
    """按工具名返回实测形状的响应，并记录回源参数。"""

    def __init__(self):
        self.calls = []

    def call(self, tool, arguments, **kwargs):
        self.calls.append({'tool': tool, 'arguments': dict(arguments), **kwargs})
        name = tool['name']
        if name == 'testcase_list':
            payload = fixtures.TESTCASE_LIST
        elif name == 'testcase_get':
            if arguments.get('tc_id') != fixtures.CASE_ID:
                return self._missing('未找到测试用例')
            payload = fixtures.TESTCASE_DETAIL_ENVELOPE
        elif name == 'testcase_stats':
            payload = fixtures.TESTCASE_STATS
        elif name == 'testcase_round_ref_params':
            return self._missing(fixtures.REF_PARAMS_MISSING_TEXT)
        elif name == 'testcase_export_job_status':
            payload = fixtures.EXPORT_JOB_STATUS
        elif name == 'testcase_refresh_status':
            payload = fixtures.REFRESH_STATUS
        else:  # pragma: no cover - 用例只走用例查询工具
            payload = {'success': True, 'data': {}}
        return RestResult(status=200, payload=payload,
                          text=json.dumps(payload, ensure_ascii=False))

    @staticmethod
    def _missing(message):
        payload = {'success': False, 'code': 404, 'message': message}
        return RestResult(status=404, payload=payload,
                          text=json.dumps(payload, ensure_ascii=False))


def make_gateway(rest=None, credentials=None):
    return SharedToolGateway(
        bridge=SharedToolRegistryBridge(),
        rest=rest or FakeTestcaseRest(),
        credentials=credentials or RunCredentialRegistry(),
    )


def ctx(permissions=('testcase:read',), run_id='r1'):
    return ToolInvocationContext(
        run_id=run_id, session_id='s1', owner_id=7, tenant_id='t1',
        step_id='step1', permissions=tuple(permissions), idempotency_key='k')


def call(arguments):
    return ToolCallRequest(tool_call_id='call-1', name='testcase_query',
                           arguments=arguments)


def _split_url(path):
    parts = urllib.parse.urlsplit(path)
    query = {k: v[0] for k, v in urllib.parse.parse_qs(parts.query).items()}
    return parts.path, query


def _normalize(path_template):
    return re.sub(r'\{[^}]+\}', '{}', path_template)


# ---------------------------------------------------------------- 注册口径

def test_testcase_query_is_enabled_readonly():
    tool = intent_tools.INTENT_TOOL_BY_NAME['testcase_query']
    assert tool.enabled is True
    assert tool.risk == 'READ'
    assert tool.kind == 'intent_rest'
    assert tool.permissions == ('testcase:read',)
    assert 'testcase_query' in intent_tools.ENABLED_TOOLS
    assert set(tool.parameters['properties']['action']['enum']) == set(
        TESTCASE_QUERY_ACTIONS)


def test_actions_map_to_readonly_tools():
    for action, name in TESTCASE_QUERY_ACTIONS.items():
        tool = (mcp_registry.get_tool(name)
                or testcase_tools.get_tool(name))
        assert tool is not None, f'{action} -> {name} 不存在'
        assert tool['method'] == 'GET', name
        assert tool['path'].startswith('/api/v1/testcases'), name
        assert tool['permissions'], name


def test_every_action_targets_a_registered_gateway_get_route():
    """动作 → 路径必须能在网关 testcase 路由表里找到对应 GET 路由。"""
    from api_gateway.routes.testcase_bp import router

    registered = {
        (_normalize(route.path), 'GET') for route in router.routes
        if route.methods and 'GET' in route.methods
    }
    prefix = '/api/v1/testcases'
    for action, name in TESTCASE_QUERY_ACTIONS.items():
        tool = (mcp_registry.get_tool(name)
                or testcase_tools.get_tool(name))
        path = tool['path']
        assert path.startswith(prefix), name
        relative = path[len(prefix):]
        assert (_normalize(relative), 'GET') in registered, (
            f'{action} -> {name} 的 {path} 在网关上没有 GET 路由')


def test_list_filters_match_gateway_query_schema():
    """可用过滤参数取自网关 TestCaseListQuery，不声明网关没有的参数。"""
    from api_gateway.schemas.testcase import TestCaseListQuery

    gateway_fields = set(TestCaseListQuery.model_fields)
    declared = set(intent_tools.TESTCASE_QUERY_PARAMS['list'])
    assert declared <= gateway_fields, sorted(declared - gateway_fields)
    # status 在网关被静默忽略（TestCaseListQuery 没有该字段），绝不能声明
    assert 'status' not in gateway_fields
    assert 'status' not in declared
    # keyword 才是关键词口径
    assert 'keyword' in declared


def test_testcase_visible_in_tool_index_and_search():
    names = {tool['name'] for tool in TOOL_INDEX}
    assert 'testcase_query' in names
    from shared.agent_tools.search import search
    hit = [t['name'] for t in search('用例列表', ['testcase:read'])['tools']]
    assert 'testcase_query' in hit


# ---------------------------------------------------------------- 10 条域任务

def test_ten_testcase_tasks_are_distinct():
    assert len(fixtures.TESTCASE_TASKS) == 10
    assert len({t['id'] for t in fixtures.TESTCASE_TASKS}) == 10


@pytest.mark.parametrize('task', fixtures.TESTCASE_TASKS,
                         ids=[t['id'] for t in fixtures.TESTCASE_TASKS])
def test_golden_task_resolves_to_expected_tool_and_path(task):
    schema = intent_tools.INTENT_TOOL_BY_NAME['testcase_query'].parameters
    assert intent_tools.validate_arguments(schema, task['arguments']) is None

    tool, merged, error = intent_tools.resolve_rest_call(
        'testcase_query', task['arguments'])
    assert error is None, error
    assert tool['name'] == task['expected_tool']

    path, query = _split_url(mcp_registry.build_path(tool, merged))
    expected_path, expected_query = _split_url(task['expected_path'])
    assert path == expected_path
    assert query == expected_query


def test_golden_task_arguments_only_use_declared_schema_fields():
    properties = intent_tools.INTENT_TOOL_BY_NAME[
        'testcase_query'].parameters['properties']
    for task in fixtures.TESTCASE_TASKS:
        for name in task['arguments']:
            assert name in properties, f'{task["id"]} 未声明参数 {name}'


@pytest.mark.parametrize('task', fixtures.TESTCASE_TASKS,
                         ids=[t['id'] for t in fixtures.TESTCASE_TASKS])
def test_domain_task_runs_through_gateway(task):
    rest = FakeTestcaseRest()
    result = make_gateway(rest).execute(call(dict(task['arguments'])), ctx())

    if task['expected_tool'] == 'testcase_round_ref_params':
        # 参考参数未生成是业务事实：失败但带上游原文，不是越权
        assert not result.ok
        assert result.error_code == RESOURCE_NOT_FOUND
        assert fixtures.REF_PARAMS_MISSING_TEXT in result.content
    else:
        assert result.ok, result.content
    sent = rest.calls[0]
    assert sent['tool']['name'] == task['expected_tool']
    assert sent['authorization'] is None  # 未注入凭证时不伪造身份头

    if result.ok:
        payload = json.loads(result.content)
        assert payload['success'] is True
        data = payload['data']
        for field in task['checks']:
            assert field in data, f"{task['id']} 缺少 {field}"


# ---------------------------------------------------------------- 校验 / 权限

def test_unsupported_param_rejected_before_rest():
    """网关 extra='ignore' 会静默丢弃 status；工具层必须先拒。"""
    rest = FakeTestcaseRest()
    result = make_gateway(rest).execute(
        call({'action': 'list', 'status': 'RUNNING'}), ctx())
    assert result.error_code == INVALID_ARGUMENTS
    assert 'status' in result.content
    assert rest.calls == []


def test_detail_requires_tc_id_before_rest():
    rest = FakeTestcaseRest()
    result = make_gateway(rest).execute(call({'action': 'detail'}), ctx())
    assert result.error_code == INVALID_ARGUMENTS
    assert 'tc_id' in result.content
    assert rest.calls == []


def test_round_ref_params_requires_positive_round():
    rest = FakeTestcaseRest()
    result = make_gateway(rest).execute(
        call({'action': 'round_ref_params', 'tc_id': fixtures.CASE_ID,
              'round_number': 0}), ctx())
    assert result.error_code == INVALID_ARGUMENTS
    assert 'round_number' in result.content
    assert rest.calls == []


def test_invalid_action_rejected_before_rest():
    rest = FakeTestcaseRest()
    result = make_gateway(rest).execute(call({'action': 'write'}), ctx())
    assert result.error_code == INVALID_ARGUMENTS
    assert rest.calls == []


def test_page_zero_rejected_with_readable_error():
    rest = FakeTestcaseRest()
    result = make_gateway(rest).execute(
        call({'action': 'list', 'page': 0}), ctx())
    assert result.error_code == INVALID_ARGUMENTS
    assert 'page' in result.content
    assert rest.calls == []


def test_missing_testcase_read_permission_denied():
    rest = FakeTestcaseRest()
    result = make_gateway(rest).execute(
        call({'action': 'list'}), ctx(permissions=('task:read',)))
    assert result.error_code == PERMISSION_DENIED
    assert '无权访问' in result.content
    assert rest.calls == []


def test_missing_case_collapses_to_plain_not_found():
    result = make_gateway().execute(
        call({'action': 'detail', 'tc_id': 'no-such-case'}), ctx())
    assert not result.ok
    assert result.error_code == RESOURCE_NOT_FOUND
    assert '不存在或无权访问' in result.content


def test_gateway_exposes_testcase_query_as_read():
    gateway = make_gateway()
    assert gateway.risk_of('testcase_query') is ToolRisk.READ
    descriptor = gateway.describe(['testcase_query'])[0]
    assert descriptor.enabled is True
    assert descriptor.permissions == ('testcase:read',)


# ---------------------------------------------------------------- 字段一致性

def test_list_and_detail_fields_cover_gateway_schemas():
    from api_gateway.schemas.testcase import (
        TestCaseDetailData, TestCaseListItem,
    )

    documented = set(fixtures.TESTCASE_ITEM)
    missing = [name for name in TestCaseListItem.model_fields
               if name not in documented]
    assert missing == [], missing

    missing_detail = [name for name in TestCaseDetailData.model_fields
                      if name not in set(fixtures.TESTCASE_DETAIL)]
    assert missing_detail == [], missing_detail


def test_round_config_fields_cover_gateway_schema():
    """轮次 / 维度字段与详情契约逐字段一致（卡面验收 2）。"""
    from api_gateway.schemas.testcase import (
        RoundConfigItem, TestCaseAudioConfigItem, TestCaseConfig,
        TestCaseDimensionItem,
    )

    round_item = fixtures.TESTCASE_ITEM['config']['rounds'][0]
    for name in RoundConfigItem.model_fields:
        if name == 'background_noise':
            continue  # 轮内噪声可选，样例用例没配
        assert name in round_item, f'轮次缺少字段 {name}'

    audio_item = round_item['audios'][0]
    for name in TestCaseAudioConfigItem.model_fields:
        if name in ('id', 'background_noise', 'interferers',
                    'playback_device_id', 'playback_device_name'):
            continue  # 详情装配填充 / 可选 / 样例用逻辑音箱组引用
        assert name in audio_item, f'轮内音频缺少字段 {name}'

    config = fixtures.TESTCASE_ITEM['config']
    for name in TestCaseConfig.model_fields:
        if name == 'background_noise':
            continue
        assert name in config, f'config 缺少字段 {name}'

    dimension = {'id': 121, 'name': '拒识成功数量', 'weight': 1,
                 'threshold': None, 'device_type': None,
                 'round_scope': 'single'}
    for name in TestCaseDimensionItem.model_fields:
        if name == 'llmJudgeConfig':
            continue
        assert name in dimension, f'维度条目缺少字段 {name}'


def test_envelope_is_the_shared_pagination_shape():
    data = fixtures.TESTCASE_LIST['data']
    assert set(data) == {'items', 'total', 'page', 'per_page', 'pages'}
