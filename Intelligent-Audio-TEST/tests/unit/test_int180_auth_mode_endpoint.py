# -*- coding: utf-8 -*-
"""INT-180 auth_mode 启动自检联动回归。

- 网关 GET /api/v1/auth/mode 未认证可达（白名单同 /auth/oauth/providers
  公开口径），仅回枚举 mode 值，无其他配置项泄漏
- AUTH_MODE 取值 enum 化（shared.constants.auth_mode）：非法值启动校验
  报错（Config.validate fail fast）、get_auth_mode 归一抛错
- auth_service 边界 GET /api/auth/mode 同口径回值（其 HTTP 面自身可观测）

网关侧走真实 AuthMiddleware（httpx ASGITransport 直驱最小应用，对齐
test_int179_login_chain_fix 的"真实路由 + 真实中间件"口径）。
"""
import os

import httpx
import pytest
from fastapi import FastAPI

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')


def _gateway_app(auth_mode: str):
    """最小网关应用：真实 auth 路由 + 真实 AuthMiddleware。"""
    mp = pytest.MonkeyPatch()
    from api_gateway.config.config import Config
    mp.setattr(Config, 'AUTH_MODE', auth_mode)
    from api_gateway.middleware import RequestAdapterMiddleware, AuthMiddleware
    from api_gateway.routes.auth_bp import router as auth_router

    app = FastAPI()
    app.add_middleware(RequestAdapterMiddleware)
    app.add_middleware(AuthMiddleware, auth_mode=auth_mode)
    app.include_router(auth_router, prefix='/api/v1/auth')
    app.client_state = mp  # 随 app 存活，测试结束后统一 undo
    return app


@pytest.fixture()
def gateway_client(request):
    """按参数化 auth_mode 构建客户端；teardown 还原 monkeypatch。"""
    app = _gateway_app(request.param)
    from fastapi.testclient import TestClient
    with TestClient(app) as client:
        yield client
    app.client_state.undo()


class TestGatewayAuthModeEndpoint:
    """网关 /auth/mode：未认证可读 + 枚举回值 + 无额外配置泄漏。"""

    @pytest.mark.parametrize('gateway_client', ['dev'], indirect=True)
    def test_no_auth_returns_mode(self, gateway_client):
        """无 token GET /auth/mode → 200 {"auth_mode": "dev"}。"""
        resp = gateway_client.get('/api/v1/auth/mode')
        assert resp.status_code == 200, resp.text
        assert resp.json() == {'auth_mode': 'dev'}

    @pytest.mark.parametrize('gateway_client', ['off', 'prod'], indirect=True)
    def test_enum_values_roundtrip(self, gateway_client):
        """off/prod 同口径回值（枚举集合内任一取值）。"""
        from api_gateway.config.config import Config
        resp = gateway_client.get('/api/v1/auth/mode')
        assert resp.status_code == 200, resp.text
        assert resp.json() == {'auth_mode': Config.AUTH_MODE}

    @pytest.mark.parametrize('gateway_client', ['prod'], indirect=True)
    def test_whitelist_reachable_in_enforcing_mode(self, gateway_client):
        """prod（JWT 强制）态无 token 仍 200 —— 白名单生效而非 off 放行。"""
        resp = gateway_client.get('/api/v1/auth/mode')
        assert resp.status_code == 200, resp.text

    @pytest.mark.parametrize('gateway_client', ['prod'], indirect=True)
    def test_middleware_really_enforcing(self, gateway_client):
        """对照用例：同应用下非白名单鉴权路径无 token → 401。"""
        resp = gateway_client.get('/api/v1/auth/me')
        assert resp.status_code == 401, resp.text

    @pytest.mark.parametrize('gateway_client', ['dev'], indirect=True)
    def test_no_extra_config_leaked(self, gateway_client):
        """响应仅 auth_mode 一个键，无任何其他配置项。"""
        body = gateway_client.get('/api/v1/auth/mode').json()
        assert set(body.keys()) == {'auth_mode'}


