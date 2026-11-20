# -*- coding: utf-8 -*-
"""INT-2470：算法域写意图工具 ``algorithm_manage``（M2 提案 + 审批 + 幂等）。

覆盖（卡面可测验收标准 1–3）：

1. **注册与动作表**：工具已启用、工具级风险 WRITE；动作 → 网关真实路由逐条核对，
   动作级权限与 ``api_gateway/routes/algorithm_bp.py`` 的 ``require_permission``
   一致；删除动作在动作层升 ``DESTRUCTIVE``。
2. **参数校验**：动作级参数白名单 / 条件必填 / body 字段白名单 / 作用域互斥
   在提案前拦下，不生成注定 422 的提案。
3. **审批链**：写调用只生成提案、不访问 REST；批准后按动作解析的请求执行一次，
   重复结算 / 重复投递不产生第二次副作用；动作权限不足不生成提案。
4. **热重载**：可重复执行（两次都成功、不改业务数据）；失败如实返回
   ``UPSTREAM_ERROR``，不静默成功 —— 含 HTTP 200 但 ``data.reload_time`` 为空
   （缓存没重建）的语义失败路径。
"""
import json
import os
import re

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

import api_gateway.app as gateway_app
from agent_service.application.tool_gateway import SharedToolGateway
from agent_service.domain.enums import RunStatus, ToolCallStatus, ToolRisk
from agent_service.domain.model.entities import ToolCallRequest
from agent_service.infrastructure.tools.registry_bridge import (
    RestResult, RunCredentialRegistry, SharedToolRegistryBridge,
)
from shared.agent_tools import algorithm_tools, intent_tools, mcp_registry
from tests.agent_write.helpers import (
    FakeLlm, approvals_of, decide, make_container, pending_approval,
    start_run, text_turn, tool_turn,
)

ALGO_TYPE = '接线测试_int2470'
PARAM_ID = 2147483001
MAPPING_ID = 2147483002


# ---------------------------------------------------------------- 夹具

class FakeAlgorithmRest:
    """记录回源请求；状态码 / 载荷可调（用于热重载失败路径）。"""

    def __init__(self, status=200, payload=None):
        self.calls = []
        self._status = status
        self._payload = payload or {
            'success': True, 'code': 0, 'message': 'Success',
            'data': {'id': 42}}

    def call(self, tool, arguments, **kwargs):
        self.calls.append({'tool': tool, 'arguments': dict(arguments),
                           **kwargs})
        return RestResult(
            status=self._status, payload=self._payload,
            text=json.dumps(self._payload, ensure_ascii=False))


def _stack(tmp_path, llm, rest, name='agent_write.db'):
    gateway = SharedToolGateway(
        bridge=SharedToolRegistryBridge(), rest=rest,
        credentials=RunCredentialRegistry())
    container, _engine, _sf = make_container(tmp_path, llm, gateway=gateway,
                                             name=name)
    return container


def _scenario(tmp_path, rest, call, permissions=('*',),
              name='agent_write.db'):
    llm = FakeLlm([tool_turn([call]), text_turn('算法配置已处理')])
    container = _stack(tmp_path, llm, rest, name=name)
    run = start_run(container, permissions=permissions)
    return container, llm, run


def _resolution(arguments):
    return intent_tools.resolve_rest_call('algorithm_manage', arguments)


# ---------------------------------------------------------------- 注册表

def test_algorithm_manage_is_enabled_write_intent_rest():
    tool = intent_tools.INTENT_TOOL_BY_NAME['algorithm_manage']
    assert tool.enabled is True
    assert tool.risk == 'WRITE'
    assert tool.kind == 'intent_rest'
    assert tool.permissions == algorithm_tools.MANAGE_PERMISSIONS
    assert set(tool.permissions) == {
        'algorithm:definition_manage', 'algorithm:param_manage'}
    assert 'algorithm_manage' in intent_tools.ENABLED_TOOLS
    entry = intent_tools.TOOL_INDEX_BY_NAME['algorithm_manage']
    assert entry['enabled'] is True and entry['risk'] == 'WRITE'


