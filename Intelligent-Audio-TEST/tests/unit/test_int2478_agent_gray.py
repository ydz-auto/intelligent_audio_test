# -*- coding: utf-8 -*-
"""INT-2478 Agent 总开关灰度白名单。

验收锚点（卡面第 2/3/6 条）：

- 总闸关闭 → ``AGENT_DISABLED``，不转发上游、不产生后台 run；
- 灰度用户可用、非灰度用户不可用，未命中与总闸关闭同一表现；
- 缺灰度配置时 ``AGENT_ENABLED=true`` 的部署仍全员放行（默认向后兼容）。

``AGENT_ENABLED`` 仍是唯一总闸：本卡只在它之上加租户 / 用户白名单。
"""
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import httpx
import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from api_gateway.config.config import Config
from api_gateway.routes import agent_runtime_bp
from api_gateway.routes.agent_guard import (
    AGENT_DISABLED_CODE, require_agent_enabled,
)
from shared.agent_access import (
    AgentAccessDecision, evaluate_agent_access, parse_gray_values,
)

GRAY_ENV_KEYS = (
    'AGENT_ENABLED', 'AGENT_GRAY_TENANTS', 'AGENT_GRAY_USERS',
    'AGENT_DEFAULT_TENANT_ID',
)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for key in GRAY_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    yield


@pytest.fixture()
def harness():
    calls = []

    def default_handler(request):
        calls.append(request)
        return httpx.Response(200, json={'ok': True})

    def make_app():
        app = FastAPI()

        # 测试替身中间件：真实 AuthMiddleware 需要 token / 用户库，这里只注入
        # 依赖判定所需的 identity（user_id），灰度读的就是这个字段。
        @app.middleware('http')
        async def inject_identity(request: Request, call_next):
            request.state.user_id = int(
                request.headers.get('X-Test-User', '0') or 0)
            request.state.permissions = ['*']
            return await call_next(request)

        app.include_router(agent_runtime_bp.router, prefix='/api/v1/agent')

        @app.get('/api/v1/tasks')
        def business_route():  # 人工业务流程代表路由
            return {'items': []}

        agent_runtime_bp._transport_override = httpx.MockTransport(
            default_handler)
        return TestClient(app), calls

    yield make_app
    agent_runtime_bp._transport_override = None


# ---------------------------------------------------------------- 纯策略分支

def test_master_switch_off_denies_even_if_gray_lists_contain_user():
    decision = evaluate_agent_access(
        master_enabled=False, tenant_id='default', user_id=7,
        gray_tenants={'default'}, gray_users={'7'})
    assert decision is AgentAccessDecision.DISABLED
    assert decision.allowed is False


def test_no_gray_config_allows_everyone_backward_compatible():
    for user_id in (0, None, 7, '42'):
        decision = evaluate_agent_access(
            master_enabled=True, tenant_id='default', user_id=user_id)
        assert decision is AgentAccessDecision.ENABLED, user_id


def test_gray_tenant_hit_and_miss():
    hit = evaluate_agent_access(
        master_enabled=True, tenant_id='tenant-a', user_id=99,
        gray_tenants={'tenant-a'})
    miss = evaluate_agent_access(
        master_enabled=True, tenant_id='tenant-b', user_id=99,
        gray_tenants={'tenant-a'})
    assert hit is AgentAccessDecision.ENABLED
    assert miss is AgentAccessDecision.NOT_IN_GRAY


def test_gray_user_hit_and_miss_for_int_and_str_ids():
    hit_int = evaluate_agent_access(
        master_enabled=True, tenant_id='default', user_id=42,
        gray_users={'42'})
    hit_str = evaluate_agent_access(
        master_enabled=True, tenant_id='default', user_id='42',
        gray_users={'42'})
    miss = evaluate_agent_access(
        master_enabled=True, tenant_id='default', user_id=5,
        gray_users={'42'})
    assert hit_int is AgentAccessDecision.ENABLED
    assert hit_str is AgentAccessDecision.ENABLED
    assert miss is AgentAccessDecision.NOT_IN_GRAY


def test_anonymous_user_never_matches_gray_user_list():
    """AUTH_MODE=off 的匿名空态（user_id=0）不得因为白名单里有 0 就放行。"""
    for user_id in (0, None, ''):
        decision = evaluate_agent_access(
            master_enabled=True, tenant_id='default', user_id=user_id,
            gray_users={'0', ''})
        assert decision is AgentAccessDecision.NOT_IN_GRAY, user_id


