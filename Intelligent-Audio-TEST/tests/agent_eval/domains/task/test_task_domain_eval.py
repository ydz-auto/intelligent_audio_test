# -*- coding: utf-8 -*-
"""INT-2461 任务 / 日志 / 首页域只读评测（agent_eval / domains / task）。

评测对象三层：

1. **意图工具** ``task_query`` / ``log_diagnose`` / ``dashboard_query``：
   动作 → MCP 只读工具 → 网关真实路由；10 条 golden tasks
   （``golden_tasks.json``：任务 5 + 日志 3 + 首页 2）逐条解析出目标工具与路径；
2. **本地只读聚合** ``task_diagnose`` / ``log_diagnose.diagnose``：纯函数汇总
   真实接口数据，失败诊断必须带来源 ID（日志 ``id`` / 用例 ``case_id``）；
3. **Skill** ``task-operations`` / ``log-diagnostics``：L1 触发覆盖、L2 正文与
   真实接口口径一致、``allowed-tools`` 只含已启用的只读工具。

卡面验收锚点（INT-2461）：
1. 每域 10 条任务走通（任务 5 + 日志 3 + 首页 2）；
2. 进度 / 统计与真实接口一致，不估算、不编造数值（字段直接透传）；
3. 2 个 Skill 触发准确率 ≥ 90%；
4. 失败诊断输出引用真实日志行或接口字段（带来源 ID）。

默认离线执行：不连 Docker 栈、不连数据库。需要真机核对契约时设
``AGENT_EVAL_LIVE=1`` 再跑（默认连本机 docker 网关 15000，可用
``AGENT_EVAL_BASE`` / ``AGENT_EVAL_USER`` / ``AGENT_EVAL_PASSWORD`` 覆盖）。
"""
import json
import os
import re
import urllib.parse

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from agent_service.application.tool_gateway import (
    INVALID_ARGUMENTS, PERMISSION_DENIED, RESOURCE_NOT_FOUND,
    SharedToolGateway,
)
from agent_service.domain.model.entities import ToolCallRequest
from agent_service.domain.ports.tool_gateway import ToolInvocationContext
from agent_service.infrastructure.tools.registry_bridge import (
    RestResult, RunCredentialRegistry, SharedToolRegistryBridge,
)
from shared.agent_tools import diagnostics, intent_tools, mcp_registry
from shared.agent_tools.intent_tools import (
    DASHBOARD_QUERY_ACTIONS, LOG_DIAGNOSE_ACTIONS,
    LOG_DIAGNOSE_LOCAL_ACTIONS, LOG_DIAGNOSE_STATS_UNSUPPORTED_PARAMS,
    TASK_QUERY_ACTIONS,
)

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(
    os.path.join(_HERE, '..', '..', '..', '..'))
_SKILLS_ROOT = os.path.join(_PROJECT_ROOT, 'skills')

with open(os.path.join(_HERE, 'golden_tasks.json'), encoding='utf-8') as _handle:
    GOLDEN = json.load(_handle)

CASES = GOLDEN['cases']
NEGATIVES = GOLDEN['negatives']

# 工具 → 网关路由模块（用于核对路径真实存在）
_ROUTE_MODULES = {
    '/api/v1/tasks': 'api_gateway.routes.task_bp',
    '/api/v1/logs': 'api_gateway.routes.log_bp',
    '/api/v1/home': 'api_gateway.routes.home_bp',
}


def _split_url(path):
    parts = urllib.parse.urlsplit(path)
    query = {k: v[0] for k, v in urllib.parse.parse_qs(parts.query).items()}
    return parts.path, query


def _normalize(path_template):
    return re.sub(r'\{[^}]+\}', '{}', path_template)


def _load_skill_registry():
    from agent_service.application.skill_registry import SkillRegistry
    from agent_service.infrastructure.skill.fs_skill_repository import (
        FsSkillRepository,
    )
    return SkillRegistry(
        FsSkillRepository(_SKILLS_ROOT),
        known_tools=lambda: [t.name for t in intent_tools.INTENT_TOOLS]).load()


def _skill(name):
    return _load_skill_registry().get(name)


def _trigger_words(description):
    """从 L1 description 的「触发词：…。」段解析触发词（含换行折叠）。"""
    text = ' '.join((description or '').split())
    marker = '触发词：'
    start = text.find(marker)
    if start < 0:
        return ()
    segment = text[start + len(marker):]
    end = segment.find('。')
    if end >= 0:
        segment = segment[:end]
    return tuple(t.strip() for t in segment.split('、') if t.strip())


def _gateway_routes(module_name):
    """返回 ``(relative_path, methods)`` 集合（含前缀裁剪由调用方做）。"""
    import importlib
    router = importlib.import_module(module_name).router
    return [
        (_normalize(getattr(route, 'path', '')),
         set(getattr(route, 'methods', set()) or set()))
        for route in router.routes
    ]


def _assert_route_exists(prefix, path, module_name):
    relative = _normalize(path[len(prefix):] or '')
    routes = _gateway_routes(module_name)
    assert any(relative == route_path and 'GET' in methods
               for route_path, methods in routes), \
        f'{path} 在网关 {module_name} 里没有 GET 路由'


# ---------------------------------------------------------------- 1. 工具契约