def test_action_enum_matches_the_action_table():
    schema = intent_tools.INTENT_TOOL_BY_NAME['algorithm_manage'].parameters
    assert schema['required'] == ['action']
    assert schema['properties']['action']['enum'] == list(
        algorithm_tools.ACTION_NAMES)
    assert len(algorithm_tools.ACTION_NAMES) == 15


def test_write_resolver_and_risk_table_are_wired():
    assert intent_tools.WRITE_RESOLVERS['algorithm_manage'] is \
        algorithm_tools.resolve
    assert intent_tools.WRITE_ACTION_TABLES['algorithm_manage'] is \
        algorithm_tools.ACTIONS
    domain = intent_tools.DOMAIN_ACTION_MAPS['algorithm_manage']
    assert domain.actions == algorithm_tools.ACTION_NAMES


# ---------------------------------------------------------------- 动作 → 路由

def _valid_arguments():
    """每个动作一条合法入参（动作映射与路由核对用）。"""
    return {
        'definition_create': {'action': 'definition_create',
                              'body': {'type': ALGO_TYPE, 'name': '接线测试_算法'}},
        'definition_update': {'action': 'definition_update',
                              'algo_type': ALGO_TYPE, 'body': {'status': 'offline'}},
        'definition_save': {'action': 'definition_save',
                            'body': {'id': 7, 'name': '接线测试_算法',
                                     'algorithm_type': ALGO_TYPE,
                                     'expected_updated_at': '2026-11-14 00:00:00'}},
        'definition_delete': {'action': 'definition_delete',
                              'algo_type': ALGO_TYPE},
        'param_create': {'action': 'param_create',
                         'body': {'algorithm_type': ALGO_TYPE,
                                  'param_code': '接线测试_param',
                                  'param_type': 'text'}},
        'param_update': {'action': 'param_update', 'param_id': PARAM_ID,
                         'body': {'param_name': '接线测试_参数名'}},
        'param_delete': {'action': 'param_delete', 'param_id': PARAM_ID},
        'reference_param_create': {
            'action': 'reference_param_create',
            'body': {'algorithm_type': ALGO_TYPE, 'code': '接线测试_ref'}},
        'reference_param_update': {
            'action': 'reference_param_update', 'param_id': PARAM_ID,
            'body': {'name': '接线测试_参考名'}},
        'reference_param_delete': {
            'action': 'reference_param_delete', 'param_id': PARAM_ID},
        'mapping_create': {
            'action': 'mapping_create',
            'body': {'algorithm_type': ALGO_TYPE, 'source_type': 'device',
                     'source_param': 'src', 'target_param': 'dst'}},
        'mapping_update': {'action': 'mapping_update', 'mapping_id': MAPPING_ID,
                           'body': {'target_param': 'dst2'}},
        'mapping_delete': {'action': 'mapping_delete',
                           'mapping_id': MAPPING_ID},
        'import': {'action': 'import',
                   'body': {'algorithms': [{'type': ALGO_TYPE,
                                            'name': '接线测试_导入'}]}},
        'reload': {'action': 'reload'},
    }


def test_every_action_maps_to_a_real_gateway_write_route():
    paths = gateway_app.app.openapi()['paths']
    for action, arguments in _valid_arguments().items():
        tool, _merged, error = _resolution(arguments)
        assert error is None, (action, error)
        path = tool['path']
        assert path in paths, f'{action} 指向不存在的路由：{path}'
        method = tool['method'].lower()
        assert method in paths[path], f'{action} 方法不存在：{method} {path}'
        assert method != 'get', f'{action} 不是写动作'
        # 动作级权限以真实网关路由为准（MCP 条目的历史口径不照抄）
        assert intent_tools.permissions_for(
            'algorithm_manage', arguments) == \
            algorithm_tools.ACTIONS[action].permissions, action


