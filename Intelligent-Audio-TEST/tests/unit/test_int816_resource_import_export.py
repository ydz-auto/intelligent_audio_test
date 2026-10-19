# -*- coding: utf-8 -*-
"""INT-816 三资源（test-devices / playback-devices / apis）导入导出单测。

覆盖：
- 导出：GET /{resource}/export?ids=&format=json|excel → 附件文件流，
  JSON 内容含 resource_key / exported_at / total_count；ids 过滤生效
- 导入：POST /{resource}/import（multipart）→ 计数报告
  （imported / updated / skipped），匹配键行为：测试设备=serial_number、
  播放设备=device_unique_id（兜底 name）、API=name；非法行跳过
- 错误路径：未上传文件 / 空文件 / 不支持格式
"""
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import api_gateway.application.services.device.device_import_export_service as svc_module
from api_gateway.middleware import RequestAdapterMiddleware


class FakeAcl:
    """记录 create/update 入参的内存 ACL（get_all 返回预置 existing）。"""

    def __init__(self, existing=None):
        self.existing = list(existing or [])
        self.create_calls = []
        self.update_calls = []
        self.get_all_calls = 0
        self._next_id = 100

    def get_all(self, **kwargs):
        self.get_all_calls += 1
        return {
            'success': True,
            'message': 'ok',
            'data': {
                'items': list(self.existing),
                'total': len(self.existing),
                'page': 1,
                'per_page': kwargs.get('per_page', 10),
                'pages': 1,
            },
            'code': 200,
        }

    def create(self, data):
        self.create_calls.append(data)
        item = dict(data)
        item['id'] = self._next_id
        self._next_id += 1
        self.existing.append(item)
        return {'success': True, 'message': 'ok', 'data': {'id': item['id']}, 'code': 200}

    def update(self, device_id, data):
        self.update_calls.append((device_id, data))
        return {'success': True, 'message': 'ok', 'data': {'id': device_id}, 'code': 200}


_ROUTES = {
    'test-devices': ('api_gateway.routes.device_bp', '/api/v1/test-devices'),
    'playback-devices': ('api_gateway.routes.playback_bp', '/api/v1/playback-devices'),
    'apis': ('api_gateway.routes.api_bp', '/api/v1/apis'),
}


def _make_client(monkeypatch, fake_acl, resource):
    """替换 spec.acl 为 FakeAcl，并挂载对应资源路由（fake auth 注入 admin 权限）。"""
    spec = svc_module._RESOURCE_SPECS[resource]
    monkeypatch.setattr(spec, 'acl', fake_acl)

    module_path, prefix = _ROUTES[resource]
    router = __import__(module_path, fromlist=['router']).router

    app = FastAPI()
    app.add_middleware(RequestAdapterMiddleware)

    @app.middleware('http')
    async def _fake_auth(request, call_next):
        request.state.permissions = ['*']
        return await call_next(request)

    app.include_router(router, prefix=prefix)
    return TestClient(app)


def _post_file(client, url, filename, payload, content_type='application/json'):
    content = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    return client.post(url, files={'file': (filename, content, content_type)})


# ==================== 导出 ====================


