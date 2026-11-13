# -*- coding: utf-8 -*-
"""INT-2492 探索-生成层：ui_tree / ui_action / api_spec。

验收锚点（卡面「可测验收标准」）：
1. ui_tree ≤200 节点、字段齐全、含截图引用与 diff，XML / base64 不出现在响应；
2. ui_action 七种动作各返回新树 diff 并写 ui_trace.json；dry_run 不产生设备动作；
3. 预算：第 31 个动作以 BUDGET 停止，run 不静默成功；
4. 安全：卸载 / 重启 / 支付 / 删账号 100% 拒绝；登录 / 验证码页以
   LOGIN_REQUIRED / CAPTCHA 交回；
5. 未租用设备调用被拒；首个动作未审批不下发，审批后同计划自动放行；
6. api_spec 解析 OpenAPI 与 WS；畸形契约返回明确错误，不抛内部异常；
7. ui_trace.json 以 kind=UI_TRACE 进 agent_artifact，含 source_trace /
   validation_report；
8. 探索工具已启用且工具总数仍为 31。
"""
import json
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from agent_service.application.exploration_service import (
    BUDGET_EXCEEDED, DESTRUCTIVE_BLOCKED, DEVICE_NOT_LEASED,
    EXPLORATION_UNAVAILABLE, LOGIN_REQUIRED, ExplorationService,
)
from agent_service.application.tool_gateway import SharedToolGateway
from agent_service.domain.enums import ToolRisk
from agent_service.domain.model.entities import ToolCallRequest
from agent_service.domain.ports.tool_gateway import (
    ToolApproval, ToolInvocationContext,
)
from agent_service.domain.ports.ui_device import DeviceLeasePort, UiDevicePort
from agent_service.infrastructure.tools.registry_bridge import (
    RestResult, RunCredentialRegistry, SharedToolRegistryBridge,
)
from shared.agent_tools import driver_tools
from shared.agent_tools import ui_exploration as ux

# ---------------------------------------------------------------- fakes


class FakeDevice(UiDevicePort):
    """脚本化设备：按动作推进页面；记录真实下发的动作（dry_run 断言用）。"""

    def __init__(self, pages, platform='ANDROID', screenshot=True):
        self.pages = [list(page) for page in pages]
        self.index = 0
        self.performed = []
        self._platform = platform
        self._screenshot = screenshot
        self.shots = 0

    def platform(self, device_id):
        return self._platform

    def dump_nodes(self, device_id, *, max_nodes):
        return {'nodes': list(self.pages[self.index]),
                'coverage': ux.coverage_notes(self.pages[self.index],
                                              self._platform)}

    def perform(self, device_id, action_type, *, node=None, params=None):
        self.performed.append({'action': action_type, 'node': node,
                               'params': dict(params or {})})
        self.index = min(self.index + 1, len(self.pages) - 1)
        return {'applied': True}

    def screenshot(self, device_id, *, label=''):
        if not self._screenshot:
            return None
        self.shots += 1
        return f'oss://archives/ui-shot/{device_id}-{label}-{self.shots}.png'


class FakeLease(DeviceLeasePort):
    def __init__(self, available=True):
        self.available = available
        self.acquired = 0
        self.released = 0

    def acquire(self, device_id, *, holder):
        if not self.available:
            return None
        self.acquired += 1
        return {'device_id': device_id, 'holder': holder}

    def release(self, lease):
        self.released += 1


class FakeArtifacts:
    def __init__(self):
        self.items = []

    def add(self, artifact):
        self.items.append(artifact)
        return artifact

    def list_by_run(self, run_id):
        return [a for a in self.items if a.run_id == run_id]


class FakeStore:
    def __init__(self):
        self.written = {}

    def put(self, content, *, run_id, name, content_type='application/json'):
        uri = f'oss://archives/agent-context/{run_id}/{name}'
        self.written[uri] = content
        return uri


class FakeRestClient:
    def call(self, tool, arguments, **kwargs):
        return RestResult(status=200, payload={'data': {}}, text='{}')


def _node(node_id, text='', *, rid=None, clickable=True,
          cls='android.widget.Button'):
    return {'id': node_id, 'text': text, 'resource_id': rid or node_id,
            'class': cls, 'bounds': [0, 0, 100, 100],
            'clickable': clickable, 'enabled': True, '_key': None}


