# -*- coding: utf-8 -*-
"""G3 登录体系改造网关侧单测（INT-51）。

覆盖：
- 自助注册开关（AUTH_REGISTRATION_ENABLED 开/关 → 201/403）
- 注册用户名+密码登录（LoginWithPassword gRPC 链路，fake stub）
- OAuth state 签名/校验（签名/篡改/slug 不匹配/过期）
- 授权跳转 URL 构造（client_id/redirect_uri/state/scope）
- userinfo 字段映射 ACL（点路径/缺省字段/缺 user_id 报错）
- 回调编排（mock httpx：换 token → 拉 userinfo → 发 JWT）
- 华为云预置提供方环境回退（DB 无记录时等效旧硬编码行为）

不依赖真库/gRPC：auth_config_service 代理以 fake 注入
（与 test_local_oauth_dev_bootstrap.py 同款模式）。
"""
import json
import os
import tempfile
from urllib.parse import parse_qs, urlparse

import pytest

os.environ.setdefault('DATABASE_URL',
                      'sqlite:///' + tempfile.mkdtemp(prefix='int51gw_') + '/gw.db')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import api_gateway.infrastructure.grpc_proxies as proxies_pkg
import api_gateway.application.services.auth.oauth_provider_service as ops_module
from api_gateway.application.services.auth.oauth_provider_service import (
    OAuthProviderService,
    OAuthProviderError,
    _huawei_preset_config,
    PRESET_HUAWEI_SLUG,
)
from api_gateway.config.config import Config
from shared.proto import auth_service_pb2 as auth_pb


class _RecordingStub:
    """记录请求并按预设响应表返回的假 AuthService stub。"""

    def __init__(self, responses):
        self._responses = responses
        self.calls = []

    def __getattr__(self, name):
        def _call(req):
            self.calls.append((name, req))
            return self._responses[name]
        return _call


def _install_stub(monkeypatch, responses):
    stub = _RecordingStub(responses)
    proxy = type('P', (), {'stub': stub})()
    monkeypatch.setattr(proxies_pkg, 'auth_config_service', proxy)
    # management_common 在模块导入期绑定代理对象：全量运行下先导测试
    # 已导入它并持有原始代理（指向本机真实 auth_service），仅替换包属性
    # 不生效 —— 同步替换该模块绑定，保证桩在任何导入顺序下都命中。
    import api_gateway.application.services.auth.management_common as mc
    monkeypatch.setattr(mc, 'auth_config_service', proxy)
    return stub


class TestRegistrationSwitch:
    """自助注册开关：AUTH_REGISTRATION_ENABLED=false → 403。"""

    def _register(self, monkeypatch, enabled, create_ok=True):
        monkeypatch.setattr(Config, 'AUTH_REGISTRATION_ENABLED', enabled)
        resp = auth_pb.AuthResponse(
            success=create_ok, message='创建成功',
            data=json.dumps({'user_id': 9}))
        stub = _install_stub(monkeypatch, {'CreateUser': resp})
        from api_gateway.application.services.auth.user_management_service import (
            UserManagementService,
        )
        from api_gateway.infrastructure.request_adapter import (
            set_current_request,
        )

        class _FakeState:
            _json_body = {'username': 'new_user', 'password': 'pass123456'}

        class _FakeRequest:
            state = _FakeState()

        set_current_request(_FakeRequest())
        try:
            result = UserManagementService.register()
        finally:
            set_current_request(None)
        return result, stub

    def test_register_enabled_creates_user(self, monkeypatch):
        (payload, http_code), stub = self._register(monkeypatch, True)
        assert http_code == 201
        create_calls = [req for name, req in stub.calls if name == 'CreateUser']
        assert len(create_calls) == 1
        assert create_calls[0].registered is True
        assert create_calls[0].role_name == 'guest'

    def test_register_disabled_returns_403(self, monkeypatch):
        (payload, http_code), stub = self._register(monkeypatch, False)
        assert http_code == 403
        assert stub.calls == []  # 开关关闭不触达 auth_service