class TestExportTestDevices:

    def test_json_export_full(self, monkeypatch):
        fake = FakeAcl(existing=[
            {'id': 1, 'name': '设备A', 'model': 'M1', 'type': 'Android',
             'system': 'Android', 'serial_number': 'SN-001'},
            {'id': 2, 'name': '设备B', 'model': 'M2', 'type': 'Android',
             'system': 'Android', 'serial_number': 'SN-002'},
        ])
        client = _make_client(monkeypatch, fake, 'test-devices')

        resp = client.get('/api/v1/test-devices/export')

        assert resp.status_code == 200
        assert resp.headers['content-disposition'].startswith('attachment')
        data = json.loads(resp.content)
        assert data['total_count'] == 2
        assert data['test_devices'][0]['serial_number'] == 'SN-001'

    def test_json_export_ids_filter(self, monkeypatch):
        fake = FakeAcl(existing=[
            {'id': 1, 'name': '设备A', 'serial_number': 'SN-001'},
            {'id': 2, 'name': '设备B', 'serial_number': 'SN-002'},
        ])
        client = _make_client(monkeypatch, fake, 'test-devices')

        resp = client.get('/api/v1/test-devices/export', params={'ids': '2'})

        data = json.loads(resp.content)
        assert data['total_count'] == 1
        # 导出行不含内部 id（导出字段=可回灌导入的 create/update 字段集），按匹配键断言
        assert data['test_devices'][0]['serial_number'] == 'SN-002'

    def test_excel_export(self, monkeypatch):
        fake = FakeAcl(existing=[
            {'id': 1, 'name': '设备A', 'model': 'M1', 'type': 'Android',
             'system': 'Android', 'serial_number': 'SN-001'},
        ])
        client = _make_client(monkeypatch, fake, 'test-devices')

        resp = client.get('/api/v1/test-devices/export', params={'format': 'excel'})

        assert resp.status_code == 200
        assert resp.headers['content-type'].startswith(
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        assert resp.content[:2] == b'PK'  # xlsx = zip 魔数
        assert '.xlsx' in resp.headers['content-disposition']

    def test_export_unsupported_format(self, monkeypatch):
        fake = FakeAcl(existing=[{'id': 1, 'name': 'A'}])
        client = _make_client(monkeypatch, fake, 'test-devices')

        resp = client.get('/api/v1/test-devices/export', params={'format': 'csv'})

        assert resp.status_code == 400
        assert resp.json()['success'] is False


class TestExportPlaybackAndApis:

    def test_playback_json_export(self, monkeypatch):
        fake = FakeAcl(existing=[
            {'id': 1, 'name': '音箱1', 'device_type': 'Speaker',
             'sample_rate': 44100, 'device_unique_id': 'UID-001'},
        ])
        client = _make_client(monkeypatch, fake, 'playback-devices')

        resp = client.get('/api/v1/playback-devices/export')

        data = json.loads(resp.content)
        assert data['total_count'] == 1
        assert data['playback_devices'][0]['device_unique_id'] == 'UID-001'

    def test_apis_json_export(self, monkeypatch):
        fake = FakeAcl(existing=[
            {'id': 1, 'name': 'API-1', 'api_url': 'http://example.com'},
        ])
        client = _make_client(monkeypatch, fake, 'apis')

        resp = client.get('/api/v1/apis/export')

        data = json.loads(resp.content)
        assert data['total_count'] == 1
        assert data['apis'][0]['name'] == 'API-1'


# ==================== 导入 ====================


class TestImportTestDevices:

    def _existing_device(self):
        return {
            'id': 1, 'name': '设备A', 'model': 'M1', 'type': 'Android',
            'system': 'Android', 'system_version': '10',
            'app_name': 'app', 'app_version': '1.0', 'serial_number': 'SN-001',
        }

    def test_mixed_import_counts(self, monkeypatch):
        fake = FakeAcl(existing=[self._existing_device()])
        client = _make_client(monkeypatch, fake, 'test-devices')

        payload = {"test_devices": [
            # 匹配 SN-001 → 更新
            {"name": "设备A", "model": "M1", "type": "Android", "system": "Android",
             "system_version": "10", "app_name": "app", "app_version": "1.0",
             "serial_number": "SN-001", "location": "房间1"},
            # 未匹配 → 新建
            {"name": "设备B", "model": "M2", "type": "Android", "system": "Android",
             "system_version": "11", "app_name": "app", "app_version": "2.0",
             "serial_number": "SN-002"},
            # 无 serial_number → 跳过
            {"name": "设备C", "model": "M3", "type": "Android", "system": "Android",
             "system_version": "12", "app_name": "app", "app_version": "3.0"},
            # 有 serial 但缺必填 → 跳过
            {"name": "设备D", "serial_number": "SN-004"},
        ]}
        resp = _post_file(client, '/api/v1/test-devices/import', 'devices.json', payload)

        assert resp.status_code == 200
        body = resp.json()
        assert body['success'] is True
        assert body['data']['imported_count'] == 1
        assert body['data']['updated_count'] == 1
        assert body['data']['skipped_count'] == 2
        assert len(body['data']['errors']) == 2

        # 更新命中 id=1；新建 payload 带 serial_number=SN-002
        assert fake.update_calls[0][0] == 1
        assert fake.update_calls[0][1]['location'] == '房间1'
        assert fake.create_calls[0]['serial_number'] == 'SN-002'

    def test_json_plain_list_payload(self, monkeypatch):
        fake = FakeAcl(existing=[])
        client = _make_client(monkeypatch, fake, 'test-devices')

        payload = [
            {"name": "设备E", "model": "M4", "type": "Android", "system": "Android",
             "system_version": "13", "app_name": "app", "app_version": "4.0",
             "serial_number": "SN-010"},
        ]
        resp = _post_file(client, '/api/v1/test-devices/import', 'devices.json', payload)

        assert resp.json()['data']['imported_count'] == 1
        assert fake.create_calls[0]['serial_number'] == 'SN-010'


class TestImportPlaybackDevices:

    def test_match_by_unique_id_and_fallback_name(self, monkeypatch):
        fake = FakeAcl(existing=[
            {'id': 1, 'name': '音箱1', 'model': 'SPK', 'device_type': 'Speaker',
             'sample_rate': 44100, 'device_unique_id': 'UID-001',
             'channel_index': 0, 'status': 'online'},
        ])
        client = _make_client(monkeypatch, fake, 'playback-devices')

        payload = {"playback_devices": [
            # 按 device_unique_id 匹配 → 更新
            {"name": "音箱1", "model": "SPK", "device_type": "Speaker",
             "sample_rate": 44100, "device_unique_id": "UID-001",
             "channel_index": 0, "description": "updated"},
            # 按 name 兜底匹配 → 更新（行缺 device_unique_id）
            {"name": "音箱1", "model": "SPK", "device_type": "Speaker",
             "sample_rate": 44100, "channel_index": 0, "description": "name-matched"},
            # 未匹配 → 新建
            {"name": "新音箱", "model": "SPK2", "device_type": "Speaker",
             "sample_rate": 48000, "device_unique_id": "UID-002"},
            # 无键且不匹配 → 跳过
            {"name": "不存在音箱", "model": "SPK3", "device_type": "Speaker",
             "sample_rate": 44100},
        ]}
        resp = _post_file(client, '/api/v1/playback-devices/import', 'playback.json', payload)

        body = resp.json()
        assert body['success'] is True
        assert body['data']['imported_count'] == 1
        assert body['data']['updated_count'] == 2
        assert body['data']['skipped_count'] == 1

        assert [c[0] for c in fake.update_calls] == [1, 1]
        assert fake.create_calls[0]['device_unique_id'] == 'UID-002'


class TestImportApis:

    def test_match_by_name(self, monkeypatch):
        fake = FakeAcl(existing=[
            {'id': 1, 'name': 'API-1', 'api_url': 'http://old'},
        ])
        client = _make_client(monkeypatch, fake, 'apis')

        payload = {"apis": [
            {"name": "API-1", "api_url": "http://new", "status": "online"},  # 更新
            {"name": "API-2", "api_url": "http://two"},                      # 新建
            {"api_url": "http://no-name"},                                   # 无 name → 跳过
        ]}
        resp = _post_file(client, '/api/v1/apis/import', 'apis.json', payload)

        body = resp.json()
        assert body['success'] is True
        assert body['data']['imported_count'] == 1
        assert body['data']['updated_count'] == 1
        assert body['data']['skipped_count'] == 1

        assert fake.update_calls[0][0] == 1
        assert fake.update_calls[0][1]['api_url'] == 'http://new'
        assert fake.create_calls[0]['name'] == 'API-2'


class TestImportErrorPaths:

    def test_missing_file(self, monkeypatch):
        fake = FakeAcl(existing=[])
        client = _make_client(monkeypatch, fake, 'test-devices')

        resp = client.post('/api/v1/test-devices/import')

        assert resp.status_code == 400
        assert resp.json()['success'] is False

    def test_unsupported_format(self, monkeypatch):
        fake = FakeAcl(existing=[])
        client = _make_client(monkeypatch, fake, 'test-devices')

        resp = client.post('/api/v1/test-devices/import',
                           files={'file': ('x.txt', b'abc', 'text/plain')})

        assert resp.status_code == 400
        assert resp.json()['success'] is False

    def test_empty_file(self, monkeypatch):
        fake = FakeAcl(existing=[])
        client = _make_client(monkeypatch, fake, 'test-devices')

        resp = _post_file(client, '/api/v1/test-devices/import', 'empty.json', {"test_devices": []})

        assert resp.status_code == 400
        assert resp.json()['success'] is False
