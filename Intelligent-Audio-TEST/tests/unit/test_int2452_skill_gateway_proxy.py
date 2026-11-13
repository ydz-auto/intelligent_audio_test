# -*- coding: utf-8 -*-
"""INT-2452 网关代理 GET /api/v1/agent/skills。

验收锚点：Skill 列表经网关转发，身份与权限头不丢（agent_service 依赖
X-User-Permissions 过滤可见性）；无 token 时 401 且不打上游。
"""
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

from api_gateway.middleware import AuthMiddleware
from api_gateway.routes import agent_runtime_bp, agent_skill_bp


@pytest.fixture()
def harness():
    calls = []

    def make_app(mode='off', handler=None):
        app = FastAPI()
        app.add_middleware(AuthMiddleware, auth_mode=mode)
        app.include_router(agent_runtime_bp.router, prefix='/api/v1/agent')
        # INT-2549：GET /skills 的代理迁到 agent_skill_bp（带权限码）
        app.include_router(agent_skill_bp.router, prefix='/api/v1/agent')
        agent_runtime_bp._transport_override = httpx.MockTransport(handler)
        return TestClient(app)

    yield make_app, calls
    agent_runtime_bp._transport_override = None


def test_skills_are_forwarded_with_identity(harness):
    make_app, calls = harness
    payload = {'items': [{'name': 'platform-reference'}],
               'l1_tokens': 174, 'l1_budget_tokens': 19200}

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=payload)

    client = make_app(mode='off', handler=handler)
    resp = client.get('/api/v1/agent/skills')
    assert resp.status_code == 200
    assert resp.json() == payload
    assert calls[0].method == 'GET'
    assert calls[0].url.path == '/api/v1/agent/skills'
    assert calls[0].headers['X-User-Id'] == '0'
    assert calls[0].headers['X-Tenant-Id'] == 'default'


def test_skills_requires_login_in_prod_and_never_reaches_upstream(harness):
    make_app, calls = harness

    def handler(request):  # pragma: no cover - 不应被调用
        calls.append(request)
        return httpx.Response(200, json={'items': []})

    client = make_app(mode='prod', handler=handler)
    assert client.get('/api/v1/agent/skills').status_code == 401
    assert calls == []


def test_upstream_unavailable_maps_to_503(harness):
    make_app, _calls = harness

    def handler(request):
        raise httpx.ConnectError('down', request=request)

    client = make_app(mode='off', handler=handler)
    resp = client.get('/api/v1/agent/skills')
    assert resp.status_code == 503
    assert resp.json()['detail'] == 'agent service unavailable'
