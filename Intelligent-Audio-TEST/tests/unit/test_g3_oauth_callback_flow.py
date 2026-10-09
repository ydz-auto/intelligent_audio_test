# -*- coding: utf-8 -*-
"""G3 OAuth 回调流程网关侧单测（INT-51）。

覆盖：
- userinfo 字段映射 ACL（点路径提取 / 缺省字段 / 缺 user_id 报错）
- 回调编排（mock httpx：换 token → 拉 userinfo → 映射 → UserInfo）
- state 校验失败 / 未知提供方拒绝
- 华为云预置提供方环境回退（DB 无记录时等效旧硬编码行为）
"""
import os
import tempfile
from urllib.parse import parse_qs, urlparse

import pytest

os.environ.setdefault('DATABASE_URL',
                      'sqlite:///' + tempfile.mkdtemp(prefix='int51cb_') + '/gw.db')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from api_gateway.application.services.auth.oauth_provider_service import (
    OAuthProviderService,
    OAuthProviderError,
    _huawei_preset_config,
    PRESET_HUAWEI_SLUG,
)
from api_gateway.config.config import Config


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


def _mock_http(monkeypatch, userinfo):
    """mock httpx.post/get，捕获请求参数。"""
    class _Resp:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    captured = {}

    def fake_post(url, data=None, timeout=None):
        captured['token_url'] = url
        captured['token_data'] = data
        return _Resp({'access_token': 'at-123', 'token_type': 'Bearer'})

    def fake_get(url, headers=None, timeout=None):
        captured['userinfo_url'] = url
        captured['userinfo_headers'] = headers
        return _Resp(userinfo)

    monkeypatch.setattr('httpx.post', fake_post)
    monkeypatch.setattr('httpx.get', fake_get)
    return captured


class TestFieldMappingAcl:
    """userinfo 字段映射 ACL：点路径提取 / 缺省字段 / 缺 user_id 报错。"""

    def test_map_fields_dot_path(self):
        userinfo = {
            'sub': 'u-1001',
            'preferred_username': 'zhang.san',
            'name': '张三',
            'contacts': {'email': 'zhang@example.com'},
        }
        config = dict(_PRESET_CONFIG,
                      user_id_field='sub',
                      username_field='preferred_username',
                      display_name_field='name',
                      email_field='contacts.email')
        user_id, username, display_name, email = \
            OAuthProviderService._map_fields(config, userinfo)
        assert user_id == 'u-1001'
        assert username == 'zhang.san'
        assert display_name == '张三'
        assert email == 'zhang@example.com'

    def test_map_fields_defaults(self):
        userinfo = {'sub': 'u-1', 'preferred_username': 'u1',
                    'name': 'User One', 'email': 'u1@x.com'}
        config = dict(_PRESET_CONFIG, user_id_field='', username_field='',
                      display_name_field='', email_field='')
        user_id, username, _, _ = OAuthProviderService._map_fields(
            config, userinfo)
        assert user_id == 'u-1'
        assert username == 'u1'

    def test_map_fields_missing_user_id_raises(self):
        config = dict(_PRESET_CONFIG, user_id_field='data.id')
        with pytest.raises(OAuthProviderError):
            OAuthProviderService._map_fields(config, {'sub': 'u-1'})


class TestOAuthCallbackFlow:
    """回调编排：state 校验 → 换 token → 拉 userinfo → 映射。"""

    def test_callback_end_to_end(self, monkeypatch):
        config = dict(_PRESET_CONFIG)
        captured = _mock_http(monkeypatch, {
            'sub': 'ext-9', 'preferred_username': 'oauth_user',
            'name': 'OAuth User', 'email': 'o@x.com',
        })
        monkeypatch.setattr(
            OAuthProviderService, 'get_provider_config',
            staticmethod(lambda slug, include_disabled=False:
                         config if slug == 'test-idp' else None))
        state = OAuthProviderService._sign_state('test-idp')
        info = OAuthProviderService.handle_callback(
            'test-idp', 'code-abc', state,
            'http://localhost:8000/api/v1/auth/oauth/test-idp/callback')
        assert info.external_id == 'ext-9'
        assert info.username == 'oauth_user'
        assert info.email == 'o@x.com'
        # token 请求携带客户端凭证与授权码
        assert captured['token_url'] == 'https://idp.example.com/token'
        assert captured['token_data']['code'] == 'code-abc'
        assert captured['token_data']['client_id'] == 'cid-1'
        assert captured['token_data']['client_secret'] == 'secret-1'
        # userinfo 以 Bearer 携带 access_token
        assert captured['userinfo_headers']['Authorization'] == 'Bearer at-123'

    def test_callback_bad_state_rejected(self, monkeypatch):
        _mock_http(monkeypatch, {'sub': 'ext-9'})
        monkeypatch.setattr(
            OAuthProviderService, 'get_provider_config',
            staticmethod(
                lambda slug, include_disabled=False: dict(_PRESET_CONFIG)))
        with pytest.raises(OAuthProviderError):
            OAuthProviderService.handle_callback(
                'test-idp', 'code-abc', 'tampered-state', 'http://cb')

    def test_callback_unknown_provider_rejected(self, monkeypatch):
        from shared.proto import auth_service_pb2 as auth_pb
        stub = type('S', (), {
            'GetOAuthProviderBySlug': staticmethod(lambda req: auth_pb.AuthResponse(
                success=False, message='提供方不存在', data='')),
        })()
        proxy = type('P', (), {'stub': stub})()
        import api_gateway.infrastructure.grpc_proxies as proxies_pkg
        monkeypatch.setattr(proxies_pkg, 'auth_config_service', proxy)
        with pytest.raises(OAuthProviderError):
            OAuthProviderService.handle_callback(
                'no-such-idp', 'code', 'state', 'http://cb')


