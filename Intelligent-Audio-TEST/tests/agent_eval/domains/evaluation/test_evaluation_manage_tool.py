# -*- coding: utf-8 -*-
"""INT-2469 评估域写意图工具（evaluation_manage）。

验收锚点（卡面可测标准 1、3）：
1. 维度 / 分类 CRUD、可见性、重评估的动作都落到真实网关路由与真实权限码；
2. 写调用没有审批凭据一律不执行（提案 + 审批 + 幂等由 INT-2466 通用审批表兜底）；
3. 参数层拦下「网关会静默忽略」的 body 字段与非法取值，不把注定失败的提案
   送进审批。
"""
import json

import pytest

from agent_service.application.tool_gateway import (
    INVALID_ARGUMENTS, PERMISSION_DENIED, SharedToolGateway,
)
from agent_service.domain.enums import ToolRisk
from agent_service.domain.model.entities import ToolCallRequest
from agent_service.domain.ports.tool_gateway import (
    ToolApproval, ToolInvocationContext,
)
from agent_service.infrastructure.tools.registry_bridge import (
    RestResult, RunCredentialRegistry, SharedToolRegistryBridge,
)
from shared.agent_tools import evaluation_tools, intent_tools, mcp_registry

MANAGE = 'evaluation_manage'
WRITE_PERMISSIONS = ('evaluation:dim_manage', 'evaluation:category_manage',
                     'evaluation:execute', 'evaluation:share')


class FakeWriteRest:
    def __init__(self, status=200, payload=None):
        self.calls = []
        self._status = status
        self._payload = payload or {'success': True, 'code': 0,
                                    'message': 'Success',
                                    'data': {'id': 42}}

    def call(self, tool, arguments, **kwargs):
        self.calls.append({'tool': tool, 'arguments': dict(arguments), **kwargs})
        return RestResult(status=self._status, payload=self._payload,
                          text=json.dumps(self._payload, ensure_ascii=False))


def make_gateway(rest=None):
    return SharedToolGateway(
        bridge=SharedToolRegistryBridge(),
        rest=rest or FakeWriteRest(),
        credentials=RunCredentialRegistry())


def ctx(permissions=WRITE_PERMISSIONS, approval=None):
    return ToolInvocationContext(
        run_id='r1', session_id='s1', owner_id=7, tenant_id='t1',
        step_id='step1', permissions=tuple(permissions), idempotency_key='k',
        approval=approval)


def approved():
    return ToolApproval(approval_id='a1', risk=ToolRisk.WRITE, proposal={})


def call(action, **arguments):
    return ToolCallRequest(tool_call_id='call-1', name=MANAGE,
                           arguments={'action': action, **arguments})


# ---------------------------------------------------------------- 注册口径

def test_manage_is_enabled_write_tool():
    tool = intent_tools.INTENT_TOOL_BY_NAME[MANAGE]
    assert tool.enabled is True
    assert tool.risk == 'WRITE'
    assert tool.kind == 'intent_rest'
    assert set(tool.permissions) == set(WRITE_PERMISSIONS)
    assert MANAGE in intent_tools.ENABLED_TOOLS
    assert set(tool.parameters['properties']['action']['enum']) == \
        set(evaluation_tools.EVALUATION_MANAGE_ACTIONS)


def test_every_action_resolves_to_real_evaluation_endpoint():
    for action in evaluation_tools.EVALUATION_MANAGE_ACTIONS:
        arguments = {'action': action}
        if action.startswith('dimension_') and action != 'dimension_create':
            arguments['dim_id'] = 12
        if action.startswith('category_') and action != 'category_create':
            arguments['cat_id'] = 3
        if action == 'dimension_visibility':
            arguments['visibility'] = 'private'
        if action in ('dimension_create', 'dimension_update',
                      'category_create', 'category_update'):
            arguments['body'] = {'name': '接线测试_维度'}
        if action == 'reevaluate':
            arguments['body'] = {'task_id': 9001}
        tool, merged, error = intent_tools.resolve_rest_call(MANAGE, arguments)
        assert error is None, f'{action}: {error}'
        assert tool['path'].startswith('/api/v1/evaluation/')
        assert tool['method'] in ('POST', 'PUT', 'PATCH', 'DELETE')
        assert 'action' not in merged


