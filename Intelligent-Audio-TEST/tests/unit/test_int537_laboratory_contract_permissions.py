# -*- coding: utf-8 -*-
"""INT-537 验收（拆分①）：契约 + 权限（INT-680 集成适配：契约切换为 INT-655 实现）。

原 INT-537 契约（子资源列表端点 /{id}/devices|playback_devices|test_cases、
写权限 lab:create/update/delete）已被 INT-655 实现取代：
- 端点：GET '' / GET {lab_id} / GET {lab_id}/summary / POST '' / PUT {lab_id} / DELETE {lab_id}
- 权限：读 device:read，写 device:create/update/delete（lab:* 单立码待后端立项切换）

本文件保留契约 + 权限的验收意图，服务打桩切换到 INT-655 新服务
（api_gateway.application.services.device.laboratory_*）。
"""
import os

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault('DATABASE_URL',
                      'sqlite:///' + __import__('tempfile').mkdtemp(
                          prefix='int537_contract_') + '/pytest.db')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

# 契约样例（设计文档 §5.4.1 / INT-655）
_LAB_ITEM = {
    'id': 1, 'code': 'LAB-A-01', 'name': '音频测试实验室1',
    'building': 'A栋', 'floor': '2楼', 'room_number': '201',
    'description': '主实验室', 'status': 'active',
    'device_count': 5, 'playback_device_count': 3, 'test_case_count': 120,
}
_LIST_PAYLOAD = {
    'success': True, 'code': 0, 'message': 'ok',
    'data': {'items': [_LAB_ITEM], 'total': 1, 'page': 1, 'per_page': 20, 'pages': 1},
}
_SUMMARY_PAYLOAD = {
    'success': True, 'code': 0, 'message': 'ok',
    'data': {'device_count': 5, 'playback_device_count': 3, 'test_case_count': 120},
}
_CREATE_PAYLOAD = {'success': True, 'code': 0, 'message': 'ok', 'data': {'id': 1}}
_UPDATE_PAYLOAD = {'success': True, 'code': 0, 'message': 'ok', 'data': {'id': 1}}
_DELETE_PAYLOAD = {'success': True, 'code': 0, 'message': 'ok', 'data': None}


def _token(permissions):
    from api_gateway.application.services.auth.token_service import TokenService
    return f'Bearer {TokenService.create_token(1, "int537_user", 1, permissions)}'


def _auth(permissions):
    return {'Authorization': _token(permissions)}


@pytest.fixture()
def client(monkeypatch):
    from api_gateway.config.config import Config
    # 真实 AuthMiddleware 走 prod 模式（合法取值 off|dev|prod；JWT 校验 →
    # request.state.permissions），dev/off 模式会注入通配 * 全部放行
    monkeypatch.setattr(Config, 'AUTH_MODE', 'prod')

    import api_gateway.application.services.device.laboratory_query_service as qmod
    import api_gateway.application.services.device.laboratory_command_service as cmod
    # 服务方法打桩（纯路由/权限验证，不触 gRPC/DB）
    qmod.LaboratoryQueryService.get_all = staticmethod(lambda: (_LIST_PAYLOAD, 200))
    qmod.LaboratoryQueryService.get_one = staticmethod(lambda lab_id: (_LAB_ITEM, 200))
    qmod.LaboratoryQueryService.get_summary = staticmethod(lambda lab_id: (_SUMMARY_PAYLOAD, 200))
    cmod.LaboratoryCommandService.create = staticmethod(lambda: (_CREATE_PAYLOAD, 201))
    cmod.LaboratoryCommandService.update = staticmethod(lambda lab_id: (_UPDATE_PAYLOAD, 200))
    cmod.LaboratoryCommandService.delete = staticmethod(lambda lab_id: (_DELETE_PAYLOAD, 200))

    from api_gateway.app import create_app
    app = create_app()
    with TestClient(app) as c:
        yield c


# ==================== 契约：路由注册 ====================