def test_parse_gray_values_tolerates_separators_and_spaces():
    assert parse_gray_values(None) == frozenset()
    assert parse_gray_values('') == frozenset()
    assert parse_gray_values(' 1, 42 ;，7 ') == frozenset({'1', '42', '7'})
    assert parse_gray_values('default\ntenant-b') == frozenset(
        {'default', 'tenant-b'})


# ------------------------------------------------------------ 配置读取口径

def test_config_reads_gray_lists_at_call_time(monkeypatch):
    monkeypatch.setenv('AGENT_GRAY_TENANTS', 'default, tenant-b')
    monkeypatch.setenv('AGENT_GRAY_USERS', '1,2')
    assert Config.agent_gray_tenants() == frozenset({'default', 'tenant-b'})
    assert Config.agent_gray_users() == frozenset({'1', '2'})
    monkeypatch.setenv('AGENT_GRAY_USERS', '3')
    assert Config.agent_gray_users() == frozenset({'3'})  # 不冻结在导入期
    monkeypatch.delenv('AGENT_GRAY_TENANTS')
    assert Config.agent_gray_tenants() == frozenset()


# ----------------------------------------------------------------- 网关入口

def test_master_off_returns_agent_disabled_and_never_forwards(
        monkeypatch, harness):
    monkeypatch.setenv('AGENT_ENABLED', 'false')
    client, calls = harness()
    response = client.get('/api/v1/agent/sessions/s-1')
    assert response.status_code == 503
    assert response.json()['detail']['code'] == AGENT_DISABLED_CODE
    assert calls == []


def test_gray_configured_non_gray_user_is_rejected_like_switch_off(
        monkeypatch, harness):
    monkeypatch.setenv('AGENT_ENABLED', 'true')
    monkeypatch.setenv('AGENT_GRAY_USERS', '42')
    client, calls = harness()
    response = client.get('/api/v1/agent/sessions/s-1',
                          headers={'X-Test-User': '5'})
    assert response.status_code == 503
    assert response.json()['detail']['code'] == AGENT_DISABLED_CODE
    assert calls == []
    # 人工业务流程完全不受影响
    assert client.get('/api/v1/tasks').status_code == 200


def test_gray_configured_anonymous_user_is_rejected(monkeypatch, harness):
    monkeypatch.setenv('AGENT_ENABLED', 'true')
    monkeypatch.setenv('AGENT_GRAY_TENANTS', 'other-tenant')
    client, calls = harness()
    response = client.get('/api/v1/agent/sessions/s-1')  # user_id=0, default 租户
    assert response.status_code == 503
    assert calls == []


def test_gray_configured_gray_user_is_allowed(monkeypatch, harness):
    monkeypatch.setenv('AGENT_ENABLED', 'true')
    monkeypatch.setenv('AGENT_GRAY_USERS', '42')
    client, calls = harness()
    response = client.get('/api/v1/agent/sessions/s-1',
                          headers={'X-Test-User': '42'})
    assert response.status_code == 200
    assert response.json() == {'ok': True}
    assert len(calls) == 1


def test_gray_configured_gray_tenant_is_allowed(monkeypatch, harness):
    monkeypatch.setenv('AGENT_ENABLED', 'true')
    monkeypatch.setenv('AGENT_GRAY_TENANTS', 'default')
    client, calls = harness()
    response = client.get('/api/v1/agent/sessions/s-1',
                          headers={'X-Test-User': '5'})
    assert response.status_code == 200
    assert len(calls) == 1


def test_master_on_without_gray_config_forwards_for_everyone(
        monkeypatch, harness):
    """现役 AGENT_ENABLED=true 且没配灰度 → 行为与 INT-2456 完全一致。"""
    monkeypatch.setenv('AGENT_ENABLED', 'true')
    client, calls = harness()
    for user in ('0', '5', '42'):
        response = client.get('/api/v1/agent/sessions/s-1',
                              headers={'X-Test-User': user})
        assert response.status_code == 200, user
    assert len(calls) == 3


def test_gate_is_still_attached_to_routers():
    assert any(dep.dependency is require_agent_enabled
               for dep in agent_runtime_bp.router.dependencies)
