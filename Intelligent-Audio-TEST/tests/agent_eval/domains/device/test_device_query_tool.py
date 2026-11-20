# -*- coding: utf-8 -*-
"""INT-2459 设备与 SPL 域只读意图工具（device_query）。

验收锚点（卡面可测标准 1、2、4）：
1. 设备查询 6 条 + SPL 查询 4 条任务全部走通（动作 → 目标工具 → REST 参数透传）；
2. 设备状态 / 告警 / SPL 映射 / 历史的字段与真实网关契约一致，来源可追溯；
4. 不编造设备在线状态或校准数值（工具只透传接口返回，动作/参数白名单拒绝猜测）。
"""
import json
import os
import re

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from agent_service.application.tool_gateway import (
    INVALID_ARGUMENTS, PERMISSION_DENIED, RESOURCE_NOT_FOUND,
    SharedToolGateway, UPSTREAM_ERROR,
)
from agent_service.domain.enums import ToolRisk
from agent_service.domain.model.entities import ToolCallRequest
from agent_service.domain.ports.tool_gateway import ToolInvocationContext
from agent_service.infrastructure.tools.registry_bridge import (
    RestResult, RunCredentialRegistry, SharedToolRegistryBridge,
)
from shared.agent_tools import device_tools, intent_tools, mcp_registry
from tests.agent_eval.domains.device import fixtures

DEVICE_QUERY = 'device_query'


def _envelope(payload):
    return {'success': True, 'code': 0, 'message': 'Success', 'data': payload}


class FakeDeviceRest:
    """按目标工具名返回实测形状的响应，并记录回源参数。"""

    def __init__(self):
        self.calls = []

    def _payload(self, name, arguments):
        if name == 'device_list':
            page = arguments.get('page', 1)
            per_page = arguments.get('per_page', 10)
            items = [fixtures.DEVICE_ITEM]
            if arguments.get('status') not in (None, 'offline'):
                items = []
            return fixtures.enveloped(items, page=page, per_page=per_page)
        if name == 'device_get':
            if arguments.get('device_id') != 10:
                return None
            return _envelope(fixtures.DEVICE_DETAIL)
        if name == 'device_group_list':
            return fixtures.enveloped([fixtures.GROUP_ITEM],
                                      page=arguments.get('page', 1),
                                      per_page=arguments.get('per_page', 100))
        if name == 'device_group_get':
            return _envelope(fixtures.GROUP_ITEM)
        if name == 'device_status_list':
            return fixtures.enveloped([fixtures.STATUS_ITEM,
                                       fixtures.STATUS_ITEM_11])
        if name in ('device_status_history', 'device_get_status_history'):
            return fixtures.enveloped([fixtures.STATUS_EVENT],
                                      page=arguments.get('page', 1),
                                      per_page=arguments.get('per_page', 50))
        if name == 'device_alarm_list':
            payload = fixtures.enveloped([fixtures.ALARM_ITEM],
                                         page=arguments.get('page', 1),
                                         per_page=arguments.get('per_page', 50))
            payload['data']['stats'] = dict(fixtures.ALARM_STATS)
            return payload
        if name == 'device_alarm_rule_list':
            return fixtures.enveloped([fixtures.ALARM_RULE_ITEM])
        if name == 'device_serials':
            return _envelope([fixtures.SERIAL_ITEM])
        if name == 'device_driver_keywords':
            return _envelope([fixtures.DRIVER_KEYWORD_ITEM])
        if name == 'spl_mapping_list':
            return fixtures.enveloped([fixtures.SPL_MAPPING],
                                      page=arguments.get('page', 1),
                                      per_page=arguments.get('per_page', 10))
        if name == 'spl_mapping_get':
            if arguments.get('mapping_id') != 3:
                # 物理域缺失映射返回 400（不是 404），与真实网关一致
                return {'status': 400, 'payload': {
                    'success': False, 'code': 203,
                    'message': '未找到 SPL 映射记录'}}
            return _envelope(fixtures.SPL_MAPPING_DETAIL)
        if name == 'spl_mapping_stats':
            return _envelope(fixtures.SPL_STATS)
        if name == 'spl_mapping_by_device':
            return fixtures.single_page([fixtures.SPL_MAPPING])
        if name == 'spl_mapping_history':
            return fixtures.single_page([fixtures.SPL_HISTORY_ITEM])
        if name == 'spl_mapping_calibration_data':
            return _envelope({'points': fixtures.SPL_POINTS})
        if name == 'digital_spl_mapping_list':
            return fixtures.enveloped([fixtures.DIGITAL_SPL_MAPPING],
                                      page=arguments.get('page', 1),
                                      per_page=arguments.get('per_page', 10))
        if name == 'digital_spl_mapping_get':
            if arguments.get('mapping_id') != 5:
                return {'status': 404, 'payload': {
                    'success': False, 'code': 201, 'message': '未找到映射记录'}}
            return _envelope(fixtures.DIGITAL_SPL_MAPPING)
        if name == 'digital_spl_mapping_by_api':
            return fixtures.single_page([fixtures.DIGITAL_SPL_MAPPING])
        raise AssertionError(f'用例没有为 {name} 准备响应')

    def call(self, tool, arguments, **kwargs):
        self.calls.append({'tool': tool, 'arguments': dict(arguments), **kwargs})
        payload = self._payload(tool['name'], arguments)
        if isinstance(payload, dict) and 'status' in payload:
            return RestResult(status=payload['status'],
                              payload=payload['payload'],
                              text=json.dumps(payload['payload'],
                                              ensure_ascii=False))
        return RestResult(status=200, payload=payload,
                          text=json.dumps(payload, ensure_ascii=False))