def test_read_only_actions_are_not_in_manage():
    """写工具不重复暴露只读动作：读走 evaluation_query。"""
    actions = set(evaluation_tools.EVALUATION_MANAGE_ACTIONS)
    assert not actions & {'dimensions', 'dimension', 'categories'}


def test_existing_mcp_write_tools_are_reused_not_copied():
    """维度写 / 可见性 / 分类创建 / 重评估复用 MCP 注册表同一份定义。"""
    for action, name in evaluation_tools.EVALUATION_MANAGE_ACTIONS.items():
        if name in {'evaluation_category_update', 'evaluation_category_delete'}:
            continue
        assert mcp_registry.get_tool(name) is not None, action


def test_category_update_and_delete_do_not_expand_external_mcp_contract():
    """分类更新 / 删除是 Agent 专用写目标，不进外部 MCP tools/list。"""
    for name in ('evaluation_category_update', 'evaluation_category_delete'):
        assert mcp_registry.get_tool(name) is None
        assert evaluation_tools.get_tool(name) is not None


def test_action_permissions_are_scoped():
    expected = {
        'dimension_create': {'evaluation:dim_manage'},
        'dimension_update': {'evaluation:dim_manage'},
        'dimension_delete': {'evaluation:dim_manage'},
        'dimension_visibility': {'evaluation:share'},
        'category_create': {'evaluation:category_manage'},
        'category_update': {'evaluation:category_manage'},
        'category_delete': {'evaluation:category_manage'},
        'reevaluate': {'evaluation:execute'},
    }
    for action, permissions in expected.items():
        assert set(intent_tools.permissions_for(
            MANAGE, {'action': action})) == permissions


# ---------------------------------------------------------------- 参数校验

@pytest.mark.parametrize('arguments, term', [
    ({'action': 'dimension_update'}, 'dim_id'),
    ({'action': 'dimension_visibility', 'dim_id': 1}, 'visibility'),
    ({'action': 'category_delete'}, 'cat_id'),
    ({'action': 'dimension_create', 'body': {}}, 'name'),
    ({'action': 'dimension_create', 'body': {'nmae': '拼错字段'}}, 'nmae'),
    ({'action': 'category_create',
      'body': {'name': '接线测试_分类', 'visibility': 'public'}}, 'visibility'),
    ({'action': 'dimension_delete', 'dim_id': 1, 'body': {'name': 'x'}}, 'body'),
    ({'action': 'reevaluate', 'body': {}}, 'task_id'),
    ({'action': 'reevaluate', 'body': {'task_id': 0}}, 'task_id'),
    ({'action': 'reevaluate',
      'body': {'task_id': 1, 'mode': 'selected'}}, 'case_ids'),
    ({'action': 'reevaluate',
      'body': {'task_id': 1, 'reevaluate_type': 'everything'}},
     'reevaluate_type'),
    ({'action': 'dimension_visibility', 'dim_id': 1,
      'visibility': 'private', 'body': {}}, 'body'),
])
def test_invalid_arguments_rejected_before_any_rest_call(arguments, term):
    rest = FakeWriteRest()
    result = make_gateway(rest).execute(
        ToolCallRequest(tool_call_id='c', name=MANAGE, arguments=arguments),
        ctx(approval=approved()))
    assert result.error_code == INVALID_ARGUMENTS
    assert term in result.content
    assert rest.calls == []


def test_bridge_validate_catches_body_typos_at_proposal_time():
    """提案前置校验（审批前）也要挡住 body 字段拼错，别让人批一条注定失败的提案。"""
    bridge = SharedToolRegistryBridge()
    error = bridge.validate(MANAGE, {'action': 'dimension_create',
                                     'body': {'nmae': '拼错字段'}})
    assert error and 'nmae' in error


def test_unknown_top_level_parameter_rejected():
    error = evaluation_tools.validate_arguments(
        {'action': 'dimension_delete', 'dim_id': 1, 'force': True})
    assert error and 'force' in error


# ---------------------------------------------------------------- 审批门禁

