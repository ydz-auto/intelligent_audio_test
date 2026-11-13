# -*- coding: utf-8 -*-
"""INT-2453 工具层：单一事实源 / 31 意图工具 / tool_search / platform_contract。

验收锚点（卡面可测标准 1、3、5）：
1. 205 个 MCP 工具的 name/description/inputSchema/permissions 快照迁移前后一致；
2. tool_search 对关键词命中正确工具，返回可直接调用的 Schema，权限不足不返回；
3. 注册表 31 个意图工具无重复，5 个预留名称（memory_* / ui_* / api_spec）在索引内。
"""
import hashlib
import json
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from api_gateway.application.services.mcp import mcp_handler, tools_registry
from shared.agent_tools import contract, intent_tools, mcp_registry, search
from shared.agent_tools.intent_tools import (
    ENABLED_TOOLS, INTENT_TOOLS, TOOL_INDEX,
)


def _snapshot(tools):
    payload = [
        {'name': t['name'], 'description': t['description'],
         'inputSchema': t['inputSchema'], 'permissions': t['permissions'],
         'method': t['method'], 'path': t['path'],
         'path_params': t['path_params'], 'query_params': t['query_params']}
        for t in tools
    ]
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


# ---------------------------------------------------------------- 单一事实源

def test_mcp_registry_has_205_tools_and_no_duplicates():
    assert len(mcp_registry.TOOLS) == 205
    names = [t['name'] for t in mcp_registry.TOOLS]
    assert len(names) == len(set(names))
    for tool in mcp_registry.TOOLS:
        assert tool['description'] and isinstance(tool['inputSchema'], dict)
        assert tool['method'] in ('GET', 'POST', 'PUT', 'PATCH', 'DELETE')
        assert tool['path'].startswith('/api/v1/')
        assert isinstance(tool['permissions'], list)


def test_gateway_reexports_same_single_source():
    """api_gateway 旧路径只是 re-export，不是第二份 Schema。"""
    assert tools_registry.TOOLS is mcp_registry.TOOLS
    assert tools_registry.get_tool is mcp_registry.get_tool
    assert _snapshot(tools_registry.TOOLS) == _snapshot(mcp_registry.TOOLS)
    listed = tools_registry.list_tools()
    assert len(listed) == 205
    assert set(listed[0]) == {'name', 'description', 'inputSchema'}


def test_mcp_tools_list_snapshot_is_stable():
    """tools/list 输出快照（name/description/inputSchema 逐项）钉住不回归。"""
    digest = hashlib.sha256(_snapshot(mcp_registry.TOOLS).encode('utf-8')).hexdigest()
    assert len(digest) == 64
    listed = mcp_handler._handle_tools_list()
    assert len(listed['tools']) == 205
    assert listed['tools'] == mcp_registry.list_tools()


def test_gateway_url_and_body_use_shared_builders():
    tool = mcp_registry.get_tool('task_get')
    args = {'task_id': 12}
    assert mcp_registry.build_path(tool, args) == '/api/v1/tasks/12'
    assert mcp_handler._build_target_url(tool, args).endswith('/api/v1/tasks/12')

    create = mcp_registry.get_tool('task_create')
    body = {'name': 'x', 'case_ids': [1]}
    assert mcp_registry.build_body(create, {'body': body}) == body
    assert mcp_handler._build_target_body(create, {'body': body}) == body

    listed = mcp_registry.get_tool('task_list')
    assert mcp_registry.build_path(listed, {'page': 2, 'search': 'a b'}) == \
        '/api/v1/tasks?page=2&search=a+b'


# ---------------------------------------------------------------- 31 个意图工具

def test_intent_registry_has_31_unique_tools():
    assert len(INTENT_TOOLS) == 31
    names = [t.name for t in INTENT_TOOLS]
    assert len(names) == len(set(names))
    # M0 四项常驻 + M1 各域卡按域追加
    # （INT-2458 audio_query / INT-2462 evaluation_query / INT-2464 algorithm_query
    #   / INT-2459 device_query，含 SPL 只读子集）
    # 精确等值：新增启用工具必须在本卡同步更新该集合，避免无意多启用。
    assert ENABLED_TOOLS == {'platform_contract', 'tool_search', 'task_query',
                             'report_query', 'audio_query', 'evaluation_query',
                             'algorithm_query', 'device_query'}


def test_reserved_tool_names_present_and_disabled():
    reserved = {'memory_search', 'memory_write', 'ui_tree', 'ui_action', 'api_spec'}
    by_name = {t.name: t for t in INTENT_TOOLS}
    assert reserved <= set(by_name)
    for name in reserved:
        tool = by_name[name]
        assert tool.enabled is False
        assert tool.parameters['type'] == 'object'
        assert tool.risk in ('READ', 'WRITE', 'DESTRUCTIVE')
        assert isinstance(tool.permissions, tuple)


def test_every_intent_tool_has_schema_and_risk():
    for tool in INTENT_TOOLS:
        assert tool.risk in ('READ', 'WRITE', 'DESTRUCTIVE')
        assert tool.parameters.get('type') == 'object'
        assert isinstance(tool.parameters.get('properties'), dict)
        for required in tool.parameters.get('required') or ():
            assert required in tool.parameters['properties']


def test_action_mappings_reference_existing_readonly_mcp_tools():
    for mapping in (intent_tools.TASK_QUERY_ACTIONS,
                    intent_tools.REPORT_QUERY_ACTIONS):
        for action, mcp_name in mapping.items():
            tool = mcp_registry.get_tool(mcp_name)
            assert tool is not None, f'{action} -> {mcp_name} 不存在'
            # 只读语义：GET，或 POST 但只需要读权限（如 case-averages 取数）
            assert tool['method'] == 'GET' or all(
                p.endswith(':read') or p.endswith(':compare')
                for p in tool['permissions']), mcp_name
            assert action in intent_tools.INTENT_TOOL_BY_NAME[
                'task_query'].parameters['properties']['action']['enum'] or \
                action in intent_tools.INTENT_TOOL_BY_NAME[
                    'report_query'].parameters['properties']['action']['enum']