def test_task_query_is_enabled_readonly_with_task_read():
    tool = intent_tools.INTENT_TOOL_BY_NAME['task_query']
    assert tool.enabled is True
    assert tool.risk == 'READ'
    assert tool.permissions == ('task:read',)
    assert 'task_query' in intent_tools.ENABLED_TOOLS


def test_task_action_enum_matches_action_mapping():
    schema = intent_tools.INTENT_TOOL_BY_NAME['task_query'].parameters
    assert schema['required'] == ['action']
    assert set(schema['properties']['action']['enum']) == set(
        TASK_QUERY_ACTIONS)


def test_every_task_action_maps_to_readonly_mcp_tool():
    for action, mcp_name in TASK_QUERY_ACTIONS.items():
        tool = mcp_registry.get_tool(mcp_name)
        assert tool is not None, f'{action} -> {mcp_name} 未注册'
        assert tool['method'] == 'GET', mcp_name
        assert tool['permissions'] == ['task:read'], mcp_name
        assert tool['path'].startswith('/api/v1/tasks'), mcp_name


def test_every_task_action_targets_a_registered_gateway_get_route():
    from api_gateway.routes.task_bp import router

    registered = {
        (_normalize(route.path), 'GET') for route in router.routes
        if route.methods and 'GET' in route.methods
    }
    for action, mcp_name in TASK_QUERY_ACTIONS.items():
        path = mcp_registry.get_tool(mcp_name)['path']
        relative = _normalize(path[len('/api/v1/tasks'):] or '')
        assert (relative, 'GET') in registered, (
            f'{action} -> {mcp_name} 的 {path} 在网关上没有 GET 路由')


def test_task_list_filters_match_gateway_query_schema():
    """list 的过滤参数与网关 TaskListQuery 逐字一致（不编造、不漏字段）。"""
    from api_gateway.schemas.task import TaskListQuery

    schema = intent_tools.INTENT_TOOL_BY_NAME['task_query'].parameters
    declared = set(schema['properties']) - {'action'}
    assert set(intent_tools.TASK_QUERY_PARAMS['list']) == set(
        TaskListQuery.model_fields)
    assert set(intent_tools.TASK_QUERY_PARAMS['list']) <= declared


def test_domain_stats_granularity_matches_gateway_schema():
    from api_gateway.schemas.task import TaskDomainStatsQuery

    field = TaskDomainStatsQuery.model_fields['granularity']
    assert field.default == 'day'
    assert intent_tools.TASK_DOMAIN_STATS_GRANULARITIES == (
        'day', 'week', 'month', 'year')
    schema = intent_tools.INTENT_TOOL_BY_NAME['task_query'].parameters
    assert set(schema['properties']['granularity']['enum']) == set(
        intent_tools.TASK_DOMAIN_STATS_GRANULARITIES)


def test_task_query_rejects_parameters_the_endpoint_ignores():
    # list 不认 task_id / case_id（服务端会静默忽略）
    _, _, error = intent_tools.resolve_rest_call(
        'task_query', {'action': 'list', 'task_id': 128})
    assert error and '不支持参数' in error and 'task_id' in error
    # detail 只认 task_id
    _, _, error = intent_tools.resolve_rest_call(
        'task_query', {'action': 'detail', 'task_id': 128, 'status': 'failed'})
    assert error and 'status' in error
    # domain_stats 只认 granularity
    _, _, error = intent_tools.resolve_rest_call(
        'task_query', {'action': 'domain_stats', 'granularity': 'hour'})
    assert error and 'granularity' in error
    tool, merged, error = intent_tools.resolve_rest_call(
        'task_query', {'action': 'domain_stats', 'granularity': 'week'})
    assert error is None and tool['name'] == 'task_stats'
    assert merged == {'granularity': 'week'}


def test_task_diagnose_contract():
    tool = intent_tools.INTENT_TOOL_BY_NAME['task_diagnose']
    assert tool.enabled is True
    assert tool.risk == 'READ'
    assert tool.parameters['required'] == ['task_id']
    assert set(tool.permissions) == {'task:read', 'log:read'}
    assert tool.kind == 'local'
    assert 'task_diagnose' in intent_tools.LOCAL_TOOL_NAMES
    assert intent_tools.validate_arguments(tool.parameters, {}) == \
        '缺少必填参数：task_id'
    assert intent_tools.validate_arguments(
        tool.parameters, {'task_id': 1}) is None


def test_task_diagnose_permissions_exist_in_rbac():
    import ast

    path = os.path.join(_PROJECT_ROOT, 'scripts', 'migrations', '202608',
                        'seed_rbac.py')
    with open(path, encoding='utf-8') as handle:
        tree = ast.parse(handle.read())
    codes = set()
    for node in tree.body:
        if isinstance(node, ast.Assign) and \
                getattr(node.targets[0], 'id', '') == 'PERMISSIONS':
            codes = {ast.literal_eval(elt)[0] for elt in node.value.elts}
    tool = intent_tools.INTENT_TOOL_BY_NAME['task_diagnose']
    assert set(tool.permissions) <= codes


def test_log_diagnose_contract():
    tool = intent_tools.INTENT_TOOL_BY_NAME['log_diagnose']
    assert tool.enabled is True
    assert tool.risk == 'READ'
    assert tool.permissions == ('log:read',)
    schema = tool.parameters
    assert set(schema['properties']['action']['enum']) == \
        set(LOG_DIAGNOSE_ACTIONS) | set(LOG_DIAGNOSE_LOCAL_ACTIONS)
    assert LOG_DIAGNOSE_LOCAL_ACTIONS == ('diagnose',)
    assert 'log_diagnose' in intent_tools.LOCAL_TOOL_NAMES


