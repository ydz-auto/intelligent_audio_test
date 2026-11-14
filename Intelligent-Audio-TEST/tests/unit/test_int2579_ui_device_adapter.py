# -*- coding: utf-8 -*-
"""INT-2579 设备 UI HTTP 适配器：端口 holder 口径 + 网关三端点 + 错误码/解析/裁剪。

验收锚点（卡面「可测验收标准」）：

1. 凭据缺失 → ``DEVICE_UNAVAILABLE``，且**在发请求之前**失败（不匿名回源）；
2. 网关 400 / 404 / 409 / 503 的业务码**原样**映射为 ``UiDeviceError.code``；
3. 树的解析复用 INT-2492 唯一口径（Android XML / HarmonyOS 组件），
   解析失败显式报错、不返回空树；``crop_nodes`` 后节点 ≤200；
4. 平台不支持 → ``PLATFORM_UNSUPPORTED``；
5. 回源请求带 ``Authorization``，且来自 ``RunCredentialRegistry``（按 run，不硬编码）；
6. ``wiring`` 在网关基址缺失时不伪造端口（``devices=None``）；
7. ``_create_session`` 先取 run 凭据再调 ``platform``：凭据缺失以
   ``DEVICE_UNAVAILABLE`` 失败并释放租约（卡面「顺序注意」评审点）。
"""
import json
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from agent_service.application.exploration_service import (
    DEVICE_UNAVAILABLE, ExplorationService,
)
from agent_service.config.config import Config
from agent_service.domain.ports.tool_registry import ToolTransportResult
from agent_service.domain.ports.ui_device import UiDeviceError
from agent_service.infrastructure.adapters.ui_device_http import (
    DEFAULT_ERROR_CODE, DEVICE_UNAVAILABLE, UiDeviceHttpAdapter,
)
from agent_service.infrastructure.tools.registry_bridge import (
    RunCredentialRegistry,
)
from shared.agent_tools import ui_exploration as ux
from shared.constants.ui_capture import UiCaptureErrorCode
from tests.unit.test_int2492_exploration import (
    FakeArtifacts, FakeLease, FakeStore,
)

RUN_ID = 'run-2579'
AUTH = 'Bearer header.payload.signature'


# ---------------------------------------------------------------- 桩网关


class StubGateway:
    """按工具名回放预置响应的 ``ToolTransportPort`` 桩（记录请求）. """

    def __init__(self, responses=None):
        self.responses = dict(responses or {})
        self.calls = []

    def call(self, tool, arguments, *, authorization=None, user_id=0,
             tenant_id='', permissions=()):
        self.calls.append({
            'tool': tool['name'], 'method': tool['method'],
            'path': tool['path'], 'arguments': dict(arguments),
            'authorization': authorization, 'permissions': tuple(permissions),
        })
        value = self.responses.get(tool['name'], _ok({}))
        return value(tool, arguments) if callable(value) else value

    def last(self, name=None):
        items = [c for c in self.calls if name is None or c['tool'] == name]
        return items[-1] if items else None


def _ok(data):
    return ToolTransportResult(
        status=200,
        payload={'success': True, 'message': 'ok', 'code': '', 'data': data},
        text=json.dumps(data, ensure_ascii=False))


def _err(status, code='', message='设备侧失败'):
    return ToolTransportResult(
        status=status,
        payload={'success': False, 'message': message, 'code': code,
                 'data': None},
        text=json.dumps({'success': False, 'message': message, 'code': code},
                        ensure_ascii=False))


def _registry(run_id=RUN_ID):
    registry = RunCredentialRegistry()
    registry.put(run_id, AUTH)
    return registry


def _adapter(responses=None, *, registry=None):
    gateway = StubGateway(responses)
    return UiDeviceHttpAdapter(rest=gateway,
                               credentials=registry if registry is not None
                               else _registry()), gateway


def _android_xml(count=3):
    nodes = ''.join(
        f'<node text="文本{i}" resource-id="com.demo:id/n{i}" '
        f'class="android.widget.Button" clickable="true" enabled="true" '
        f'bounds="[0,{i * 10}][100,{i * 10 + 50}]" />'
        for i in range(count))
    return f'<hierarchy rotation="0">{nodes}</hierarchy>'


_UNSET = object()


def _tree_data(count=3, *, platform='ANDROID', fmt='ANDROID_XML',
               payload=_UNSET):
    return {'platform': platform, 'format': fmt,
            'payload': _android_xml(count) if payload is _UNSET else payload,
            'node_count': count, 'degraded': False, 'degrade_reason': None}