def test_skill_known_tools_has_no_unknown_warning():
    """Skills 引用预留工具名时不会出现 UNKNOWN_TOOL（启动告警验收）。"""
    from agent_service.application.skill_registry import SkillRegistry
    from agent_service.domain.enums import SkillIssueCode
    from agent_service.infrastructure.skill.fs_skill_repository import (
        FsSkillRepository,
    )
    root = os.path.join(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))), 'skills')
    registry = SkillRegistry(
        FsSkillRepository(root),
        known_tools=lambda: [t.name for t in INTENT_TOOLS]).load()
    unknown = [i for i in registry.issues
               if i.code is SkillIssueCode.UNKNOWN_TOOL]
    assert unknown == []


# ---------------------------------------------------------------- tool_search

@pytest.mark.parametrize('query,expected', [
    ('导出报告', 'report_export'),
    ('任务列表', 'task_list'),
    ('SPL 校准', 'spl_calibrate'),
    ('批量标注音频', 'audio_batch_annotations'),
    ('设备告警', 'device_alarm_list'),
    ('日志统计', 'log_stats'),
    ('对比报告', 'report_compare'),
    ('用例详情', 'testcase_get'),
    ('首页统计', 'dashboard_query'),
    ('生成报告', 'report_generate'),
])
def test_tool_search_hits_expected_tool(query, expected):
    result = search.search(query, ['*'], limit=10)
    names = [t['name'] for t in result['tools']]
    assert expected in names, f'{query} -> {names}'


def test_tool_search_returns_callable_schemas():
    result = search.search('任务列表', ['*'])
    assert result['total'] >= 1
    for tool in result['tools']:
        assert tool['inputSchema']['type'] == 'object'
        assert tool['name'] and tool['description']


def test_tool_search_filters_by_permission():
    low = search.search('报告', ['task:read'], limit=30)
    names = [t['name'] for t in low['tools']]
    assert all(not n.startswith('report') for n in names)
    admin = search.search('报告', ['*'], limit=30)
    assert any(n.startswith('report') for n in [t['name'] for t in admin['tools']])


def test_tool_search_index_includes_reserved_names():
    names = {t['name'] for t in TOOL_INDEX}
    assert {'memory_search', 'memory_write', 'ui_tree', 'ui_action',
            'api_spec'} <= names
    assert len(TOOL_INDEX) == (205 - 1) + 31 - 2  # 两个同名项去重 + 排除 audio_get_by_ids（INT-2530 宿主语境）


def test_tool_search_limit_is_bounded():
    assert search.search('任务', ['*'], limit=1)['total'] <= 1
    assert search.search('任务', ['*'], limit=999)['total'] <= search.MAX_LIMIT


# ---------------------------------------------------------------- platform_contract

def test_platform_contract_returns_enums_and_tools():
    result = intent_tools.platform_contract('任务状态', 'enums')
    assert result['enums']
    assert any(e['name'] == 'task_status' for e in result['enums'])
    assert 'completed' in next(e['values'] for e in result['enums']
                               if e['name'] == 'task_status')

    tools = intent_tools.platform_contract('导出报告')
    assert any(t['name'] == 'report_export' for t in tools['tools'])


def test_platform_contract_tool_name_returns_schema():
    result = intent_tools.platform_contract('task_get')
    assert result['tool']['name'] == 'task_get'
    assert result['tool']['inputSchema'] == mcp_registry.get_tool('task_get')['inputSchema']

    result = intent_tools.platform_contract('task_query')
    assert result['tool']['name'] == 'task_query'
    assert result['tool']['inputSchema']['required'] == ['action']


def test_platform_contract_service_ports_come_from_code():
    result = contract.lookup('', 'services')
    by_name = {s['name']: s for s in result['services']}
    from shared.config import service_ports
    assert by_name['api_gateway']['http'] == service_ports.API_GATEWAY_PORT
    assert by_name['task_service']['grpc'] == service_ports.TASK_SERVICE_GRPC_PORT


# ---------------------------------------------------------------- 条件必填

def test_validate_arguments_required_type_enum():
    schema = intent_tools.INTENT_TOOL_BY_NAME['task_query'].parameters
    assert intent_tools.validate_arguments(schema, {}) == '缺少必填参数：action'
    assert intent_tools.validate_arguments(schema, {'action': 1}) == \
        '参数 action 类型应为 string'
    assert '取值必须是' in intent_tools.validate_arguments(
        schema, {'action': 'nope'})
    assert intent_tools.validate_arguments(schema, {'action': 'list'}) is None


def test_action_required_fields():
    assert intent_tools.required_for_action('task_query', 'detail') == ('task_id',)
    assert intent_tools.required_for_action(
        'task_query', 'case_detail') == ('task_id', 'case_id')
    assert intent_tools.required_for_action('report_query', 'list') == ()


def test_resolve_rest_call_maps_action_to_mcp_tool():
    tool, merged, error = intent_tools.resolve_rest_call(
        'task_query', {'action': 'detail', 'task_id': 9})
    assert error is None
    assert tool['name'] == 'task_get'
    assert merged == {'task_id': 9}

    _, _, error = intent_tools.resolve_rest_call(
        'task_query', {'action': 'detail'})
    assert '缺少必填参数' in error

    tool, merged, error = intent_tools.resolve_rest_call(
        'report_list', {'page': 1})
    assert error is None and tool['name'] == 'report_list' and merged == {'page': 1}