def test_every_log_diagnose_rest_action_maps_to_readonly_mcp_tool():
    for action, mcp_name in LOG_DIAGNOSE_ACTIONS.items():
        tool = mcp_registry.get_tool(mcp_name)
        assert tool is not None, f'{action} -> {mcp_name} 未注册'
        assert tool['method'] == 'GET', mcp_name
        assert tool['permissions'] == ['log:read'], mcp_name
        assert tool['path'].startswith('/api/v1/logs'), mcp_name
        _assert_route_exists('/api/v1/logs', tool['path'],
                             'api_gateway.routes.log_bp')


def test_log_diagnose_diagnose_is_local_not_rest():
    tool, merged, error = intent_tools.resolve_rest_call(
        'log_diagnose', {'action': 'diagnose', 'task_id': 128})
    assert tool is None and merged is None
    assert error and '本地日志聚合' in error


def test_log_filters_match_gateway_query_schemas():
    from api_gateway.schemas.log import LogListQuery, LogStatsQuery

    search_params = set(intent_tools.LOG_DIAGNOSE_PARAMS['search'])
    stats_params = set(intent_tools.LOG_DIAGNOSE_PARAMS['stats'])
    assert search_params <= set(LogListQuery.model_fields)
    assert stats_params <= set(LogStatsQuery.model_fields)
    # stats 端点没有 test_case_id / page / per_page，工具层不声明
    assert not stats_params & {'test_case_id', 'page', 'per_page'}
    # MCP 工具声明的查询参数与动作白名单一致（单一事实源）
    assert set(mcp_registry.get_tool('log_list')['query_params']) == \
        search_params
    assert set(mcp_registry.get_tool('log_stats')['query_params']) == \
        stats_params


def test_log_diagnose_rejects_unsupported_action_params():
    _, _, error = intent_tools.resolve_rest_call(
        'log_diagnose', {'action': 'stats', 'page': 2})
    assert error and '不支持参数' in error and 'page' in error
    _, _, error = intent_tools.resolve_rest_call(
        'log_diagnose', {'action': 'search', 'user_id': 7})
    assert error and 'user_id' in error


def test_log_diagnose_stats_only_params_are_declared_and_unsupported():
    """INT-2461 P2：只作用于取样的参数必须在动作白名单里，且不得进统计。"""
    diagnose_params = set(intent_tools.LOG_DIAGNOSE_PARAMS['diagnose'])
    stats_params = set(intent_tools.LOG_DIAGNOSE_PARAMS['stats'])
    assert set(LOG_DIAGNOSE_STATS_UNSUPPORTED_PARAMS) <= diagnose_params
    # 统计动作本身就不声明这些参数（工具层直接拒绝，不静默忽略）
    assert not set(LOG_DIAGNOSE_STATS_UNSUPPORTED_PARAMS) & stats_params


def test_log_diagnose_max_rows_bounds_come_from_schema():
    schema = intent_tools.INTENT_TOOL_BY_NAME['log_diagnose'].parameters
    prop = schema['properties']['max_rows']
    assert (prop['minimum'], prop['maximum']) == (
        1, intent_tools.LOG_DIAGNOSE_MAX_ROWS)
    assert '不能小于' in intent_tools.validate_arguments(
        schema, {'action': 'diagnose', 'max_rows': 0})
    assert '不能大于' in intent_tools.validate_arguments(
        schema, {'action': 'diagnose',
                 'max_rows': intent_tools.LOG_DIAGNOSE_MAX_ROWS + 1})
    assert intent_tools.validate_arguments(
        schema, {'action': 'diagnose', 'max_rows': 30}) is None


def test_dashboard_query_contract_and_routes():
    tool = intent_tools.INTENT_TOOL_BY_NAME['dashboard_query']
    assert tool.enabled is True
    assert tool.risk == 'READ'
    assert tool.permissions == ('home:read',)
    schema = tool.parameters
    assert schema['required'] == ['action']
    assert set(schema['properties']['action']['enum']) == set(
        DASHBOARD_QUERY_ACTIONS)
    for action, mcp_name in DASHBOARD_QUERY_ACTIONS.items():
        mcp = mcp_registry.get_tool(mcp_name)
        assert mcp is not None, f'{action} -> {mcp_name} 未注册'
        assert mcp['method'] == 'GET' and mcp['permissions'] == ['home:read']
        assert mcp['path'].startswith('/api/v1/home')
        _assert_route_exists('/api/v1/home', mcp['path'],
                             'api_gateway.routes.home_bp')
    # 缓存刷新（POST /home/stats/refresh）是写侧，M1 不暴露
    paths = [mcp_registry.get_tool(name)['path']
             for name in DASHBOARD_QUERY_ACTIONS.values()]
    assert not any('refresh' in path for path in paths)


@pytest.mark.parametrize('query,expected', [
    ('任务诊断', 'task_diagnose'),
    ('日志诊断', 'log_diagnose'),
    ('首页统计', 'dashboard_query'),
    ('错误日志', 'log_list'),
])
def test_tool_search_surfaces_task_log_home_tools(query, expected):
    from shared.agent_tools.search import search
    names = [t['name'] for t in search(query, ['task:read', 'log:read',
                                               'home:read'])['tools']]
    assert expected in names, f'{query} -> {names}'