def test_action_permissions_exist_in_the_gateway_route_table():
    """动作级权限码必须是 algorithm 路由真实 ``require_permission`` 的取值。"""
    from api_gateway.routes import algorithm_bp

    with open(algorithm_bp.__file__, encoding='utf-8') as handle:
        source = handle.read()
    route_codes = set(re.findall(
        r"require_permission\('([^']+)'\)", source))
    declared = {code for spec in algorithm_tools.ACTIONS.values()
                for code in spec.permissions}
    assert declared <= route_codes, declared - route_codes
    # 映射写动作按真实路由收窄到 param_manage（MCP 表的历史口径是
    # definition_manage，不能照抄）
    assert intent_tools.permissions_for(
        'algorithm_manage', {'action': 'mapping_create'}) == \
        ('algorithm:param_manage',)
    assert intent_tools.permissions_for(
        'algorithm_manage', {'action': 'reload'}) == \
        ('algorithm:definition_manage',)


def test_every_action_builds_the_expected_path_and_body():
    cases = {
        'definition_create': ('/api/v1/algorithm/definitions', 'POST'),
        'definition_update':
            (f'/api/v1/algorithm/definitions/{ALGO_TYPE}', 'PUT'),
        'definition_save': ('/api/v1/algorithm/definitions/save', 'PUT'),
        'definition_delete':
            (f'/api/v1/algorithm/definitions/{ALGO_TYPE}', 'DELETE'),
        'param_create': ('/api/v1/algorithm/params', 'POST'),
        'param_update': (f'/api/v1/algorithm/params/{PARAM_ID}', 'PUT'),
        'param_delete': (f'/api/v1/algorithm/params/{PARAM_ID}', 'DELETE'),
        'reference_param_create':
            ('/api/v1/algorithm/reference-params', 'POST'),
        'reference_param_update':
            (f'/api/v1/algorithm/reference-params/{PARAM_ID}', 'PUT'),
        'reference_param_delete':
            (f'/api/v1/algorithm/reference-params/{PARAM_ID}', 'DELETE'),
        'mapping_create': ('/api/v1/algorithm/mappings', 'POST'),
        'mapping_update': (f'/api/v1/algorithm/mappings/{MAPPING_ID}', 'PUT'),
        'mapping_delete':
            (f'/api/v1/algorithm/mappings/{MAPPING_ID}', 'DELETE'),
        'import': ('/api/v1/algorithm/import', 'POST'),
        'reload': ('/api/v1/algorithm/reload', 'POST'),
    }
    for action, arguments in _valid_arguments().items():
        tool, merged, error = _resolution(arguments)
        assert error is None, (action, error)
        path, method = cases[action]
        assert mcp_registry.build_path(tool, merged) == path, action
        assert tool['method'] == method, action
    # 参数创建显式回写判别键（缺省 device），不会被网关按 device 静默处理
    _tool, merged, _error = _resolution(_valid_arguments()['param_create'])
    assert mcp_registry.build_body(_tool, merged)['param_type_source'] == 'device'
    # 删除只带路径 ID，不带 body
    for action in ('definition_delete', 'param_delete',
                   'reference_param_delete', 'mapping_delete'):
        tool, merged, _error = _resolution(_valid_arguments()[action])
        assert mcp_registry.build_body(tool, merged) is None, action


# ---------------------------------------------------------------- 风险

def test_delete_actions_are_destructive_and_others_write():
    assert intent_tools.risk_of('algorithm_manage') == 'WRITE'
    for action in algorithm_tools.DELETE_ACTIONS:
        assert intent_tools.risk_for(
            'algorithm_manage', {'action': action}) == 'DESTRUCTIVE', action
    for action in algorithm_tools.ACTION_NAMES:
        if action in algorithm_tools.DELETE_ACTIONS:
            continue
        assert intent_tools.risk_for(
            'algorithm_manage', {'action': action}) == 'WRITE', action
    assert algorithm_tools.DELETE_ACTIONS == (
        'definition_delete', 'param_delete', 'reference_param_delete',
        'mapping_delete')