def _harmony_payload():
    return [
        {'id': 'h1', 'text': '音箱设置', 'type': 'Button',
         'bounds': '[0,0][200,80]', 'clickable': True, 'enabled': True},
        {'id': 'h2', 'text': '播放', 'type': 'Text',
         'bounds': '[0,90][200,170]', 'clickable': False, 'enabled': True},
    ]


# ---------------------------------------------------------------- 凭据


def test_missing_credential_fails_before_any_request():
    """四个方法都先取凭据：缺失即 DEVICE_UNAVAILABLE，绝不匿名发请求。"""
    adapter, gateway = _adapter(
        {'device_ui_tree': _ok(_tree_data()),
         'device_get': _ok({'system': 'Android'}),
         'device_ui_action': _ok({'performed': True}),
         'device_ui_screenshot': _ok({'screenshot_ref': 'oss://x.png'})},
        registry=RunCredentialRegistry())  # 空注册表
    for call in (
        lambda: adapter.platform(3, holder=RUN_ID),
        lambda: adapter.dump_nodes(3, max_nodes=200, holder=RUN_ID),
        lambda: adapter.perform(3, 'BACK', holder=RUN_ID),
        lambda: adapter.screenshot(3, holder=RUN_ID),
    ):
        with pytest.raises(UiDeviceError) as caught:
            call()
        assert caught.value.code == DEVICE_UNAVAILABLE
    assert gateway.calls == []


def test_authorization_header_comes_from_run_registry():
    """Authorization 按 holder(=run_id) 取自 RunCredentialRegistry，非硬编码。"""
    registry = RunCredentialRegistry()
    registry.put('run-a', 'Bearer token-a')
    registry.put('run-b', 'Bearer token-b')
    adapter, gateway = _adapter({'device_ui_tree': _ok(_tree_data())},
                                registry=registry)

    adapter.dump_nodes(3, max_nodes=200, holder='run-a')
    adapter.dump_nodes(3, max_nodes=200, holder='run-b')

    assert gateway.calls[0]['authorization'] == 'Bearer token-a'
    assert gateway.calls[1]['authorization'] == 'Bearer token-b'
    assert gateway.calls[0]['permissions'] == ('device:read',)


def test_unknown_holder_has_no_credential():
    adapter, gateway = _adapter({'device_ui_tree': _ok(_tree_data())})
    with pytest.raises(UiDeviceError) as caught:
        adapter.dump_nodes(3, max_nodes=200, holder='run-never-seen')
    assert caught.value.code == DEVICE_UNAVAILABLE
    assert gateway.calls == []


# ---------------------------------------------------------------- 错误码


@pytest.mark.parametrize('status,code', [
    (400, UiCaptureErrorCode.ACTION_NOT_ALLOWED.value),
    (400, UiCaptureErrorCode.PLATFORM_UNSUPPORTED.value),
    (404, UiCaptureErrorCode.DEVICE_NOT_FOUND.value),
    (409, UiCaptureErrorCode.BUSY.value),
    (503, UiCaptureErrorCode.UI_CAPTURE_UNAVAILABLE.value),
])
def test_gateway_business_code_passes_through(status, code):
    """网关信封的 code 原样成为 UiDeviceError.code（不靠 message 判型）。"""
    adapter, _ = _adapter({'device_ui_tree': _err(status, code, '原始文案')})
    with pytest.raises(UiDeviceError) as caught:
        adapter.dump_nodes(3, max_nodes=200, holder=RUN_ID)
    assert caught.value.code == code
    assert '原始文案' in str(caught.value)


def test_code_falls_back_to_http_status_when_envelope_lacks_code():
    """非信封响应（网关鉴权失败等）按 HTTP 状态归类，仍显式失败。"""
    bare = ToolTransportResult(status=404, payload={'detail': '设备不存在'},
                              text='{"detail": "设备不存在"}')
    adapter, _ = _adapter({'device_ui_tree': bare})
    with pytest.raises(UiDeviceError) as caught:
        adapter.dump_nodes(3, max_nodes=200, holder=RUN_ID)
    assert caught.value.code == UiCaptureErrorCode.DEVICE_NOT_FOUND.value


def test_network_failure_is_unavailable():
    dead = ToolTransportResult(status=0, error='Connection refused')
    adapter, _ = _adapter({'device_ui_tree': dead})
    with pytest.raises(UiDeviceError) as caught:
        adapter.dump_nodes(3, max_nodes=200, holder=RUN_ID)
    assert caught.value.code == DEFAULT_ERROR_CODE
    assert 'Connection refused' in str(caught.value)