# ---------------------------------------------------------------- 2. golden tasks


def test_golden_tasks_are_ten_and_cover_five_task_three_log_two_home():
    assert len(CASES) == 10
    assert len({case['id'] for case in CASES}) == 10
    by_tool = {}
    for case in CASES:
        by_tool.setdefault(case['tool'], []).append(case)
    assert len(by_tool['task_query']) == 5
    assert len(by_tool['log_diagnose']) == 3
    assert len(by_tool['dashboard_query']) == 2


@pytest.mark.parametrize('case', CASES, ids=[c['id'] for c in CASES])
def test_golden_task_resolves_to_expected_tool_and_path(case):
    tool_name = case['tool']
    schema = intent_tools.INTENT_TOOL_BY_NAME[tool_name].parameters
    assert intent_tools.validate_arguments(schema, case['arguments']) is None

    if case.get('local'):
        tool, merged, error = intent_tools.resolve_rest_call(
            tool_name, case['arguments'])
        assert tool is None and merged is None
        assert error and '本地日志聚合' in error
        return

    tool, merged, error = intent_tools.resolve_rest_call(
        tool_name, case['arguments'])
    assert error is None, error
    assert tool['name'] == case['expected_tool']
    assert tool['method'] == case['expected_method']

    path, query = _split_url(mcp_registry.build_path(tool, merged))
    expected_path, expected_query = _split_url(case['expected_path'])
    assert path == expected_path
    assert query == expected_query


def test_golden_task_arguments_only_use_declared_schema_fields():
    for case in CASES:
        properties = intent_tools.INTENT_TOOL_BY_NAME[
            case['tool']].parameters['properties']
        for name in case['arguments']:
            assert name in properties, f"{case['id']} 未声明参数 {name}"


def test_golden_task_actions_exist_in_action_mappings():
    for case in CASES:
        action = case['action']
        assert action in intent_tools.INTENT_TOOL_BY_NAME[
            case['tool']].parameters['properties']['action']['enum'], \
            f"{case['id']} action={action} 不在枚举里"


# ---------------------------------------------------------------- 3. 诊断聚合


TASK_DETAIL = {
    'id': 128,
    'name': '唤醒测试',
    'status': 'failed',
    'execution_status': 'failed',
    'evaluation_status': 'skipped',
    'total_cases': 2,
    'completed_cases': 2,
    'failed_cases': 1,
    'started_at': '2026-11-12T10:00:00Z',
    'completed_at': '2026-11-12T10:02:00Z',
    'cases': [
        {'case_id': 'case-abc', 'name': '近场唤醒',
         'status': 'failed', 'execution_status': 'failed',
         'evaluation_status': 'skipped', 'error_message': 'ASR 超时'},
        {'case_id': 'case-ok', 'name': '远场唤醒',
         'status': 'completed', 'execution_status': 'completed',
         'evaluation_status': 'completed', 'error_message': None},
    ],
}

TASK_PROGRESS = {
    'task_id': '128', 'status': 'failed', 'execution_status': 'failed',
    'evaluation_status': 'skipped', 'total_cases': 2, 'completed_cases': 2,
    'failed_cases': 1, 'progress': 100.0,
    'current_case': None, 'updated_at': '2026-11-12T10:02:00Z',
}

TASK_STATS = {
    'total': 2, 'completed': 1, 'failed': 1, 'pending': 0, 'skipped': 0,
    'pass_rate': 50.0, 'tag_stats': {'wakeup': {'total': 2}}, 'duration': 120.0,
}

LOG_ITEMS = [
    {'id': 1770000000000001, 'time': '2026-11-12T10:01:59Z', 'level': 'ERROR',
     'module': 'asr', 'category': 'algorithm', 'content': 'ASR 超时 10s',
     'task_id': 128, 'test_case_id': 'case-abc'},
    {'id': 1770000000000002, 'time': '2026-11-12T10:01:59Z', 'level': 'CRITICAL',
     'module': 'asr', 'category': 'algorithm', 'content': 'ASR 进程退出',
     'task_id': 128, 'test_case_id': 'case-abc'},
    {'id': 1770000000000003, 'time': '2026-11-12T10:02:00Z', 'level': 'ERROR',
     'module': 'device', 'category': 'network', 'content': '播放设备断连',
     'task_id': 128, 'test_case_id': None},
]


def _task_diagnosis(**overrides):
    sources = {
        'task_id': 128,
        'detail': TASK_DETAIL,
        'progress': TASK_PROGRESS,
        'stats': TASK_STATS,
        'log_items': LOG_ITEMS,
        'log_total': 7,
        'case_id': None,
        'keyword': None,
        'logs_available': True,
        'log_denied': False,
        'log_error': None,
        'progress_error': None,
        'stats_error': None,
        'log_filter': {'task_id': 128, 'level': 'error,critical',
                       'per_page': 20},
    }
    sources.update(overrides)
    return diagnostics.build_task_diagnosis(**sources)