def test_risk_probe_covers_every_algorithm_write_action():
    rows = {(name, action): target for name, action, target
            in intent_tools.rest_action_targets()
            if name == 'algorithm_manage'}
    assert set(action for _name, action in rows) == set(
        algorithm_tools.ACTION_NAMES)
    for (name, action), target in rows.items():
        assert target is not None, f'{name}.{action} 目标缺失'
        assert target['method'] != 'GET', f'{name}.{action} 不是写目标'


# ---------------------------------------------------------------- 参数校验

@pytest.mark.parametrize('arguments,fragment', [
    # 动作不支持的顶层参数（网关会静默丢弃）
    ({'action': 'reload', 'body': {'x': 1}}, '不支持参数'),
    ({'action': 'definition_delete', 'algo_type': ALGO_TYPE,
      'param_id': 1}, '不支持参数'),
    # body 白名单
    ({'action': 'definition_create',
      'body': {'type': ALGO_TYPE, 'name': 'n', 'unknown': 1}}, '不支持字段'),
    ({'action': 'definition_update', 'algo_type': ALGO_TYPE,
      'body': {'type': 'other'}}, '不支持字段'),
    ({'action': 'defparam'}, 'action 取值必须是'),
    # 必填
    ({'action': 'definition_create', 'body': {'name': 'n'}}, 'type'),
    ({'action': 'definition_update', 'algo_type': ALGO_TYPE, 'body': {}},
     'body'),
    ({'action': 'definition_update', 'body': {'name': 'n'}}, 'algo_type'),
    # 乐观锁 / 算法类型（保存路径两分支都必填 algorithm_type）
    ({'action': 'definition_save',
      'body': {'id': 7, 'name': 'n'}}, 'expected_updated_at'),
    ({'action': 'definition_save',
      'body': {'id': 7, 'name': 'n',
               'expected_updated_at': '2026-11-14 00:00:00'}},
     'body.type 或 body.algorithm_type'),
    ({'action': 'definition_save',
      'body': {'name': 'n'}}, 'type 或 body.algorithm_type'),
    # 状态 / 方向取值
    ({'action': 'definition_create',
      'body': {'type': ALGO_TYPE, 'name': 'n', 'status': 'ACTIVE'}}, 'status'),
    ({'action': 'param_create',
      'body': {'algorithm_type': ALGO_TYPE, 'param_code': 'p',
               'param_type': 'text', 'direction': 'in'}}, 'direction'),
    # 参数作用域
    ({'action': 'param_create',
      'body': {'algorithm_type': ALGO_TYPE, 'param_code': 'p',
               'param_type': 'text', 'param_type_source': 'api'}}, 'api_id'),
    ({'action': 'param_create',
      'body': {'algorithm_type': ALGO_TYPE, 'param_code': 'p',
               'param_type': 'text', 'param_type_source': 'api',
               'api_id': 1, 'device_id': 9}}, 'device_id'),
    ({'action': 'param_create',
      'body': {'algorithm_type': ALGO_TYPE, 'param_code': 'p',
               'param_type': 'text', 'param_type_source': 'group'}},
     'param_type_source'),
    ({'action': 'param_update',
      'body': {'param_name': 'x'}}, 'param_id'),
    # 更新路径不生效的字段（options_* / 作用域 / 归属）
    ({'action': 'param_update', 'param_id': PARAM_ID,
      'body': {'options_source': 'x'}}, '不支持字段'),
    ({'action': 'param_update', 'param_id': PARAM_ID,
      'body': {'device_id': 9}}, '不支持字段'),
    ({'action': 'reference_param_update', 'param_id': PARAM_ID,
      'body': {'algorithm_type': ALGO_TYPE}}, '不支持字段'),
    ({'action': 'reference_param_create', 'body': {'code': 'c'}},
     'algorithm_type'),
    # 映射
    ({'action': 'mapping_create',
      'body': {'algorithm_type': ALGO_TYPE, 'source_type': 'evaluation',
               'source_param': 's', 'target_param': 't'}}, 'source_type'),
    ({'action': 'mapping_create',
      'body': {'algorithm_type': ALGO_TYPE, 'source_type': 'api',
               'source_param': 's', 'target_param': 't'}}, 'api_id'),
    ({'action': 'mapping_update', 'mapping_id': MAPPING_ID,
      'body': {'source_type': 'bogus'}}, 'source_type'),
    # 导入
    ({'action': 'import', 'body': {'algorithms': []}}, '非空数组'),
    ({'action': 'import', 'body': {'algorithms': [{'name': 'n'}]}}, 'type'),
    ({'action': 'import', 'body': {'algorithms': [{'type': 't'}],
                                   'extra': 1}}, '不支持字段'),
])
def test_invalid_arguments_are_rejected_before_proposal(arguments, fragment):
    _tool, _merged, error = _resolution(arguments)
    assert error is not None
    assert fragment in error, error