class TestStateSecurity:
    """state 防伪：签名 / 篡改 / slug 绑定 / 时效。"""

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
            dict(_PRESET_CONFIG),
            'http://localhost:8000/api/v1/auth/oauth/test-idp/callback')
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
        OAuthProviderService._verify_state(qs['state'][0], 'test-idp')

    def test_build_without_scopes_omits_scope_param(self):
        config = dict(_PRESET_CONFIG, scopes='')
        url = OAuthProviderService.build_authorize_url(config, 'http://cb')
        assert 'scope=' not in url


class TestHuaweiPresetFallback:
    """华为云预置提供方：DB 无记录时以环境变量等效回归旧硬编码行为。"""

    def test_preset_config_from_env(self, monkeypatch):
        monkeypatch.setattr(Config, 'HW_OAUTH_CLIENT_ID', 'hw-client')
        monkeypatch.setattr(Config, 'HW_OAUTH_CLIENT_SECRET', 'hw-secret')
        monkeypatch.setattr(
            Config, 'HW_OAUTH_AUTHORIZE_URL',
            'https://oauth.huaweicloud.com/oauth2/authorize')
        monkeypatch.setattr(
            Config, 'HW_OAUTH_TOKEN_URL',
            'https://oauth.huaweicloud.com/oauth2/token')
        monkeypatch.setattr(
            Config, 'HW_OAUTH_USERINFO_URL',
            'https://oauth.huaweicloud.com/oauth2/userinfo')
        config = _huawei_preset_config()
        assert config['slug'] == PRESET_HUAWEI_SLUG == 'huawei'
        assert config['client_id'] == 'hw-client'
        assert config['user_id_field'] == 'sub'
        assert config['username_field'] == 'preferred_username'

    def test_preset_authorize_url_matches_legacy_behavior(self, monkeypatch):
        """预置提供方授权 URL 与旧 HuaweiOAuthProvider.get_login_url 等效。"""
        from api_gateway.application.services.auth.huawei_oauth import (
            HuaweiOAuthProvider,
        )
        monkeypatch.setattr(Config, 'HW_OAUTH_CLIENT_ID', 'hw-client')
        monkeypatch.setattr(
            Config, 'HW_OAUTH_REDIRECT_URI',
            'http://localhost:8000/api/v1/auth/callback')
        monkeypatch.setattr(
            Config, 'HW_OAUTH_AUTHORIZE_URL',
            'https://oauth.huaweicloud.com/oauth2/authorize')
        legacy_url = HuaweiOAuthProvider.get_login_url(state='auth')
        legacy = urlparse(legacy_url)
        legacy_qs = parse_qs(legacy.query)

        config = _huawei_preset_config()
        url = OAuthProviderService.build_authorize_url(
            config, 'http://localhost:8000/api/v1/auth/callback')
        parsed = urlparse(url)
        qs = parse_qs(parsed.query)
        # 端点与业务参数一致（state 为签名 token，格式不同属预期）
        assert (f'{parsed.scheme}://{parsed.netloc}{parsed.path}'
                == f'{legacy.scheme}://{legacy.netloc}{legacy.path}')
        assert qs['client_id'] == legacy_qs['client_id']
        assert qs['redirect_uri'] == legacy_qs['redirect_uri']
        assert qs['response_type'] == legacy_qs['response_type'] == ['code']
        OAuthProviderService._verify_state(qs['state'][0], 'huawei')
