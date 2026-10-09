# -*- coding: utf-8 -*-
"""G3 登录体系改造 sqlite 级自测（INT-51）。

直接驱动真实 gRPC servicer → 应用层 handler → 真实 SQLAlchemy 仓储
（SQLite 临时库），验证：
- 自定义 OAuth 提供方 CRUD 全流程（slug 规则/唯一性/掩码/启停过滤）
- 提供方审计事件（AUTH_OAUTH_PROVIDER_CREATED/UPDATED/DELETED）
- 自助注册审计事件（AUTH_USER_REGISTERED，registered=True 区分管理员建号）
- 用户名+密码登录校验（LoginWithPassword，bcrypt 真实校验）
- 提供方领域服务（配置校验默认值 / 点路径字段映射）
"""
import json
import os
import tempfile

import pytest

os.environ.setdefault('DATABASE_URL',
                      'sqlite:///' + tempfile.mkdtemp(prefix='int51_') + '/auth.db')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from shared.models.database import init_db, get_db_session, remove_db_session

# 进程唯一后缀：防共享库跨运行残留碰撞
_RUN_TAG = os.getpid()
from auth_service.infrastructure.persistence.models import (
    Role, Permission, RolePermission, UserPermission, User,
    CustomOAuthProvider,
)
from sqlalchemy import BigInteger
from sqlalchemy.ext.compiler import compiles


@compiles(BigInteger, 'sqlite')
def _render_bigint_as_integer_sqlite(type_, compiler, **kw):
    """SQLite 不支持 BigInteger 主键自增，建表时渲染为 INTEGER。"""
    return 'INTEGER'


@pytest.fixture(scope='module')
def db():
    """初始化 SQLite 库并建 auth 相关表。"""
    init_db(pool_size=3)
    from shared.models.database import Base
    Base.metadata.create_all(
        bind=get_db_session().get_bind(),
        tables=[Role.__table__, Permission.__table__, RolePermission.__table__,
                UserPermission.__table__, User.__table__,
                CustomOAuthProvider.__table__],
    )
    yield
    remove_db_session()


# ---- 测试数据与桩 ----

_PROVIDER_BASE = {
    'name': '测试提供方',
    'slug': f'test-idp-{_RUN_TAG}',
    'client_id': 'cid-1',
    'client_secret': 'secret-1',
    'authorize_url': 'https://idp.example.com/authorize',
    'token_url': 'https://idp.example.com/token',
    'userinfo_url': 'https://idp.example.com/userinfo',
    'enabled': True,
}


@pytest.fixture()
def servicer(db):
    from auth_service.interfaces.grpc.servicers import AuthServicer
    from shared.proto import auth_service_pb2 as auth_pb
    session = get_db_session()
    # 按名幂等补种（勿用 count==0 门控：共享库下部分条目已存在时会漏种本模块所需权限）
    if session.query(Permission).filter_by(name='task:read').first() is None:
        session.add(Permission(name='task:read', description='查看任务'))
        session.flush()
    return AuthServicer(), auth_pb


def _provider_request(pb, **overrides):
    fields = dict(_PROVIDER_BASE)
    fields.update(overrides)
    return pb.CreateOAuthProviderRequest(**fields)


