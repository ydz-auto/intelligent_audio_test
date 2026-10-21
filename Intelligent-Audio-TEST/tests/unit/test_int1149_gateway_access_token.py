# -*- coding: utf-8 -*-
"""网关鉴权扩展 + Access Token CRUD 路由单测（INT-1149 / INT-1140 分道 A）。

覆盖：
- _intersect_permissions 生效权限 = 用户当前权限 ∩ token scopes（含 '*' / 空 scopes）
- resolve_access_token_identity：ValidateAccessToken 成功/失败、实时权限交集、
  username/role_id 拉取
- AuthMiddleware Bearer 分支：JWT 优先，非 JWT → access token 查证（off/prod
  双模式）；AUTH_MODE=off 下真实 access token 不被降级为 dev_user；无效 token
  → 401；scopes 收窄 → 越权 403
- 网关 /api/v1/auth/access-tokens CRUD 路由转发 auth_service 本组 HTTP 端点
  （X-User-Id 头 = 当前登录用户本人；未认证 401；响应透传）
"""
import json
import os
from types import SimpleNamespace

import pytest

os.environ.setdefault('DATABASE_URL',
                      'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from api_gateway.application.services.auth.access_token_service import (  # noqa: E402
    AccessTokenService,
    _intersect_permissions,
    resolve_access_token_identity,
)


# ============================================================
# _intersect_permissions（生效权限 = 用户当前权限 ∩ token scopes）
# ============================================================

class TestIntersectPermissions:

    def test_empty_scopes_inherits_user_all(self):
        assert _intersect_permissions(['task:read', 'audio:read'], []) \
            == ['task:read', 'audio:read']

    def test_wildcard_scope_inherits_user_all(self):
        assert _intersect_permissions(['task:read', 'audio:read'], ['*']) \
            == ['task:read', 'audio:read']

    def test_admin_user_narrowed_by_scopes(self):
        # 用户为 '*'（管理员）→ 按 token scopes 收窄（token 定义上限）
        assert _intersect_permissions(['*'], ['task:read']) == ['task:read']

    def test_normal_intersection(self):
        assert _intersect_permissions(
            ['task:read', 'audio:read'], ['task:read', 'audio:delete']) \
            == ['task:read']

    def test_revoked_permission_drops_from_effective(self):
        # 用户权限被实时收回 → 从生效集消失（越权 403）
        assert _intersect_permissions(
            ['audio:read'], ['task:read', 'audio:read']) == ['audio:read']

    def test_no_user_perms_yields_empty(self):
        assert _intersect_permissions([], ['task:read']) == []

    def test_preserves_wildcard_admin_token(self):
        # 管理员用户 + 管理员 token → 保留 '*'（require_permission 通配放行）
        assert _intersect_permissions(['*'], ['*']) == ['*']


# ============================================================
# gRPC stub 打桩（auth_proxies.get_auth_service_stub）
# ============================================================

class _FakeAuthStub:
    """模拟 auth_service gRPC stub：ValidateAccessToken / GetUserPermissions / GetUser。"""

    def __init__(self):
        self.validate_success = True
        self.validate_message = 'ok'
        self.token_user_id = 7
        self.token_scopes = ['task:read']
        self.user_permissions = ['task:read', 'audio:read']
        self.user_info = {'id': 7, 'username': 'u1', 'role_id': 2,
                          'permissions': ['task:read', 'audio:read']}

    def ValidateAccessToken(self, request, **kwargs):
        if not self.validate_success:
            return SimpleNamespace(success=False, message=self.validate_message,
                                   data='')
        return SimpleNamespace(success=True, message='ok', data=json.dumps({
            'valid': True, 'token': {
                'id': 1, 'user_id': self.token_user_id, 'name': 't',
                'token_hint': 'abcd', 'status': 'enabled',
                'scopes': self.token_scopes, 'expires_at': 0,
                'last_used_at': None,
            },
        }))

    def GetUserPermissions(self, request, **kwargs):
        return SimpleNamespace(success=True, message='ok',
                               data=json.dumps({'permissions': self.user_permissions}))

    def GetUser(self, request, **kwargs):
        return SimpleNamespace(success=True, message='ok',
                               data=json.dumps(self.user_info))


@pytest.fixture()
def fake_stub(monkeypatch):
    stub = _FakeAuthStub()
    import api_gateway.infrastructure.grpc_proxies.auth_proxies as auth_proxies
    monkeypatch.setattr(auth_proxies, 'get_auth_service_stub', lambda: stub)
    return stub


