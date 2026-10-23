# -*- coding: utf-8 -*-
"""INT-1383 设备 SPL 批量导入接口 POST /spl/import + GET /spl/import-template 单测。

覆盖：
- 导入：POST /api/v1/spl/import（multipart 文件，JSON/CSV）→ 计数报告
  （imported_count / failed_count / errors），纯新增 create-only
- 行级错误：缺 name / 缺 device_id+device_type / device_id 不存在 /
  calibration_points 非法
- calibration_points JSON 数组字符串 → calibration_data={'points': [...]} 包装
- 错误路径：未上传文件 / 空文件 / 不支持格式
- 模板：GET /api/v1/spl/import-template → CSV 附件（列头 + 示例行）
"""
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import io
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import api_gateway.application.services.spl.spl_command_service as svc_module
from api_gateway.middleware import RequestAdapterMiddleware
from api_gateway.routes.spl_bp import router as spl_router


class FakeAcl:
    """记录 create 入参的内存 ACL（可配置 device_id 失败行为）。"""

    def __init__(self, fail_device_ids=None):
        self.create_calls = []
        self.fail_device_ids = set(fail_device_ids or [])
        self._next_id = 100

    def create(self, data):
        self.create_calls.append(data)
        device_id = data.get('device_id')
        if device_id is not None and device_id in self.fail_device_ids:
            return {'success': False, 'message': f'设备 {device_id} 不存在', 'data': None, 'code': 404}
        item = dict(data)
        item['id'] = self._next_id
        self._next_id += 1
        return {'success': True, 'message': 'SPL 映射记录创建成功', 'data': {'id': item['id']}, 'code': 201}


def _make_client(monkeypatch, fake_acl):
    """替换 _spl_acl 为 FakeAcl，并挂载 spl 路由（fake auth 注入 admin 权限）。"""
    monkeypatch.setattr(svc_module, '_spl_acl', fake_acl)

    app = FastAPI()
    app.add_middleware(RequestAdapterMiddleware)

    @app.middleware('http')
    async def _fake_auth(request, call_next):
        request.state.permissions = ['*']
        return await call_next(request)

    app.include_router(spl_router, prefix='/api/v1/spl')
    return TestClient(app)


def _post_file(client, url, filename, payload, content_type='application/json'):
    content = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    return client.post(url, files={'file': (filename, content, content_type)})


_VALID_ROW = {
    'name': '映射A',
    'description': 'desc',
    'device_id': 1,
    'distance': 1.0,
    'target_spl': 65,
    'test_frequency': 1000,
}


class TestImportSuccess:

    def test_json_plain_list_success(self, monkeypatch):
        fake = FakeAcl()
        client = _make_client(monkeypatch, fake)

        resp = _post_file(client, '/api/v1/spl/import', 'spl.json', [
            {**_VALID_ROW, 'name': '映射A'},
            {**_VALID_ROW, 'name': '映射B', 'device_type': 'Speaker', 'device_id': None},
            {**_VALID_ROW, 'name': '映射C', 'calibration_points': '[{"spl":65,"gainOffset":0}]'},
        ])

        assert resp.status_code == 200
        body = resp.json()
        assert body['success'] is True
        assert body['data']['imported_count'] == 3
        assert body['data']['failed_count'] == 0
        assert body['data']['errors'] == []
        assert len(fake.create_calls) == 3
        assert fake.create_calls[2]['calibration_data'] == {'points': [{'spl': 65, 'gainOffset': 0}]}

    def test_json_dict_spl_mappings_key(self, monkeypatch):
        fake = FakeAcl()
        client = _make_client(monkeypatch, fake)

        resp = _post_file(client, '/api/v1/spl/import', 'spl.json',
                          {'spl_mappings': [{**_VALID_ROW, 'name': '映射D'}]})

        assert resp.json()['data']['imported_count'] == 1
        assert fake.create_calls[0]['name'] == '映射D'

    def test_csv_import_success(self, monkeypatch):
        fake = FakeAcl()
        client = _make_client(monkeypatch, fake)

        # 用 csv 模块生成：含逗号的 JSON 单元格会被正确引号包裹
        import csv as _csv
        buffer = io.StringIO()
        writer = _csv.writer(buffer)
        writer.writerow(['name', 'description', 'device_id', 'device_type', 'distance',
                         'target_spl', 'test_frequency', 'calibration_points'])
        writer.writerow(['映射E', 'desc', 2, 'Speaker', 1.0, 65, 1000,
                         '[{"spl":65,"gainOffset":0}]'])
        csv_content = buffer.getvalue().encode('utf-8-sig')
        resp = client.post('/api/v1/spl/import',
                           files={'file': ('spl.csv', csv_content, 'text/csv')})

        assert resp.status_code == 200
        body = resp.json()
        assert body['success'] is True
        assert body['data']['imported_count'] == 1
        assert fake.create_calls[0]['device_id'] == 2
        assert fake.create_calls[0]['calibration_data'] == {'points': [{'spl': 65, 'gainOffset': 0}]}

    def test_same_name_rows_each_created(self, monkeypatch):
        """同名行各自新建（create-only，不按 name 匹配更新）。"""
        fake = FakeAcl()
        client = _make_client(monkeypatch, fake)

        resp = _post_file(client, '/api/v1/spl/import', 'spl.json', [
            {**_VALID_ROW, 'name': '同名'},
            {**_VALID_ROW, 'name': '同名'},
        ])

        assert resp.json()['data']['imported_count'] == 2
        assert len(fake.create_calls) == 2


