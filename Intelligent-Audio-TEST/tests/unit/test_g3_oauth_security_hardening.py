# -*- coding: utf-8 -*-
"""INT-51 审计打回修复单测：OAuth 账户绑定与提供方三态（网关侧）。

对照 2026-10-09 代码审计问题清单：
- P1-1 自定义提供方 OAuth 同名不合并既有本地账户（username 冲突降级
  {slug}_{username} 建号）；本地密码登录与预置 huawei 合并语义保持
- P1-2 get_provider_config 仅在 OAUTH_PROVIDER_NOT_FOUND 时回退华为云
  环境预置；禁用（OAUTH_PROVIDER_DISABLED）/无 error_code 失败一律拒绝；
  get_login_entry 禁用/未配置不再回退旧硬编码授权页

不依赖真库/gRPC：auth_config_service 代理以假 stub 注入
（与 test_g3_oauth_login_flow 同款模式）。
"""
import json
import os
import tempfile

os.environ.setdefault('DATABASE_URL',
                      'sqlite:///' + tempfile.mkdtemp(prefix='int51sec_')
                      + '/gw.db')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from api_gateway.application.services.auth.auth_service import AuthService
from api_gateway.application.services.auth.oauth_provider_service import (
    OAuthProviderService,
    _huawei_preset_config,
)
from api_gateway.config.config import Config
from api_gateway.domain.value_objects.auth_value_objects import UserInfo
from shared.proto import auth_service_pb2 as auth_pb


class _RecordingStub:
    """记录请求并按预设响应表返回的假 AuthService stub。

    预设值为 list 时按序弹出（同 RPC 多次调用），为 callable 时以请求
    为参调用，否则常量返回。
    """

    def __init__(self, responses):
        self._responses = responses
        self.calls = []

    def __getattr__(self, name):
        def _call(req):
            self.calls.append((name, req))
            preset = self._responses[name]
            if isinstance(preset, list):
                assert preset, f'{name} 预设响应已耗尽'
                return preset.pop(0) if len(preset) > 1 else preset[0]
            if callable(preset):
                return preset(req)
            return preset
        return _call


def _install_stub(monkeypatch, responses):
    stub = _RecordingStub(responses)
    proxy = type('P', (), {'stub': stub})()
    import api_gateway.infrastructure.grpc_proxies as proxies_pkg
    monkeypatch.setattr(proxies_pkg, 'auth_config_service', proxy)
    # management_common 在模块导入期绑定代理对象：同步替换该模块绑定，
    # 保证桩在任何导入顺序下都命中（与 test_g3_oauth_login_flow 同款）。
    import api_gateway.application.services.auth.management_common as mc
    monkeypatch.setattr(mc, 'auth_config_service', proxy)
    return stub


def _fail(error_code='', message='失败'):
    data = json.dumps({'error_code': error_code}) if error_code else ''
    return auth_pb.AuthResponse(success=False, message=message, data=data)


def _ok(data):
    payload = data if isinstance(data, str) else json.dumps(data)
    return auth_pb.AuthResponse(success=True, message='ok', data=payload)


def _user_row(user_id=9, username='alice', role_id=2, role_name='guest'):
    return json.dumps({'id': user_id, 'username': username,
                       'role_id': role_id, 'role_name': role_name,
                       'permissions': [], 'is_active': True})


class TestOAuthAccountBinding:
    """P1-1：自定义提供方 OAuth 同名不合并既有本地账户。"""

    def test_custom_provider_same_username_creates_new_account(self, monkeypatch):
        """① (provider, subject) 未命中；② CreateUser 首次撞既有用户名
        （USERNAME_DUPLICATED）；③ 降级 {slug}_{username} 建号成功。"""
        stub = _install_stub(monkeypatch, {
            'GetUserByOAuth': _fail('USER_NOT_FOUND'),
            'CreateUser': [
                _fail('USERNAME_DUPLICATED', '用户名已存在: alice'),
                _ok({'user_id': 88}),
            ],
            'GetUser': _ok(_user_row(user_id=88, username='evil-idp_alice')),
        })
        user = AuthService._find_or_create_user(
            UserInfo(username='alice', email='a@x.com', external_id='ext-9'),
            provider='evil-idp')
        assert user.id == 88
        assert user.username == 'evil-idp_alice'
        called = [name for name, _ in stub.calls]
        # 同名既有账户不查找、更不签发其身份（接管向量关闭）
        assert 'GetUserByUsername' not in called
        creates = [req for name, req in stub.calls if name == 'CreateUser']
        assert [r.username for r in creates] == ['alice', 'evil-idp_alice']
        # 降级建号仍绑定 (provider, subject) 外部身份
        for req in creates:
            assert req.oauth_provider == 'evil-idp'
            assert req.oauth_subject == 'ext-9'

    def test_custom_provider_fresh_username_creates_single_account(self, monkeypatch):
        stub = _install_stub(monkeypatch, {
            'GetUserByOAuth': _fail('USER_NOT_FOUND'),
            'CreateUser': _ok({'user_id': 90}),
            'GetUser': _ok(_user_row(user_id=90, username='newcomer')),
        })
        user = AuthService._find_or_create_user(
            UserInfo(username='newcomer', external_id='ext-10'),
            provider='corp-idp')
        assert user.id == 90
        assert user.username == 'newcomer'
        creates = [req for name, req in stub.calls if name == 'CreateUser']
        assert len(creates) == 1  # 无冲突不降级改名

    def test_huawei_preset_username_merge_preserved(self, monkeypatch):
        """存量语义锁定：预置 huawei 按用户名合并既有账户（企业受控 IdP）。"""
        stub = _install_stub(monkeypatch, {
            'GetUserByOAuth': _fail('USER_NOT_FOUND'),
            'GetUserByUsername': _ok(_user_row(user_id=7, username='alice')),
        })
        user = AuthService._find_or_create_user(
            UserInfo(username='alice', external_id='ext-11'),
            provider='huawei')
        assert user.id == 7
        assert user.username == 'alice'
        assert 'CreateUser' not in [name for name, _ in stub.calls]

    def test_local_password_login_username_lookup_preserved(self, monkeypatch):
        """本地密码登录（无外部标识）按用户名查找保持不变。"""
        stub = _install_stub(monkeypatch, {
            'GetUserByUsername': _ok(_user_row(user_id=5, username='bob')),
        })
        user = AuthService._find_or_create_user(
            UserInfo(username='bob'), provider='')
        assert user.id == 5
        assert [name for name, _ in stub.calls] == ['GetUserByUsername']