def _ctx(run_id='run-1', approval=None, session='s1'):
    return ToolInvocationContext(
        run_id=run_id, session_id=session, owner_id=7, tenant_id='t1',
        step_id='step-1', permissions=('*',), idempotency_key='idem-1',
        approval=approval)


def _approval():
    return ToolApproval(approval_id='ap-1', risk=ToolRisk.WRITE,
                        proposal={'tool': 'ui_action'})


def make_service(devices=None, lease=None, artifacts=None, store=None,
                 budget=None):
    return ExplorationService(
        devices=devices, leases=lease or FakeLease(),
        artifacts=artifacts if artifacts is not None else FakeArtifacts(),
        store=store if store is not None else FakeStore(),
        budget=budget or ux.ExplorationBudget())


def make_gateway(**kwargs):
    return SharedToolGateway(
        bridge=SharedToolRegistryBridge(), rest=FakeRestClient(),
        credentials=RunCredentialRegistry(),
        exploration=make_service(**kwargs))


def call(name, arguments):
    return ToolCallRequest(tool_call_id='call-1', name=name,
                          arguments=arguments)


def payload_of(result):
    return json.loads(result.content)


# ---------------------------------------------------------------- 树裁剪


def test_ui_tree_crops_to_200_and_strips_raw_xml_or_base64():
    big = [_node(f'n{i}', f'文本{i}') for i in range(500)]
    gateway = make_gateway(devices=FakeDevice([big]))
    result = gateway.execute(call('ui_tree', {'device_id': 3}), _ctx())
    assert result.ok
    payload = payload_of(result)
    assert payload['node_count'] == ux.MAX_TREE_NODES == 200
    assert payload['total_nodes'] == 500
    assert payload['truncated'] is True
    assert payload['screenshot_ref']
    node = payload['nodes'][0]
    assert set(node) <= set(ux.NODE_FIELDS) | {'key'}
    for field in ('id', 'text', 'resource_id', 'class', 'bounds',
                  'clickable', 'enabled'):
        assert field in node
    # 整页 XML / base64 不进响应（体积与内容双重断言）
    assert '<node' not in result.content
    assert 'base64' not in result.content.lower()
    assert len(result.content.encode('utf-8')) < 200 * 1024


def test_ui_tree_key_fallback_and_diff_from_previous_snapshot():
    page1 = [_node('n1', '记录', rid=None)]
    page1[0]['resource_id'] = None
    page1[0]['_key'] = 'content-desc:录音'
    page2 = [_node('n1', '记录', rid=None), _node('n2', '完成')]
    page2[0]['resource_id'] = None
    page2[0]['_key'] = 'content-desc:录音'
    device = FakeDevice([page1, page2])
    gateway = make_gateway(devices=device)
    first = payload_of(gateway.execute(call('ui_tree', {'device_id': 3}), _ctx()))
    assert first['nodes'][0]['key'] == 'content-desc:录音'
    assert first['diff'] is None and first['diff_from_snapshot_id'] is None
    device.index = 1
    second = payload_of(gateway.execute(call('ui_tree', {'device_id': 3}), _ctx()))
    assert second['diff_from_snapshot_id'] == first['snapshot_id']
    assert second['diff']['counts']['added'] == 1


def test_android_and_harmony_parsers_cover_platforms():
    android = ux.parse_android_hierarchy(
        '<hierarchy>'
        '<node text="录音" resource-id="app:id/rec" class="android.widget.Button"'
        ' clickable="true" enabled="true" bounds="[0,0][10,20]"/>'
        '<node text="" class="android.widget.FrameLayout" bounds="[0,0][10,20]"/>'
        '</hierarchy>')
    assert len(android) == 1 and android[0]['resource_id'] == 'app:id/rec'
    harmony = ux.parse_harmony_components([
        {'id': 'btn_rec', 'text': '录音', 'type': 'Button',
         'bounds': {'left': 0, 'top': 0, 'right': 10, 'bottom': 20},
         'clickable': True},
        {'type': 'Text', 'text': '结果'},
    ])
    assert harmony[0]['resource_id'] == 'btn_rec'
    assert harmony[1]['resource_id'] is None and harmony[1]['_key']
    coverage = ux.coverage_notes(harmony, 'HARMONYOS')
    assert coverage == {'platform': 'HARMONYOS', 'nodes': 2,
                        'resource_id': 1, 'key': 1, 'text_only': 0}