def test_write_without_approval_never_reaches_rest():
    rest = FakeWriteRest()
    result = make_gateway(rest).execute(
        call('dimension_delete', dim_id=12), ctx())
    assert result.error_code == 'APPROVAL_REQUIRED'
    assert rest.calls == []


def test_approved_write_executes_once_with_narrowed_permission():
    rest = FakeWriteRest()
    gateway = make_gateway(rest)
    result = gateway.execute(
        call('category_delete', cat_id=3), ctx(approval=approved()))
    assert result.ok, result.content
    sent = rest.calls[0]
    assert sent['tool']['name'] == 'evaluation_category_delete'
    assert sent['tool']['method'] == 'DELETE'
    assert sent['tool']['path'] == '/api/v1/evaluation/categories/{cat_id}'
    assert sent['arguments'] == {'cat_id': 3}


def test_permission_narrowed_by_action_even_with_approval():
    rest = FakeWriteRest()
    # 执行（reevaluate）权限不能拿来做维度删除
    result = make_gateway(rest).execute(
        call('dimension_delete', dim_id=12),
        ctx(permissions=('evaluation:execute',), approval=approved()))
    assert result.error_code == PERMISSION_DENIED
    assert rest.calls == []


def test_dimension_visibility_request_shape():
    rest = FakeWriteRest()
    result = make_gateway(rest).execute(
        call('dimension_visibility', dim_id=12, visibility='private'),
        ctx(permissions=('evaluation:share',), approval=approved()))
    assert result.ok, result.content
    sent = rest.calls[0]
    assert sent['tool']['method'] == 'PATCH'
    assert sent['tool']['path'] == \
        '/api/v1/evaluation/dimensions/{dim_id}/visibility'
    assert sent['arguments'] == {'dim_id': 12, 'visibility': 'private'}


def test_reevaluate_sends_body_and_surfaces_duplicate_rejection():
    payload = {'success': False, 'code': 400,
               'message': '任务已在重新评估队列中'}
    rest = FakeWriteRest(status=400, payload=payload)
    result = make_gateway(rest).execute(
        call('reevaluate', body={'task_id': 9001, 'mode': 'all'}),
        ctx(permissions=('evaluation:execute',), approval=approved()))
    assert not result.ok
    assert result.error_code == 'UPSTREAM_ERROR'
    assert '任务已在重新评估队列中' in result.content
    assert rest.calls[0]['tool']['name'] == 'evaluation_task_reevaluate'
    assert rest.calls[0]['arguments'] == {
        'body': {'task_id': 9001, 'mode': 'all'}}


# ---------------------------------------------------------------- 审批预览

def test_proposal_diff_is_field_level():
    gateway = make_gateway()
    diff = gateway.proposal_diff(MANAGE, {
        'action': 'dimension_update', 'dim_id': 12,
        'body': {'weight': 8, 'status': True}})
    assert diff['kind'] == 'evaluation_config'
    assert diff['operation'] == 'dimension_update'
    assert diff['target_table'] == 'evaluation_dimension'
    assert diff['dim_id'] == 12
    assert diff['changes'] == {'weight': 8, 'status': True}
    assert diff['request'] == 'evaluation_dimension_update'


def test_proposal_diff_marks_soft_delete_and_reevaluate_scope():
    gateway = make_gateway()
    delete = gateway.proposal_diff(MANAGE, {'action': 'category_delete',
                                            'cat_id': 3})
    assert '软删' in delete['effect']
    reevaluate = gateway.proposal_diff(MANAGE, {
        'action': 'reevaluate',
        'body': {'task_id': 9, 'mode': 'selected', 'case_ids': ['a', 'b']}})
    assert reevaluate['scope'] == {
        'mode': 'selected', 'case_ids': ['a', 'b'], 'dimension_ids': []}
    assert '不重跑执行' in reevaluate['effect']


def test_gateway_exposes_manage_as_write():
    gateway = make_gateway()
    assert gateway.risk_of(MANAGE) is ToolRisk.WRITE
    descriptor = gateway.describe([MANAGE])[0]
    assert descriptor.enabled is True
    assert set(descriptor.permissions) == set(WRITE_PERMISSIONS)
