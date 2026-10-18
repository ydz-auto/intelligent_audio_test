# -*- coding: utf-8 -*-
"""INT-787 验收回归（路由层）：GET /api/v1/system/health。

原卡：系统健康汇总端点（网关 + 认证服务健康），INT-766 契约审核必须项：
① 公开白名单 —— /api/v1/system/health 入 AuthMiddleware.PUBLIC_PATHS，
   AUTH_MODE=prod 强制态下匿名可达（401 即契约违约）
② auth 探测降级 —— auth_service 探测失败返回 200 信封 + auth
   {status:'error', service:'auth_service'}，不拖垮整卡

本用例经真实 FastAPI 路由 + 真实 AuthMiddleware + to_response 序列化链路验证：
1. 正常态：data.gateway 复用根 /health 口径（status/service/version/database），
   data.auth 透传 auth_service 探测结果
2. 降级态：auth 探测失败 → 200 + auth {status:'error', service:'auth_service'}
3. 公开白名单：prod 强制态无 token 匿名访问 200（非 401）
4. 网关 app 路由表含 /api/v1/system/health（不改动既有 /health）
"""
import os

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import api_gateway.application.services.system_health_service as shs
from api_gateway.middleware import RequestAdapterMiddleware, AuthMiddleware
from api_gateway.routes.system_bp import router as system_router


def _make_app(auth_mode: str = 'off'):
    """最小网关应用：真实系统健康路由 + 真实 AuthMiddleware。"""
    app = FastAPI()
    app.add_middleware(RequestAdapterMiddleware)
    app.add_middleware(AuthMiddleware, auth_mode=auth_mode)
    app.include_router(system_router, prefix='/api/v1/system')
    return app


class _FakeResp:
    """httpx.get 返回值桩：仅暴露 .json()。"""

    def __init__(self, body):
        self._body = body

    def json(self):
        return self._body


@pytest.fixture()
def client(monkeypatch):
    """路由客户端：auth 探测桩为 ok，隔离 gRPC/DB/网络。"""
    monkeypatch.setattr(shs.SystemHealthService, '_probe_auth',
                        staticmethod(lambda: {'status': 'ok', 'service': 'auth_service'}))
    return TestClient(_make_app())


class TestSystemHealthRoute:

    def test_envelope_gateway_and_auth(self, client):
        """正常态：统一信封 + data.gateway 复用根 /health 口径 + data.auth 透传。"""
        resp = client.get('/api/v1/system/health')
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body['success'] is True
        assert body['code'] == 0
        assert body['message'] == 'ok'
        data = body['data']
        assert data['gateway']['status'] == 'ok'
        assert data['gateway']['service'] == 'api_gateway'
        assert data['gateway']['version'] == shs.Config.PLATFORM_VERSION
        assert 'database' in data['gateway']  # 隔离库/sqlite 下为 None，字段恒在
        assert data['auth'] == {'status': 'ok', 'service': 'auth_service'}

    def test_gateway_database_from_config(self, client, monkeypatch):
        """data.gateway.database 取 Config.DATABASE_URL 解析库名（INT-246 口径）。"""
        monkeypatch.setattr(shs.Config, 'DATABASE_URL',
                            'postgresql://test:test@localhost/intelligent_audio_test')
        body = client.get('/api/v1/system/health').json()
        assert body['data']['gateway']['database'] == 'intelligent_audio_test'

    def test_auth_probe_failure_degrades_not_whole_card(self, monkeypatch):
        """必须项②：auth 探测失败 → 200 信封 + auth {status:'error'}，不整卡失败。"""
        monkeypatch.setattr(shs.SystemHealthService, '_probe_auth',
                            staticmethod(lambda: {'status': 'error', 'service': 'auth_service'}))
        resp = TestClient(_make_app()).get('/api/v1/system/health')
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body['success'] is True
        assert body['data']['auth'] == {'status': 'error', 'service': 'auth_service'}
        # 网关自身健康不受下游拖垮
        assert body['data']['gateway']['status'] == 'ok'

    def test_public_in_prod_enforcing_mode(self):
        """必须项①：prod 强制态无 token 匿名访问 200；对照非白名单路径 401。"""
        client = TestClient(_make_app(auth_mode='prod'))
        resp = client.get('/api/v1/system/health')
        assert resp.status_code == 200, f'白名单应放行匿名访问，实际 {resp.status_code}'
        # 对照：同前缀下非白名单路径（不存在的路由）仍被中间件拦为 401
        resp2 = client.get('/api/v1/system/whatever')
        assert resp2.status_code == 401, f'非白名单路径应 401，实际 {resp2.status_code}'


class TestAuthProbe:

    def test_probe_ok_parses_body(self, monkeypatch):
        """探测成功：透传 auth_service /health 的 status/service。"""
        monkeypatch.setattr(shs.httpx, 'get',
                            lambda *a, **k: _FakeResp({'status': 'ok', 'service': 'auth_service'}))
        assert shs.SystemHealthService._probe_auth() == {
            'status': 'ok', 'service': 'auth_service'}

    def test_probe_timeout_degrades(self, monkeypatch):
        """探测超时/连接拒绝 → 降级 {status:'error', service:'auth_service'}，不抛异常。"""
        monkeypatch.setattr(shs.httpx, 'get', lambda *a, **k: (_ for _ in ()).throw(
            TimeoutError('auth_service 连接超时')))
        assert shs.SystemHealthService._probe_auth() == {
            'status': 'error', 'service': 'auth_service'}

    def test_probe_non_json_degrades(self, monkeypatch):
        """探测返回非 JSON → 降级 error（异常收敛），不抛给路由层。"""
        monkeypatch.setattr(shs.httpx, 'get', lambda *a, **k: (_ for _ in ()).throw(
            ValueError('Invalid JSON')))

        assert shs.SystemHealthService._probe_auth() == {
            'status': 'error', 'service': 'auth_service'}


class TestGatewayAppRegistration:

    def test_route_registered_in_gateway_app(self):
        """网关 create_app 路由表含 /api/v1/system/health，且不破坏既有 /health。

        注：新版 FastAPI 将 include_router 的 APIRoute 包装为 _IncludedRouter
        （app.routes 不再扁平列出子路由），以 OpenAPI paths 断言最稳定。
        """
        import api_gateway.app as gateway_app
        paths = sorted(gateway_app.app.openapi()['paths'].keys())
        assert '/api/v1/system/health' in paths
        assert '/health' in paths
        assert 'get' in gateway_app.app.openapi()['paths']['/api/v1/system/health']
