# -*- coding: utf-8 -*-
"""INT-2578 专项：设备 UI 探索网关三端点（读树 / 截图 / 动作）。

INT-2569（设备侧 UI 探索通道）拆分卡 2/4。覆盖：

- 路由表：``/api/v1/test-devices/{id}/ui/{tree,screenshot,action}`` 三端点；
  读树 / 截图要 ``device:read``，动作要 ``device:control``（缺权限 403）
- 业务码 → HTTP：``DEVICE_NOT_FOUND`` 404 / 非七枚举 ``ACTION_NOT_ALLOWED`` 400 /
  ``BUSY`` 409 / 上游不可达 ``UI_CAPTURE_UNAVAILABLE`` 503，且 ``code`` 原样透传
- 动作端点每次调用写一条设备审计（``DEVICE_CONTROL_EXECUTED``）
- 读树 / 截图不回 base64 整图（截图只回 ``screenshot_ref`` 对象键）
- gRPC 代理：``_DeviceUiProxy`` 不可达兜底与信封 ``code`` 透传

测试基建对齐 tests/unit/test_int655_laboratory_gateway.py（最小 app +
RequestAdapterMiddleware + 假认证中间件），ACL 以替身避免触达真实 gRPC。
"""
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import api_gateway.application.services.device.device_ui_service as dui
from api_gateway.infrastructure.grpc_proxies import device_proxies
from api_gateway.middleware import RequestAdapterMiddleware
from api_gateway.routes.device_bp import router as device_router
from shared.constants.ui_capture import UI_ACTION_TYPE_VALUES
from shared.models.common_enums import AuditEvent

PREFIX = '/api/v1/test-devices'
UI_BASE = f'{PREFIX}/7'

TREE_DATA = {
    'platform': 'ANDROID',
    'format': 'ANDROID_XML',
    'payload': '<hierarchy><node text="首页"/></hierarchy>',
    'node_count': 1,
    'degraded': False,
    'degrade_reason': None,
}
SCREENSHOT_DATA = {
    'screenshot_ref': 'device-ui/sn-1/1763100000000-abcd1234.png',
    'format': 'PNG',
    'width': 1080,
    'height': 2340,
}
ACTION_DATA = {'action_type': 'TAP', 'performed': True, 'elapsed_ms': 42}


def _ok(data):
    return {'success': True, 'message': 'ok', 'code': '', 'data': data}


def _fail(code, message='failed', data=None):
    return {'success': False, 'message': message, 'code': code, 'data': data}


class FakeDeviceUiAcl:
    """网关 ACL 替身：模拟 ``DeviceUiService`` 的信封（code 为字符串业务码）。"""

    def __init__(self):
        self.calls = []
        self.tree_result = _ok(dict(TREE_DATA))
        self.screenshot_result = _ok(dict(SCREENSHOT_DATA))
        self.action_result = _ok(dict(ACTION_DATA))

    def dump_ui_tree(self, device_id):
        self.calls.append(('dump_ui_tree', device_id))
        return dict(self.tree_result)

    def capture_ui_screenshot(self, device_id, label=None):
        self.calls.append(('capture_ui_screenshot', device_id, label))
        return dict(self.screenshot_result)

    def perform_ui_action(self, device_id, action_type, node=None, params=None):
        self.calls.append(('perform_ui_action', device_id, action_type, node, params))
        return dict(self.action_result)


@pytest.fixture
def acl(monkeypatch):
    fake = FakeDeviceUiAcl()
    monkeypatch.setattr(dui, '_device_ui_acl', fake)
    return fake


@pytest.fixture
def audits(monkeypatch):
    """拦截 write_device_audit，记录 (event, module, content)。"""
    calls = []
    monkeypatch.setattr(
        dui, 'write_device_audit',
        lambda event, module, content: calls.append((event, module, content)),
    )
    return calls


@pytest.fixture
def client(acl):
    app = FastAPI()
    app.add_middleware(RequestAdapterMiddleware)

    @app.middleware('http')
    async def _fake_auth(request, call_next):
        """对齐 AuthMiddleware：按测试头注入 request.state.permissions。"""
        raw = request.headers.get('X-Test-Perms', '*')
        request.state.permissions = [p for p in raw.split(',') if p]
        request.state.user_id = 1
        request.state.username = 'tester'
        return await call_next(request)

    app.include_router(device_router, prefix=PREFIX, tags=['devices'])
    test_client = TestClient(app)
    test_client.fake_acl = acl
    return test_client


