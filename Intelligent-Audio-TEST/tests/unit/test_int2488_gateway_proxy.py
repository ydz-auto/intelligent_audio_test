# -*- coding: utf-8 -*-
"""INT-2488 网关供应商代理：权限码 / 身份头透传 / 审计不含 Key。"""
import json
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')
# INT-2456：网关 Agent 总开关默认关闭，本组代理用例必须显式开启。
os.environ.setdefault('AGENT_ENABLED', 'true')

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api_gateway.routes import agent_provider_bp, agent_runtime_bp

PERMISSION = 'agent:provider:manage'


@pytest.fixture()
def harness():
    calls = []
    audits = []

    def make_app(handler):
        app = FastAPI()
        app.include_router(agent_provider_bp.router, prefix='/api/v1/agent')

        @app.middleware('http')
        async def inject(request, call_next):
            request.state.user_id = int(
                request.headers.get('X-User-Id', '7'))
            request.state.username = 'tester'
            raw = request.headers.get('X-Permissions', PERMISSION)
            request.state.permissions = [p for p in raw.split(',') if p]
            return await call_next(request)

        agent_runtime_bp._transport_override = httpx.MockTransport(handler)
        return TestClient(app)

    def fake_audit(event, *, request, provider_id, operation,
                   status_code=None):
        audits.append({
            'event': event.value, 'provider_id': provider_id,
            'operation': operation, 'status_code': status_code,
        })

    original = agent_provider_bp.write_agent_provider_audit
    agent_provider_bp.write_agent_provider_audit = fake_audit
    try:
        yield make_app, calls, audits
    finally:
        agent_provider_bp.write_agent_provider_audit = original
        agent_runtime_bp._transport_override = None


def test_missing_permission_is_403_and_not_forwarded(harness):
    make_app, calls, _audits = harness

    def handler(request):  # pragma: no cover
        calls.append(request)
        return httpx.Response(200, json={'items': []})

    client = make_app(handler)
    resp = client.get('/api/v1/agent/providers',
                      headers={'X-Permissions': 'task:read'})
    assert resp.status_code == 403
    assert calls == []


def test_forwards_identity_headers(harness):
    make_app, calls, _audits = harness

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={'items': []})

    client = make_app(handler)
    resp = client.get('/api/v1/agent/providers',
                      headers={'X-User-Id': '42'})
    assert resp.status_code == 200
    assert len(calls) == 1
    forwarded = calls[0]
    assert forwarded.headers.get('X-User-Id') == '42'
    assert forwarded.headers.get('X-Tenant-Id')
    assert forwarded.headers.get('X-User-Permissions') == PERMISSION
    assert str(forwarded.url.path) == '/api/v1/agent/providers'


def test_all_provider_routes_are_proxied(harness):
    make_app, calls, audits = harness

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={'id': 'p1'})

    client = make_app(handler)
    client.get('/api/v1/agent/providers')
    client.post('/api/v1/agent/providers', json={
        'name': 'x', 'protocol': 'OPENAI_COMPATIBLE',
        'base_url': 'http://x.local/v1', 'model': 'm', 'api_key': 'sk-secret-key-1234'})
    client.put('/api/v1/agent/providers/p1', json={'name': 'y'})
    client.post('/api/v1/agent/providers/p1/verify')
    client.post('/api/v1/agent/providers/p1/set-default')
    client.delete('/api/v1/agent/providers/p1')
    client.get('/api/v1/agent/model-catalog')

    methods = [request.method for request in calls]
    assert methods == ['GET', 'POST', 'PUT', 'POST', 'POST', 'DELETE', 'GET']
    assert str(calls[5].url.path) == '/api/v1/agent/providers/p1'

    # 审计只记 provider_id / 操作类型；请求体（明文 Key）不进审计
    dumped = json.dumps(audits, ensure_ascii=False)
    assert 'sk-secret-key-1234' not in dumped
    operations = {item['operation'] for item in audits}
    assert {'create', 'update', 'verify', 'set_default', 'delete'} <= operations


def test_upstream_unavailable_returns_503(harness):
    make_app, _calls, audits = harness

    def handler(request):
        raise httpx.ConnectError('down', request=request)

    client = make_app(handler)
    resp = client.get('/api/v1/agent/providers')
    assert resp.status_code == 503
    assert audits == []  # 失败不写成功审计