# ============================================================
# resolve_access_token_identity
# ============================================================

class TestResolveAccessTokenIdentity:

    def test_success_injects_user_id_username_role(self, fake_stub):
        identity = resolve_access_token_identity('at_testtoken')
        assert identity is not None
        user_id, username, role_id, perms = identity
        assert user_id == 7
        assert username == 'u1'
        assert role_id == 2
        # 生效权限 = 用户当前权限 ∩ token scopes
        assert perms == ['task:read']

    def test_failure_returns_none(self, fake_stub):
        fake_stub.validate_success = False
        fake_stub.validate_message = 'Access Token 已禁用'
        assert resolve_access_token_identity('at_bad') is None

    def test_validate_rpc_failure_returns_none(self, fake_stub, monkeypatch):
        # auth_service 不可达/超时（RPC 异常）→ 按查证失败处理，不抛 500
        def _boom(self_, request, **kwargs):
            raise RuntimeError('auth_service 不可达')
        monkeypatch.setattr(_FakeAuthStub, 'ValidateAccessToken', _boom)
        assert resolve_access_token_identity('at_x') is None

    def test_scopes_narrowed_by_user_permissions(self, fake_stub):
        # token scopes 含 audio:delete，但用户当前权限无 → 交集剔除
        fake_stub.token_scopes = ['task:read', 'audio:delete']
        identity = resolve_access_token_identity('at_x')
        assert identity[3] == ['task:read']

    def test_empty_scopes_inherit_user_all(self, fake_stub):
        fake_stub.token_scopes = []
        identity = resolve_access_token_identity('at_x')
        assert identity[3] == ['task:read', 'audio:read']

    def test_user_perm_fetch_failure_tightens_to_empty(self, fake_stub,
                                                       monkeypatch):
        # GetUserPermissions RPC 异常 → 按空权限交集（收紧不放宽）
        fake_stub.user_permissions = None

        def _boom(self_, request, **kwargs):
            raise RuntimeError('auth_service 不可用')
        monkeypatch.setattr(_FakeAuthStub, 'GetUserPermissions', _boom)
        identity = resolve_access_token_identity('at_x')
        assert identity is not None
        assert identity[3] == []

    def test_get_user_failure_tolerated(self, fake_stub, monkeypatch):
        def _boom(self_, request, **kwargs):
            raise RuntimeError('GetUser 失败')
        monkeypatch.setattr(_FakeAuthStub, 'GetUser', _boom)
        identity = resolve_access_token_identity('at_x')
        assert identity is not None
        assert identity[0] == 7
        assert identity[1] == ''  # username 置空但不阻断鉴权
        assert identity[3] == ['task:read']


# ============================================================
# AuthMiddleware Bearer 分支（off / prod 双模式，TestClient 实测）
# ============================================================

def _build_app(auth_mode):
    from fastapi import FastAPI, Request
    from api_gateway.middleware import AuthMiddleware, RequestAdapterMiddleware
    from api_gateway.application.services.auth.dependencies import require_permission

    app = FastAPI()
    app.add_middleware(RequestAdapterMiddleware)
    app.add_middleware(AuthMiddleware, auth_mode=auth_mode)

    @app.get('/echo')
    def echo(request: Request):
        return {
            'user_id': getattr(request.state, 'user_id', None),
            'username': getattr(request.state, 'username', ''),
            'role_id': getattr(request.state, 'role_id', None),
            'permissions': getattr(request.state, 'permissions', []),
        }

    @app.get('/need-task-read')
    def need_task_read(_: None = require_permission('task:read')):
        return {'ok': True}

    return app