def make_gateway(rest=None, credentials=None):
    return SharedToolGateway(
        bridge=SharedToolRegistryBridge(),
        rest=rest or FakeDeviceRest(),
        credentials=credentials or RunCredentialRegistry(),
    )


def ctx(permissions=('device:read', 'spl:read', 'digital_spl:read'),
        run_id='r1'):
    return ToolInvocationContext(
        run_id=run_id, session_id='s1', owner_id=7, tenant_id='t1',
        step_id='step1', permissions=tuple(permissions), idempotency_key='k')


def call(arguments):
    return ToolCallRequest(tool_call_id='call-1', name=DEVICE_QUERY,
                           arguments=arguments)


# ---------------------------------------------------------------- 注册口径

def test_device_query_is_enabled_readonly():
    tool = intent_tools.INTENT_TOOL_BY_NAME[DEVICE_QUERY]
    assert tool.enabled is True
    assert tool.risk == 'READ'
    assert tool.kind == 'intent_rest'
    assert tool.permissions == ('device:read', 'spl:read',
                                'digital_spl:read')
    assert DEVICE_QUERY in intent_tools.ENABLED_TOOLS
    assert tuple(tool.parameters['properties']['action']['enum']) == \
        device_tools.DEVICE_QUERY_ACTION_NAMES
    assert len(device_tools.DEVICE_QUERY_ACTION_NAMES) == 19


def test_every_action_has_permission_and_param_entries():
    for action in device_tools.DEVICE_QUERY_ACTION_NAMES:
        assert action in device_tools.DEVICE_QUERY_PARAMS, action
        assert device_tools.action_permissions(action), action
    assert set(device_tools.DEVICE_QUERY_PARAMS) == set(
        device_tools.DEVICE_QUERY_ACTION_NAMES)


def test_action_permissions_are_narrowed_by_domain():
    for action in device_tools.DEVICE_QUERY_ACTIONS:
        assert device_tools.action_permissions(action) == ('device:read',)
    for action in ('spl_mappings', 'spl_mapping', 'spl_stats',
                   'spl_by_device', 'spl_history', 'spl_calibration_data'):
        assert device_tools.action_permissions(action) == ('spl:read',), action
    for action in ('digital_spl_mappings', 'digital_spl_mapping',
                   'digital_spl_by_api'):
        assert device_tools.action_permissions(action) == \
            ('digital_spl:read',), action


def test_device_actions_map_to_existing_readonly_mcp_tools():
    for action, mcp_name in device_tools.DEVICE_QUERY_ACTIONS.items():
        mcp = mcp_registry.get_tool(mcp_name)
        assert mcp is not None, f'{action} -> {mcp_name} 不存在'
        assert mcp['method'] == 'GET', mcp_name
        assert mcp['permissions'] == ['device:read'], mcp_name
        assert mcp['path'].startswith('/api/v1/test-devices'), mcp_name