class TestImportRowErrors:

    def test_missing_name_fails(self, monkeypatch):
        fake = FakeAcl()
        client = _make_client(monkeypatch, fake)

        resp = _post_file(client, '/api/v1/spl/import', 'spl.json',
                          [{**_VALID_ROW, 'name': ''}, {**_VALID_ROW}])

        body = resp.json()
        assert body['success'] is True
        assert body['data']['imported_count'] == 1
        assert body['data']['failed_count'] == 1
        assert any('第1行' in e and 'name' in e for e in body['data']['errors'])
        assert len(fake.create_calls) == 1

    def test_missing_device_identity_fails(self, monkeypatch):
        fake = FakeAcl()
        client = _make_client(monkeypatch, fake)

        resp = _post_file(client, '/api/v1/spl/import', 'spl.json',
                          [{'name': '无设备', 'device_id': None, 'device_type': None}])

        body = resp.json()
        assert body['data']['failed_count'] == 1
        assert any('device_id 或 device_type' in e for e in body['data']['errors'])

    def test_device_id_not_found_fails(self, monkeypatch):
        fake = FakeAcl(fail_device_ids=[999])
        client = _make_client(monkeypatch, fake)

        resp = _post_file(client, '/api/v1/spl/import', 'spl.json',
                          [{**_VALID_ROW, 'name': '映射F', 'device_id': 999}])

        body = resp.json()
        assert body['data']['imported_count'] == 0
        assert body['data']['failed_count'] == 1
        assert any('第1行' in e and '999' in e for e in body['data']['errors'])

    def test_invalid_calibration_points_fails(self, monkeypatch):
        fake = FakeAcl()
        client = _make_client(monkeypatch, fake)

        resp = _post_file(client, '/api/v1/spl/import', 'spl.json',
                          [{**_VALID_ROW, 'calibration_points': 'not-json'}])

        body = resp.json()
        assert body['data']['failed_count'] == 1
        assert any('calibration_points' in e for e in body['data']['errors'])


class TestImportErrorPaths:

    def test_missing_file(self, monkeypatch):
        fake = FakeAcl()
        client = _make_client(monkeypatch, fake)

        resp = client.post('/api/v1/spl/import')

        assert resp.status_code == 400
        assert resp.json()['success'] is False

    def test_unsupported_format(self, monkeypatch):
        fake = FakeAcl()
        client = _make_client(monkeypatch, fake)

        resp = client.post('/api/v1/spl/import',
                           files={'file': ('x.txt', b'abc', 'text/plain')})

        assert resp.status_code == 400
        assert resp.json()['success'] is False

    def test_empty_file(self, monkeypatch):
        fake = FakeAcl()
        client = _make_client(monkeypatch, fake)

        resp = _post_file(client, '/api/v1/spl/import', 'empty.json', [])

        assert resp.status_code == 400
        assert resp.json()['success'] is False


class TestImportTemplate:

    def test_template_csv_attachment(self, monkeypatch):
        fake = FakeAcl()
        client = _make_client(monkeypatch, fake)

        resp = client.get('/api/v1/spl/import-template')

        assert resp.status_code == 200
        assert resp.headers['content-type'].startswith('text/csv')
        assert resp.headers['content-disposition'].startswith('attachment')
        assert '.csv' in resp.headers['content-disposition']
        text = resp.content.decode('utf-8-sig')
        assert 'name' in text and 'device_id' in text and 'test_frequency' in text
        assert 'calibration_points' in text
        assert '示例映射' in text