def test_laboratory_routes_registered_in_order():
    """端点注册在册；静态子路径（/summary）先于 /{lab_id}。"""
    from api_gateway.routes.laboratory_bp import router
    paths = [r.path for r in router.routes]
    assert '' in paths                       # GET/POST /api/v1/laboratories
    assert '/{lab_id}' in paths
    assert '/{lab_id}/summary' in paths
    assert paths.index('/{lab_id}/summary') < paths.index('/{lab_id}'), (
        f'子资源路由 /{{lab_id}}/summary 必须先于 /{{lab_id}} 注册，否则被 int 校验拦截 422')


def test_app_registers_laboratory_prefix():
    """create_app 挂载 /api/v1/laboratories 前缀。"""
    from api_gateway.app import app as gateway_app
    prefixes = []
    for r in gateway_app.routes:
        pfx = getattr(getattr(r, 'include_context', None), 'prefix', None)
        if pfx:
            prefixes.append(pfx)
        elif hasattr(r, 'path'):
            prefixes.append(r.path)
    assert any(str(p) == '/api/v1/laboratories' or str(p).startswith('/api/v1/laboratories')
               for p in prefixes), f'laboratories 前缀未注册，已注册: {prefixes}'


# ==================== 契约：响应结构 ====================

def test_list_contract_structure(client):
    resp = client.get('/api/v1/laboratories?page=1&per_page=20',
                      headers=_auth(['device:read']))
    assert resp.status_code == 200, resp.text
    data = resp.json()['data']
    assert {'items', 'total', 'page', 'per_page'} <= set(data)
    assert data['total'] == 1 and data['page'] == 1 and data['per_page'] == 20
    item = data['items'][0]
    assert {'id', 'code', 'name', 'building', 'floor', 'room_number',
            'description', 'status', 'device_count', 'playback_device_count',
            'test_case_count'} <= set(item)


def test_summary_contract_structure(client):
    resp = client.get('/api/v1/laboratories/1/summary', headers=_auth(['device:read']))
    assert resp.status_code == 200, resp.text
    assert set(resp.json()['data']) == {'device_count', 'playback_device_count',
                                        'test_case_count'}


# ==================== 权限 ====================

def test_anonymous_401(client):
    assert client.get('/api/v1/laboratories').status_code == 401
    assert client.post('/api/v1/laboratories', json={'code': 'X', 'name': 'Y'}).status_code == 401


def test_read_requires_device_read(client):
    assert client.get('/api/v1/laboratories', headers=_auth([])).status_code == 403
    assert client.get('/api/v1/laboratories/1', headers=_auth([])).status_code == 403
    assert client.get('/api/v1/laboratories/1/summary', headers=_auth([])).status_code == 403
    # device:read 放行读
    assert client.get('/api/v1/laboratories', headers=_auth(['device:read'])).status_code == 200


def test_write_requires_device_write_codes(client):
    # 无写码（仅 device:read）→ 403
    read_only = _auth(['device:read'])
    assert client.post('/api/v1/laboratories', headers=read_only,
                       json={'code': 'X', 'name': 'Y'}).status_code == 403
    assert client.put('/api/v1/laboratories/1', headers=read_only,
                      json={'name': 'Y'}).status_code == 403
    assert client.delete('/api/v1/laboratories/1', headers=read_only).status_code == 403

    # 持 device:create → POST 放行；无 device:update/delete 仍 403
    create_perm = _auth(['device:read', 'device:create'])
    assert client.post('/api/v1/laboratories', headers=create_perm,
                       json={'code': 'X', 'name': 'Y'}).status_code == 201
    assert client.put('/api/v1/laboratories/1', headers=create_perm,
                      json={'name': 'Y'}).status_code == 403
    assert client.delete('/api/v1/laboratories/1', headers=create_perm).status_code == 403


def test_update_and_delete_require_own_codes(client):
    update_perm = _auth(['device:read', 'device:update'])
    assert client.put('/api/v1/laboratories/1', headers=update_perm,
                      json={'name': 'Y'}).status_code == 200
    assert client.delete('/api/v1/laboratories/1', headers=update_perm).status_code == 403

    delete_perm = _auth(['device:read', 'device:delete'])
    assert client.delete('/api/v1/laboratories/1', headers=delete_perm).status_code == 200