def test_spl_actions_are_agent_only_readonly_targets():
    """SPL 只读没有对外 MCP 工具：目标只经 device_query 暴露（§6.1 / §6.2）。"""
    for action, target in device_tools.DEVICE_SPL_TARGETS.items():
        assert target['method'] == 'GET', action
        assert target['path'].startswith('/api/v1/'), action
        assert target['permissions'] in (['spl:read'], ['digital_spl:read']), \
            action
        # 不进外部 MCP tools/list（INT-2461 后为 207 项），只能由 device_query 调用
        assert mcp_registry.get_tool(target['name']) is None, target['name']


def test_external_mcp_surface_is_unchanged():
    # INT-2453 谱的 205 项 + INT-2461 追加的 2 个首页只读工具（home_stats_details /
    # home_stats_summary），与 tests/unit/test_int2453_agent_tools.MCP_TOOL_COUNT 同口径
    assert len(mcp_registry.TOOLS) == 207
    mcp_names = {tool['name'] for tool in mcp_registry.TOOLS}
    for target in device_tools.DEVICE_SPL_TARGETS.values():
        assert target['name'] not in mcp_names
    assert 'spl_query' not in mcp_names
    assert 'digital_spl_query' not in mcp_names


def test_every_target_route_exists_in_gateway():
    """动作目标路径必须是网关真实注册的 GET 路由（防路径漂移）。"""
    import api_gateway.app as gateway_app

    registered = set()
    for path, operations in gateway_app.app.openapi()['paths'].items():
        if 'get' in operations:
            registered.add(re.sub(r'\{[^}]+\}', '{}', path))

    targets = [mcp_registry.get_tool(name)
               for name in device_tools.DEVICE_QUERY_ACTIONS.values()]
    # status_history 带 device_id 时改投的单设备端点
    targets.append(mcp_registry.get_tool('device_get_status_history'))
    targets += list(device_tools.DEVICE_SPL_TARGETS.values())
    for target in targets:
        normalized = re.sub(r'\{[^}]+\}', '{}', target['path'])
        assert normalized in registered, target['name']


def test_all_declared_params_exist_in_schema():
    properties = intent_tools.INTENT_TOOL_BY_NAME[
        DEVICE_QUERY].parameters['properties']
    declared = {'action'}
    for params in device_tools.DEVICE_QUERY_PARAMS.values():
        declared.update(params)
    for required in device_tools.DEVICE_QUERY_REQUIRED.values():
        declared.update(required)
    assert declared <= set(properties), sorted(declared - set(properties))


# ---------------------------------------------------------------- 10 条域任务

def test_domain_tasks_are_ten_distinct():
    assert len(fixtures.DOMAIN_TASKS) == 10
    assert len({task['name'] for task in fixtures.DOMAIN_TASKS}) == 10
    actions = [task['arguments']['action'] for task in fixtures.DOMAIN_TASKS]
    assert len(set(actions)) == 10


@pytest.mark.parametrize('task', fixtures.DOMAIN_TASKS,
                         ids=[t['name'] for t in fixtures.DOMAIN_TASKS])
def test_domain_task_runs_through_gateway(task):
    rest = FakeDeviceRest()
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


def test_device_list_fields_cover_gateway_schema():
    """样例字段覆盖网关 DeviceItem 全字段（逐字段一致）。"""
    from api_gateway.schemas.device import DeviceItem, DeviceStatusItem

    assert set(DeviceItem.model_fields) <= set(fixtures.DEVICE_ITEM)
    assert set(DeviceStatusItem.model_fields) <= set(fixtures.STATUS_ITEM)


def test_alarm_fields_cover_repository_projection():
    """告警字段覆盖 device_service 的告警投影（真实字段来源）。"""
    from device_service.infrastructure.persistence.device_monitor_repository import (
        _alarm_to_dict, _event_to_dict, _rule_to_dict,
    )

    def projection_keys(fn, po):
        return set(fn(po))

    class _Po:
        pass

    alarm_po = _Po()
    for key in fixtures.ALARM_ITEM:
        setattr(alarm_po, key, None)
    assert set(fixtures.ALARM_ITEM) == projection_keys(_alarm_to_dict, alarm_po)

    event_po = _Po()
    for key in fixtures.STATUS_EVENT:
        setattr(event_po, key, None)
    assert set(fixtures.STATUS_EVENT) == projection_keys(_event_to_dict,
                                                        event_po)

    rule_po = _Po()
    for key in fixtures.ALARM_RULE_ITEM:
        setattr(rule_po, key, None)
    assert set(fixtures.ALARM_RULE_ITEM) == projection_keys(_rule_to_dict,
                                                            rule_po)