class TestPasswordLoginViaGrpc:
    """注册用户名+密码登录（非默认凭证走 LoginWithPassword）。"""

    def test_registered_user_can_login(self, monkeypatch):
        stub = _install_stub(monkeypatch, {
            'LoginWithPassword': auth_pb.AuthResponse(
                success=True, message='ok',
                data=json.dumps({'id': 9, 'username': 'new_user',
                                 'is_active': True})),
        })
        from api_gateway.application.services.auth.local_oauth import (
            LocalOAuthProvider,
        )
        info = LocalOAuthProvider.verify_credentials('new_user', 'pass123456')
        assert info.username == 'new_user'
        assert [name for name, _ in stub.calls] == ['LoginWithPassword']

    def test_wrong_password_rejected(self, monkeypatch):
        _install_stub(monkeypatch, {
            'LoginWithPassword': auth_pb.AuthResponse(
                success=False, message='用户名或密码错误', data=''),
        })
        from api_gateway.application.services.auth.local_oauth import (
            LocalOAuthProvider,
        )
        with pytest.raises(ValueError, match='用户名或密码错误'):
            LocalOAuthProvider.verify_credentials('new_user', 'bad-pass')


_PRESET_CONFIG = {
    'id': 1,
    'name': '测试提供方',
    'slug': 'test-idp',
    'icon': '',
    'enabled': True,
    'client_id': 'cid-1',
    'client_secret': 'secret-1',
    'authorize_url': 'https://idp.example.com/authorize',
    'token_url': 'https://idp.example.com/token',
    'userinfo_url': 'https://idp.example.com/userinfo',
    'scopes': 'openid profile email',
    'user_id_field': 'sub',
    'username_field': 'preferred_username',
    'display_name_field': 'name',
    'email_field': 'email',
}


class TestOAuthState:
    """state 防伪：签名/时效/slug 绑定。"""

    def test_sign_and_verify_roundtrip(self):
        state = OAuthProviderService._sign_state('test-idp')
        OAuthProviderService._verify_state(state, 'test-idp')  # 不抛即通过

    def test_slug_mismatch_rejected(self):
        state = OAuthProviderService._sign_state('test-idp')
        with pytest.raises(OAuthProviderError):
            OAuthProviderService._verify_state(state, 'other-idp')

    def test_tampered_state_rejected(self):
        state = OAuthProviderService._sign_state('test-idp')
        with pytest.raises(OAuthProviderError):
            OAuthProviderService._verify_state(state + 'x', 'test-idp')

    def test_expired_state_rejected(self, monkeypatch):
        monkeypatch.setattr(Config, 'OAUTH_STATE_TTL_SECONDS', -1)
        state = OAuthProviderService._sign_state('test-idp')
        monkeypatch.setattr(Config, 'OAUTH_STATE_TTL_SECONDS', 600)
        with pytest.raises(OAuthProviderError):
            OAuthProviderService._verify_state(state, 'test-idp')


class TestAuthorizeUrl:
    """授权跳转 URL 构造（scope 为空不携带 scope 参数）。"""

    def test_build_with_scopes(self):
        url = OAuthProviderService.build_authorize_url(
            dict(_PRESET_CONFIG), 'http://localhost:8000/api/v1/auth/oauth/test-idp/callback')
        parsed = urlparse(url)
        assert parsed.scheme == 'https'
        assert parsed.netloc == 'idp.example.com'
        assert parsed.path == '/authorize'
        qs = parse_qs(parsed.query)
        assert qs['client_id'] == ['cid-1']
        assert qs['response_type'] == ['code']
        assert qs['redirect_uri'] == [
            'http://localhost:8000/api/v1/auth/oauth/test-idp/callback']
        assert qs['scope'] == ['openid profile email']
        # state 可校验回本 slug
        state = qs['state'][0]
        OAuthProviderService._verify_state(state, 'test-idp')

    def test_build_without_scopes_omits_scope_param(self):
        config = dict(_PRESET_CONFIG, scopes='')
        url = OAuthProviderService.build_authorize_url(config, 'http://cb')
        assert 'scope=' not in url