def test_explicit_none_body_fields_count_as_absent():
    """显式 ``None`` = 不设置（与下游 None 跳过同口径），不按未知字段拒绝。"""
    tool, merged, error = _resolution({
        'action': 'param_create',
        'body': {'algorithm_type': ALGO_TYPE, 'param_code': 'p',
                 'param_type': 'text', 'api_id': None, 'field_path': None}})
    assert error is None
    assert merged['body']['param_type_source'] == 'device'
    # 非 None 的越界字段仍然拒绝
    _tool, _merged, error = _resolution({
        'action': 'param_create',
        'body': {'algorithm_type': ALGO_TYPE, 'param_code': 'p',
                 'param_type': 'text', 'api_id': 1}})
    assert error and 'api_id' in error


def test_delete_ids_must_be_positive_integers():
    for action, field in (('param_delete', 'param_id'),
                          ('reference_param_delete', 'param_id'),
                          ('mapping_delete', 'mapping_id')):
        for bad in (0, -3, '7', True):
            _tool, _merged, error = _resolution(
                {'action': action, field: bad})
            assert error and field in error, (action, bad)


def test_bridge_validation_blocks_invalid_proposals():
    bridge = SharedToolRegistryBridge()
    assert bridge.validate('algorithm_manage',
                           {'action': 'param_delete'}) is not None
    assert bridge.validate(
        'algorithm_manage', {'action': 'param_delete',
                             'param_id': PARAM_ID}) is None
    assert bridge.validate(
        'algorithm_manage', {'action': 'reload', 'body': {}}) is not None


# ---------------------------------------------------------------- 审批预览

def test_proposal_diff_describes_the_change_and_effect():
    diff = algorithm_tools.proposal_diff({
        'action': 'definition_save',
        'body': {'id': 7, 'name': '接线测试_算法',
                 'expected_updated_at': '2026-11-14 00:00:00',
                 'device_params': [{}, {}], 'mappings': {'device': [{}]}}})
    assert diff['kind'] == 'algorithm_config'
    assert diff['operation'] == 'definition_save'
    assert diff['target_table'].startswith('algorithm_definitions')
    assert diff['changes']['name'] == '接线测试_算法'
    assert 'device_params' not in diff['changes']
    assert diff['sub_entities']['device_params'] == {'count': 2}
    assert diff['sub_entities']['mappings'] == {'groups': ['device'],
                                               'count': 1}
    assert '聚合保存' in diff['effect']

    delete = algorithm_tools.proposal_diff(
        {'action': 'param_delete', 'param_id': PARAM_ID})
    assert delete['param_id'] == PARAM_ID
    assert '软删除' in delete['effect']
    assert delete['irreversible_by_tool'] is True

    reload_diff = algorithm_tools.proposal_diff({'action': 'reload'})
    assert '可重复执行' in reload_diff['effect']
    assert 'irreversible_by_tool' not in reload_diff