class TestAuthModeEnum:
    """shared 枚举：取值集合、归一与非法值拒绝。"""

    def test_values(self):
        from shared.constants.auth_mode import AUTH_MODE_VALUES, AuthMode
        assert AUTH_MODE_VALUES == ('off', 'dev', 'prod')
        assert AuthMode.OFF.value == 'off'

    def test_normalize_accepts_enum_and_str(self):
        from shared.constants.auth_mode import AuthMode, normalize_auth_mode
        assert normalize_auth_mode('dev') == 'dev'
        assert normalize_auth_mode(AuthMode.PROD) == 'prod'

    def test_normalize_rejects_invalid(self):
        from shared.constants.auth_mode import normalize_auth_mode
        with pytest.raises(ValueError):
            normalize_auth_mode('DEV')  # 大写不在枚举内（拒绝魔法变体）
        with pytest.raises(ValueError):
            normalize_auth_mode('')

    def test_gateway_validate_rejects_invalid_auth_mode(self):
        """网关启动校验：非法 AUTH_MODE 启动即自曝（fail fast）。"""
        from api_gateway.config.config import Config
        from shared.infrastructure.config import ConfigValidationError
        mp = pytest.MonkeyPatch()
        mp.setattr(Config, 'AUTH_MODE', 'typo-mode')
        try:
            with pytest.raises(ConfigValidationError, match='AUTH_MODE'):
                Config.validate()
        finally:
            mp.undo()

    def test_gateway_validate_passes_valid_auth_mode(self):
        from api_gateway.config.config import Config
        mp = pytest.MonkeyPatch()
        mp.setattr(Config, 'AUTH_MODE', 'dev')
        try:
            Config.validate()  # 不抛即过
        finally:
            mp.undo()


class TestAuthServiceEndpoint:
    """auth_service 边界 /api/auth/mode 同口径。"""

    def test_auth_service_mode_endpoint(self):
        mp = pytest.MonkeyPatch()
        from auth_service.config.config import Config
        mp.setattr(Config, 'AUTH_MODE', 'dev')
        try:
            from fastapi import FastAPI as _FastAPI
            from auth_service.interfaces.api.routes import router

            app = _FastAPI()
            app.include_router(router)
            from fastapi.testclient import TestClient
            with TestClient(app) as client:
                resp = client.get('/api/auth/mode')
            assert resp.status_code == 200, resp.text
            body = resp.json()
            assert body['success'] is True
            assert body['data'] == {'auth_mode': 'dev'}
        finally:
            mp.undo()


def _off_app_with_me_route():
    """最小网关应用：真实 AuthMiddleware(auth_mode='off') + /me 暴露注入身份。

    /me 同时回 state 注入值（request.state.user_id / username）与出站上下文
    get_current_user_id()，用于锁定 INT-774 方案 A 的可选 Bearer 解析行为。
    """
    from api_gateway.middleware import RequestAdapterMiddleware, AuthMiddleware

    app = FastAPI()

    @app.get('/me')
    def me():
        from api_gateway.infrastructure.request_adapter import get_current_request
        from shared.infrastructure.user_context import get_current_user_id
        req = get_current_request()
        return {
            'context_user_id': get_current_user_id(),
            'state_user_id': getattr(req.state, 'user_id', None),
            'username': getattr(req.state, 'username', None),
        }

    app.add_middleware(RequestAdapterMiddleware)
    app.add_middleware(AuthMiddleware, auth_mode='off')
    return app


class TestAuthOffOptionalBearer:
    """INT-774 方案 A：AUTH_MODE=off Bearer 可选解析。

    off 从「完全跳过认证」演进为「可选认证」——有合法 token 注入真实 user_id
    （购物车等 per-user 写侧可用）；无/无效 token 保持 None 空态
    （dev_user 归一未认证，不充当真实操作人，不 401）。
    """

    @pytest.fixture()
    def off_client(self):
        app = _off_app_with_me_route()
        from fastapi.testclient import TestClient
        with TestClient(app) as client:
            yield client

    def test_no_token_keeps_none_state(self, off_client):
        """无 token → state 注入 dev_user（user_id=0 归一 None），context None。"""
        body = off_client.get('/me').json()
        assert body['context_user_id'] is None
        assert body['state_user_id'] == 0
        assert body['username'] == 'dev_user'

    def test_valid_bearer_injects_real_user(self, off_client):
        """合法 Bearer → 注入真实 user_id（per-user 写侧 _require_user 不再拒绝）。"""
        from api_gateway.application.services.auth.token_service import TokenService
        token = TokenService.create_token(42, 'alice', 1, ['*'])
        body = off_client.get('/me', headers={'Authorization': f'Bearer {token}'}).json()
        assert body['context_user_id'] == 42
        assert body['state_user_id'] == 42
        assert body['username'] == 'alice'

    def test_invalid_bearer_keeps_none_state(self, off_client):
        """无效 token → 不 401，保持 None 空态（Bearer 可选，非强制）。"""
        body = off_client.get('/me', headers={'Authorization': 'Bearer garbage'}).json()
        assert body['context_user_id'] is None
        assert body['state_user_id'] == 0
        assert body['username'] == 'dev_user'
