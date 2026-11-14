# -*- coding: utf-8 -*-
"""INT-2551 网关审核流鉴权（双条件的第一半）+ 身份头防伪造。

验收锚点（卡面「可测验收标准」3、4）：
- 审核流四个端点（提交 / 审批 / 撤回 / 待审队列）要求 ``agent:skill:admin``，
  仅持 ``agent:skill:manage`` → 403 且不打上游；
- ``?scope=TENANT`` 的创建额外要求 ``agent:skill:admin``；
- 客户端伪造的 ``X-Tenant-Id`` / ``X-User-Is-Admin`` 被网关覆盖，上游只收到
  网关按认证身份算出的值（伪造 tenant_id 无效）。
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

from api_gateway.middleware import RequestAdapterMiddleware
from api_gateway.routes import agent_runtime_bp, agent_skill_bp
from shared.constants.permissions import SKILL_ADMIN_PERMISSION

ADMIN_PERMS = ['*']
MANAGE_ONLY = ['agent:skill:read', 'agent:skill:manage']


@pytest.fixture()
def harness():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={'items': []})

    def make_app(permissions):
        app = FastAPI()
        app.add_middleware(RequestAdapterMiddleware)

        @app.middleware('http')
        async def _inject(request, call_next):
            request.state.user_id = 7
            request.state.permissions = list(permissions)
            return await call_next(request)

        app.include_router(agent_runtime_bp.router, prefix='/api/v1/agent')
        app.include_router(agent_skill_bp.router, prefix='/api/v1/agent')
        agent_runtime_bp._transport_override = httpx.MockTransport(handler)
        return TestClient(app)

    yield make_app, calls
    agent_runtime_bp._transport_override = None


def test_review_endpoints_require_admin_permission(harness):
    make_app, calls = harness
    client = make_app(MANAGE_ONLY)
    for method, path in (
            ('post', '/api/v1/agent/skills/x/submit-review'),
            ('post', '/api/v1/agent/skills/x/review'),
            ('post', '/api/v1/agent/skills/x/withdraw'),
            ('get', '/api/v1/agent/skills/reviews')):
        resp = getattr(client, method)(path)
        assert resp.status_code == 403, (path, resp.text)
    assert calls == []


def test_tenant_create_requires_admin_permission(harness):
    make_app, calls = harness
    client = make_app(MANAGE_ONLY)
    resp = client.post('/api/v1/agent/skills?scope=TENANT',
                       json={'name': 'demo-skill'})
    assert resp.status_code == 403, resp.text
    assert calls == []
    # USER 作用域的写入口不变（INT-2549 无回归）
    ok = client.post('/api/v1/agent/skills?scope=USER',
                     json={'name': 'demo-skill'})
    assert ok.status_code == 200, ok.text
    assert calls[0].url.path == '/api/v1/agent/skills'


def test_admin_passes_and_body_is_forwarded(harness):
    make_app, calls = harness
    client = make_app(ADMIN_PERMS)
    resp = client.post('/api/v1/agent/skills/x/review',
                       json={'decision': 'APPROVE', 'reason': ''})
    assert resp.status_code == 200, resp.text
    assert calls[0].method == 'POST'
    assert calls[0].headers['Content-Type'] == 'application/json'
    assert b'APPROVE' in calls[0].content


def test_forged_tenant_and_admin_headers_are_overwritten(harness):
    make_app, calls = harness
    client = make_app(MANAGE_ONLY)
    resp = client.get(
        '/api/v1/agent/skills',
        headers={'X-Tenant-Id': 't2', 'X-User-Is-Admin': 'true',
                 'X-User-Permissions': '*'})
    assert resp.status_code == 200, resp.text
    forwarded = calls[0].headers
    # 租户只取部署口径；权限与管理员标记只取网关算出的值
    assert forwarded['X-Tenant-Id'] == 'default'
    assert forwarded['X-User-Permissions'] == ','.join(MANAGE_ONLY)
    assert forwarded['X-User-Is-Admin'] == 'false'


@pytest.mark.parametrize('permissions', [
    ['*'],
    ['agent:skill:read', SKILL_ADMIN_PERMISSION],
])
def test_admin_flag_true_for_admin_credential(harness, permissions):
    """管理员级授予的两种来源（通配 ``*`` / ``agent:skill:admin``）都下发 true。

    INT-2594 P3：此前只认 ``*``，只授该权限码的自定义管理员角色过得了网关
    却被服务端 403。
    """
    make_app, calls = harness
    client = make_app(permissions)
    client.get('/api/v1/agent/skills')
    assert calls[0].headers['X-User-Is-Admin'] == 'true'
