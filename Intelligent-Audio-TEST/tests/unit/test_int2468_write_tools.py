# -*- coding: utf-8 -*-
"""INT-2468：用例 / 标签 / 任务写意图工具（M2 提案 + 审批 + 幂等）。

覆盖：

1. 三个写工具已启用、工具级风险 = WRITE，动作表与真实网关路由一一对应；
2. 动作级权限 / 风险：删除与 ``rename_tag`` 是 DESTRUCTIVE，其余 WRITE；
3. 动作级参数白名单（传了不生效的参数直接拒绝，不静默忽略）、条件必填、
   body 注入（``reextract`` / 批量打标 / 批量接口载荷）；
4. 审批链路：写调用只生成提案、不访问 REST；批准后按动作解析的请求执行一次，
   重复提交不产生第二次副作用；动作权限不足时连提案都不生成。
"""
import json
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

import api_gateway.app as gateway_app
from agent_service.application.run_worker import InlineRunExecutor
from agent_service.application.tool_gateway import SharedToolGateway
from agent_service.domain.enums import RunStatus, ToolCallStatus, ToolRisk
from agent_service.domain.model.entities import ToolCallRequest
from agent_service.infrastructure.tools.registry_bridge import (
    RestResult, RunCredentialRegistry, SharedToolRegistryBridge,
)
from shared.agent_tools import (
    intent_tools, mcp_registry, tag_group_tools, task_write_tools,
    testcase_write_tools,
)
from tests.agent_write.helpers import (
    FakeLlm, decide, pending_approval, start_run, text_turn, tool_turn,
)
from tests.unit.int2451_agent_fakes import build_stack

CASE_ID = 'f50b2c8c-c0e7-4ed7-b582-d065da135269'
GROUP_ID = 'efdce97d-f8a5-497d-85f6-8e74ef877ebd'

WRITE_TOOLS = ('testcase_write', 'tag_group_manage', 'task_run')


# ---------------------------------------------------------------- 注册表

@pytest.mark.parametrize('name', WRITE_TOOLS)
def test_write_tools_enabled_and_declared_write(name):
    tool = intent_tools.INTENT_TOOL_BY_NAME[name]
    assert tool.enabled is True
    assert tool.risk == 'WRITE'
    assert tool.kind == 'intent_rest'
    assert name in intent_tools.ENABLED_TOOLS
    # 写工具都在 tool_search 索引里（模型可发现），且标记为已启用
    entry = intent_tools.TOOL_INDEX_BY_NAME[name]
    assert entry['enabled'] is True and entry['risk'] == 'WRITE'


def _resolved_calls():
    """枚举全部动作的解析结果（用于逐条核对目标路由）。"""
    calls = {}

    def add(label, name, arguments):
        tool, merged, error = intent_tools.resolve_rest_call(name, arguments)
        assert error is None, f'{label} 解析失败：{error}'
        calls[label] = (tool, merged)

    add('testcase.create', 'testcase_write',
        {'action': 'create', 'body': {'name': '接线测试_用例',
                                      'group_id': GROUP_ID}})
    add('testcase.update', 'testcase_write',
        {'action': 'update', 'tc_id': CASE_ID, 'body': {'name': '新名'}})
    add('testcase.copy', 'testcase_write',
        {'action': 'copy', 'tc_id': CASE_ID})
    add('testcase.delete', 'testcase_write',
        {'action': 'delete', 'tc_id': CASE_ID})
    add('testcase.tag', 'testcase_write',
        {'action': 'tag', 'tc_id': CASE_ID, 'tag_mode': 'add',
         'tags': ['接线测试_标签']})
    for kind, id_field, id_value in (('tag', 'tag_id', 7),
                                     ('group', 'group_id', GROUP_ID)):
        add(f'{kind}.create', 'tag_group_manage',
            {'action': 'create', 'target_kind': kind,
             'body': {'name': f'接线测试_{kind}'}})
        add(f'{kind}.update', 'tag_group_manage',
            {'action': 'update', 'target_kind': kind, id_field: id_value,
             'body': {'name': f'接线测试_{kind}_改'}})
        add(f'{kind}.delete', 'tag_group_manage',
            {'action': 'delete', 'target_kind': kind, id_field: id_value})
    add('batch_tag.add', 'tag_group_manage',
        {'action': 'batch_tag', 'batch_action': 'add_tags',
         'ids': [CASE_ID], 'tags': ['接线测试_标签']})
    add('batch_tag.rename', 'tag_group_manage',
        {'action': 'batch_tag', 'batch_action': 'rename_tag',
         'old_tag_name': '旧标签', 'new_tag_name': '新标签'})
    add('task.create', 'task_run',
        {'action': 'create', 'body': {'name': '接线测试_任务'}})
    for action in ('start', 'stop', 'retry', 'reextract'):
        add(f'task.{action}', 'task_run', {'action': action, 'task_id': 128})
    add('task.merge', 'task_run',
        {'action': 'merge', 'body': {'task_ids': [128, 129]}})
    return calls