# ══════════════ 1. 路由表 + 权限 ══════════════

def test_ui_routes_registered():
    """三端点注册在 device_bp，方法与卡面一致。"""
    routes = {
        (route.path, tuple(sorted(route.methods)))
        for route in device_router.routes
        if getattr(route, 'path', '').endswith(('/ui/tree', '/ui/screenshot', '/ui/action'))
    }
    assert routes == {
        ('/{device_id}/ui/tree', ('POST',)),
        ('/{device_id}/ui/screenshot', ('POST',)),
        ('/{device_id}/ui/action', ('POST',)),
    }


def test_openapi_contains_ui_paths(client):
    """网关 openapi 指纹含三个新路径（部署后 M2 收口复核用）。"""
    paths = client.get('/openapi.json').json()['paths']
    for suffix in ('/ui/tree', '/ui/screenshot', '/ui/action'):
        assert f'{PREFIX}/{{device_id}}{suffix}' in paths
        assert 'post' in paths[f'{PREFIX}/{{device_id}}{suffix}']


@pytest.mark.parametrize('path', ['/ui/tree', '/ui/screenshot'])
def test_read_endpoints_require_device_read(client, path):
    """读树 / 截图：无 device:read 403；有则放行。"""
    denied = client.post(f'{UI_BASE}{path}', json={}, headers={'X-Test-Perms': ''})
    assert denied.status_code == 403
    allowed = client.post(f'{UI_BASE}{path}', json={}, headers={'X-Test-Perms': 'device:read'})
    assert allowed.status_code == 200


def test_action_requires_device_control(client, audits):
    """动作端点：device:read 不放行，device:control 才放行。"""
    body = {'action_type': 'TAP', 'node': {'resource_id': 'x'}}
    denied = client.post(f'{UI_BASE}/ui/action', json=body,
                         headers={'X-Test-Perms': 'device:read'})
    assert denied.status_code == 403
    assert audits == []  # 权限在路由依赖层拦截，未进服务

    allowed = client.post(f'{UI_BASE}/ui/action', json=body,
                          headers={'X-Test-Perms': 'device:control'})
    assert allowed.status_code == 200


# ══════════════ 2. 读树 / 截图契约 ══════════════

def test_dump_tree_success(client, acl):
    resp = client.post(f'{UI_BASE}/ui/tree', json={})
    assert resp.status_code == 200
    body = resp.json()
    assert body['success'] is True
    assert body['code'] == ''
    assert body['data'] == TREE_DATA
    assert acl.calls[-1] == ('dump_ui_tree', 7)


def test_screenshot_returns_ref_not_base64(client, acl):
    """截图只回 screenshot_ref 对象键，不返回 base64 整图。"""
    resp = client.post(f'{UI_BASE}/ui/screenshot', json={'label': 'a3'})
    assert resp.status_code == 200
    data = resp.json()['data']
    assert data['screenshot_ref'] == SCREENSHOT_DATA['screenshot_ref']
    assert set(data) == {'screenshot_ref', 'format', 'width', 'height'}
    # 任何形态的整图内容都不允许出现在响应里
    dumped = str(resp.content)
    assert 'base64' not in dumped.lower()
    assert 'iVBOR' not in dumped  # PNG base64 魔数
    assert acl.calls[-1] == ('capture_ui_screenshot', 7, 'a3')


def test_screenshot_without_body_ok(client):
    """label 可省略（请求体 {} / 空体均可）。"""
    resp = client.post(f'{UI_BASE}/ui/screenshot', json={})
    assert resp.status_code == 200


# ══════════════ 3. 动作端点：七枚举白名单 + 参数校验 ══════════════

def test_action_seven_enum_values_are_the_card_contract():
    assert UI_ACTION_TYPE_VALUES == (
        'TAP', 'LONG_PRESS', 'SWIPE', 'INPUT_TEXT', 'BACK', 'HOME', 'WAIT')