# ---------------------------------------------------------------- 审批链

def test_param_create_proposes_without_side_effect(tmp_path):
    rest = FakeAlgorithmRest()
    call = ToolCallRequest(
        tool_call_id='c1', name='algorithm_manage',
        arguments={'action': 'param_create',
                   'body': {'algorithm_type': ALGO_TYPE,
                            'param_code': '接线测试_param',
                            'param_type': 'text'}})
    container, _llm, run = _scenario(tmp_path, rest, call)

    assert rest.calls == []
    approval = pending_approval(container, run.id)
    assert approval.proposal['tool'] == 'algorithm_manage'
    assert approval.proposal['risk'] == 'WRITE'
    assert approval.diff['kind'] == 'algorithm_config'
    assert approval.diff['operation'] == 'param_create'
    assert approval.diff['scope'] == 'device'
    assert container.repositories['runs'].get(run.id).status is \
        RunStatus.WAITING_APPROVAL
    record = container.repositories['tool_calls'].find(run.id, 'c1')
    assert record.status is ToolCallStatus.WAITING_APPROVAL

    # 重复投递（仍在等待审批）：只保留一张单，不执行
    container.orchestrator.execute(run.id)
    assert len(approvals_of(container, run.id)) == 1
    assert rest.calls == []


def test_approved_write_executes_once_and_resumes(tmp_path):
    rest = FakeAlgorithmRest()
    call = ToolCallRequest(
        tool_call_id='c1', name='algorithm_manage',
        arguments={'action': 'param_update', 'param_id': PARAM_ID,
                   'body': {'param_name': '接线测试_参数名'}})
    container, llm, run = _scenario(tmp_path, rest, call)
    approval = pending_approval(container, run.id)

    decide(container, approval.id, 'APPROVE', permissions=['*'])
    container.executor.submit(run.id)

    assert len(rest.calls) == 1
    sent = rest.calls[0]
    assert sent['tool']['name'] == 'algorithm_param_update'
    assert sent['tool']['method'] == 'PUT'
    assert sent['arguments'] == {'param_id': PARAM_ID,
                                 'body': {'param_name': '接线测试_参数名'}}
    assert sent['permissions'] == ('*',)
    assert container.repositories['runs'].get(run.id).status is \
        RunStatus.SUCCEEDED
    record = container.repositories['tool_calls'].find(run.id, 'c1')
    assert record.status is ToolCallStatus.COMPLETED
    assert record.result_code == 'OK'
    assert len(llm.requests) == 2

    # 幂等：重复结算 / 重复投递不再产生第二次副作用
    container.orchestrator.execute(run.id)
    container.orchestrator.execute(run.id)
    assert len(rest.calls) == 1


def test_destructive_delete_is_recorded_and_uses_delete_route(tmp_path):
    """删除动作按 DESTRUCTIVE 提案（审计与审批单如实记录），走软删路由。

    二次确认门禁按**工具级**风险判定（``ApprovalService`` 用 ``risk_of``），
    ``algorithm_manage`` 工具级是 WRITE，因此删除动作不额外要求 ``confirm``
    —— 与 ``testcase_write.delete``（INT-2468）同口径；动作级 DESTRUCTIVE
    体现在审批单 ``risk`` 与预览的 ``irreversible_by_tool``。
    """
    rest = FakeAlgorithmRest()
    call = ToolCallRequest(
        tool_call_id='c1', name='algorithm_manage',
        arguments={'action': 'definition_delete', 'algo_type': ALGO_TYPE})
    container, _llm, run = _scenario(tmp_path, rest, call)
    approval = pending_approval(container, run.id)
    assert approval.proposal['risk'] == 'DESTRUCTIVE'
    assert approval.diff['irreversible_by_tool'] is True
    assert '软删除' in approval.diff['effect']

    decide(container, approval.id, 'APPROVE', permissions=['*'])
    container.executor.submit(run.id)
    assert len(rest.calls) == 1
    assert rest.calls[0]['tool']['name'] == 'algorithm_definition_delete'
    assert rest.calls[0]['tool']['method'] == 'DELETE'