def test_every_action_maps_to_a_real_gateway_route():
    """动作解析出来的 method + path 必须在网关真实注册（不编接口）。"""
    paths = gateway_app.app.openapi()['paths']
    for label, (tool, _merged) in _resolved_calls().items():
        path = tool['path']
        assert path in paths, f'{label} 指向不存在的路由：{path}'
        method = tool['method'].lower()
        assert method in paths[path], f'{label} 方法不存在：{method} {path}'


def test_resolved_requests_build_real_rest_payloads():
    """解析结果经共享构造器拼出的 path / body 与实测端口径一致。"""
    calls = _resolved_calls()
    expected_paths = {
        'testcase.create': '/api/v1/testcases',
        'testcase.update': f'/api/v1/testcases/{CASE_ID}',
        'testcase.copy': f'/api/v1/testcases/{CASE_ID}/copy',
        'testcase.delete': f'/api/v1/testcases/{CASE_ID}',
        'testcase.tag': '/api/v1/testcases/batch',
        'tag.create': '/api/v1/tags',
        'tag.update': '/api/v1/tags/7',
        'tag.delete': '/api/v1/tags/7',
        'group.create': '/api/v1/groups',
        'group.update': f'/api/v1/groups/{GROUP_ID}',
        'group.delete': f'/api/v1/groups/{GROUP_ID}',
        'batch_tag.add': '/api/v1/testcases/batch',
        'batch_tag.rename': '/api/v1/testcases/batch',
        'task.create': '/api/v1/tasks',
        'task.start': '/api/v1/tasks/128/start',
        'task.stop': '/api/v1/tasks/128/stop',
        'task.retry': '/api/v1/tasks/128/retry',
        'task.merge': '/api/v1/tasks/merge',
        'task.reextract': '/api/v1/tasks/128/reextract',
    }
    for label, (tool, merged) in calls.items():
        assert mcp_registry.build_path(tool, merged) == expected_paths[label], label

    def body_of(label):
        tool, merged = calls[label]
        return mcp_registry.build_body(tool, merged)

    assert body_of('testcase.create') == {'name': '接线测试_用例',
                                          'group_id': GROUP_ID}
    assert body_of('testcase.update') == {'name': '新名'}
    assert body_of('testcase.tag') == {'action': 'add_tags', 'ids': [CASE_ID],
                                       'tags': ['接线测试_标签']}
    assert body_of('tag.create') == {'name': '接线测试_tag'}
    assert body_of('group.create') == {'name': '接线测试_group'}
    assert body_of('batch_tag.rename') == {'action': 'rename_tag', 'ids': [],
                                           'old_tag_name': '旧标签',
                                           'new_tag_name': '新标签'}
    assert body_of('task.create') == {'name': '接线测试_任务'}
    assert body_of('task.merge') == {'task_ids': [128, 129]}
    assert body_of('task.reextract') == {'task_id': 128,
                                         'execution_status': 'completed'}
    for label in ('testcase.copy', 'testcase.delete', 'task.start',
                  'task.stop'):
        assert body_of(label) is None, label


# ---------------------------------------------------------------- 权限 / 风险

def test_delete_actions_are_destructive_and_others_write():
    assert intent_tools.risk_for(
        'testcase_write', {'action': 'delete', 'tc_id': CASE_ID}) == \
        'DESTRUCTIVE'
    assert intent_tools.risk_for(
        'testcase_write', {'action': 'create', 'body': {'name': 'x'}}) == 'WRITE'
    for kind, id_field, id_value in (('tag', 'tag_id', 7),
                                     ('group', 'group_id', GROUP_ID)):
        assert intent_tools.risk_for(
            'tag_group_manage', {'action': 'delete', 'target_kind': kind,
                                 id_field: id_value}) == 'DESTRUCTIVE'
    assert intent_tools.risk_for(
        'tag_group_manage', {'action': 'batch_tag',
                             'batch_action': 'rename_tag'}) == 'DESTRUCTIVE'
    assert intent_tools.risk_for(
        'tag_group_manage', {'action': 'batch_tag',
                             'batch_action': 'add_tags'}) == 'WRITE'
    for action in task_write_tools.ACTION_NAMES:
        assert intent_tools.risk_for('task_run', {'action': action}) == 'WRITE'
    # 工具级声明仍是方案 §6.1 的 WRITE（动作级升档不影响表口径）
    assert intent_tools.risk_of('testcase_write') == 'WRITE'