def test_diff_trees_reports_added_removed_changed():
    before = [_node('a', 'A'), _node('b', 'B')]
    after = [_node('a', 'A2'), _node('c', 'C')]
    diff = ux.diff_trees(before, after)
    assert diff['counts']['added'] == 1
    assert diff['counts']['removed'] == 1
    assert diff['counts']['changed'] == 1
    assert diff['changed'][0]['fields'] == ['text']


# ---------------------------------------------------------------- 安全 / 预算


def test_destructive_actions_are_blocked_without_device_call():
    page = [_node('del', '卸载应用')]
    device = FakeDevice([page])
    lease = FakeLease()
    gateway = make_gateway(devices=device, lease=lease)
    result = gateway.execute(
        call('ui_action', {'device_id': 3, 'action_type': 'TAP',
                           'target': {'id': 'del'}}),
        _ctx(approval=_approval()))
    assert result.error_code == DESTRUCTIVE_BLOCKED
    payload = payload_of(result)
    assert payload['stop_reason'] == 'DESTRUCTIVE_BLOCKED'
    assert payload['matched_keyword'] == '卸载'
    assert device.performed == []          # 一个设备动作都没下发
    assert lease.released == 1


@pytest.mark.parametrize('text, expected', [
    ('登录', LOGIN_REQUIRED),
    ('请输入验证码', 'CAPTCHA'),
])
def test_login_and_captcha_pages_hand_back(text, expected):
    page = [_node('n1', text)]
    gateway = make_gateway(devices=FakeDevice([page]))
    result = gateway.execute(call('ui_tree', {'device_id': 3}), _ctx())
    assert result.ok
    assert payload_of(result)['stop_reason'] == expected


def test_action_on_login_page_is_refused_without_device_call():
    page = [_node('n1', '手机号登录'), _node('n2', '密码登录')]
    device = FakeDevice([page])
    gateway = make_gateway(devices=device)
    result = gateway.execute(
        call('ui_action', {'device_id': 3, 'action_type': 'TAP',
                           'target': {'id': 'n1'}}),
        _ctx(approval=_approval()))
    assert result.error_code == LOGIN_REQUIRED
    payload = payload_of(result)
    assert payload['stop_reason'] == 'LOGIN_REQUIRED'
    assert payload['blocked_page'] == 'LOGIN'
    assert device.performed == []


def test_budget_stops_at_31st_action():
    page = [_node('n1', '按钮')]
    device = FakeDevice([page])
    gateway = make_gateway(
        devices=device, budget=ux.ExplorationBudget(max_actions=30,
                                                    max_seconds=300))
    context = _ctx(approval=_approval())
    for index in range(30):
        result = gateway.execute(
            call('ui_action', {'device_id': 3, 'action_type': 'WAIT',
                               'params': {'duration_ms': 1}}), context)
        assert result.ok, index
    result = gateway.execute(
        call('ui_action', {'device_id': 3, 'action_type': 'WAIT',
                           'params': {'duration_ms': 1}}), context)
    assert result.error_code == BUDGET_EXCEEDED
    assert payload_of(result)['stop_reason'] == 'BUDGET'
    assert len(device.performed) == 30     # 第 31 个动作没有下发
    assert '预算' in payload_of(result)['message']


def test_budget_stops_when_duration_exceeded():
    page = [_node('n1', '按钮')]
    gateway = make_gateway(devices=FakeDevice([page]))
    service = gateway._exploration
    payload = service.ui_tree({'device_id': 3}, _ctx())  # 建立会话 + 租约
    assert payload['node_count'] == 1
    session = service._sessions[('run-1', 3)]
    session.started_monotonic -= 301
    result = gateway.execute(
        call('ui_action', {'device_id': 3, 'action_type': 'WAIT',
                           'params': {'duration_ms': 1}}),
        _ctx(approval=_approval()))
    assert result.error_code == BUDGET_EXCEEDED


def test_lease_is_required_and_released_on_stop():
    gateway = make_gateway(devices=FakeDevice([[_node('n1', '按钮')]]),
                           lease=FakeLease(available=False))
    result = gateway.execute(call('ui_tree', {'device_id': 3}), _ctx())
    assert result.error_code == DEVICE_NOT_LEASED
    assert '租用' in payload_of(result)['message']


