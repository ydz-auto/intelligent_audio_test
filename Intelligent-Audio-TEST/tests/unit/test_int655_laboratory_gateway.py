# -*- coding: utf-8 -*-
"""INT-655 专项：/api/v1/laboratories HTTP 契约 + DeviceItem/PlaybackDeviceItem lab 字段。

覆盖：
- 路由表：laboratory_bp 注册 GET ''/POST ''/GET {lab_id}/GET {lab_id}/summary/PUT {lab_id}/DELETE {lab_id}
  且权限为 device:read（读）与 device:create/update/delete（写）
- app.py 挂载前缀 /api/v1/laboratories
- HTTP 契约（FastAPI TestClient + 替身 ACL）：
  GET 列表（分页+资源统计）/ GET 详情 / GET summary / POST 201 / PUT / DELETE /
  POST code 冲突 → 409 / PUT 未知 → 404
- lab_name 网关装饰：DeviceItem/PlaybackDeviceItem 由 device_service 返回 lab_id，
  网关回填 lab_name
- schema：DeviceItem/PlaybackDeviceItem 含 lab_id/lab_name 字段
"""
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import api_gateway.application.services.device.laboratory_query_service as lqs_module
import api_gateway.application.services.device.laboratory_command_service as lcs_module
import api_gateway.application.services.device.lab_name_decorator as lnd_module
from api_gateway.middleware import RequestAdapterMiddleware, AuthMiddleware
from api_gateway.routes.laboratory_bp import router as laboratory_router
from api_gateway.schemas.device import DeviceItem
from api_gateway.schemas.playback import PlaybackDeviceItem
from api_gateway.schemas.laboratory import LaboratoryItem


LAB_ITEM = {
    'id': 1,
    'code': 'LAB-A-01',
    'name': '音频测试实验室1',
    'building': 'A栋',
    'floor': '2楼',
    'room_number': '201',
    'description': None,
    'status': 'active',
    'device_count': 5,
    'playback_device_count': 3,
    'test_case_count': 120,
    'created_at': '2026-10-18T00:00:00',
    'updated_at': '2026-10-18T00:00:00',
}


class FakeLaboratoryAcl:
    """网关 ACL 替身：模拟 gRPC 信封返回。"""

    def __init__(self, labs=None, next_id=10):
        self.labs = labs if labs is not None else {1: dict(LAB_ITEM)}
        self.next_id = next_id
        self.calls = []

    def get_all(self, page=1, per_page=10, keyword=None, status=None):
        self.calls.append(('get_all', page, per_page, keyword, status))
        items = [
            {**lab} for lab in self.labs.values()
            if (not keyword or keyword in lab['code'] or keyword in lab['name'])
            and (not status or lab['status'] == status)
        ]
        return {'success': True, 'message': 'ok',
                'data': {'items': items, 'total': len(items), 'page': page,
                         'per_page': per_page, 'pages': 1}, 'code': 200}

    def get_one(self, lab_id):
        self.calls.append(('get_one', lab_id))
        lab = self.labs.get(lab_id)
        if not lab:
            return {'success': False, 'message': '未找到实验室', 'data': None, 'code': 404}
        return {'success': True, 'message': 'ok', 'data': dict(lab), 'code': 200}

    def get_summary(self, lab_id):
        self.calls.append(('get_summary', lab_id))
        lab = self.labs.get(lab_id)
        if not lab:
            return {'success': False, 'message': '未找到实验室', 'data': None, 'code': 404}
        return {'success': True, 'message': 'ok', 'data': {
            'device_count': lab['device_count'],
            'playback_device_count': lab['playback_device_count'],
            'test_case_count': lab['test_case_count'],
        }, 'code': 200}

    def create(self, data):
        self.calls.append(('create', data))
        code = data['code']
        if any(lab['code'] == code for lab in self.labs.values()):
            return {'success': False, 'message': f'实验室代码 {code} 已存在', 'data': None, 'code': 409}
        lab_id = self.next_id
        self.next_id += 1
        lab = {'id': lab_id, 'code': code, 'name': data['name'],
               'building': data.get('building'), 'floor': data.get('floor'),
               'room_number': data.get('room_number'), 'description': data.get('description'),
               'status': data.get('status', 'active'),
               'device_count': 0, 'playback_device_count': 0, 'test_case_count': 0,
               'created_at': '2026-10-18T00:00:00', 'updated_at': '2026-10-18T00:00:00'}
        self.labs[lab_id] = lab
        return {'success': True, 'message': '实验室创建成功', 'data': {'id': lab_id}, 'code': 201}

    def update(self, lab_id, data):
        self.calls.append(('update', lab_id, data))
        lab = self.labs.get(lab_id)
        if not lab:
            return {'success': False, 'message': '未找到实验室', 'data': None, 'code': 404}
        if 'code' in data:
            if any(other['code'] == data['code'] and other_id != lab_id
                   for other_id, other in self.labs.items()):
                return {'success': False, 'message': f"实验室代码 {data['code']} 已存在", 'data': None, 'code': 409}
        lab.update(data)
        return {'success': True, 'message': '实验室更新成功', 'data': dict(lab), 'code': 200}

    def delete(self, lab_id):
        self.calls.append(('delete', lab_id))
        if lab_id not in self.labs:
            return {'success': False, 'message': '未找到实验室', 'data': None, 'code': 404}
        del self.labs[lab_id]
        return {'success': True, 'message': '实验室已删除', 'data': None, 'code': 200}