def test_action_permission_is_device_control():
    adapter, gateway = _adapter(
        {'device_ui_action': _ok({'action_type': 'TAP', 'performed': True,
                                  'elapsed_ms': 12})})
    adapter.perform(3, 'TAP', node={'resource_id': 'ok'}, holder=RUN_ID)
    call = gateway.last('device_ui_action')
    assert call['permissions'] == ('device:control',)
    assert call['method'] == 'POST'
    assert call['path'].endswith('/{device_id}/ui/action')
    assert call['arguments']['action_type'] == 'TAP'


# ---------------------------------------------------------------- 解析 / 裁剪


def test_android_tree_parsed_with_shared_parser_and_cropped():
    adapter, _ = _adapter({'device_ui_tree': _ok(_tree_data(250))})
    result = adapter.dump_nodes(3, max_nodes=500, holder=RUN_ID)
    nodes = result['nodes']
    assert len(nodes) == ux.MAX_TREE_NODES == 200
    assert result['coverage']['nodes'] == 250
    assert result['coverage']['platform'] == 'ANDROID'
    # 解析走 normalize_node 的唯一口径：七字段 + _key 定位降级位
    assert set(nodes[0]) == set(ux.NODE_FIELDS) | {'_key'}
    assert nodes[0]['resource_id'] == 'com.demo:id/n0'
    assert nodes[0]['bounds'] == [0, 0, 100, 50]


def test_crop_honours_caller_max_nodes():
    adapter, _ = _adapter({'device_ui_tree': _ok(_tree_data(250))})
    result = adapter.dump_nodes(3, max_nodes=50, holder=RUN_ID)
    assert len(result['nodes']) == 50


def test_harmony_components_parsed_with_shared_parser():
    adapter, _ = _adapter({'device_ui_tree': _ok(_tree_data(
        2, platform='HARMONYOS', fmt='HARMONY_COMPONENTS',
        payload=_harmony_payload()))})
    result = adapter.dump_nodes(3, max_nodes=200, holder=RUN_ID)
    assert [n['id'] for n in result['nodes']] == ['h1', 'h2']
    assert result['nodes'][0]['text'] == '音箱设置'
    assert result['coverage']['platform'] == 'HARMONYOS'


def test_harmony_components_json_string_payload_is_accepted():
    payload = json.dumps(_harmony_payload(), ensure_ascii=False)
    adapter, _ = _adapter({'device_ui_tree': _ok(_tree_data(
        2, platform='HARMONYOS', fmt='HARMONY_COMPONENTS', payload=payload))})
    assert len(adapter.dump_nodes(3, max_nodes=200,
                                  holder=RUN_ID)['nodes']) == 2


@pytest.mark.parametrize('data', [
    _tree_data(1, payload='<hierarchy></hierarchy>'),   # 空树
    _tree_data(1, payload='<hierarchy'),                # 畸形 XML
    _tree_data(1, fmt='HARMONY_COMPONENTS', payload='not-json'),
    _tree_data(1, fmt='UNKNOWN_FORMAT'),                # 契约不一致
    _tree_data(1, payload=None),                        # 缺 payload
])
def test_tree_parse_failure_is_explicit_not_empty_tree(data):
    adapter, _ = _adapter({'device_ui_tree': _ok(data)})
    with pytest.raises(UiDeviceError) as caught:
        adapter.dump_nodes(3, max_nodes=200, holder=RUN_ID)
    assert caught.value.code == DEFAULT_ERROR_CODE


# ---------------------------------------------------------------- 平台


def test_platform_normalized_from_device_get():
    adapter, gateway = _adapter(
        {'device_get': _ok({'device_id': 3, 'system': 'Android'})})
    assert adapter.platform(3, holder=RUN_ID) == 'ANDROID'
    call = gateway.last('device_get')
    assert call['method'] == 'GET'
    assert call['arguments'] == {'device_id': 3}
    assert call['permissions'] == ('device:read',)


def test_platform_unsupported_when_system_unknown():
    """未知系统值 → PLATFORM_UNSUPPORTED（与卡 1 ``_resolve`` 同一分类）。"""
    adapter, _ = _adapter({'device_get': _ok({'system': 'Tizen'})})
    with pytest.raises(UiDeviceError) as caught:
        adapter.platform(3, holder=RUN_ID)
    assert caught.value.code == UiCaptureErrorCode.PLATFORM_UNSUPPORTED.value


def test_platform_missing_system_is_platform_unsupported():
    adapter, _ = _adapter({'device_get': _ok({})})
    with pytest.raises(UiDeviceError) as caught:
        adapter.platform(3, holder=RUN_ID)
    assert caught.value.code == UiCaptureErrorCode.PLATFORM_UNSUPPORTED.value