def test_device_channel_missing_is_explicit_not_faked():
    gateway = make_gateway(devices=None)
    tree = gateway.execute(call('ui_tree', {'device_id': 3}), _ctx())
    assert tree.error_code == EXPLORATION_UNAVAILABLE
    assert '不返回伪造的树' in tree.content
    action = gateway.execute(
        call('ui_action', {'device_id': 3, 'action_type': 'BACK'}),
        _ctx(approval=_approval()))
    assert action.error_code == EXPLORATION_UNAVAILABLE
    # 提案阶段就拦下：不生成一条注定执行不了的审批单
    assert gateway.validate_call('ui_action', {'device_id': 3,
                                               'action_type': 'BACK'})


# ---------------------------------------------------------------- 动作 / 轨迹


def test_all_seven_actions_return_diff_and_write_trace():
    page = [_node('n1', '按钮')]
    device = FakeDevice([page])
    artifacts, store = FakeArtifacts(), FakeStore()
    gateway = make_gateway(devices=device, artifacts=artifacts, store=store)
    context = _ctx(approval=_approval())
    actions = [
        ('TAP', {'target': {'id': 'n1'}}),
        ('LONG_PRESS', {'target': {'id': 'n1'},
                        'params': {'duration_ms': 600}}),
        ('SWIPE', {'target': {'id': 'n1'},
                   'params': {'to_x': 10, 'to_y': 20}}),
        ('INPUT_TEXT', {'target': {'id': 'n1'}, 'params': {'text': '你好'}}),
        ('BACK', {}), ('HOME', {}), ('WAIT', {'params': {'duration_ms': 1}}),
    ]
    for index, (action_type, extra) in enumerate(actions):
        result = gateway.execute(
            call('ui_action', dict({'device_id': 3,
                                    'action_type': action_type}, **extra)),
            context)
        assert result.ok, (action_type, result.content)
        payload = payload_of(result)
        assert payload['tree_diff'] is not None
        assert payload['trace_ref']
        assert payload['stop_reason'] == 'DONE'
        assert payload['action_index'] == index + 1
    assert [item['action'] for item in device.performed] == [
        action for action, _ in actions]
    # 每一个动作都回写同一份 ui_trace.json；artifact 只登记一行
    assert len(artifacts.items) == 1
    trace = json.loads(store.written[artifacts.items[0].uri])
    assert len(trace['actions']) == 7
    assert sorted({item['action'] for item in trace['actions']}) == sorted(
        action for action, _ in actions)
    assert trace['pages'] and trace['screenshots']
    assert driver_tools.validate_ui_trace(trace, required=True) is None


def test_dry_run_does_not_perform_device_action():
    page = [_node('n1', '按钮')]
    device = FakeDevice([page])
    gateway = make_gateway(devices=device)
    result = gateway.execute(
        call('ui_action', {'device_id': 3, 'action_type': 'TAP',
                           'target': {'id': 'n1'}, 'dry_run': True}),
        _ctx())                       # 预演不需要审批
    assert result.ok
    payload = payload_of(result)
    assert payload['dry_run'] is True and payload['applied'] is False
    assert payload['projected'] is True
    assert device.performed == []


def test_validate_flag_is_a_precheck_without_device_action():
    page = [_node('n1', '按钮')]
    device = FakeDevice([page])
    gateway = make_gateway(devices=device)
    result = gateway.execute(
        call('ui_action', {'device_id': 3, 'action_type': 'TAP',
                           'target': {'id': 'n1'}, 'validate': True}),
        _ctx())                       # 只校验，不需要审批
    assert result.ok
    payload = payload_of(result)
    assert payload['validate_only'] is True and payload['applied'] is False
    assert device.performed == []


def test_captcha_message_matches_stop_reason():
    gateway = make_gateway(devices=FakeDevice([[_node('n1', '请拖动滑块完成验证')]]))
    result = gateway.execute(call('ui_tree', {'device_id': 3}), _ctx())
    payload = payload_of(result)
    assert payload['stop_reason'] == 'CAPTCHA'
    assert '验证码' in payload['message']


