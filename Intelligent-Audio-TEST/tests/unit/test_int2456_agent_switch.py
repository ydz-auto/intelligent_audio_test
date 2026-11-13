# -*- coding: utf-8 -*-
"""INT-2456 Agent 总开关（网关侧）。

验收锚点（卡面第 3 条）：关闭总开关时 Agent 接口返回明确「未启用」，
业务页面与人工流程不受影响；开启后网关代理可达。

执行点只在网关：agent_service 不发布宿主端口，开关不写第二套口径。
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

from api_gateway.routes import agent_provider_bp, agent_runtime_bp
from api_gateway.routes.agent_guard import (
    AGENT_DISABLED_CODE, AGENT_DISABLED_MESSAGE, require_agent_enabled,
)


@pytest.fixture()
def harness():
    calls = []

    def default_handler(request):
        calls.append(request)
        return httpx.Response(200, json={'ok': True})

    def make_app(handler=None):
        app = FastAPI()
        app.include_router(agent_runtime_bp.router, prefix='/api/v1/agent')
        app.include_router(agent_provider_bp.router, prefix='/api/v1/agent')

        @app.get('/api/v1/tasks')
        def business_route():  # 人工业务流程的代表路由
            return {'items': []}

        agent_runtime_bp._transport_override = httpx.MockTransport(
            handler or default_handler)
        return TestClient(app), calls

    yield make_app
    agent_runtime_bp._transport_override = None


def test_disabled_session_route_returns_explicit_unavailable(monkeypatch, harness):
    monkeypatch.setenv('AGENT_ENABLED', 'false')
    client, calls = harness()
    response = client.get('/api/v1/agent/sessions/s-1')
    assert response.status_code == 503
    detail = response.json()['detail']
    assert detail['code'] == AGENT_DISABLED_CODE
    assert '未启用' in detail['message']
    assert calls == []  # 未转发上游


def test_disabled_blocks_all_agent_runtime_routes(monkeypatch, harness):
    monkeypatch.setenv('AGENT_ENABLED', 'false')
    client, calls = harness()
    for method, path in (
        ('post', '/api/v1/agent/sessions'),
        ('get', '/api/v1/agent/runs/r-1'),
        ('post', '/api/v1/agent/runs/r-1/cancel'),
        ('get', '/api/v1/agent/runs/r-1/approvals'),
        ('get', '/api/v1/agent/skills'),
    ):
        kwargs = {'json': {}} if method == 'post' else {}
        response = getattr(client, method)(path, **kwargs)
        assert response.status_code == 503, path
        assert response.json()['detail']['code'] == AGENT_DISABLED_CODE, path
    assert calls == []


def test_disabled_sse_route_never_does_preflight(monkeypatch, harness):
    monkeypatch.setenv('AGENT_ENABLED', 'false')
    client, calls = harness()
    response = client.get('/api/v1/agent/runs/r-1/events')
    assert response.status_code == 503
    assert calls == []


def test_disabled_provider_routes_are_gated(monkeypatch, harness):
    monkeypatch.setenv('AGENT_ENABLED', 'false')
    client, calls = harness()
    response = client.get('/api/v1/agent/providers')
    assert response.status_code == 503
    assert response.json()['detail']['code'] == AGENT_DISABLED_CODE
    assert calls == []


def test_disabled_does_not_touch_business_routes(monkeypatch, harness):
    monkeypatch.setenv('AGENT_ENABLED', 'false')
    client, _calls = harness()
    response = client.get('/api/v1/tasks')
    assert response.status_code == 200
    assert response.json() == {'items': []}


def test_enabled_forwards_upstream(monkeypatch, harness):
    monkeypatch.setenv('AGENT_ENABLED', 'true')
    client, calls = harness()
    response = client.get('/api/v1/agent/skills')
    assert response.status_code == 200
    assert response.json() == {'ok': True}
    assert len(calls) == 1


def test_enabled_flag_values(monkeypatch):
    from api_gateway.config.config import Config
    for raw, expected in (
        ('true', True), ('1', True), ('yes', True), ('on', True),
        ('false', False), ('0', False), ('', False), ('off', False),
    ):
        monkeypatch.setenv('AGENT_ENABLED', raw)
        assert Config.agent_enabled() is expected, raw
    monkeypatch.delenv('AGENT_ENABLED', raising=False)
    assert Config.agent_enabled() is False  # 缺省关闭


def test_gate_is_attached_to_runtime_and_provider_routers():
    for router in (agent_runtime_bp.router, agent_provider_bp.router):
        assert any(dep.dependency is require_agent_enabled
                   for dep in router.dependencies)


def test_legacy_skill_download_router_is_not_gated():
    """INT-1150 的外部 Skill 包下载/MCP 路由不属于 Agent 运行时，不被总开关拦住。"""
    from api_gateway.routes import agent_bp
    assert not any(dep.dependency is require_agent_enabled
                   for dep in agent_bp.router.dependencies)


def test_disabled_message_is_documented():
    assert AGENT_DISABLED_MESSAGE == 'Agent 未启用'