# ---------------------------------------------------------------- 动作 / 截图


def test_perform_maps_performed_to_applied():
    adapter, _ = _adapter({'device_ui_action': _ok(
        {'action_type': 'SWIPE', 'performed': False, 'elapsed_ms': 30})})
    result = adapter.perform(3, 'SWIPE', params={'direction': 'up'},
                             holder=RUN_ID)
    assert result['performed'] is False
    # 编排层读 applied：网关 performed=False 时不得被默认成「已生效」
    assert result['applied'] is False
    assert result['elapsed_ms'] == 30


def test_screenshot_returns_object_ref_and_none_when_missing():
    adapter, gateway = _adapter({'device_ui_screenshot': _ok(
        {'screenshot_ref': 'device-ui/SN/1.png', 'format': 'PNG'})})
    assert adapter.screenshot(3, label='a0', holder=RUN_ID) == \
        'device-ui/SN/1.png'
    assert gateway.last('device_ui_screenshot')['arguments'] == {
        'device_id': 3, 'label': 'a0'}

    adapter, _ = _adapter({'device_ui_screenshot': _ok({'format': 'PNG'})})
    assert adapter.screenshot(3, holder=RUN_ID) is None


# ---------------------------------------------------------------- 真实 RestToolClient 回源


def test_rest_tool_client_builds_gateway_requests(monkeypatch):
    """与 ``RestToolClient`` 真实拼装路径联调：URL / body / Authorization 头。"""
    from agent_service.infrastructure.tools import registry_bridge
    from agent_service.infrastructure.tools.registry_bridge import (
        RestToolClient,
    )

    captured = []

    class _Resp:
        status_code = 200
        text = ''

        def __init__(self, data):
            self._data = {'success': True, 'message': 'ok', 'code': '',
                          'data': data}

        def json(self):
            return self._data

    def fake_request(method, url, json=None, headers=None, timeout=None):
        captured.append({'method': method, 'url': url, 'json': json,
                         'headers': dict(headers or {})})
        if url.endswith('/ui/tree'):
            return _Resp(_tree_data(2))
        if url.endswith('/ui/action'):
            return _Resp({'action_type': 'TAP', 'performed': True})
        return _Resp({'screenshot_ref': 'oss://shot.png'})

    monkeypatch.setattr(registry_bridge.httpx, 'request', fake_request)
    adapter = UiDeviceHttpAdapter(
        rest=RestToolClient('http://127.0.0.1:15000', timeout_seconds=1),
        credentials=_registry())

    adapter.dump_nodes(7, max_nodes=200, holder=RUN_ID)
    adapter.perform(7, 'TAP', node={'resource_id': 'ok'},
                    params={'x': 1}, holder=RUN_ID)
    adapter.screenshot(7, label='a0', holder=RUN_ID)

    tree, action, shot = captured
    assert tree['url'] == 'http://127.0.0.1:15000/api/v1/test-devices/7/ui/tree'
    assert tree['method'] == 'POST'
    assert tree['json'] is None                      # 空请求体（读树不解析体）
    assert tree['headers']['Authorization'] == AUTH
    assert tree['headers']['X-User-Permissions'] == 'device:read'

    assert action['url'].endswith('/api/v1/test-devices/7/ui/action')
    assert action['json'] == {'action_type': 'TAP',
                              'node': {'resource_id': 'ok'}, 'params': {'x': 1}}
    assert action['headers']['X-User-Permissions'] == 'device:control'

    assert shot['url'].endswith('/api/v1/test-devices/7/ui/screenshot')
    assert shot['json'] == {'label': 'a0'}


# ---------------------------------------------------------------- 组合根 / 编排


def test_wiring_keeps_devices_none_without_gateway_base_url(monkeypatch):
    from agent_service.wiring import build_ui_device_adapter

    monkeypatch.setattr(Config, 'TOOL_GATEWAY_BASE_URL', '')
    assert build_ui_device_adapter(StubGateway(), _registry()) is None

    monkeypatch.setattr(Config, 'TOOL_GATEWAY_BASE_URL',
                        'http://127.0.0.1:15000')
    adapter = build_ui_device_adapter(StubGateway(), _registry())
    assert isinstance(adapter, UiDeviceHttpAdapter)