# ---------------------------------------------------------------- 参数校验

def test_required_param_missing_rejected_before_rest():
    rest = FakeDeviceRest()
    result = make_gateway(rest).execute(call({'action': 'detail'}), ctx())
    assert result.error_code == INVALID_ARGUMENTS
    assert 'device_id' in result.content
    assert rest.calls == []


def test_invalid_action_rejected_before_rest():
    rest = FakeDeviceRest()
    result = make_gateway(rest).execute(call({'action': 'reboot'}), ctx())
    assert result.error_code == INVALID_ARGUMENTS
    assert rest.calls == []


def test_unsupported_param_for_action_rejected():
    """网关 extra=ignore：不支持参数会被静默忽略，工具层必须拒绝。"""
    rest = FakeDeviceRest()
    result = make_gateway(rest).execute(
        call({'action': 'serials', 'page': 1}), ctx())
    assert result.error_code == INVALID_ARGUMENTS
    assert 'page' in result.content
    assert rest.calls == []

    result = make_gateway(rest).execute(
        call({'action': 'detail', 'device_id': 10, 'keyword': 'x'}), ctx())
    assert result.error_code == INVALID_ARGUMENTS
    assert 'keyword' in result.content
    assert rest.calls == []


def test_ids_arrays_are_serialized_as_csv():
    tool, merged, error = intent_tools.resolve_rest_call(
        DEVICE_QUERY, {'action': 'status', 'ids': [10, 11]})
    assert error is None and tool['name'] == 'device_status_list'
    assert merged == {'ids': '10,11'}
    assert mcp_registry.build_path(tool, merged) == \
        '/api/v1/test-devices/status?ids=10%2C11'

    tool, merged, error = intent_tools.resolve_rest_call(
        DEVICE_QUERY, {'action': 'status_history', 'device_ids': [10, 11],
                       'event_type': 'health_check'})
    assert error is None and tool['name'] == 'device_status_history'
    assert merged == {'device_ids': '10,11', 'event_type': 'health_check'}


def test_empty_or_non_integer_ids_rejected():
    for ids in ([], ['10'], [10, True]):
        _, _, error = intent_tools.resolve_rest_call(
            DEVICE_QUERY, {'action': 'status', 'ids': ids})
        assert error and 'ids' in error, ids


def test_status_history_rejects_device_id_and_device_ids_together():
    _, _, error = intent_tools.resolve_rest_call(
        DEVICE_QUERY, {'action': 'status_history', 'device_id': 10,
                       'device_ids': [10, 11]})
    assert error and 'device_ids' in error


def test_alarm_status_must_be_alarm_enum():
    """传错告警状态服务端返回空列表，工具层提前拦截（不把空当成没有告警）。"""
    _, _, error = intent_tools.resolve_rest_call(
        DEVICE_QUERY, {'action': 'alarms', 'status': 'pending'})
    assert error and 'status' in error
    tool, _, error = intent_tools.resolve_rest_call(
        DEVICE_QUERY, {'action': 'alarms', 'status': 'acknowledged'})
    assert error is None and tool['name'] == 'device_alarm_list'


@pytest.mark.parametrize('page,per_page', [(0, 10), (1, 0), (-1, 10)])
def test_pagination_must_be_positive(page, per_page):
    _, _, error = intent_tools.resolve_rest_call(
        DEVICE_QUERY, {'action': 'list', 'page': page, 'per_page': per_page})
    assert error and ('page' in error or 'per_page' in error)


def test_enabled_boolean_is_serialized_lowercase():
    tool, merged, error = intent_tools.resolve_rest_call(
        DEVICE_QUERY, {'action': 'alarm_rules', 'enabled': False})
    assert error is None and tool['name'] == 'device_alarm_rule_list'
    assert merged == {'enabled': 'false'}
    assert mcp_registry.build_path(tool, merged) == \
        '/api/v1/test-devices/alarm-rules?enabled=false'


