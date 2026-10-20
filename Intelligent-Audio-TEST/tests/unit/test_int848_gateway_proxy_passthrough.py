# -*- coding: utf-8 -*-
"""INT-848 网关接口透传实测 —— proxy_type / proxy_url 经真实 HTTP 端点进出网关。

验收标准 1/2/3 的 schema 层已由 test_int848_api_gateway_proxy_schema.py 覆盖；
本文件补「接口」一层：schema → ApiCommandService → ACL（gRPC JSON blob 前的
最后一道）整链，证明新字段在网关写侧被接受并进入下发 data dict，读侧原样返回。
- POST  /api/v1/apis       创建（snake_case / camelCase / 缺省三态）
- PUT   /api/v1/apis/{id}  编辑
- GET   /api/v1/apis/{id}  读回（字段原样透传，不丢）
"""
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api_gateway.application.services.api import api_command_service, api_query_service
from api_gateway.domain.dto import CommandResultDTO
from api_gateway.middleware import RequestAdapterMiddleware
from api_gateway.routes.api_bp import router as api_router


def _make_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestAdapterMiddleware)

    @app.middleware('http')
    async def _fake_auth(request, call_next):
        request.state.permissions = ['*']
        return await call_next(request)

    app.include_router(api_router, prefix='/api/v1/apis', tags=['apis'])
    return app


@pytest.fixture()
def client():
    return TestClient(_make_app())


class _RecordingAcl:
    """记录 create/update 收到的 data dict（= 即将 json.dumps 进 gRPC blob 的载荷）。"""

    def __init__(self, result=None):
        self.create_calls = []
        self.update_calls = []
        self._result = result

    def create(self, data):
        self.create_calls.append(data)
        return self._result if self._result is not None else CommandResultDTO(
            success=True, message='API配置创建成功', data={'id': 21}, code=201)

    def update(self, api_id, data):
        self.update_calls.append((api_id, data))
        return self._result if self._result is not None else CommandResultDTO(
            success=True, message='API配置更新成功',
            data={'id': api_id, 'name': 'API-1'}, code=200)

    def get_one(self, api_id):
        return CommandResultDTO(
            success=True, message='ok',
            data={'id': api_id, 'name': 'API-1',
                  'proxy_type': 'http', 'proxy_url': 'user:pass@proxy.example.com:8080'},
            code=200)


@pytest.fixture()
def acl(monkeypatch):
    stub = _RecordingAcl()
    monkeypatch.setattr(api_command_service, '_api_acl', stub)
    monkeypatch.setattr(api_query_service, '_api_acl', stub)
    return stub


class TestCreatePassthrough:
    """写侧创建：新字段被 schema 接受并进入下发 data dict。"""

    def test_create_accepts_snake_case_proxy_fields(self, client, acl):
        resp = client.post('/api/v1/apis', json={
            'name': 'API-1', 'api_url': 'http://example.com',
            'proxy_type': 'socks5h', 'proxy_url': 'user:pass@proxy.example.com:8080',
        })
        assert resp.status_code == 201, resp.text
        assert resp.json()['success'] is True
        sent = acl.create_calls[0]
        assert sent['proxy_type'] == 'socks5h'
        assert sent['proxy_url'] == 'user:pass@proxy.example.com:8080'

    def test_create_accepts_camel_case_aliases(self, client, acl):
        """前端 DTO（camelCase）提交 → schema 转 snake_case 后原样下发。"""
        resp = client.post('/api/v1/apis', json={
            'name': 'API-1',
            'proxyType': 'https', 'proxyUrl': 'u:p@h:8443',
        })
        assert resp.status_code == 201, resp.text
        sent = acl.create_calls[0]
        assert sent['proxy_type'] == 'https'
        assert sent['proxy_url'] == 'u:p@h:8443'

    def test_create_without_proxy_fields_loads_unchanged(self, client, acl):
        """缺省代理字段 → 下发 data dict 不含 proxy_*（回归：exclude_none 透传负载不变）。"""
        resp = client.post('/api/v1/apis', json={
            'name': 'API-1', 'api_url': 'http://example.com', 'vendor': 'v',
        })
        assert resp.status_code == 201, resp.text
        sent = acl.create_calls[0]
        assert 'proxy_type' not in sent
        assert 'proxy_url' not in sent
        assert sent['name'] == 'API-1'  # 其余既有字段不受影响

    def test_create_rejects_bad_payload_without_acl_call(self, client, acl):
        """非法载荷（缺 name）→ 400 数据验证失败，不触达 ACL（写侧校验仍生效）。"""
        resp = client.post('/api/v1/apis', json={'proxy_type': 'http'})
        assert resp.status_code == 400, resp.text
        assert resp.json()['success'] is False
        assert acl.create_calls == []


class TestUpdatePassthrough:
    def test_update_accepts_proxy_fields(self, client, acl):
        resp = client.put('/api/v1/apis/9', json={
            'proxy_type': 'http', 'proxy_url': 'user:pass@proxy.example.com:8080',
        })
        assert resp.status_code == 200, resp.text
        api_id, sent = acl.update_calls[0]
        assert api_id == 9
        assert sent['proxy_type'] == 'http'
        assert sent['proxy_url'] == 'user:pass@proxy.example.com:8080'

    def test_update_without_proxy_fields_loads_unchanged(self, client, acl):
        resp = client.put('/api/v1/apis/9', json={'name': 'API-rename'})
        assert resp.status_code == 200, resp.text
        api_id, sent = acl.update_calls[0]
        assert sent['name'] == 'API-rename'
        assert 'proxy_type' not in sent
        assert 'proxy_url' not in sent


class TestReadPassthrough:
    def test_get_one_returns_proxy_fields(self, client, acl):
        """读侧：api_test_service 返回的 proxy 字段原样透传给前端（不丢、不改名）。"""
        resp = client.get('/api/v1/apis/1')
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body['success'] is True
        assert body['data']['proxy_type'] == 'http'
        assert body['data']['proxy_url'] == 'user:pass@proxy.example.com:8080'