def test_action_permissions_follow_gateway_require_permission():
    cases = [
        ('testcase_write', {'action': 'create'}, ('testcase:create',)),
        ('testcase_write', {'action': 'copy'}, ('testcase:copy',)),
        ('testcase_write', {'action': 'delete'}, ('testcase:delete',)),
        ('testcase_write', {'action': 'tag'}, ('testcase:update',)),
        ('tag_group_manage',
         {'action': 'delete', 'target_kind': 'tag'}, ('tag:delete',)),
        ('tag_group_manage',
         {'action': 'update', 'target_kind': 'group'}, ('group:update',)),
        ('tag_group_manage',
         {'action': 'batch_tag', 'batch_action': 'add_tags'},
         ('testcase:update',)),
        ('tag_group_manage',
         {'action': 'batch_tag', 'batch_action': 'rename_tag'},
         ('testcase:delete',)),
        ('task_run', {'action': 'start'}, ('task:execute',)),
        ('task_run', {'action': 'merge'}, ('task:merge',)),
        ('task_run', {'action': 'reextract'}, ('task:reextract',)),
    ]
    for name, arguments, expected in cases:
        assert intent_tools.permissions_for(name, arguments) == expected, name


# ---------------------------------------------------------------- 参数解析

def test_tag_action_builds_single_id_batch_payload():
    tool, merged, error = intent_tools.resolve_rest_call(
        'testcase_write', {'action': 'tag', 'tc_id': CASE_ID,
                           'tag_mode': 'remove', 'tags': ['a', 'b']})
    assert error is None
    assert tool['name'] == 'testcase_batch'
    assert tool['method'] == 'POST'
    assert tool['path'] == '/api/v1/testcases/batch'
    assert merged == {'body': {'action': 'remove_tags', 'ids': [CASE_ID],
                               'tags': ['a', 'b']}}


def test_reextract_injects_body_task_id():
    tool, merged, error = intent_tools.resolve_rest_call(
        'task_run', {'action': 'reextract', 'task_id': 128})
    assert error is None
    assert tool['path'] == '/api/v1/tasks/{task_id}/reextract'
    assert merged['task_id'] == 128
    assert merged['body'] == {'task_id': 128,
                              'execution_status': 'completed'}
    # 网关要求 body 里的 task_id，不能被 build_body 漏掉
    body = mcp_registry.build_body(tool, merged)
    assert body['task_id'] == 128


def test_group_delete_passes_cascade_query_param():
    tool, merged, error = intent_tools.resolve_rest_call(
        'tag_group_manage', {'action': 'delete', 'target_kind': 'group',
                             'group_id': GROUP_ID, 'cascade': True})
    assert error is None
    path = mcp_registry.build_path(tool, merged)
    assert path == f'/api/v1/groups/{GROUP_ID}?cascade=True'


def test_rename_tag_sends_empty_ids_as_gateway_requires():
    """实测：批量接口的 ids 是必填字段，rename_tag 必须显式带空数组。"""
    tool, merged, error = intent_tools.resolve_rest_call(
        'tag_group_manage', {'action': 'batch_tag',
                             'batch_action': 'rename_tag',
                             'old_tag_name': '旧标签',
                             'new_tag_name': '新标签'})
    assert error is None
    assert tool['path'] == '/api/v1/testcases/batch'
    assert merged['body'] == {'action': 'rename_tag', 'ids': [],
                              'old_tag_name': '旧标签',
                              'new_tag_name': '新标签'}
    # 显式给空数组也接受；给非空 ids（按用例筛选语义）直接拒绝
    assert intent_tools.resolve_rest_call(
        'tag_group_manage', {'action': 'batch_tag',
                             'batch_action': 'rename_tag', 'ids': [],
                             'old_tag_name': 'a', 'new_tag_name': 'b'})[2] is None
    _tool, _merged, error = intent_tools.resolve_rest_call(
        'tag_group_manage', {'action': 'batch_tag',
                             'batch_action': 'rename_tag', 'ids': [CASE_ID],
                             'old_tag_name': 'a', 'new_tag_name': 'b'})
    assert error and 'ids' in error