@pytest.mark.parametrize('action_type', ['TAP', 'wait'])
def test_action_accepted(client, acl, audits, action_type):
    """七枚举放行（大小写归一），ACL 收到大写枚举值与 node/params。"""
    resp = client.post(f'{UI_BASE}/ui/action', json={
        'action_type': action_type,
        'node': {'text': '开始'},
        'params': {'seconds': 1},
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body['success'] is True
    assert body['data'] == ACTION_DATA
    call = acl.calls[-1]
    assert call[0] == 'perform_ui_action' and call[2] == action_type.upper()
    assert call[3] == {'text': '开始'} and call[4] == {'seconds': 1}
    # 动作每次调用一条设备审计
    assert len(audits) == 1
    assert audits[0][0] is AuditEvent.DEVICE_CONTROL_EXECUTED
    assert audits[0][1] == 'device_ui'
    assert audits[0][2]['action_type'] == action_type.upper()
    assert audits[0][2]['success'] is True


@pytest.mark.parametrize('action_type', ['DOUBLE_TAP', 'SCROLL', '', 'tap; rm -rf /'])
def test_action_non_enum_rejected_400(client, acl, audits, action_type):
    """非七枚举一律 400 ``ACTION_NOT_ALLOWED``，不触达 device_service。"""
    resp = client.post(f'{UI_BASE}/ui/action', json={'action_type': action_type})
    assert resp.status_code == 400
    body = resp.json()
    assert body['success'] is False
    assert body['code'] == 'ACTION_NOT_ALLOWED'
    assert acl.calls == []  # 网关先拦，不下发
    # 被拦截的动作同样留审计
    assert len(audits) == 1
    assert audits[0][0] is AuditEvent.DEVICE_CONTROL_EXECUTED
    assert audits[0][2]['success'] is False
    assert audits[0][2]['code'] == 'ACTION_NOT_ALLOWED'


@pytest.mark.parametrize('payload', [
    {'action_type': 'TAP', 'node': 'not-a-dict'},
    {'action_type': 'TAP', 'params': ['x']},
    {'node': {}},  # 缺 action_type
])
def test_action_invalid_body_400(client, acl, audits, payload):
    """参数非法 → 400（ACTION_NOT_ALLOWED），不触达 device_service、不写审计。"""
    resp = client.post(f'{UI_BASE}/ui/action', json=payload)
    assert resp.status_code == 400
    assert resp.json()['code'] == 'ACTION_NOT_ALLOWED'
    assert acl.calls == []
    assert audits == []


def test_action_missing_device_404(client, acl, audits):
    acl.action_result = _fail('DEVICE_NOT_FOUND', '设备 7 不存在')
    resp = client.post(f'{UI_BASE}/ui/action', json={'action_type': 'HOME'})
    assert resp.status_code == 404
    body = resp.json()
    assert body['code'] == 'DEVICE_NOT_FOUND'
    assert body['message'] == '设备 7 不存在'
    assert audits[0][2]['success'] is False
    assert audits[0][2]['code'] == 'DEVICE_NOT_FOUND'


# ══════════════ 4. 业务码 → HTTP 映射（code 透传） ══════════════

@pytest.mark.parametrize('code,http_status,path,has_audit', [
    ('DEVICE_NOT_FOUND', 404, '/ui/tree', False),
    ('BUSY', 409, '/ui/action', True),
    ('UI_CAPTURE_UNAVAILABLE', 503, '/ui/tree', False),
    ('UI_CAPTURE_UNAVAILABLE', 503, '/ui/screenshot', False),
    ('ELEMENT_NOT_FOUND', 400, '/ui/action', True),
    ('TREE_TOO_LARGE', 400, '/ui/tree', False),
    ('PLATFORM_UNSUPPORTED', 400, '/ui/screenshot', False),
])
def test_error_code_http_mapping(client, acl, audits, code, http_status, path, has_audit):
    """错误码映射 HTTP，且 ``code`` 原样透传（不靠 message 判型）。"""
    failure = _fail(code, f'{code} 的人话解释', {'degraded': True})
    if path == '/ui/tree':
        acl.tree_result = failure
    elif path == '/ui/screenshot':
        acl.screenshot_result = failure
    else:
        acl.action_result = failure

    payload = {'action_type': 'TAP'} if path == '/ui/action' else {}
    resp = client.post(f'{UI_BASE}{path}', json=payload)
    assert resp.status_code == http_status
    body = resp.json()
    assert body['success'] is False
    assert body['code'] == code
    assert body['message'] == f'{code} 的人话解释'
    assert body['data'] == {'degraded': True}
    assert bool(audits) is has_audit


def test_unknown_business_code_not_masked_as_400(client, acl):
    """未登记业务码 = 契约漂移，按 500 暴露，不掩成参数错误。"""
    acl.tree_result = _fail('SOMETHING_NEW')
    resp = client.post(f'{UI_BASE}/ui/tree', json={})
    assert resp.status_code == 500
    assert resp.json()['code'] == 'SOMETHING_NEW'


# ══════════════ 5. gRPC 代理（不可达 / 信封透传） ══════════════

class _BoomStub:
    """模拟 device_service 不可达：任何 RPC 都抛连接异常。"""

    def __getattr__(self, name):
        def _raise(*args, **kwargs):
            raise RuntimeError('failed to connect to device_service:50053')
        return _raise


class _StubResponse:
    def __init__(self, success, code, message='', data=''):
        self.success = success
        self.code = code
        self.message = message
        self.data = data


@pytest.mark.parametrize('method,args', [
    ('dump_ui_tree', (7,)),
    ('perform_ui_action', (7, 'TAP', {'text': 'x'}, {'seconds': 1})),
    ('capture_ui_screenshot', (7, 'a3')),
])
def test_proxy_unreachable_maps_to_ui_capture_unavailable(monkeypatch, method, args):
    """上游不可达 → ``UI_CAPTURE_UNAVAILABLE``（网关据此 503），不抛 500 栈。"""
    monkeypatch.setattr(device_proxies, 'get_device_ui_service_stub', lambda: _BoomStub())
    result = getattr(device_proxies.device_ui_proxy, method)(*args)
    assert result['success'] is False
    assert result['code'] == 'UI_CAPTURE_UNAVAILABLE'
    assert result['data'] is None


def test_proxy_passes_business_code_through(monkeypatch):
    """servicer 的字符串业务码原样透传，代理不自行改写。"""
    class _ActionStub:
        def PerformUiAction(self, request):
            # 网关已把 node/params 序列化为 JSON 字符串
            assert request.action_type == 'TAP'
            assert request.node == '{"text": "x"}'
            return _StubResponse(False, 'BUSY', '设备忙', '{"holder": {"run_id": "r1"}}')

    monkeypatch.setattr(device_proxies, 'get_device_ui_service_stub', lambda: _ActionStub())
    result = device_proxies.device_ui_proxy.perform_ui_action(
        7, 'TAP', node={'text': 'x'}, params=None)
    assert result == {
        'success': False,
        'message': '设备忙',
        'code': 'BUSY',
        'data': {'holder': {'run_id': 'r1'}},
    }


def test_proxy_success_envelope(monkeypatch):
    """成功信封：data 解析为 JSON、code 为空串（与卡 1 gRPC 同形）。"""
    class _TreeStub:
        def DumpUiTree(self, request):
            assert request.device_id == 7
            return _StubResponse(True, '', 'ok', '{"platform": "ANDROID", "node_count": 3}')

    monkeypatch.setattr(device_proxies, 'get_device_ui_service_stub', lambda: _TreeStub())
    result = device_proxies.device_ui_proxy.dump_ui_tree(7)
    assert result == {
        'success': True,
        'message': 'ok',
        'code': '',
        'data': {'platform': 'ANDROID', 'node_count': 3},
    }


def test_proxy_failure_without_code_falls_back(monkeypatch):
    """失败但 servicer 没填 code（契约漂移）→ 兜底 UI_CAPTURE_UNAVAILABLE，不返回空码。"""
    class _NoCodeStub:
        def CaptureUiScreenshot(self, request):
            return _StubResponse(False, '', '截图失败', '')

    monkeypatch.setattr(device_proxies, 'get_device_ui_service_stub', lambda: _NoCodeStub())
    result = device_proxies.device_ui_proxy.capture_ui_screenshot(7)
    assert result['success'] is False
    assert result['code'] == 'UI_CAPTURE_UNAVAILABLE'
    assert result['data'] is None