@pytest.fixture
def client(monkeypatch):
    fake = FakeLaboratoryAcl()
    monkeypatch.setattr(lqs_module, '_laboratory_acl', fake)
    monkeypatch.setattr(lcs_module, '_laboratory_acl', fake)

    app = FastAPI()
    app.add_middleware(AuthMiddleware, auth_mode='off')
    app.add_middleware(RequestAdapterMiddleware)
    app.include_router(laboratory_router, prefix='/api/v1/laboratories', tags=['laboratories'])

    test_client = TestClient(app)
    test_client.fake_acl = fake
    return test_client


# ══════════════ 1. 路由表 + 权限 ══════════════

def _find_route(path):
    for r in laboratory_router.routes:
        if getattr(r, 'path', None) == path:
            return r
    return None


def test_laboratory_routes_registered():
    expected = {
        ('', 'GET'), ('', 'POST'),
        ('/{lab_id}', 'GET'), ('/{lab_id}', 'PUT'), ('/{lab_id}', 'DELETE'),
        ('/{lab_id}/summary', 'GET'),
    }
    actual = {(r.path, method) for r in laboratory_router.routes
              for method in getattr(r, 'methods', set())}
    assert expected <= actual


def test_summary_route_before_dynamic_id():
    """静态段 /{lab_id}/summary 必须先于 /{lab_id} 注册，避免被 int 校验拦截。"""
    paths = [r.path for r in laboratory_router.routes]
    assert paths.index('/{lab_id}/summary') < paths.index('/{lab_id}')


def test_route_permissions():
    import inspect
    from api_gateway.routes.laboratory_bp import router as bp

    def _required(route):
        checker = route.dependant.dependencies[0].call
        required = next(
            c.cell_contents for c in (checker.__closure__ or ())
            if isinstance(c.cell_contents, (set, frozenset))
        )
        return set(required)

    by_path_method = {
        (r.path, next(iter(r.methods))): r
        for r in bp.routes if r.methods
    }
    assert _required(by_path_method[('', 'GET')]) == {'device:read'}
    assert _required(by_path_method[('', 'POST')]) == {'device:create'}
    assert _required(by_path_method[('/{lab_id}', 'GET')]) == {'device:read'}
    assert _required(by_path_method[('/{lab_id}/summary', 'GET')]) == {'device:read'}
    assert _required(by_path_method[('/{lab_id}', 'PUT')]) == {'device:update'}
    assert _required(by_path_method[('/{lab_id}', 'DELETE')]) == {'device:delete'}
    # 写权限源：device:* 码（lab:* 单立码待后端立项后切换）
    assert "require_permission('device:create')" in inspect.getsource(by_path_method[('', 'POST')].endpoint)