class TestAuthMiddlewareAccessToken:

    def _client(self, app):
        from fastapi.testclient import TestClient
        return TestClient(app)

    # ---- prod 模式 ----

    def test_prod_access_token_authenticates(self, fake_stub):
        client = self._client(_build_app('prod'))
        resp = client.get('/echo', headers={'Authorization': 'Bearer at_testtoken'})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body['user_id'] == 7
        assert body['username'] == 'u1'
        assert body['permissions'] == ['task:read']

    def test_prod_access_token_scopes_narrowed_403(self, fake_stub):
        fake_stub.token_scopes = ['audio:read']
        client = self._client(_build_app('prod'))
        # token 无 task:read → require_permission 403
        resp = client.get('/need-task-read',
                          headers={'Authorization': 'Bearer at_testtoken'})
        assert resp.status_code == 403, resp.text

    def test_prod_access_token_scopes_pass(self, fake_stub):
        client = self._client(_build_app('prod'))
        resp = client.get('/need-task-read',
                          headers={'Authorization': 'Bearer at_testtoken'})
        assert resp.status_code == 200, resp.text

    def test_prod_invalid_token_401(self, fake_stub):
        fake_stub.validate_success = False
        client = self._client(_build_app('prod'))
        resp = client.get('/echo', headers={'Authorization': 'Bearer at_bad'})
        assert resp.status_code == 401, resp.text

    def test_prod_no_bearer_401(self, fake_stub):
        client = self._client(_build_app('prod'))
        resp = client.get('/echo')
        assert resp.status_code == 401, resp.text

    # ---- off 模式：真实 access token 不被降级为 dev_user ----

    def test_off_access_token_not_downgraded_to_dev_user(self, fake_stub):
        client = self._client(_build_app('off'))
        resp = client.get('/echo', headers={'Authorization': 'Bearer at_testtoken'})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body['user_id'] == 7           # 真实用户，非 dev_user 0
        assert body['username'] == 'u1'
        assert body['permissions'] == ['task:read']  # 非 ['*']

    def test_off_invalid_token_falls_back_dev_user(self, fake_stub):
        fake_stub.validate_success = False
        client = self._client(_build_app('off'))
        resp = client.get('/echo', headers={'Authorization': 'Bearer at_bad'})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body['user_id'] == 0
        assert body['username'] == 'dev_user'
        assert body['permissions'] == ['*']

    def test_off_validate_rpc_failure_falls_back_dev_user(self, fake_stub,
                                                          monkeypatch):
        # auth_service 不可达 → 按查证失败回落 dev_user，不 500
        def _boom(self_, request, **kwargs):
            raise RuntimeError('auth_service 不可达')
        monkeypatch.setattr(_FakeAuthStub, 'ValidateAccessToken', _boom)
        client = self._client(_build_app('off'))
        resp = client.get('/echo', headers={'Authorization': 'Bearer garbage'})
        assert resp.status_code == 200, resp.text
        assert resp.json()['username'] == 'dev_user'

    def test_prod_validate_rpc_failure_401(self, fake_stub, monkeypatch):
        # prod 模式 auth_service 不可达 → 401（不 500）
        def _boom(self_, request, **kwargs):
            raise RuntimeError('auth_service 不可达')
        monkeypatch.setattr(_FakeAuthStub, 'ValidateAccessToken', _boom)
        client = self._client(_build_app('prod'))
        resp = client.get('/echo', headers={'Authorization': 'Bearer garbage'})
        assert resp.status_code == 401, resp.text

    def test_off_no_bearer_dev_user(self, fake_stub):
        client = self._client(_build_app('off'))
        resp = client.get('/echo')
        assert resp.status_code == 200, resp.text
        assert resp.json()['username'] == 'dev_user'

    def test_off_access_token_scopes_narrowed_403(self, fake_stub):
        # off 模式同样生效权限交集：token 无 task:read → 越权 403
        fake_stub.token_scopes = ['audio:read']
        client = self._client(_build_app('off'))
        resp = client.get('/need-task-read',
                          headers={'Authorization': 'Bearer at_testtoken'})
        assert resp.status_code == 403, resp.text

    # ---- JWT 优先分支不受影响 ----

    def test_off_valid_jwt_still_works(self, fake_stub):
        from api_gateway.application.services.auth.token_service import TokenService
        jwt_token = TokenService.create_token(
            user_id=3, username='jwt_user', role_id=1, permissions=['audio:read'])
        client = self._client(_build_app('off'))
        resp = client.get('/echo',
                          headers={'Authorization': f'Bearer {jwt_token}'})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body['user_id'] == 3
        assert body['username'] == 'jwt_user'
        assert body['permissions'] == ['audio:read']

    def test_prod_valid_jwt_still_works(self, fake_stub):
        from api_gateway.application.services.auth.token_service import TokenService
        jwt_token = TokenService.create_token(
            user_id=3, username='jwt_user', role_id=1, permissions=['task:read'])
        client = self._client(_build_app('prod'))
        resp = client.get('/need-task-read',
                          headers={'Authorization': f'Bearer {jwt_token}'})
        assert resp.status_code == 200, resp.text

    # ---- 白名单不受 access token 影响 ----

    def test_public_path_skips_auth(self, fake_stub):
        from api_gateway.middleware import AuthMiddleware
        from fastapi import FastAPI
        app = FastAPI()
        app.add_middleware(AuthMiddleware, auth_mode='prod')

        @app.get('/api/v1/auth/mode')
        def mode():
            return {'auth_mode': 'prod'}

        client = self._client(app)
        resp = client.get('/api/v1/auth/mode')  # 白名单，无 token 可达
        assert resp.status_code == 200, resp.text
        assert resp.json()['auth_mode'] == 'prod'