def test_task_diagnosis_cites_real_case_and_log_ids():
    payload = _task_diagnosis()
    assert payload['task_id'] == 128
    assert payload['status']['progress'] == 100.0
    assert payload['status']['failed_cases'] == 1
    assert payload['counts'] == TASK_STATS          # 原样透传，不重算
    assert [case['case_id'] for case in payload['failed_cases']] == ['case-abc']
    assert payload['failed_cases'][0]['error_message'] == 'ASR 超时'

    ids = [row['id'] for row in payload['error_logs']['rows']]
    assert ids == [1770000000000001, 1770000000000002, 1770000000000003]
    assert payload['error_logs']['total_matched'] == 7

    top = payload['attribution'][0]
    assert (top['module'], top['category'], top['count']) == (
        'asr', 'algorithm', 2)
    assert top['log_ids'] == [1770000000000001, 1770000000000002]
    assert top['sample_content'] == 'ASR 超时 10s'

    suggestion = payload['retest']['suggestions'][0]
    assert suggestion['case_id'] == 'case-abc'
    assert suggestion['executed'] is False
    evidence = {(e['source'], e['field']): e['value']
                for e in suggestion['evidence']}
    assert evidence[('task_detail',
                     'cases[case_id=case-abc].execution_status')] == 'failed'
    assert evidence[('log_list', 'id')] == [1770000000000001,
                                            1770000000000002]
    assert payload['retest']['executed'] is False


def test_task_diagnosis_notes_sample_coverage():
    payload = _task_diagnosis()
    notes = ' '.join(payload['notes'])
    assert '样本 3 行' in notes and '共 7 行' in notes


def test_task_diagnosis_case_filter_non_failed_case_is_explained():
    payload = _task_diagnosis(case_id='case-ok')
    assert payload['failed_cases'] == []
    notes = ' '.join(payload['notes'])
    assert 'case_id=case-ok 当前不是失败状态' in notes


def test_task_diagnosis_without_log_permission_says_so():
    payload = _task_diagnosis(log_items=None, log_total=None,
                              logs_available=False, log_denied=True)
    assert payload['error_logs']['rows'] == []
    notes = ' '.join(payload['notes'])
    assert '缺少 log:read' in notes
    log_source = [s for s in payload['sources'] if s['kind'] == 'log_list'][0]
    assert log_source['available'] is False


def test_task_diagnosis_empty_logs_are_not_reported_as_healthy():
    payload = _task_diagnosis(log_items=[], log_total=0)
    notes = ' '.join(payload['notes'])
    assert '没有 ERROR / CRITICAL 日志行' in notes
    assert '不等于执行正常' in notes


def test_task_diagnosis_degraded_sources_are_reported():
    payload = _task_diagnosis(progress=None, stats=None,
                              progress_error='500 内部错误',
                              stats_error='404 未找到')
    notes = ' '.join(payload['notes'])
    assert '进度接口本轮不可用' in notes and '用例统计接口本轮不可用' in notes
    by_kind = {s['kind']: s for s in payload['sources']}
    assert by_kind['task_progress']['available'] is False
    assert by_kind['task_stats']['available'] is False


def test_task_diagnosis_no_failed_case_does_not_invent_reasons():
    detail = dict(TASK_DETAIL, status='completed',
                  execution_status='completed', cases=[TASK_DETAIL['cases'][1]])
    payload = _task_diagnosis(detail=detail)
    assert payload['failed_cases'] == []
    assert payload['retest']['suggestions'] == []
    assert any('没有执行失败的用例' in note for note in payload['notes'])


def test_log_diagnosis_passes_stats_through_and_flags_sample_coverage():
    stats = {'total': 100, 'debug': 10, 'info': 80, 'warning': 4,
             'error': 5, 'critical': 1}
    payload = diagnostics.build_log_diagnosis(
        stats_filters={'task_id': 128},
        list_filters={'task_id': 128, 'level': 'error,critical',
                      'page': 1, 'per_page': 20},
        levels=('error', 'critical'), stats=stats, items=LOG_ITEMS, total=6,
        max_rows=20)
    assert payload['stats'] == stats                 # 原值透传
    assert payload['sample_levels'] == ['error', 'critical']
    assert payload['sampled_rows'] == 3
    assert [row['id'] for row in payload['log_rows']] == [
        1770000000000001, 1770000000000002, 1770000000000003]
    notes = ' '.join(payload['notes'])
    assert '样本 3 行' in notes and '共 6 行' in notes
    assert payload['sources'][0]['filters'] == {'task_id': 128}
    assert payload['sources'][1]['filters']['level'] == 'error,critical'


def test_log_diagnosis_without_rows_is_not_reported_as_healthy():
    payload = diagnostics.build_log_diagnosis(
        stats={'total': 0, 'debug': 0, 'info': 0, 'warning': 0,
               'error': 0, 'critical': 0},
        items=[], total=0)
    assert payload['log_rows'] == []
    notes = ' '.join(payload['notes'])
    assert '不等于「服务正常」' in notes


def test_log_diagnosis_reports_stats_scope_when_case_filter_is_sample_only():
    """INT-2461 P2：级别统计接口没有 test_case_id，notes 必须写明口径。"""
    payload = diagnostics.build_log_diagnosis(
        stats_filters={'task_id': 588},
        list_filters={'task_id': 588, 'test_case_id': 'case-abc',
                      'level': 'error,critical', 'page': 1, 'per_page': 20},
        stats_unsupported=['test_case_id'],
        stats={'error': 5, 'critical': 1}, items=[], total=0)
    assert payload['stats_filters'] == {'task_id': 588}
    assert payload['sources'][0]['filters'] == {'task_id': 588}
    assert payload['list_filters']['test_case_id'] == 'case-abc'
    notes = ' '.join(payload['notes'])
    assert '不支持按 test_case_id 过滤' in notes
    assert '任务 / 全局口径' in notes
    assert '只作用于日志样本取样' in notes