def test_retry_body_is_passed_through():
    tool, merged, error = intent_tools.resolve_rest_call(
        'task_run', {'action': 'retry', 'task_id': 128,
                     'body': {'mode': 'failed_only'}})
    assert error is None
    assert merged['body'] == {'mode': 'failed_only'}
    assert mcp_registry.build_body(tool, merged) == {'mode': 'failed_only'}


@pytest.mark.parametrize('name,arguments,fragment', [
    # 动作不支持的参数：网关会静默忽略 / 丢弃，工具层必须拒绝
    ('testcase_write', {'action': 'delete', 'tc_id': CASE_ID,
                        'body': {'name': 'x'}}, '不支持参数'),
    ('testcase_write', {'action': 'create', 'body': {}}, 'body'),
    ('testcase_write', {'action': 'create', 'body': {'description': 'x'}},
     'body.name'),
    ('testcase_write', {'action': 'create', 'body': {'name': '接线测试_用例'}},
     'group_id'),
    ('testcase_write', {'action': 'tag', 'tc_id': CASE_ID, 'tags': ['a']},
     'tag_mode'),
    ('tag_group_manage', {'action': 'batch_tag', 'target_kind': 'tag',
                          'batch_action': 'add_tags', 'ids': [CASE_ID],
                          'tags': ['a']}, '不支持参数'),
    ('tag_group_manage', {'action': 'batch_tag',
                          'batch_action': 'rename_tag', 'ids': [CASE_ID],
                          'old_tag_name': 'a', 'new_tag_name': 'b'}, 'ids'),
    ('tag_group_manage', {'action': 'delete', 'target_kind': 'tag'},
     'tag_id'),
    ('tag_group_manage', {'action': 'create', 'body': {'name': 'x'}},
     'target_kind'),
    ('task_run', {'action': 'start', 'task_id': 128, 'case_ids': [CASE_ID]},
     '不支持参数'),
    ('task_run', {'action': 'retry', 'task_id': 128,
                  'body': {'case_ids': [CASE_ID]}}, 'mode=selected'),
    ('task_run', {'action': 'merge', 'body': {'task_ids': [128]}},
     '至少需要'),
    ('task_run', {'action': 'merge',
                  'body': {'task_ids': [128, 129], 'name': 'x'}},
     '不支持字段'),
    ('task_run', {'action': 'reextract', 'task_id': 128,
                  'execution_status': 'unknown'}, 'execution_status'),
])
def test_invalid_write_arguments_are_rejected(name, arguments, fragment):
    _tool, _merged, error = intent_tools.resolve_rest_call(name, arguments)
    assert error is not None
    assert fragment in error, error


def test_validate_call_rejects_before_proposal():
    """网关提案前校验也走动作解析：非法参数不会生成审批单。"""
    bridge = SharedToolRegistryBridge()
    error = bridge.validate('testcase_write', {'action': 'delete'})
    assert error and 'tc_id' in error
    assert bridge.validate('testcase_write',
                           {'action': 'delete', 'tc_id': CASE_ID}) is None
    assert bridge.validate('tag_group_manage',
                           {'action': 'batch_tag',
                            'batch_action': 'rename_tag'}) is not None


# ---------------------------------------------------------------- 审批链路

class FakeRestClient:
    """记录回源请求，返回成功信封。"""

    def __init__(self):
        self.calls = []

    def call(self, tool, arguments, **kwargs):
        self.calls.append({'tool': tool, 'arguments': arguments, **kwargs})
        payload = {'success': True, 'data': {'id': 99}}
        return RestResult(status=200, payload=payload,
                          text=json.dumps(payload, ensure_ascii=False))


def _stack(tmp_path, llm, rest):
    gateway = SharedToolGateway(
        bridge=SharedToolRegistryBridge(), rest=rest,
        credentials=RunCredentialRegistry())
    return build_stack(
        tmp_path / 'write_tools.db', llm, gateway=gateway,
        executor_factory=lambda orch: InlineRunExecutor(orch))