def test_app_mounts_laboratory_router():
    from pathlib import Path
    repo_root = Path(__file__).resolve().parents[2]
    src = (repo_root / 'api_gateway' / 'app.py').read_text(encoding='utf-8')
    assert "laboratory_router, prefix='/api/v1/laboratories'" in src


# ══════════════ 2. HTTP 契约 ══════════════

class TestLaboratoryHttp:
    def test_get_list(self, client):
        resp = client.get('/api/v1/laboratories')
        assert resp.status_code == 200
        body = resp.json()
        assert body['success'] is True
        data = body['data']
        assert data['total'] == 1
        item = data['items'][0]
        assert item['code'] == 'LAB-A-01'
        assert item['device_count'] == 5
        assert item['test_case_count'] == 120

    def test_get_list_status_filter(self, client, monkeypatch):
        fake = client.fake_acl
        resp = client.get('/api/v1/laboratories', params={'status': 'active'})
        assert resp.status_code == 200
        assert fake.calls[-1][0] == 'get_all'

    def test_get_list_invalid_status_400(self, client):
        resp = client.get('/api/v1/laboratories', params={'status': 'bogus'})
        assert resp.status_code == 400

    def test_get_one(self, client):
        resp = client.get('/api/v1/laboratories/1')
        assert resp.status_code == 200
        body = resp.json()
        assert body['data']['name'] == '音频测试实验室1'

    def test_get_one_404(self, client):
        resp = client.get('/api/v1/laboratories/999')
        assert resp.status_code == 404

    def test_get_summary(self, client):
        resp = client.get('/api/v1/laboratories/1/summary')
        assert resp.status_code == 200
        assert resp.json()['data']['device_count'] == 5

    def test_get_summary_404(self, client):
        resp = client.get('/api/v1/laboratories/999/summary')
        assert resp.status_code == 404

    def test_create_201(self, client):
        resp = client.post('/api/v1/laboratories', json={
            'code': 'LAB-B-01', 'name': '噪声实验室',
        })
        assert resp.status_code == 201
        body = resp.json()
        assert body['data']['id'] == 10
        assert body['success'] is True

    def test_create_duplicate_code_409(self, client):
        resp = client.post('/api/v1/laboratories', json={
            'code': 'LAB-A-01', 'name': '重复',
        })
        assert resp.status_code == 409
        assert '已存在' in resp.json()['message']

    def test_create_invalid_status_400(self, client):
        resp = client.post('/api/v1/laboratories', json={
            'code': 'LAB-X', 'name': 'X', 'status': 'bogus',
        })
        assert resp.status_code == 400

    def test_update(self, client):
        resp = client.put('/api/v1/laboratories/1', json={'name': '改名'})
        assert resp.status_code == 200
        assert resp.json()['data']['name'] == '改名'

    def test_update_404(self, client):
        resp = client.put('/api/v1/laboratories/999', json={'name': 'x'})
        assert resp.status_code == 404

    def test_update_code_conflict_409(self, client, monkeypatch):
        fake = client.fake_acl
        # 预置第二个实验室
        fake.create({'code': 'LAB-B-01', 'name': 'B'})
        resp = client.put('/api/v1/laboratories/1', json={'code': 'LAB-B-01'})
        assert resp.status_code == 409

    def test_delete(self, client):
        resp = client.delete('/api/v1/laboratories/1')
        assert resp.status_code == 200
        assert client.fake_acl.labs == {}

    def test_delete_404(self, client):
        resp = client.delete('/api/v1/laboratories/999')
        assert resp.status_code == 404


# ══════════════ 3. lab_name 网关装饰 ══════════════