def test_status_history_without_device_id_uses_global_endpoint():
    tool, merged, error = intent_tools.resolve_rest_call(
        DEVICE_QUERY, {'action': 'status_history', 'event_type': 'online'})
    assert error is None and tool['name'] == 'device_status_history'
    assert mcp_registry.build_path(tool, merged) == \
        '/api/v1/test-devices/status-history?event_type=online'

    tool, merged, error = intent_tools.resolve_rest_call(
        DEVICE_QUERY, {'action': 'status_history', 'device_id': 10})
    assert error is None and tool['name'] == 'device_get_status_history'
    assert mcp_registry.build_path(tool, merged) == \
        '/api/v1/test-devices/10/status-history'


# ---------------------------------------------------------------- 权限收窄

def test_action_permissions_are_narrowed_at_tool_layer():
    rest = FakeDeviceRest()

    # 只有 device:read：设备动作可执行，SPL 动作在回源前被拒
    result = make_gateway(rest).execute(call({'action': 'list'}),
                                        ctx(permissions=('device:read',)))
    assert result.ok, result.content

    result = make_gateway(rest).execute(
        call({'action': 'spl_history', 'mapping_id': 3}),
        ctx(permissions=('device:read',)))
    assert result.error_code == PERMISSION_DENIED
    assert '无权访问' in result.content

    # 只有 spl:read：SPL 动作可执行，设备动作被拒
    result = make_gateway(rest).execute(
        call({'action': 'spl_history', 'mapping_id': 3}),
        ctx(permissions=('spl:read',)))
    assert result.ok, result.content

    result = make_gateway(rest).execute(call({'action': 'list'}),
                                        ctx(permissions=('spl:read',)))
    assert result.error_code == PERMISSION_DENIED

    # 数字域动作只认 digital_spl:read
    result = make_gateway(rest).execute(
        call({'action': 'digital_spl_mapping', 'mapping_id': 5}),
        ctx(permissions=('spl:read',)))
    assert result.error_code == PERMISSION_DENIED
    result = make_gateway(rest).execute(
        call({'action': 'digital_spl_mapping', 'mapping_id': 5}),
        ctx(permissions=('digital_spl:read',)))
    assert result.ok, result.content

    # 权限拒绝发生在回源前（只有两次成功的回源）
    assert len(rest.calls) == 3


def test_gateway_exposes_device_query_as_read():
    gateway = make_gateway()
    assert gateway.risk_of(DEVICE_QUERY) is ToolRisk.READ
    descriptor = gateway.describe([DEVICE_QUERY])[0]
    assert descriptor.enabled is True
    assert descriptor.permissions == ('device:read', 'spl:read',
                                      'digital_spl:read')


# ---------------------------------------------------------------- 资源缺失口径

def test_digital_spl_missing_is_plain_not_found():
    result = make_gateway().execute(
        call({'action': 'digital_spl_mapping', 'mapping_id': 999}),
        ctx(permissions=('digital_spl:read',)))
    assert not result.ok
    assert result.error_code == RESOURCE_NOT_FOUND
    assert '不存在或无权访问' in result.content


def test_physical_spl_missing_keeps_upstream_semantics():
    """物理域缺失映射返回 400（真实契约），工具层按 UPSTREAM_ERROR 透传。"""
    result = make_gateway().execute(
        call({'action': 'spl_mapping', 'mapping_id': 999}),
        ctx(permissions=('spl:read',)))
    assert not result.ok
    assert result.error_code == UPSTREAM_ERROR
    assert '400' in result.content


# ---------------------------------------------------------------- tool_search

@pytest.mark.parametrize('query', ['SPL 校准', 'SPL 映射', '测试音校准点',
                                   '数字 SPL 映射'])
def test_tool_search_surfaces_device_query_for_spl(query):
    """SPL 没有对外 MCP 工具：长尾检索必须回到 device_query，避免自造工具名。"""
    from shared.agent_tools.search import search
    names = [tool['name'] for tool in
             search(query, ['device:read', 'spl:read'])['tools']]
    assert DEVICE_QUERY in names, f'{query} -> {names}'


@pytest.mark.parametrize('query,expected', [
    ('设备告警', 'device_alarm_list'),
    ('设备序列号', 'device_serials'),
    ('驱动关键词', 'device_driver_keywords'),
])
def test_tool_search_surfaces_device_readonly_mcp_tools(query, expected):
    """设备只读本身就在对外 MCP 长尾里：检索到具体只读工具也是合法通道。"""
    from shared.agent_tools.search import search
    names = [tool['name'] for tool in
             search(query, ['device:read'])['tools']]
    assert expected in names, f'{query} -> {names}'
