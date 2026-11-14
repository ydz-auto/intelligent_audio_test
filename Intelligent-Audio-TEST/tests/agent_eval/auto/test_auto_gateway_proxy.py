# -*- coding: utf-8 -*-
"""INT-2474：网关 Auto「继续」代理（§9.4 / 方案 §3.1）。

网关只做鉴权后的透明转发：身份头透传、409（RUN_NOT_PAUSED）原样回传、
AUTH_MODE=prod 时未认证不触达上游。
"""
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')
os.environ.setdefault('AGENT_ENABLED', 'true')

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api_gateway.middleware import AuthMiddleware
from api_gateway.routes import agent_runtime_bp


@pytest.fixture()
def harness():
    calls = []

    def make_app(mode='off', handler=None):
        app = FastAPI()
        app.add_middleware(AuthMiddleware, auth_mode=mode)
        app.include_router(agent_runtime_bp.router, prefix='/api/v1/agent')
        agent_runtime_bp._transport_override = httpx.MockTransport(handler)
        return TestClient(app)

    yield make_app, calls
    agent_runtime_bp._transport_override = None


def test_resume_is_forwarded_with_identity_headers(harness):
    make_app, calls = harness

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={'id': 'r1', 'status': 'RUNNING',
                                         'mode': 'auto'})

    client = make_app(mode='off', handler=handler)
    resp = client.post('/api/v1/agent/runs/r1/resume',
                       headers={'Authorization': 'Bearer token-1'})
    assert resp.status_code == 200
    assert resp.json()['status'] == 'RUNNING'
    assert resp.json()['mode'] == 'auto'
    forwarded = calls[0]
    assert forwarded.method == 'POST'
    assert forwarded.url.path == '/api/v1/agent/runs/r1/resume'
    assert forwarded.headers['Authorization'] == 'Bearer token-1'
    assert forwarded.headers['X-User-Id'] == '0'
    assert forwarded.headers['X-Tenant-Id'] == 'default'


def test_resume_conflict_passes_through(harness):
    make_app, calls = harness

    def handler(request):
        calls.append(request)
        return httpx.Response(409, json={
            'detail': '仍有待审批提案：请先处理审批单，再继续',
            'code': 'RUN_NOT_PAUSED'})

    client = make_app(mode='off', handler=handler)
    resp = client.post('/api/v1/agent/runs/r1/resume')
    assert resp.status_code == 409
    assert resp.json()['code'] == 'RUN_NOT_PAUSED'
    assert len(calls) == 1


def test_resume_unauthenticated_never_reaches_upstream(harness):
    make_app, calls = harness

    def handler(request):  # pragma: no cover - 不应被调用
        calls.append(request)
        return httpx.Response(200, json={})

    client = make_app(mode='prod', handler=handler)
    resp = client.post('/api/v1/agent/runs/r1/resume')
    assert resp.status_code == 401
    assert calls == []