class TestProviderConfigThreeStates:
    """P1-2：环境预置回退仅对「未配置」生效，禁用一律拒绝。"""

    def _env_huawei(self, monkeypatch):
        monkeypatch.setattr(Config, 'HW_OAUTH_CLIENT_ID', 'hw-acc-1')
        monkeypatch.setattr(Config, 'HW_OAUTH_CLIENT_SECRET', 'hw-sec-1')

    def test_disabled_huawei_rejected_even_with_env(self, monkeypatch):
        """核心修复：DB 禁用 huawei + 环境变量保留 → 不再环境回退。"""
        self._env_huawei(monkeypatch)
        _install_stub(monkeypatch, {
            'GetOAuthProviderBySlug': _fail('OAUTH_PROVIDER_DISABLED',
                                            '提供方未启用'),
        })
        assert OAuthProviderService.get_provider_config('huawei') is None

    def test_disabled_custom_provider_rejected(self, monkeypatch):
        _install_stub(monkeypatch, {
            'GetOAuthProviderBySlug': _fail('OAUTH_PROVIDER_DISABLED',
                                            '提供方未启用'),
        })
        assert OAuthProviderService.get_provider_config('corp-idp') is None

    def test_not_found_huawei_still_falls_back_to_env(self, monkeypatch):
        """回归锁定：未 seed 部署（DB 无记录）环境回退保持可用。"""
        self._env_huawei(monkeypatch)
        _install_stub(monkeypatch, {
            'GetOAuthProviderBySlug': _fail('OAUTH_PROVIDER_NOT_FOUND',
                                            '提供方不存在'),
        })
        config = OAuthProviderService.get_provider_config('huawei')
        assert config is not None
        assert config['slug'] == 'huawei'
        assert config['client_id'] == 'hw-acc-1'

    def test_not_found_without_env_rejected(self, monkeypatch):
        monkeypatch.setattr(Config, 'HW_OAUTH_CLIENT_ID', '')
        _install_stub(monkeypatch, {
            'GetOAuthProviderBySlug': _fail('OAUTH_PROVIDER_NOT_FOUND',
                                            '提供方不存在'),
        })
        assert OAuthProviderService.get_provider_config('huawei') is None

    def test_unknown_slug_not_found_no_fallback(self, monkeypatch):
        self._env_huawei(monkeypatch)
        _install_stub(monkeypatch, {
            'GetOAuthProviderBySlug': _fail('OAUTH_PROVIDER_NOT_FOUND',
                                            '提供方不存在'),
        })
        assert OAuthProviderService.get_provider_config('no-such-idp') is None

    def test_missing_error_code_no_fallback(self, monkeypatch):
        """servicer 异常兜底（无 error_code 的通用失败）不再触发回退。"""
        self._env_huawei(monkeypatch)
        _install_stub(monkeypatch, {
            'GetOAuthProviderBySlug': _fail('', '内部错误'),
        })
        assert OAuthProviderService.get_provider_config('huawei') is None


class TestLoginEntryNoLegacyBypass:
    """get_login_entry：禁用/未配置不再回退旧硬编码授权页。"""

    def test_disabled_huawei_login_entry_not_legacy_url(self, monkeypatch):
        monkeypatch.setattr(Config, 'AUTH_MODE', 'prod')
        monkeypatch.setattr(Config, 'HW_OAUTH_CLIENT_ID', 'hw-acc-1')
        _install_stub(monkeypatch, {
            'GetOAuthProviderBySlug': _fail('OAUTH_PROVIDER_DISABLED',
                                            '提供方未启用'),
        })
        entry = AuthService.get_login_entry()
        assert entry == '/#/login'
        assert 'huaweicloud' not in entry

    def test_not_found_with_env_still_preset_url(self, monkeypatch):
        """未 seed + 环境变量：登录入口等效旧行为（回退预置提供方）。"""
        monkeypatch.setattr(Config, 'AUTH_MODE', 'prod')
        monkeypatch.setattr(Config, 'HW_OAUTH_CLIENT_ID', 'hw-acc-1')
        monkeypatch.setattr(Config, 'HW_OAUTH_CLIENT_SECRET', 'hw-sec-1')
        _install_stub(monkeypatch, {
            'GetOAuthProviderBySlug': _fail('OAUTH_PROVIDER_NOT_FOUND',
                                            '提供方不存在'),
        })
        entry = AuthService.get_login_entry()
        assert entry.startswith(
            'https://oauth.huaweicloud.com/oauth2/authorize')