class TestOAuthProviderCrudChain:

    def test_create_list_get_update_delete(self, servicer):
        svc, pb = servicer
        # 创建（字段映射缺省 → 领域服务自动补默认值）
        resp = svc.CreateOAuthProvider(_provider_request(pb, operator_id=1))
        assert resp.success, resp.message
        provider_id = json.loads(resp.data)['provider_id']
        assert provider_id

        # 管理端列表：client_secret 掩去（全量运行共享进程级 SQLite 库，
        # 其他模块可能已建提供方——按本模块 slug 过滤断言，不假设总数）
        resp = svc.ListOAuthProviders(pb.ListOAuthProvidersRequest(
            include_disabled=True))
        data = json.loads(resp.data)
        mine = [p for p in data['providers']
                if p['slug'] == f'test-idp-{_RUN_TAG}']
        assert len(mine) == 1
        provider = mine[0]
        assert 'client_secret' not in provider
        assert provider['has_client_secret'] is True
        # 缺省字段映射补默认值
        assert provider['user_id_field'] == 'sub'
        assert provider['username_field'] == 'preferred_username'
        assert provider['display_name_field'] == 'name'
        assert provider['email_field'] == 'email'
        assert provider['scopes'] == 'openid profile email'

        # 按 ID 详情
        resp = svc.GetOAuthProvider(pb.GetOAuthProviderRequest(
            provider_id=provider_id))
        assert resp.success, resp.message
        assert json.loads(resp.data)['slug'] == f'test-idp-{_RUN_TAG}'

        # 更新（client_secret 空串=保留原值）
        resp = svc.UpdateOAuthProvider(pb.UpdateOAuthProviderRequest(
            provider_id=provider_id, name='改名后', client_secret='',
            operator_id=1))
        assert resp.success, resp.message
        resp = svc.GetOAuthProvider(pb.GetOAuthProviderRequest(
            provider_id=provider_id))
        data = json.loads(resp.data)
        assert data['name'] == '改名后'
        assert data['has_client_secret'] is True

        # 按 slug（登录链路，含 client_secret 供网关换 token）
        resp = svc.GetOAuthProviderBySlug(pb.GetOAuthProviderBySlugRequest(
            slug=f'test-idp-{_RUN_TAG}'))
        assert resp.success, resp.message
        full = json.loads(resp.data)
        assert full['client_secret'] == 'secret-1'

        # 删除
        resp = svc.DeleteOAuthProvider(pb.DeleteOAuthProviderRequest(
            provider_id=provider_id, operator_id=1))
        assert resp.success, resp.message
        resp = svc.GetOAuthProvider(pb.GetOAuthProviderRequest(
            provider_id=provider_id))
        assert not resp.success


    def test_slug_rules_enforced(self, servicer):
        """slug 规则：小写字母/数字/连字符，首尾不得为连字符。"""
        svc, pb = servicer
        for bad_slug in ('Bad_Slug', '-lead', 'trail-', 'has space'):
            resp = svc.CreateOAuthProvider(_provider_request(pb, slug=bad_slug))
            assert not resp.success, bad_slug

    def test_duplicate_slug_rejected(self, servicer):
        svc, pb = servicer
        resp = svc.CreateOAuthProvider(_provider_request(pb))
        assert resp.success, resp.message
        resp = svc.CreateOAuthProvider(_provider_request(pb))
        assert not resp.success
        data = json.loads(resp.data)
        assert data['error_code'] == 'OAUTH_SLUG_DUPLICATED'

    def test_update_missing_provider_rejected(self, servicer):
        svc, pb = servicer
        resp = svc.UpdateOAuthProvider(pb.UpdateOAuthProviderRequest(
            provider_id=99999, name='x'))
        assert not resp.success
        data = json.loads(resp.data)
        assert data['error_code'] == 'OAUTH_PROVIDER_NOT_FOUND'

    def test_enabled_filter_public_list(self, servicer):
        """公开列表仅含启用提供方；管理端列表含禁用项。"""
        svc, pb = servicer
        resp = svc.CreateOAuthProvider(_provider_request(
            pb, slug=f'disabled-idp-{_RUN_TAG}', enabled=False))
        assert resp.success, resp.message
        disabled_id = json.loads(resp.data)['provider_id']

        resp = svc.ListEnabledOAuthProviders(
            pb.ListEnabledOAuthProvidersRequest())
        slugs = [p['slug'] for p in json.loads(resp.data)['providers']]
        assert f'disabled-idp-{_RUN_TAG}' not in slugs
        assert f'test-idp-{_RUN_TAG}' in slugs  # 前序用例创建的启用项
        # 公开列表无凭证字段
        for p in json.loads(resp.data)['providers']:
            assert 'client_secret' not in p

        # 启用后出现在公开列表
        resp = svc.UpdateOAuthProvider(pb.UpdateOAuthProviderRequest(
            provider_id=disabled_id, update_enabled=True, enabled=True))
        assert resp.success, resp.message
        resp = svc.ListEnabledOAuthProviders(
            pb.ListEnabledOAuthProvidersRequest())
        assert f'disabled-idp-{_RUN_TAG}' in [p['slug']
                                  for p in json.loads(resp.data)['providers']]

        svc.DeleteOAuthProvider(pb.DeleteOAuthProviderRequest(
            provider_id=disabled_id, operator_id=1))

    def test_by_slug_disabled_or_missing_fails(self, servicer):
        svc, pb = servicer
        resp = svc.GetOAuthProviderBySlug(pb.GetOAuthProviderBySlugRequest(
            slug='no-such-idp'))
        assert not resp.success


class TestAuditEvents:
    """审计事件：monkeypatch write_auth_audit 捕获（logs 表由日志服务托管）。"""

    @pytest.fixture()
    def audit_capture(self, monkeypatch):
        import auth_service.application.handlers.auth_handlers as ah
        captured = []
        monkeypatch.setattr(ah, 'write_auth_audit',
                            lambda event, module, content:
                            captured.append((event.value, content)))
        return captured

    def test_provider_crud_emits_audit(self, servicer, audit_capture):
        svc, pb = servicer
        resp = svc.CreateOAuthProvider(_provider_request(
            pb, slug=f'audit-idp-{_RUN_TAG}', operator_id=7))
        provider_id = json.loads(resp.data)['provider_id']
        svc.UpdateOAuthProvider(pb.UpdateOAuthProviderRequest(
            provider_id=provider_id, name='改名', operator_id=7))
        svc.DeleteOAuthProvider(pb.DeleteOAuthProviderRequest(
            provider_id=provider_id, operator_id=7))
        events = [e for e, _ in audit_capture]
        assert 'AUTH_OAUTH_PROVIDER_CREATED' in events
        assert 'AUTH_OAUTH_PROVIDER_UPDATED' in events
        assert 'AUTH_OAUTH_PROVIDER_DELETED' in events
        # 审计归因：operator_id 透传
        created = [c for e, c in audit_capture
                   if e == 'AUTH_OAUTH_PROVIDER_CREATED'][0]
        assert created['operator_id'] == 7

    def test_registered_user_emits_registered_audit(self, servicer,
                                                    audit_capture):
        """自助注册（registered=True）→ AUTH_USER_REGISTERED，与建号区分。"""
        svc, pb = servicer
        resp = svc.CreateUser(pb.CreateUserRequest(
            username=f'self_registered_{_RUN_TAG}', password='pass123456',
            registered=True))
        assert resp.success, resp.message
        events = [e for e, _ in audit_capture]
        assert 'AUTH_USER_REGISTERED' in events
        assert 'AUTH_USER_CREATED' not in events

    def test_admin_created_user_emits_created_audit(self, servicer,
                                                    audit_capture):
        svc, pb = servicer
        resp = svc.CreateUser(pb.CreateUserRequest(
            username=f'admin_created_{_RUN_TAG}', password='pass123456', operator_id=1))
        assert resp.success, resp.message
        events = [e for e, _ in audit_capture]
        assert 'AUTH_USER_CREATED' in events
        assert 'AUTH_USER_REGISTERED' not in events