def test_log_diagnosis_list_error_is_reported():
    payload = diagnostics.build_log_diagnosis(
        stats={'error': 0, 'critical': 0}, items=None,
        list_error='500 内部错误')
    notes = ' '.join(payload['notes'])
    assert '日志列表接口本轮不可用' in notes


# ---------------------------------------------------------------- 4. ToolGateway 本地聚合


class ScriptedRest:
    """按工具名返回脚本化响应（记录回源调用）。"""

    def __init__(self, responses=None):
        self.responses = responses or {}
        self.calls = []

    def call(self, tool, arguments, **kwargs):
        self.calls.append({'name': tool['name'], 'arguments': dict(arguments)})
        item = self.responses.get(tool['name'])
        if item is None:
            status, payload = 200, {'success': True, 'data': {}}
        elif callable(item):
            status, payload = item(arguments)
        else:
            status, payload = item
        return RestResult(status=status, payload=payload,
                          text=json.dumps(payload, ensure_ascii=False))


def _gateway(rest):
    return SharedToolGateway(bridge=SharedToolRegistryBridge(), rest=rest,
                             credentials=RunCredentialRegistry())


def _ctx(permissions=('task:read', 'log:read')):
    return ToolInvocationContext(
        run_id='r1', session_id='s1', owner_id=7, tenant_id='t1',
        step_id='st1', permissions=tuple(permissions),
        idempotency_key='k1')


def _call(name, arguments):
    return ToolCallRequest(tool_call_id='call-1', name=name,
                           arguments=arguments)


def _task_responses():
    return {
        'task_get': (200, {'success': True, 'data': TASK_DETAIL}),
        'task_get_progress': (200, {'success': True, 'data': TASK_PROGRESS}),
        'task_get_stats': (200, {'success': True, 'data': TASK_STATS}),
        'log_list': (200, {'success': True, 'data': {
            'items': LOG_ITEMS, 'total': 7, 'page': 1, 'per_page': 20,
            'pages': 1}}),
    }


def test_task_diagnose_gateway_reads_real_sources_and_keeps_source_ids():
    rest = ScriptedRest(_task_responses())
    result = _gateway(rest).execute(
        _call('task_diagnose', {'task_id': 128}), _ctx())
    assert result.ok is True and result.error_code == 'OK'
    assert [c['name'] for c in rest.calls] == [
        'task_get', 'task_get_progress', 'task_get_stats', 'log_list']
    log_call = rest.calls[-1]['arguments']
    assert log_call['task_id'] == 128
    assert log_call['level'] == 'error,critical'
    assert log_call['per_page'] == 20        # 取样上限（同一事实源）

    payload = json.loads(result.content)
    assert payload['failed_cases'][0]['case_id'] == 'case-abc'
    assert payload['error_logs']['rows'][0]['id'] == 1770000000000001
    assert payload['retest']['executed'] is False


def test_task_diagnose_without_log_read_degrades_without_silence():
    rest = ScriptedRest(_task_responses())
    result = _gateway(rest).execute(
        _call('task_diagnose', {'task_id': 128}), _ctx(('task:read',)))
    assert result.ok is True
    assert [c['name'] for c in rest.calls] == [
        'task_get', 'task_get_progress', 'task_get_stats']
    payload = json.loads(result.content)
    assert any('缺少 log:read' in note for note in payload['notes'])
    assert payload['error_logs']['rows'] == []


def test_task_diagnose_missing_task_fails_with_not_found():
    responses = dict(_task_responses())
    responses['task_get'] = (404, {'success': False, 'message': '未找到任务'})
    result = _gateway(ScriptedRest(responses)).execute(
        _call('task_diagnose', {'task_id': 404}), _ctx())
    assert result.ok is False
    assert result.error_code == RESOURCE_NOT_FOUND


def test_task_diagnose_requires_task_id_and_task_read():
    result = _gateway(ScriptedRest()).execute(
        _call('task_diagnose', {}), _ctx())
    assert result.error_code == INVALID_ARGUMENTS

    rest = ScriptedRest()
    result = _gateway(rest).execute(
        _call('task_diagnose', {'task_id': 128}), _ctx(('home:read',)))
    assert result.error_code == PERMISSION_DENIED
    assert rest.calls == []


def test_log_diagnose_local_aggregation_calls_stats_then_list():
    rest = ScriptedRest({
        'log_stats': (200, {'success': True, 'data': {
            'total': 100, 'debug': 10, 'info': 80, 'warning': 4,
            'error': 5, 'critical': 1}}),
        'log_list': (200, {'success': True, 'data': {
            'items': LOG_ITEMS, 'total': 6, 'page': 1, 'per_page': 20,
            'pages': 1}}),
    })
    result = _gateway(rest).execute(
        _call('log_diagnose', {'action': 'diagnose', 'task_id': 128}), _ctx())
    assert result.ok is True
    assert [c['name'] for c in rest.calls] == ['log_stats', 'log_list']
    stats_args, list_args = rest.calls[0]['arguments'], rest.calls[1]['arguments']
    assert 'level' not in stats_args          # 统计保留完整 breakdown
    assert list_args['level'] == 'error,critical'
    assert list_args['per_page'] == 20
    payload = json.loads(result.content)
    assert payload['stats']['error'] == 5
    assert payload['sampled_rows'] == 3
    assert payload['attribution'][0]['module'] == 'asr'