def test_device_list_decorates_lab_names(monkeypatch):
    """device_query_service.get_all：device_service 返回 lab_id，网关回填 lab_name。"""
    import api_gateway.application.services.device.device_query_service as dqs
    import api_gateway.application.services.device.lab_name_decorator as lnd

    class FakeDeviceAcl:
        def get_all(self, **kwargs):
            return {'success': True, 'message': 'ok', 'code': 200,
                    'data': {'items': [
                        {'id': 1, 'name': 'd1', 'lab_id': 2},
                        {'id': 2, 'name': 'd2', 'lab_id': None},
                    ], 'total': 2, 'page': 1, 'per_page': 10, 'pages': 1}}

    class FakeRequest:
        args = type('A', (), {'to_dict': lambda self: {}})()

    monkeypatch.setattr(dqs, '_device_acl', FakeDeviceAcl())
    monkeypatch.setattr(dqs, 'request', FakeRequest())
    monkeypatch.setattr(lnd, '_fetch_lab_name_map', lambda ids: {2: '音频测试实验室1'})

    payload, code = dqs.DeviceQueryService.get_all()
    assert code == 200
    items = payload['data']['items']
    assert items[0]['lab_name'] == '音频测试实验室1'
    assert items[1]['lab_name'] is None


def test_decorate_lab_names(monkeypatch):
    items = [
        {'id': 1, 'name': 'd1', 'lab_id': 2},
        {'id': 2, 'name': 'd2', 'lab_id': None},
    ]
    monkeypatch.setattr(lnd_module, '_fetch_lab_name_map', lambda ids: {2: '音频测试实验室1'})
    decorated = lnd_module._decorate_lab_names(items)
    assert decorated[0]['lab_name'] == '音频测试实验室1'
    assert decorated[1]['lab_name'] is None
    # 不修改原 item（就地更新符合服务层惯例）
    assert items[0]['lab_name'] == '音频测试实验室1'


def test_decorate_skips_when_no_lab_id(monkeypatch):
    items = [{'id': 1, 'name': 'd1', 'lab_id': None}]
    called = []

    def _fetch(ids):
        called.append(ids)
        return {}

    monkeypatch.setattr(lnd_module, '_fetch_lab_name_map', _fetch)
    lnd_module._decorate_lab_names(items)
    assert called == []


def test_fetch_lab_name_map(monkeypatch):
    class FakeAcl:
        def __init__(self):
            self.labs = [{'id': 1, 'name': 'A'}, {'id': 2, 'name': 'B'}]

        def get_all(self, **kwargs):
            return {'success': True, 'message': 'ok',
                    'data': {'items': self.labs, 'total': 2}, 'code': 200}

    monkeypatch.setattr(
        'api_gateway.infrastructure.acl.LaboratoryAclRepositoryImpl', FakeAcl)
    result = lnd_module._fetch_lab_name_map({1, 2})
    assert result == {1: 'A', 2: 'B'}


def test_fetch_lab_name_map_grpc_down_returns_none(monkeypatch):
    class FailingAcl:
        def get_all(self, **kwargs):
            return {'success': False, 'message': 'down', 'data': None, 'code': 400}

    monkeypatch.setattr(
        'api_gateway.infrastructure.acl.LaboratoryAclRepositoryImpl', FailingAcl)
    assert lnd_module._fetch_lab_name_map({1}) is None


# ══════════════ 4. Schema lab 字段 ══════════════

def test_device_item_has_lab_fields():
    item = DeviceItem.model_validate({
        'id': 1, 'name': 'd1', 'model': 'm', 'type': 'phone', 'system': 'Android',
        'system_version': '14', 'app_name': 'a', 'app_version': '1',
        'lab_id': 2, 'lab_name': '音频测试实验室1',
    })
    assert item.lab_id == 2
    assert item.lab_name == '音频测试实验室1'


def test_playback_item_has_lab_fields():
    item = PlaybackDeviceItem.model_validate({
        'id': 1, 'name': 'p1', 'model': 'm', 'device_type': 'dry',
        'sample_rate': 44100, 'device_unique_id': 'u',
        'lab_id': 3, 'lab_name': '噪声实验室',
    })
    assert item.lab_id == 3
    assert item.lab_name == '噪声实验室'


def test_laboratory_item_shape():
    item = LaboratoryItem.model_validate(LAB_ITEM)
    assert item.device_count == 5
    assert item.test_case_count == 120