class TestPasswordLogin:
    """LoginWithPassword：bcrypt 真实校验（用户不存在/无密码/错密码一律拒绝）。"""

    def test_login_with_password_success(self, servicer):
        svc, pb = servicer
        resp = svc.CreateUser(pb.CreateUserRequest(
            username=f'login_user_{_RUN_TAG}', password='s3cret-pass'))
        assert resp.success, resp.message
        resp = svc.LoginWithPassword(pb.LoginWithPasswordRequest(
            username=f'login_user_{_RUN_TAG}', password='s3cret-pass'))
        assert resp.success, resp.message
        data = json.loads(resp.data)
        assert data['username'] == f'login_user_{_RUN_TAG}'
        assert data['is_active'] is True

    def test_login_with_password_wrong_password(self, servicer):
        svc, pb = servicer
        resp = svc.CreateUser(pb.CreateUserRequest(
            username=f'wrong_pw_user_{_RUN_TAG}', password='s3cret-pass'))
        assert resp.success, resp.message
        resp = svc.LoginWithPassword(pb.LoginWithPasswordRequest(
            username=f'wrong_pw_user_{_RUN_TAG}', password='wrong-pass'))
        assert not resp.success

    def test_login_unknown_user_fails(self, servicer):
        svc, pb = servicer
        resp = svc.LoginWithPassword(pb.LoginWithPasswordRequest(
            username='ghost', password='whatever'))
        assert not resp.success

    def test_login_oauth_user_without_password_fails(self, servicer):
        """OAuth 用户（无 password_hash）不可用密码登录。"""
        svc, pb = servicer
        resp = svc.CreateUser(pb.CreateUserRequest(
            username=f'oauth_only_{_RUN_TAG}', oauth_provider='test-idp',
            oauth_subject='ext-1'))
        assert resp.success, resp.message
        resp = svc.LoginWithPassword(pb.LoginWithPasswordRequest(
            username=f'oauth_only_{_RUN_TAG}', password='anything'))
        assert not resp.success


class TestProviderDomainService:

    def test_validate_fills_field_defaults(self):
        from auth_service.domain.services.oauth_provider_service import (
            validate_provider_config,
        )
        from auth_service.domain.entities.oauth_provider import (
            OAuthProviderEntity,
        )
        entity = OAuthProviderEntity(
            name='X', slug='x1', client_id='c', client_secret='s',
            authorize_url='https://a', token_url='https://t',
            userinfo_url='https://u')
        validate_provider_config(entity)
        assert entity.user_id_field == 'sub'
        assert entity.username_field == 'preferred_username'
        assert entity.display_name_field == 'name'
        assert entity.email_field == 'email'
        assert entity.scopes == 'openid profile email'

    def test_map_user_fields_dot_path(self):
        from auth_service.domain.services.oauth_provider_service import (
            map_user_fields,
        )
        from auth_service.domain.entities.oauth_provider import (
            OAuthProviderEntity,
        )
        provider = OAuthProviderEntity(
            name='X', slug='x', client_id='c', client_secret='s',
            authorize_url='https://a', token_url='https://t',
            userinfo_url='https://u',
            user_id_field='data.user.id', username_field='login',
            display_name_field='name', email_field='contacts.email')
        userinfo = {
            'data': {'user': {'id': 42}},
            'login': 'bob',
            'name': 'Bob',
            'contacts': {'email': 'b@x.com'},
        }
        user_id, username, display_name, email = map_user_fields(
            userinfo, provider)
        assert (user_id, username, display_name, email) == (
            '42', 'bob', 'Bob', 'b@x.com')

    def test_map_user_fields_missing_user_id_raises(self):
        from auth_service.domain.services.oauth_provider_service import (
            map_user_fields,
        )
        from auth_service.domain.entities.oauth_provider import (
            OAuthProviderEntity,
        )
        provider = OAuthProviderEntity(
            name='X', slug='x', client_id='c', client_secret='s',
            authorize_url='https://a', token_url='https://t',
            userinfo_url='https://u')
        with pytest.raises(Exception):
            map_user_fields({'login': 'bob'}, provider)