def test_log_diagnose_custom_level_narrows_sample_but_keeps_stats_full():
    rest = ScriptedRest({
        'log_stats': (200, {'success': True, 'data': {'warning': 4}}),
        'log_list': (200, {'success': True, 'data': {
            'items': [], 'total': 0, 'page': 1, 'per_page': 20, 'pages': 1}}),
    })
    result = _gateway(rest).execute(
        _call('log_diagnose', {'action': 'diagnose', 'level': 'warning',
                               'max_rows': 30}), _ctx())
    assert result.ok is True
    assert rest.calls[1]['arguments']['level'] == 'warning'
    assert rest.calls[1]['arguments']['per_page'] == 30
    payload = json.loads(result.content)
    assert payload['sample_levels'] == ['warning']


def test_log_diagnose_case_scope_only_narrows_sample_not_level_stats():
    """INT-2461 P2：diagnose 带 test_case_id 时统计口径仍是任务 / 全局。"""
    rest = ScriptedRest({
        'log_stats': (200, {'success': True, 'data': {
            'total': 1448, 'debug': 10, 'info': 1430, 'warning': 3,
            'error': 5, 'critical': 0}}),
        'log_list': (200, {'success': True, 'data': {
            'items': [], 'total': 0, 'page': 1, 'per_page': 20, 'pages': 1}}),
    })
    result = _gateway(rest).execute(
        _call('log_diagnose', {'action': 'diagnose', 'task_id': 588,
                               'test_case_id': 'case-abc'}), _ctx())
    assert result.ok is True
    stats_args = rest.calls[0]['arguments']
    list_args = rest.calls[1]['arguments']
    # /api/v1/logs/stats 没有 test_case_id：不能带上去（会被静默忽略）
    assert stats_args == {'task_id': 588}
    # 按用例过滤只作用于样本取样
    assert list_args['test_case_id'] == 'case-abc'

    payload = json.loads(result.content)
    assert payload['stats_filters'] == {'task_id': 588}
    assert payload['sources'][0]['filters'] == {'task_id': 588}
    assert payload['list_filters']['test_case_id'] == 'case-abc'
    assert payload['stats']['error'] == 5          # 统计值原样保留
    notes = ' '.join(payload['notes'])
    assert '不支持按 test_case_id 过滤' in notes
    assert '任务 / 全局口径' in notes


def test_log_diagnose_search_maps_to_single_log_list_call():
    rest = ScriptedRest({
        'log_list': (200, {'success': True, 'data': {
            'items': LOG_ITEMS, 'total': 3, 'page': 1, 'per_page': 50,
            'pages': 1}}),
    })
    result = _gateway(rest).execute(
        _call('log_diagnose', {'action': 'search', 'task_id': 128,
                               'level': 'error'}), _ctx())
    assert result.ok is True
    assert [c['name'] for c in rest.calls] == ['log_list']
    payload = json.loads(result.content)
    assert payload['data']['items'][0]['id'] == 1770000000000001


def test_log_diagnose_rejects_unknown_params_for_local_action():
    rest = ScriptedRest()
    result = _gateway(rest).execute(
        _call('log_diagnose', {'action': 'diagnose', 'user_id': 7}), _ctx())
    assert result.error_code == INVALID_ARGUMENTS
    assert 'user_id' in result.content
    assert rest.calls == []


def test_dashboard_query_maps_to_home_read_tool():
    rest = ScriptedRest({
        'home_stats_details': (200, {'success': True, 'data': {
            'test_cases': {'total': 12, 'groups': 3},
            'tasks': {'total': 9, 'completed': 5, 'running': 1, 'failed': 3},
            'audio_files': {'total': 40},
            'updated_at': '2026-11-12T10:00:00Z'}}),
    })
    result = _gateway(rest).execute(
        _call('dashboard_query', {'action': 'details'}), _ctx(('home:read',)))
    assert result.ok is True
    assert [c['name'] for c in rest.calls] == ['home_stats_details']
    assert json.loads(result.content)['data']['tasks']['total'] == 9


def test_dashboard_query_requires_home_read():
    rest = ScriptedRest()
    result = _gateway(rest).execute(
        _call('dashboard_query', {'action': 'summary'}), _ctx(('task:read',)))
    assert result.error_code == PERMISSION_DENIED
    assert rest.calls == []


# ---------------------------------------------------------------- 5. Skill L1/L2


@pytest.mark.parametrize('skill_name', ['task-operations', 'log-diagnostics'])
def test_skill_loads_with_required_sections(skill_name):
    registry = _load_skill_registry()
    skill = registry.get(skill_name)
    assert skill is not None, [i.message for i in registry.issues]
    assert not [i for i in registry.issues_for(skill_name)
                if i.severity.value == 'ERROR']
    assert skill.meta.version and skill.meta.owner
    assert skill.has_section('Gotchas')
    assert skill.has_section('验收')
    assert skill.body_line_count <= 500
    assert '触发词' in skill.meta.description
    assert '不适用' in skill.meta.description