def test_first_action_needs_approval_then_plan_is_auto_allowed():
    page = [_node('n1', '按钮')]
    device = FakeDevice([page])
    gateway = make_gateway(devices=device)
    args = {'device_id': 3, 'action_type': 'TAP', 'target': {'id': 'n1'}}
    denied = gateway.execute(call('ui_action', args), _ctx())
    assert denied.error_code == 'APPROVAL_REQUIRED'
    assert device.performed == []
    assert gateway.approval_waived('ui_action', args,
                                   run_id='run-1') is False

    approved = gateway.execute(call('ui_action', args), _ctx(
        approval=_approval()))
    assert approved.ok and len(device.performed) == 1
    assert gateway.approval_waived('ui_action', args, run_id='run-1') is True

    # 同一探索计划（同 run + 同设备）后续动作自动放行
    again = gateway.execute(call('ui_action', args), _ctx())
    assert again.ok and len(device.performed) == 2
    # 其他设备仍需单独审批
    assert gateway.approval_waived('ui_action', {'device_id': 99,
                                                 'action_type': 'TAP'},
                                   run_id='run-1') is False


def test_trace_artifact_carries_source_trace_and_validation_report():
    page = [_node('n1', '按钮')]
    artifacts, store = FakeArtifacts(), FakeStore()
    gateway = make_gateway(devices=FakeDevice([page]), artifacts=artifacts,
                           store=store)
    result = gateway.execute(
        call('ui_action', {'device_id': 3, 'action_type': 'TAP',
                           'target': {'id': 'n1'}}),
        _ctx(approval=_approval()))
    assert result.ok
    artifact = artifacts.items[0]
    assert artifact.kind == ux.ARTIFACT_KIND_UI_TRACE == 'UI_TRACE'
    assert artifact.size > 0 and artifact.uri in store.written
    metadata = artifact.metadata
    assert metadata['artifact_kind'] == 'UI_TRACE'
    assert metadata['source_trace']['sha256']
    assert metadata['source_trace']['actions'] == 1
    assert metadata['validation_report']['ok'] is True


def test_close_run_releases_lease():
    lease = FakeLease()
    gateway = make_gateway(devices=FakeDevice([[_node('n1', '按钮')]]),
                           lease=lease)
    gateway.execute(call('ui_tree', {'device_id': 3}), _ctx())
    assert lease.acquired == 1
    gateway.release_exploration('run-1')
    assert lease.released == 1


# ---------------------------------------------------------------- api_spec

_OPENAPI = json.dumps({
    'openapi': '3.0.0',
    'info': {'title': '语音网关'},
    'components': {'securitySchemes': {
        'bearer': {'type': 'http', 'scheme': 'bearer'}}},
    'paths': {'/asr': {'post': {
        'operationId': 'asr',
        'security': [{'bearer': []}],
        'parameters': [{'name': 'lang', 'in': 'query', 'required': False,
                        'schema': {'type': 'string'}}],
        'requestBody': {'required': True, 'content': {'application/json': {
            'schema': {'type': 'object',
                       'properties': {'audio': {'type': 'string'}}}}}},
        'responses': {'200': {'content': {'application/json': {
            'schema': {'type': 'object',
                       'properties': {'text': {'type': 'string'}}}}}}},
    }}},
}, ensure_ascii=False)

_WS = json.dumps({
    'url': 'wss://vendor.example/stream',
    'auth': {'type': 'apiKey', 'in': 'header', 'header': 'X-Api-Key'},
    'messages': [
        {'type': 'start', 'send': {'format': 'pcm'}, 'receive': {'ok': True}},
        {'type': 'audio', 'send': {'chunk': 'bytes'}, 'receive': {'text': ''}},
    ],
}, ensure_ascii=False)

_PROTO = """
syntax = "proto3";
package vendor.asr;
message AsrRequest { bytes audio = 1; string lang = 2; }
message AsrResponse { string text = 1; }
service AsrService {
  rpc Recognize (AsrRequest) returns (AsrResponse);
}
"""


def test_api_spec_parses_openapi_with_auth_and_samples():
    spec = ux.parse_api_spec(_OPENAPI, kind='OPENAPI')
    assert spec['kind'] == 'OPENAPI'
    endpoint = spec['endpoints'][0]
    assert endpoint['method'] == 'POST' and endpoint['path'] == '/asr'
    assert endpoint['auth'] == ['bearer']
    assert endpoint['request_sample'] == {'audio': 'string'}
    assert endpoint['response_sample'] == {'text': 'string'}
    assert spec['auth_schemes'][0]['scheme'] == 'bearer'