# ============================================================
# 网关 /api/v1/auth/access-tokens CRUD 转发（auth_service 本组 HTTP 端点）
# ============================================================

class TestAccessTokenCrudRoutes:

    @pytest.fixture()
    def client(self, fake_stub, monkeypatch):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from api_gateway.middleware import AuthMiddleware, RequestAdapterMiddleware
        from api_gateway.routes.auth_bp import router as auth_router

        app = FastAPI()
        app.add_middleware(RequestAdapterMiddleware)
        app.add_middleware(AuthMiddleware, auth_mode='off')
        app.include_router(auth_router, prefix='/api/v1/auth', tags=['auth'])

        # 打桩 httpx.request：模拟 auth_service 本组 HTTP 端点响应透传
        import httpx
        upstream = {'status_code': 200, 'json': {'success': True, 'message': 'ok',
                                                 'data': {'id': 1, 'name': 't'}}}

        def _fake_request(method, url, json=None, headers=None, timeout=None):
            return SimpleNamespace(status_code=upstream['status_code'],
                                   json=lambda: upstream['json'],
                                   text=__import__('json').dumps(upstream['json']))

        monkeypatch.setattr(httpx, 'request', _fake_request)
        self._upstream = upstream
        with TestClient(app) as c:
            yield c

    def _auth_headers(self):
        from api_gateway.application.services.auth.token_service import TokenService
        jwt_token = TokenService.create_token(
            user_id=5, username='owner', role_id=1, permissions=['*'])
        return {'Authorization': f'Bearer {jwt_token}'}

    def test_post_forwards_with_x_user_id_and_body(self, client):
        resp = client.post('/api/v1/auth/access-tokens',
                           headers=self._auth_headers(),
                           json={'name': 't1', 'scopes': ['task:read']})
        assert resp.status_code == 200, resp.text
        assert resp.json()['data']['id'] == 1
        # 无明文泄露：透传 auth_service 响应（掩码由 auth_service 保证）

    def test_get_list_passthrough(self, client):
        resp = client.get('/api/v1/auth/access-tokens',
                          headers=self._auth_headers())
        assert resp.status_code == 200, resp.text

    def test_get_detail_passthrough(self, client):
        resp = client.get('/api/v1/auth/access-tokens/1',
                          headers=self._auth_headers())
        assert resp.status_code == 200, resp.text

    def test_patch_forwards(self, client):
        resp = client.patch('/api/v1/auth/access-tokens/1',
                            headers=self._auth_headers(),
                            json={'status': 'disabled'})
        assert resp.status_code == 200, resp.text

    def test_delete_forwards(self, client):
        resp = client.delete('/api/v1/auth/access-tokens/1',
                             headers=self._auth_headers())
        assert resp.status_code == 200, resp.text

    def test_off_dev_user_401(self, client):
        # 无 token → off 模式 dev_user（user_id=0）→ 未认证 401
        resp = client.post('/api/v1/auth/access-tokens',
                           json={'name': 'no-user'})
        assert resp.status_code == 401, resp.text

    def test_upstream_error_passthrough(self, client):
        self._upstream.update({'status_code': 404,
                               'json': {'detail': 'Access Token 不存在'}})
        resp = client.get('/api/v1/auth/access-tokens/999999',
                          headers=self._auth_headers())
        assert resp.status_code == 404, resp.text
        assert resp.json()['detail'] == 'Access Token 不存在'

    def test_upstream_unavailable_502(self, client, monkeypatch):
        import httpx

        def _boom(method, url, json=None, headers=None, timeout=None):
            raise httpx.ConnectError('auth_service 不可达')

        monkeypatch.setattr(httpx, 'request', _boom)
        resp = client.get('/api/v1/auth/access-tokens',
                          headers=self._auth_headers())
        assert resp.status_code == 502, resp.text