def test_rejected_proposal_never_executes(tmp_path):
    rest = FakeAlgorithmRest()
    call = ToolCallRequest(
        tool_call_id='c1', name='algorithm_manage',
        arguments={'action': 'reference_param_delete', 'param_id': PARAM_ID})
    container, _llm, run = _scenario(tmp_path, rest, call)
    approval = pending_approval(container, run.id)

    decide(container, approval.id, 'REJECT', permissions=['*'])
    container.executor.submit(run.id)

    assert rest.calls == []
    record = container.repositories['tool_calls'].find(run.id, 'c1')
    assert record.status is ToolCallStatus.DENIED
    assert record.result_code == 'APPROVAL_REJECTED'


def test_permission_revoked_between_proposal_and_execution(tmp_path):
    rest = FakeAlgorithmRest()
    call = ToolCallRequest(
        tool_call_id='c1', name='algorithm_manage',
        arguments={'action': 'mapping_delete', 'mapping_id': MAPPING_ID})
    container, _llm, run = _scenario(tmp_path, rest, call)
    approval = pending_approval(container, run.id)

    # 审批时只剩只读权限：algorithm:param_manage 已收回
    decide(container, approval.id, 'APPROVE', permissions=['algorithm:read'],
           confirm=True)
    container.executor.submit(run.id)

    assert rest.calls == []
    record = container.repositories['tool_calls'].find(run.id, 'c1')
    assert record.result_code == 'PERMISSION_DENIED'


# ---------------------------------------------------------------- 热重载

def test_reload_is_repeatable_and_reports_success(tmp_path):
    rest = FakeAlgorithmRest(payload={
        'success': True, 'code': 0, 'message': 'Config reloaded',
        'data': {'success': True, 'message': 'Config reloaded: True',
                 'reload_time': '2026-11-14T00:00:00'}})
    # 两次独立提案 → 两次执行都成功，证明热重载可重复执行
    for index in range(2):
        call = ToolCallRequest(
            tool_call_id=f'c{index}', name='algorithm_manage',
            arguments={'action': 'reload'})
        container, _llm, run = _scenario(
            tmp_path, rest, call, name=f'reload{index}.db')
        approval = pending_approval(container, run.id)
        decide(container, approval.id, 'APPROVE', permissions=['*'])
        container.executor.submit(run.id)
        record = container.repositories['tool_calls'].find(run.id, f'c{index}')
        assert record.status is ToolCallStatus.COMPLETED
        assert record.result_code == 'OK'
    assert len(rest.calls) == 2
    for sent in rest.calls:
        assert sent['tool']['name'] == 'algorithm_reload'
        assert sent['tool']['method'] == 'POST'
        assert sent['arguments'] == {}


def test_reload_failure_is_not_reported_as_success(tmp_path):
    rest = FakeAlgorithmRest(
        status=500,
        payload={'success': False, 'code': 500,
                 'message': '重载失败: cache rebuild failed', 'data': None})
    call = ToolCallRequest(
        tool_call_id='c1', name='algorithm_manage',
        arguments={'action': 'reload'})
    container, _llm, run = _scenario(tmp_path, rest, call)
    approval = pending_approval(container, run.id)

    decide(container, approval.id, 'APPROVE', permissions=['*'])
    container.executor.submit(run.id)

    assert len(rest.calls) == 1
    record = container.repositories['tool_calls'].find(run.id, 'c1')
    assert record.status is ToolCallStatus.FAILED
    assert record.result_code == 'UPSTREAM_ERROR'
    assert '重载失败' in (record.result or {}).get('content', '')
    # 上游拒绝是业务结论：模型继续答复后 run 正常结束，不静默成功
    assert container.repositories['runs'].get(run.id).status is \
        RunStatus.SUCCEEDED


