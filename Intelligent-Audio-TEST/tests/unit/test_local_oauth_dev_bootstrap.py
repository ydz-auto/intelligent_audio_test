# -*- coding: utf-8 -*-
"""dev 模式首个 admin 引导单测（INT-36）。

覆盖 LocalOAuthProvider 默认凭证建用户的角色绑定逻辑：
- 默认凭证 + 用户不存在 → CreateUser 携带 role_name=DEV_DEFAULT_ROLE（默认 admin）；
- 自定义 DEV_DEFAULT_ROLE → 按配置透传角色名；
- 用户已存在 → 不触发 CreateUser，直接放行；
- CreateUser 失败（如角色未 seed）→ 抛 ValueError 中断登录，
  不再放行给 _find_or_create_user 以无角色兜底建号（回归守护）；
- 非默认凭证不触发建号（默认凭证建号逻辑不外溢）。

不依赖真库/gRPC：auth_config_service 代理以 fake 注入
（与 test_auth_user_role_management.py 网关侧同款模式）。
"""
import json
import os
import tempfile

import pytest

# api_gateway.config（经 BaseConfig）在导入期强制要求 DATABASE_URL，
# 且类属性在首次导入时冻结 —— 必须先设环境变量再触发导入。
os.environ.setdefault('DATABASE_URL',
                      'sqlite:///' + tempfile.mkdtemp(prefix='int36_') + '/unit.db')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import api_gateway.application.services.auth.local_oauth as local_oauth_module
import api_gateway.infrastructure.grpc_proxies as proxies_pkg
from api_gateway.config.config import Config
from api_gateway.domain.value_objects.auth_value_objects import UserInfo
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
    """替换 grpc_proxies 包级 auth_config_service 单例（函数内延迟 import
    每次调用都从包属性取值，patch 该属性即可生效）。"""
    stub = _RecordingStub(responses)
    proxy = type('P', (), {'stub': stub})()
    monkeypatch.setattr(proxies_pkg, 'auth_config_service', proxy)
    return stub


def _user_not_found_resp():
    return auth_pb.AuthResponse(success=False, message='用户不存在', data='')


class TestDefaultCredentialRoleBinding:

    def test_first_login_binds_default_role(self, monkeypatch):
        """首次登录（用户不存在）→ CreateUser 携带 DEV_DEFAULT_ROLE。"""
        stub = _install_stub(monkeypatch, {
            'GetUserByUsername': _user_not_found_resp(),
            'CreateUser': auth_pb.AuthResponse(
                success=True, message='创建成功',
                data=json.dumps({'user_id': 1})),
        })
        info = local_oauth_module.LocalOAuthProvider.verify_credentials(
            Config.DEV_DEFAULT_USERNAME, Config.DEV_DEFAULT_PASSWORD)
        assert isinstance(info, UserInfo)
        create_calls = [req for name, req in stub.calls if name == 'CreateUser']
        assert len(create_calls) == 1
        assert create_calls[0].role_name == Config.DEV_DEFAULT_ROLE
        assert Config.DEV_DEFAULT_ROLE == 'admin'  # 默认配置必须引导出 admin

    def test_custom_dev_default_role_is_passed_through(self, monkeypatch):
        """自定义 DEV_DEFAULT_ROLE → 按配置透传角色名。"""
        monkeypatch.setattr(Config, 'DEV_DEFAULT_ROLE', 'tester')
        stub = _install_stub(monkeypatch, {
            'GetUserByUsername': _user_not_found_resp(),
            'CreateUser': auth_pb.AuthResponse(
                success=True, message='创建成功',
                data=json.dumps({'user_id': 1})),
        })
        local_oauth_module.LocalOAuthProvider.verify_credentials(
            Config.DEV_DEFAULT_USERNAME, Config.DEV_DEFAULT_PASSWORD)
        create_calls = [req for name, req in stub.calls if name == 'CreateUser']
        assert create_calls[0].role_name == 'tester'

    def test_existing_user_skips_create(self, monkeypatch):
        """用户已存在 → 不再触发 CreateUser，直接放行。"""
        stub = _install_stub(monkeypatch, {
            'GetUserByUsername': auth_pb.AuthResponse(
                success=True, message='ok',
                data=json.dumps({'id': 1, 'username': 'dev_user',
                                 'role_id': 1, 'is_active': True})),
        })
        info = local_oauth_module.LocalOAuthProvider.verify_credentials(
            Config.DEV_DEFAULT_USERNAME, Config.DEV_DEFAULT_PASSWORD)
        assert isinstance(info, UserInfo)
        assert [name for name, _ in stub.calls] == ['GetUserByUsername']

    def test_create_failure_raises_instead_of_roleless_fallback(self, monkeypatch):
        """CreateUser 失败（如角色未 seed）→ 抛 ValueError 中断登录。

        回归守护：修复前失败被吞掉，下游 _find_or_create_user 会以
        无角色兜底建号，重新引入「首个用户无权限」。
        """
        _install_stub(monkeypatch, {
            'GetUserByUsername': _user_not_found_resp(),
            'CreateUser': auth_pb.AuthResponse(
                success=False, message='角色不存在: admin', data=''),
        })
        with pytest.raises(ValueError, match='角色不存在'):
            local_oauth_module.LocalOAuthProvider.verify_credentials(
                Config.DEV_DEFAULT_USERNAME, Config.DEV_DEFAULT_PASSWORD)

    def test_non_default_credentials_do_not_create_user(self, monkeypatch):
        """非默认凭证且用户不存在 → 拒绝登录，不触发建号。"""
        stub = _install_stub(monkeypatch, {
            'GetUserByUsername': _user_not_found_resp(),
        })
        with pytest.raises(ValueError, match='用户名或密码错误'):
            local_oauth_module.LocalOAuthProvider.verify_credentials(
                'nobody', 'wrong-password')
        assert [name for name, _ in stub.calls] == ['GetUserByUsername']