def test_session_creation_fails_unavailable_when_run_credential_missing():
    """卡面「顺序注意」：platform 是首个设备调用，凭据缺失 → DEVICE_UNAVAILABLE + 释放租约。"""
    from agent_service.application.tool_gateway import SharedToolGateway
    from agent_service.domain.model.entities import ToolCallRequest
    from agent_service.domain.ports.tool_gateway import ToolInvocationContext
    from agent_service.infrastructure.tools.registry_bridge import (
        SharedToolRegistryBridge,
    )

    class _Rest:
        def call(self, tool, arguments, **kwargs):
            return ToolTransportResult(status=200, payload={'data': {}},
                                       text='{}')

    adapter, gateway_calls = _adapter(
        {'device_get': _ok({'system': 'Android'})},
        registry=RunCredentialRegistry())
    lease = FakeLease()
    service = ExplorationService(
        devices=adapter, leases=lease, artifacts=FakeArtifacts(),
        store=FakeStore())
    gateway = SharedToolGateway(
        bridge=SharedToolRegistryBridge(), rest=_Rest(),
        credentials=RunCredentialRegistry(), exploration=service)

    result = gateway.execute(
        ToolCallRequest(tool_call_id='c1', name='ui_tree',
                        arguments={'device_id': 3}),
        ToolInvocationContext(run_id=RUN_ID, session_id='s1', owner_id=7,
                              tenant_id='t1', step_id='st1',
                              permissions=('*',), idempotency_key='i1'))
    assert result.ok is False
    assert result.error_code == DEVICE_UNAVAILABLE
    assert lease.released == 1          # 租约已释放，不泄漏设备
    assert gateway_calls.calls == []    # 未发出任何匿名请求


def test_holder_reaches_adapter_from_service_session():
    """服务层用 session.run_id 作 holder：注册表里有该 run 凭据才成功。"""
    from agent_service.application.tool_gateway import SharedToolGateway
    from agent_service.domain.model.entities import ToolCallRequest
    from agent_service.domain.ports.tool_gateway import ToolInvocationContext
    from agent_service.infrastructure.tools.registry_bridge import (
        SharedToolRegistryBridge,
    )

    class _Rest:
        def call(self, tool, arguments, **kwargs):
            return ToolTransportResult(status=200, payload={'data': {}},
                                       text='{}')

    adapter, gateway_calls = _adapter({
        'device_get': _ok({'system': 'Android'}),
        'device_ui_tree': _ok(_tree_data(2)),
        'device_ui_screenshot': _ok({'screenshot_ref': 'oss://shot.png'}),
    })
    service = ExplorationService(
        devices=adapter, leases=FakeLease(), artifacts=FakeArtifacts(),
        store=FakeStore())
    gateway = SharedToolGateway(
        bridge=SharedToolRegistryBridge(), rest=_Rest(),
        credentials=RunCredentialRegistry(), exploration=service)

    context = ToolInvocationContext(
        run_id=RUN_ID, session_id='s1', owner_id=7, tenant_id='t1',
        step_id='st1', permissions=('*',), idempotency_key='i1')
    result = gateway.execute(
        ToolCallRequest(tool_call_id='c1', name='ui_tree',
                        arguments={'device_id': 3}), context)
    assert result.ok is True
    assert json.loads(result.content)['node_count'] == 2
    # 四个设备调用都带同一个 holder（run_id）
    assert {c['authorization'] for c in gateway_calls.calls} == {AUTH}
    assert gateway_calls.calls[0]['tool'] == 'device_get'


def test_ui_tree_without_device_port_still_reports_unavailable():
    """未注入端口时保持既有口径（不伪造空树）。"""
    from agent_service.application.tool_gateway import SharedToolGateway
    from agent_service.domain.model.entities import ToolCallRequest
    from agent_service.domain.ports.tool_gateway import ToolInvocationContext
    from agent_service.infrastructure.tools.registry_bridge import (
        SharedToolRegistryBridge,
    )

    class _Rest:
        def call(self, tool, arguments, **kwargs):
            return ToolTransportResult(status=200, payload={'data': {}},
                                       text='{}')

    service = ExplorationService(devices=None, leases=FakeLease(),
                                artifacts=FakeArtifacts(), store=FakeStore())
    gateway = SharedToolGateway(
        bridge=SharedToolRegistryBridge(), rest=_Rest(),
        credentials=RunCredentialRegistry(), exploration=service)
    result = gateway.execute(
        ToolCallRequest(tool_call_id='c1', name='ui_tree',
                        arguments={'device_id': 3}),
        ToolInvocationContext(run_id=RUN_ID, session_id='s1', owner_id=7,
                              tenant_id='t1', step_id='st1',
                              permissions=('*',), idempotency_key='i1'))
    assert result.ok is False
    assert result.error_code == 'EXPLORATION_UNAVAILABLE'