def test_api_spec_parses_ws_and_proto():
    ws = ux.parse_api_spec(_WS, kind='WS')
    assert ws['kind'] == 'WS' and len(ws['endpoints']) == 2
    assert ws['endpoints'][0]['request_sample'] == {'format': 'pcm'}
    assert ws['auth_schemes'][0]['key'] == 'X-Api-Key'
    proto = ux.parse_api_spec(_PROTO, kind='PROTO')
    assert proto['kind'] == 'PROTO'
    assert proto['endpoints'][0]['method'] == 'GRPC'
    assert proto['endpoints'][0]['path'] == 'vendor.asr.AsrService/Recognize'
    assert {p['name'] for p in proto['endpoints'][0]['params']} == {
        'audio', 'lang'}


def test_api_spec_endpoint_filter_and_malformed_contract():
    spec = ux.parse_api_spec(_OPENAPI, endpoint='asr')
    assert len(spec['endpoints']) == 1
    with pytest.raises(ux.SpecParseError):
        ux.parse_api_spec('{}', kind='OPENAPI')
    with pytest.raises(ux.SpecParseError):
        ux.parse_api_spec('not a contract', kind='OPENAPI')
    with pytest.raises(ux.SpecParseError):
        ux.parse_api_spec('{"openapi":"3.0.0"}', kind='OPENAPI')


def test_api_spec_gateway_returns_plain_failure_not_exception():
    gateway = make_gateway()
    bad = gateway.execute(call('api_spec', {'content': '{}'}), _ctx())
    assert bad.error_code == 'INVALID_ARGUMENTS'
    assert '契约解析失败' in bad.content
    ok = gateway.execute(call('api_spec', {'content': _WS}), _ctx())
    assert ok.ok and payload_of(ok)['summary']['endpoints'] == 2


# ---------------------------------------------------------------- 清单 / 预算等级


def test_tool_catalog_has_31_tools_with_exploration_enabled():
    gateway = make_gateway()
    descriptors = {tool.name: tool for tool in gateway.all_tools()}
    assert len(descriptors) == 31
    assert descriptors['ui_tree'].enabled and descriptors['api_spec'].enabled
    assert descriptors['ui_action'].enabled
    assert gateway.risk_of('ui_action') is ToolRisk.WRITE
    assert gateway.risk_of('ui_tree') is ToolRisk.READ
    assert gateway.risk_of('api_spec') is ToolRisk.READ


# ---------------------------------------------------------------- run 级预算收口

from tests.unit.int2451_agent_fakes import (  # noqa: E402
    FakeLlm, FakeToolGateway, build_stack, event_types, new_session,
    text_turn, tool_turn, write_tool,
)


class BudgetToolGateway(FakeToolGateway):
    """工具回灌 BUDGET_EXCEEDED：run 必须收口为 BUDGET_EXCEEDED，不静默成功。

    ``approval_waived`` 模拟「同一探索计划内已审批」：直接进入执行，
    本用例只验证预算收口，不复测审批链（审批链有独立用例）。
    """

    def approval_waived(self, name, arguments=None, *, run_id='',
                        session_id='', permissions=()):
        return name == 'ui_action'

    def execute(self, call, context):
        self.executed.append((call.tool_call_id, call.name, call.arguments))
        from agent_service.domain.model.entities import ToolResult
        return ToolResult(tool_call_id=call.tool_call_id, tool=call.name,
                          ok=False, error_code='BUDGET_EXCEEDED',
                          content=json.dumps({'stop_reason': 'BUDGET'}))


def test_exploration_budget_finishes_run_as_budget_exceeded(tmp_path):
    from agent_service.application.run_worker import InlineRunExecutor
    from agent_service.domain.enums import RunStatus

    tool_call = ToolCallRequest(tool_call_id='b1', name='ui_action',
                                arguments={'device_id': 1,
                                           'action_type': 'WAIT'})
    llm = FakeLlm([tool_turn([tool_call]), text_turn('不该到这里')])
    gateway = BudgetToolGateway(tools=[write_tool('ui_action')])
    container, _engine, _sf = build_stack(
        tmp_path / 'budget.db', llm, gateway=gateway,
        executor_factory=lambda orch: InlineRunExecutor(orch))
    session = new_session(container)
    run, _ = container.run_service.create_run(
        session.id, owner_id=7, tenant_id='t1', message='探索')
    container.executor.submit(run.id)

    stored = container.repositories['runs'].get(run.id)
    assert stored.status is RunStatus.BUDGET_EXCEEDED
    assert 'error' in event_types(container, run.id)
    container.shutdown()
