# -*- coding: utf-8 -*-
"""INT-2466 网关代理：审批决议转发。

网关只做「鉴权后的透明转发」：身份头 / body / 上游 404 / 409 原样返回，
不绕过 AuthMiddleware，不在网关另写一套审批语义。
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


def test_decision_is_forwarded_with_identity_and_body(harness):
    make_app, calls = harness

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={
            'approval': {'id': 'a1', 'status': 'APPROVED'},
            'run_status': 'WAITING_APPROVAL'})

    client = make_app(mode='off', handler=handler)
    resp = client.post('/api/v1/agent/approvals/a1/decision',
                       json={'decision': 'APPROVE'})
    assert resp.status_code == 200
    assert resp.json()['approval']['status'] == 'APPROVED'
    sent = calls[0]
    assert sent.method == 'POST'
    assert sent.url.path == '/api/v1/agent/approvals/a1/decision'
    assert sent.headers['X-User-Id'] == '0'
    assert sent.headers['Content-Type'].startswith('application/json')
    assert sent.content == b'{"decision":"APPROVE"}'


def test_decision_conflict_passes_through(harness):
    make_app, calls = harness

    def handler(request):
        calls.append(request)
        return httpx.Response(409, json={
            'detail': '审批单已处理或 run 已收口',
            'code': 'APPROVAL_ALREADY_DECIDED'})

    client = make_app(mode='off', handler=handler)
    resp = client.post('/api/v1/agent/approvals/a1/decision',
                       json={'decision': 'REJECT'})
    assert resp.status_code == 409
    assert resp.json()['code'] == 'APPROVAL_ALREADY_DECIDED'


def test_decision_requires_auth_and_is_not_forwarded(harness):
    make_app, calls = harness

    def handler(request):  # pragma: no cover - 不应被调用
        calls.append(request)
        return httpx.Response(200, json={})

    client = make_app(mode='prod', handler=handler)
    resp = client.post('/api/v1/agent/approvals/a1/decision',
                       json={'decision': 'APPROVE'})
    assert resp.status_code == 401
    assert calls == []