def test_delete_proposes_destructive_then_executes_once(tmp_path):
    call = ToolCallRequest(tool_call_id='c1', name='testcase_write',
                           arguments={'action': 'delete', 'tc_id': CASE_ID})
    llm = FakeLlm([tool_turn([call]), text_turn('已提交删除提案')])
    rest = FakeRestClient()
    container, _engine, _sf = _stack(tmp_path, llm, rest)
    run = start_run(container, message='删除用例')

    # 提案前不回源
    assert rest.calls == []
    approval = pending_approval(container, run.id)
    assert approval.proposal['risk'] == 'DESTRUCTIVE'
    assert approval.proposal['arguments'] == {'action': 'delete',
                                              'tc_id': CASE_ID}
    assert approval.diff['method'] == 'DELETE'
    assert approval.diff['path'] == '/api/v1/testcases/{tc_id}'
    record = container.repositories['tool_calls'].find(run.id, 'c1')
    assert record.status is ToolCallStatus.WAITING_APPROVAL
    assert record.risk is ToolRisk.DESTRUCTIVE

    # 批准后按解析出的请求执行一次
    decide(container, approval.id, 'APPROVE', permissions=['*'])
    container.executor.submit(run.id)
    assert len(rest.calls) == 1
    sent = rest.calls[0]
    assert sent['tool']['method'] == 'DELETE'
    assert sent['arguments'] == {'tc_id': CASE_ID}
    record = container.repositories['tool_calls'].find(run.id, 'c1')
    assert record.status is ToolCallStatus.COMPLETED
    assert record.result_code == 'OK'
    assert container.repositories['runs'].get(run.id).status is \
        RunStatus.SUCCEEDED

    # 重复提交 execute 不再回源（幂等：同一 tool_call 只有一次副作用）
    container.executor.submit(run.id)
    assert len(rest.calls) == 1


def test_batch_tag_proposes_and_executes_batch_endpoint(tmp_path):
    call = ToolCallRequest(
        tool_call_id='c1', name='tag_group_manage',
        arguments={'action': 'batch_tag', 'batch_action': 'add_tags',
                   'ids': [CASE_ID], 'tags': ['接线测试_标签']})
    llm = FakeLlm([tool_turn([call]), text_turn('已提交打标提案')])
    rest = FakeRestClient()
    container, _engine, _sf = _stack(tmp_path, llm, rest)
    run = start_run(container, message='批量打标')

    approval = pending_approval(container, run.id)
    assert approval.proposal['risk'] == 'WRITE'
    assert approval.diff['path'] == '/api/v1/testcases/batch'

    decide(container, approval.id, 'APPROVE', permissions=['*'])
    container.executor.submit(run.id)
    assert len(rest.calls) == 1
    sent = rest.calls[0]
    assert sent['tool']['name'] == 'testcase_batch'
    assert sent['arguments'] == {
        'body': {'action': 'add_tags', 'ids': [CASE_ID],
                 'tags': ['接线测试_标签']}}


def test_action_permission_gap_blocks_proposal(tmp_path):
    """只有 task:merge 没有 task:execute：start 不生成提案、不回源。"""
    call = ToolCallRequest(tool_call_id='c1', name='task_run',
                           arguments={'action': 'start', 'task_id': 128})
    llm = FakeLlm([tool_turn([call]), text_turn('未执行')])
    rest = FakeRestClient()
    container, _engine, _sf = _stack(tmp_path, llm, rest)
    run = start_run(container, message='启动任务',
                    permissions=('task:read', 'task:merge'))

    assert rest.calls == []
    approvals = container.repositories['approvals'].list_by_run(run.id)
    assert approvals == []
    record = container.repositories['tool_calls'].find(run.id, 'c1')
    assert record.status is ToolCallStatus.DENIED
    assert record.result_code == 'PERMISSION_DENIED'


def test_task_start_proposes_write_with_execute_permission(tmp_path):
    call = ToolCallRequest(tool_call_id='c1', name='task_run',
                           arguments={'action': 'start', 'task_id': 128})
    llm = FakeLlm([tool_turn([call]), text_turn('已提交启动提案')])
    rest = FakeRestClient()
    container, _engine, _sf = _stack(tmp_path, llm, rest)
    run = start_run(container, message='启动任务',
                    permissions=('task:read', 'task:execute'))

    approval = pending_approval(container, run.id)
    assert approval.proposal['risk'] == 'WRITE'
    assert approval.diff['method'] == 'POST'
    assert approval.diff['path'] == '/api/v1/tasks/{task_id}/start'

    decide(container, approval.id, 'APPROVE',
           permissions=('task:read', 'task:execute'))
    container.executor.submit(run.id)
    assert len(rest.calls) == 1
    assert rest.calls[0]['arguments'] == {'task_id': 128}
    assert container.repositories['runs'].get(run.id).status is \
        RunStatus.SUCCEEDED