@pytest.mark.parametrize('skill_name', ['task-operations', 'log-diagnostics'])
def test_skill_allowed_tools_are_enabled_readonly(skill_name):
    skill = _skill(skill_name)
    assert skill.meta.allowed_tools
    by_name = {t.name: t for t in intent_tools.INTENT_TOOLS}
    for name in skill.meta.allowed_tools:
        tool = by_name.get(name)
        assert tool is not None, f'allowed-tools 引用了未注册工具：{name}'
        assert tool.enabled is True, f'allowed-tools 引用了未启用工具：{name}'
        assert tool.risk == 'READ', f'allowed-tools 引用了写工具：{name}'
    assert 'task_run' not in skill.meta.allowed_tools


def test_task_skill_l2_documents_every_action():
    body = _skill('task-operations').body
    for action in TASK_QUERY_ACTIONS:
        assert f'`{action}`' in body, f'L2 正文没有覆盖动作 {action}'
    for keyword in ('task_diagnose', 'task:read', 'status', 'execution_status',
                    'evaluation_status', 'log:read', 'M2'):
        assert keyword in body, keyword


def test_log_skill_l2_documents_every_action():
    body = _skill('log-diagnostics').body
    for action in set(LOG_DIAGNOSE_ACTIONS) | set(LOG_DIAGNOSE_LOCAL_ACTIONS):
        assert f'`{action}`' in body, f'L2 正文没有覆盖动作 {action}'
    for keyword in ('log:read', 'log:manage', 'error', 'critical',
                    'LOG_DB_MERGE_MAX_ROWS', 'LOG_AUDIT_QUERY_DEFAULT_DAYS'):
        assert keyword in body, keyword
    assert 'log:write' not in body


def test_task_skill_does_not_claim_unreal_permission_codes():
    body = _skill('task-operations').body
    for code in ('task:write', 'task:diagnose', 'task:log'):
        assert code not in body, code


@pytest.mark.parametrize('skill_name', ['task-operations', 'log-diagnostics'])
def test_skill_trigger_accuracy_at_least_90_percent(skill_name):
    triggers = _trigger_words(_skill(skill_name).description)
    assert triggers, 'L1 description 缺少「触发词：」段'
    positives = [case['utterance'] for case in CASES
                 if case['skill'] == skill_name]
    negatives = NEGATIVES[skill_name]
    hit = [u for u in positives if any(t in u for t in triggers)]
    false_positive = [u for u in negatives if any(t in u for t in triggers)]
    total = len(positives) + len(negatives)
    correct = len(hit) + (len(negatives) - len(false_positive))
    accuracy = correct / total
    misses = [u for u in positives if u not in hit]
    assert accuracy >= 0.9, (
        f'{skill_name} 触发准确率 {accuracy:.0%} < 90%；'
        f'未命中={misses}；误命中={false_positive}')


# ---------------------------------------------------------------- 6. 真机契约（可选）

_LIVE = os.environ.get('AGENT_EVAL_LIVE') == '1'


@pytest.mark.skipif(not _LIVE, reason='AGENT_EVAL_LIVE!=1：默认离线，真机契约核对按需开启')
def test_live_task_log_home_contracts_match_documented_shapes():
    """连 docker 网关核对：任务 / 进度 / 统计 / 日志 / 首页返回形态。"""
    from tests.ui.utils.api_client import ApiClient

    base = os.environ.get('AGENT_EVAL_BASE', 'http://127.0.0.1:15000')
    client = ApiClient(base)
    client.login(os.environ.get('AGENT_EVAL_USER', 'dev_user'),
                 os.environ.get('AGENT_EVAL_PASSWORD', 'dev_password'))

    def get(path):
        return client.request('GET', path)

    listing = get('/tasks?per_page=1')['data']
    assert set(listing) >= {'items', 'total', 'page', 'per_page', 'pages'}
    if listing['items']:
        item = listing['items'][0]
        for key in ('id', 'name', 'status', 'execution_status'):
            assert key in item
        task_id = item['id']

        detail = get(f'/tasks/{task_id}')['data']
        assert isinstance(detail.get('cases'), list)
        for case in detail['cases']:
            assert 'case_id' in case and 'execution_status' in case

        progress = get(f'/tasks/{task_id}/progress')['data']
        for key in ('total_cases', 'completed_cases', 'failed_cases',
                    'progress'):
            assert key in progress

        stats = get(f'/tasks/{task_id}/stats')['data']
        for key in ('total', 'completed', 'failed', 'pending', 'skipped',
                    'pass_rate'):
            assert key in stats

    logs = get('/logs?per_page=1')['data']
    assert set(logs) >= {'items', 'total', 'page', 'per_page', 'pages'}
    if logs['items']:
        for key in ('id', 'time', 'level', 'module', 'content'):
            assert key in logs['items'][0]

    log_stats = get('/logs/stats')['data']
    for key in ('total', 'debug', 'info', 'warning', 'error', 'critical'):
        assert key in log_stats

    home_details = get('/home/stats/details')['data']
    for key in ('test_cases', 'tasks', 'devices', 'audio_files', 'apis',
                'reports', 'dimensions'):
        assert key in home_details

    home_summary = get('/home/stats/summary')['data']
    for key in ('recent_tasks', 'top_groups', 'device_status'):
        assert key in home_summary