def test_reload_success_payload_passes_the_semantic_check():
    assert algorithm_tools.validate_result('reload', {
        'success': True, 'code': 0, 'message': 'Config reloaded',
        'data': {'success': True, 'message': 'Config reloaded: True',
                 'reload_time': '2026-11-14T00:00:00'}}) is None
    # 非 reload 动作不做载荷断言（结果由接口自身语义表达）
    assert algorithm_tools.validate_result('param_update', {'anything': 1}) is None


@pytest.mark.parametrize('action,payload,fragment', [
    # 真实可达路径（打回项 P2）：task_service.reload_config 在 gRPC 重载失败时
    # 仍返回 200 + success=True + reload_time=None，只看 HTTP 状态会报成功。
    ('reload', {'success': True, 'code': 0, 'message': 'Config reloaded',
                'data': {'success': True, 'message': 'Config reloaded: False',
                         'reload_time': None}}, 'reload_time 为空'),
    # 服务层若改为如实传播失败：内层 success=false
    ('reload', {'success': True, 'code': 0, 'message': 'Config reloaded',
                'data': {'success': False, 'message': 'Config reloaded: False',
                         'reload_time': None}}, '热重载未成功'),
    # 信封缺 data（网关异常形态）
    ('reload', {'success': True, 'code': 0, 'message': 'ok'}, '缺少 data'),
    ('reload', ['not', 'an', 'object'], '非 JSON 对象'),
])
def test_reload_semantic_failure_is_reported_as_upstream_error(
        tmp_path, action, payload, fragment):
    rest = FakeAlgorithmRest(status=200, payload=payload)
    call = ToolCallRequest(
        tool_call_id='c1', name='algorithm_manage',
        arguments={'action': action})
    container, _llm, run = _scenario(tmp_path, rest, call)
    approval = pending_approval(container, run.id)
    assert approval.proposal['risk'] == 'WRITE'

    decide(container, approval.id, 'APPROVE', permissions=['*'])
    container.executor.submit(run.id)

    assert len(rest.calls) == 1
    record = container.repositories['tool_calls'].find(run.id, 'c1')
    assert record.status is ToolCallStatus.FAILED
    assert record.result_code == 'UPSTREAM_ERROR'
    assert fragment in (record.result or {}).get('content', '')
    # 失败是业务结论：模型继续答复后 run 正常结束，不静默成功
    assert container.repositories['runs'].get(run.id).status is \
        RunStatus.SUCCEEDED


def test_upstream_business_failure_is_returned_to_the_model(tmp_path):
    """写操作被上游业务拒绝（如重名 / 未找到）原样回灌，不当作成功。"""
    rest = FakeAlgorithmRest(
        status=400,
        payload={'success': False, 'code': 400,
                 'message': "Algorithm '接线测试_int2470' already exists",
                 'data': None})
    call = ToolCallRequest(
        tool_call_id='c1', name='algorithm_manage',
        arguments={'action': 'definition_create',
                   'body': {'type': ALGO_TYPE, 'name': '接线测试_算法'}})
    container, _llm, run = _scenario(tmp_path, rest, call)
    approval = pending_approval(container, run.id)

    decide(container, approval.id, 'APPROVE', permissions=['*'])
    container.executor.submit(run.id)

    record = container.repositories['tool_calls'].find(run.id, 'c1')
    assert record.status is ToolCallStatus.FAILED
    assert record.result_code == 'UPSTREAM_ERROR'
    assert 'already exists' in (record.result or {}).get('content', '')
