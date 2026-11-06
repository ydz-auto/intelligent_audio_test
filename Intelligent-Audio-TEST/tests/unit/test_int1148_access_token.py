# -*- coding: utf-8 -*-
"""Access Token 领域实施单测（INT-1148 / INT-1140 分道 D）。

覆盖（sqlite 文件型库直连真实仓储/handler/servicer/HTTP 路由）：
- 领域纯函数：明文 token 生成格式（at_ + 32 hex）、SHA-256 哈希、末 4 位 hint
- scopes/status/name 校验纯函数
- CQRS 路径：创建（明文仅一次、库中只有哈希）→ 列表掩码 → 校验成功一次
- 禁用 / 过期 / 软删 → 校验失败（ACCESS_TOKEN_DISABLED/EXPIRED/INVALID，401 语义）
- scopes 生效：非空=按清单；空=继承用户全部权限（实时拉取）
- 每用户 token 上限
- 更新（name/scopes/status/expires_at 清空）与软删除
- gRPC ValidateAccessToken / GetAccessTokenByHash
- HTTP CRUD（X-User-Id 头鉴权=当前登录用户本人）
"""
import json
import os
import tempfile

import pytest

os.environ.setdefault('DATABASE_URL',
                      'sqlite:///' + tempfile.mkdtemp(prefix='int1148_') + '/auth.db')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from shared.models.database import init_db, get_db_session, get_engine, remove_db_session
from auth_service.infrastructure.persistence.models import (
    Role, Permission, RolePermission, UserPermission, User, AccessToken,
)
from sqlalchemy import BigInteger
from sqlalchemy.ext.compiler import compiles


@compiles(BigInteger, 'sqlite')
def _render_bigint_as_integer_sqlite(type_, compiler, **kw):
    """SQLite 不支持 BigInteger 主键自增，建表时渲染为 INTEGER。"""
    return 'INTEGER'


@pytest.fixture(scope='module')
def db():
    """初始化 SQLite 文件库并建 access token 相关表 + RBAC 种子。"""
    init_db(pool_size=3)
    engine = get_engine()
    assert ':memory:' not in str(engine.url), '需要文件型 sqlite（跨线程共享表）'
    remove_db_session()
    from shared.models.database import Base
    Base.metadata.create_all(
        bind=engine,
        tables=[Role.__table__, Permission.__table__, RolePermission.__table__,
                UserPermission.__table__, User.__table__, AccessToken.__table__],
    )
    session = get_db_session()
    # RBAC 种子：guest 角色 + 两个权限点 + 用户 u1（role_id=guest）
    _seed_permission(session, 'task:read', '查看任务')
    _seed_permission(session, 'audio:delete', '删除音频')
    role = session.query(Role).filter_by(name='guest').first()
    if role is None:
        role = Role(name='guest', description='访客', is_system=True)
        session.add(role)
        session.flush()
    _seed_role_permission(session, role.id, 'task:read')
    _seed_role_permission(session, role.id, 'audio:delete')
    for username in ('u1', 'limit_user'):
        if session.query(User).filter_by(username=username).first() is None:
            session.add(User(username=username,
                             email=f'{username}@example.com',
                             role_id=role.id, status='active'))
    session.commit()
    yield
    remove_db_session()


@pytest.fixture(autouse=True)
def _commit_after_each(db):
    """每个用例后提交当前线程会话，释放 sqlite 写锁。

    handler/servicer 测试仅 flush（interfaces 层才 commit），不提交会
    让测试线程长期持 sqlite 写锁，阻塞后续 HTTP 用例（TestClient 线程）
    的写操作（database is locked）。
    """
    yield
    session = get_db_session()
    try:
        session.commit()
    except Exception:
        session.rollback()


def _seed_permission(session, code, description=''):
    po = session.query(Permission).filter_by(name=code).first()
    if po is None:
        po = Permission(name=code, description=description)
        session.add(po)
        session.flush()
    return po.id


def _seed_role_permission(session, role_id, code):
    pid = _seed_permission(session, code)
    if session.query(RolePermission).filter_by(
            role_id=role_id, permission_id=pid).first() is None:
        session.add(RolePermission(role_id=role_id, permission_id=pid))
        session.flush()


def _user_id():
    session = get_db_session()
    row = session.query(User.id).filter_by(username='u1').first()
    return row[0]


def _limit_user_id():
    session = get_db_session()
    row = session.query(User.id).filter_by(username='limit_user').first()
    return row[0]


@pytest.fixture()
def repo(db):
    from auth_service.infrastructure.persistence.access_token_repository import (
        access_token_repository,
    )
    return access_token_repository


@pytest.fixture()
def handlers(db):
    from auth_service.application.handlers.access_token_handlers import (
        access_token_command_handler,
        access_token_query_handler,
    )
    return access_token_command_handler, access_token_query_handler


# ============================================================
# 领域纯函数
# ============================================================

class TestTokenPrimitives:

    def test_generate_token_format(self):
        from auth_service.domain.entities.access_token import generate_token
        tok = generate_token()
        assert tok.startswith('at_')
        # 32 hex（≈128bit）：at_ 3 字符 + 32 hex = 35 字符
        assert len(tok) == 3 + 32
        assert all(c in '0123456789abcdef' for c in tok[3:])

    def test_hash_and_hint(self):
        from auth_service.domain.entities.access_token import (
            hash_token, token_hint_of,
        )
        tok = 'at_' + 'ab' * 16
        digest = hash_token(tok)
        assert len(digest) == 64
        assert digest != tok
        assert token_hint_of(tok) == tok[-4:]

    def test_is_expired(self):
        from datetime import timedelta
        from auth_service.domain.entities.access_token import (
            AccessTokenAggregate, utc8_now,
        )
        never = AccessTokenAggregate(expires_at=None)
        assert never.is_expired() is False
        past = AccessTokenAggregate(expires_at=utc8_now() - timedelta(days=1))
        assert past.is_expired() is True
        future = AccessTokenAggregate(expires_at=utc8_now() + timedelta(days=30))
        assert future.is_expired() is False

    def test_is_enabled(self):
        from auth_service.domain.entities.access_token import (
            AccessTokenAggregate, AccessTokenStatus, utc8_now,
        )
        assert AccessTokenAggregate(status=AccessTokenStatus.ENABLED.value).is_enabled()
        assert not AccessTokenAggregate(
            status=AccessTokenStatus.DISABLED.value).is_enabled()
        deleted = AccessTokenAggregate(
            status=AccessTokenStatus.ENABLED.value, deleted_at=utc8_now())
        assert not deleted.is_enabled()


class TestAccessTokenValidations:

    def test_scopes_empty_normalized(self):
        from auth_service.domain.services.auth_service import (
            validate_access_token_scopes,
        )
        assert validate_access_token_scopes(None, {'task:read'}) == []
        assert validate_access_token_scopes([], {'task:read'}) == []

    def test_scopes_valid(self):
        from auth_service.domain.services.auth_service import (
            validate_access_token_scopes,
        )
        out = validate_access_token_scopes(
            ['task:read', 'audio:delete'], {'task:read', 'audio:delete'})
        assert out == ['task:read', 'audio:delete']

    def test_scopes_wildcard_allowed(self):
        from auth_service.domain.services.auth_service import (
            validate_access_token_scopes,
        )
        assert validate_access_token_scopes(['*'], {'*', 'task:read'}) == ['*']

    def test_scopes_unknown_rejected(self):
        from auth_service.domain.services.auth_service import (
            validate_access_token_scopes,
        )
        from auth_service.domain.exceptions import AuthDomainError
        from shared.models.common_enums import AuthErrorCode
        with pytest.raises(AuthDomainError) as ei:
            validate_access_token_scopes(['nope:xxx'], {'task:read'})
        assert ei.value.error_code == AuthErrorCode.PERMISSION_NOT_FOUND

    def test_status_valid(self):
        from auth_service.domain.services.auth_service import (
            validate_access_token_status,
        )
        validate_access_token_status('enabled')
        validate_access_token_status('disabled')

    def test_status_invalid(self):
        from auth_service.domain.services.auth_service import (
            validate_access_token_status,
        )
        from auth_service.domain.exceptions import AuthDomainError
        with pytest.raises(AuthDomainError):
            validate_access_token_status('deleted')

    def test_name_empty_rejected(self):
        from auth_service.domain.services.auth_service import (
            validate_access_token_name,
        )
        from auth_service.domain.exceptions import AuthDomainError
        with pytest.raises(AuthDomainError):
            validate_access_token_name('   ')


# ============================================================
# CQRS handler 链路（真实仓储）
# ============================================================

class TestAccessTokenCQRS:

    def test_create_returns_plaintext_once_and_db_hashes_only(
            self, handlers, repo):
        cmd_h, qry_h = handlers
        from auth_service.application.commands.access_token_commands import (
            CreateAccessTokenCommand,
        )
        from auth_service.domain.entities.access_token import hash_token
        uid = _user_id()
        token_id, plaintext = cmd_h.handle_create(CreateAccessTokenCommand(
            user_id=uid, name='CI-token', scopes=['task:read']))
        assert token_id > 0
        assert plaintext.startswith('at_')
        # 库中只有 SHA-256 哈希
        agg = repo.get_by_id(token_id, uid)
        assert agg is not None
        assert agg.token_hash == hash_token(plaintext)
        assert agg.token_hint == plaintext[-4:]
        assert agg.scopes == ['task:read']
        # 明文不在任何持久化字段中
        assert plaintext not in (agg.token_hash, agg.token_hint, agg.name)

    def test_default_expiry_applied(self, handlers, repo):
        cmd_h, _ = handlers
        from auth_service.application.commands.access_token_commands import (
            CreateAccessTokenCommand,
        )
        from auth_service.config.config import Config
        uid = _user_id()
        token_id, _ = cmd_h.handle_create(CreateAccessTokenCommand(
            user_id=uid, name='exp-token', default_expiry=True))
        agg = repo.get_by_id(token_id, uid)
        from datetime import timedelta
        from auth_service.domain.entities.access_token import utc8_now
        days = int(Config.ACCESS_TOKEN_DEFAULT_EXPIRY_DAYS)
        assert agg.expires_at is not None
        assert abs((agg.expires_at - (utc8_now() + timedelta(days=days))).days) <= 1

    def test_list_masked(self, handlers, repo):
        cmd_h, qry_h = handlers
        from auth_service.application.commands.access_token_commands import (
            CreateAccessTokenCommand,
        )
        from auth_service.application.queries.access_token_queries import (
            ListAccessTokensQuery,
        )
        uid = _user_id()
        token_id, plaintext = cmd_h.handle_create(CreateAccessTokenCommand(
            user_id=uid, name='list-me'))
        items = qry_h.handle_list(ListAccessTokensQuery(user_id=uid))
        assert any(t.id == token_id for t in items)
        for t in items:
            assert t.token_hint
            assert plaintext not in t.token_hint  # 仅掩码
            assert t.token_hash  # 实体含哈希（接口层负责掩去）

    def test_list_excludes_soft_deleted(self, handlers, repo):
        cmd_h, qry_h = handlers
        from auth_service.application.commands.access_token_commands import (
            CreateAccessTokenCommand, DeleteAccessTokenCommand,
        )
        from auth_service.application.queries.access_token_queries import (
            ListAccessTokensQuery,
        )
        uid = _user_id()
        # 已软删 token
        deleted_id, _ = cmd_h.handle_create(CreateAccessTokenCommand(
            user_id=uid, name='deleted-row'))
        cmd_h.handle_delete(DeleteAccessTokenCommand(
            token_id=deleted_id, user_id=uid))
        # 未软删 token
        keep_id, _ = cmd_h.handle_create(CreateAccessTokenCommand(
            user_id=uid, name='keep-row'))
        # 软删保留行语义：get_by_id 仍可查（鉴权判定用）
        assert repo.get_by_id(deleted_id, uid).deleted_at is not None
        ids = {t.id for t in qry_h.handle_list(
            ListAccessTokensQuery(user_id=uid))}
        assert keep_id in ids
        assert deleted_id not in ids  # 软删行从管理列表消失

    def test_validate_success_updates_last_used(self, handlers, repo):
        cmd_h, qry_h = handlers
        from auth_service.application.commands.access_token_commands import (
            CreateAccessTokenCommand,
        )
        from auth_service.application.queries.access_token_queries import (
            ValidateAccessTokenQuery,
        )
        uid = _user_id()
        token_id, plaintext = cmd_h.handle_create(CreateAccessTokenCommand(
            user_id=uid, name='valid-me', scopes=['task:read']))
        result = qry_h.handle_validate(ValidateAccessTokenQuery(
            token=plaintext, ip='10.0.0.1'))
        assert result['id'] == token_id
        assert result['user_id'] == uid
        assert result['scopes'] == ['task:read']
        agg = repo.get_by_id(token_id, uid)
        assert agg.last_used_at is not None
        assert agg.last_used_ip == '10.0.0.1'

    def test_validate_empty_scopes_inherits_user_permissions(self, handlers):
        cmd_h, qry_h = handlers
        from auth_service.application.commands.access_token_commands import (
            CreateAccessTokenCommand,
        )
        from auth_service.application.queries.access_token_queries import (
            ValidateAccessTokenQuery,
        )
        uid = _user_id()
        _, plaintext = cmd_h.handle_create(CreateAccessTokenCommand(
            user_id=uid, name='inherit-me', scopes=[]))
        result = qry_h.handle_validate(ValidateAccessTokenQuery(token=plaintext))
        # guest 角色基线权限
        assert set(result['scopes']) == {'task:read', 'audio:delete'}

    def test_validate_disabled_fails(self, handlers):
        cmd_h, qry_h = handlers
        from auth_service.application.commands.access_token_commands import (
            CreateAccessTokenCommand, UpdateAccessTokenCommand,
        )
        from auth_service.application.queries.access_token_queries import (
            ValidateAccessTokenQuery,
        )
        from auth_service.domain.exceptions import AuthDomainError
        from shared.models.common_enums import AuthErrorCode
        uid = _user_id()
        token_id, plaintext = cmd_h.handle_create(CreateAccessTokenCommand(
            user_id=uid, name='disable-me'))
        cmd_h.handle_update(UpdateAccessTokenCommand(
            token_id=token_id, user_id=uid, status='disabled'))
        with pytest.raises(AuthDomainError) as ei:
            qry_h.handle_validate(ValidateAccessTokenQuery(token=plaintext))
        assert ei.value.error_code == AuthErrorCode.ACCESS_TOKEN_DISABLED

    def test_validate_expired_fails(self, handlers):
        from datetime import timedelta
        cmd_h, qry_h = handlers
        from auth_service.application.commands.access_token_commands import (
            CreateAccessTokenCommand,
        )
        from auth_service.application.queries.access_token_queries import (
            ValidateAccessTokenQuery,
        )
        from auth_service.domain.entities.access_token import utc8_now
        from auth_service.domain.exceptions import AuthDomainError
        from shared.models.common_enums import AuthErrorCode
        uid = _user_id()
        _, plaintext = cmd_h.handle_create(CreateAccessTokenCommand(
            user_id=uid, name='expired-me',
            expires_at=utc8_now() - timedelta(days=1)))
        with pytest.raises(AuthDomainError) as ei:
            qry_h.handle_validate(ValidateAccessTokenQuery(token=plaintext))
        assert ei.value.error_code == AuthErrorCode.ACCESS_TOKEN_EXPIRED

    def test_validate_soft_deleted_fails(self, handlers, repo):
        cmd_h, qry_h = handlers
        from auth_service.application.commands.access_token_commands import (
            CreateAccessTokenCommand, DeleteAccessTokenCommand,
        )
        from auth_service.application.queries.access_token_queries import (
            ValidateAccessTokenQuery,
        )
        from auth_service.domain.exceptions import AuthDomainError
        from shared.models.common_enums import AuthErrorCode
        uid = _user_id()
        token_id, plaintext = cmd_h.handle_create(CreateAccessTokenCommand(
            user_id=uid, name='deleted-me'))
        cmd_h.handle_delete(DeleteAccessTokenCommand(token_id=token_id, user_id=uid))
        # 软删保留行（软删语义）
        assert repo.get_by_id(token_id, uid) is not None
        with pytest.raises(AuthDomainError) as ei:
            qry_h.handle_validate(ValidateAccessTokenQuery(token=plaintext))
        assert ei.value.error_code == AuthErrorCode.ACCESS_TOKEN_INVALID

    def test_validate_unknown_token_fails(self, handlers):
        _, qry_h = handlers
        from auth_service.application.queries.access_token_queries import (
            ValidateAccessTokenQuery,
        )
        from auth_service.domain.exceptions import AuthDomainError
        from shared.models.common_enums import AuthErrorCode
        with pytest.raises(AuthDomainError) as ei:
            qry_h.handle_validate(
                ValidateAccessTokenQuery(token='at_' + '00' * 16))
        assert ei.value.error_code == AuthErrorCode.ACCESS_TOKEN_INVALID

    def test_per_user_limit(self, handlers, monkeypatch):
        from auth_service.config.config import Config
        monkeypatch.setattr(Config, 'ACCESS_TOKEN_MAX_PER_USER', 2)
        cmd_h, _ = handlers
        from auth_service.application.commands.access_token_commands import (
            CreateAccessTokenCommand,
        )
        from auth_service.domain.exceptions import AuthDomainError
        from shared.models.common_enums import AuthErrorCode
        uid = _limit_user_id()  # 隔离用户：不受其他用例已建 token 影响
        cmd_h.handle_create(CreateAccessTokenCommand(user_id=uid, name='t1'))
        cmd_h.handle_create(CreateAccessTokenCommand(user_id=uid, name='t2'))
        with pytest.raises(AuthDomainError) as ei:
            cmd_h.handle_create(CreateAccessTokenCommand(user_id=uid, name='t3'))
        assert ei.value.error_code == AuthErrorCode.ACCESS_TOKEN_LIMIT_REACHED
        monkeypatch.setattr(Config, 'ACCESS_TOKEN_MAX_PER_USER', 0)  # 可关闭=不限制
        token_id, _ = cmd_h.handle_create(
            CreateAccessTokenCommand(user_id=uid, name='t4'))
        assert token_id > 0

    def test_update_fields_and_clear_expiry(self, handlers, repo):
        cmd_h, qry_h = handlers
        from auth_service.application.commands.access_token_commands import (
            CreateAccessTokenCommand, UpdateAccessTokenCommand,
        )
        from auth_service.application.queries.access_token_queries import (
            GetAccessTokenQuery,
        )
        uid = _user_id()
        token_id, _ = cmd_h.handle_create(CreateAccessTokenCommand(
            user_id=uid, name='before', scopes=['task:read'],
            expires_at=None))  # 永不过期
        cmd_h.handle_update(UpdateAccessTokenCommand(
            token_id=token_id, user_id=uid, name='after',
            scopes=['audio:delete'], status='disabled',
            expires_at=None, update_expires_at=True))  # 清空=永不过期
        agg = qry_h.handle_get(GetAccessTokenQuery(token_id=token_id, user_id=uid))
        assert agg.name == 'after'
        assert agg.scopes == ['audio:delete']
        assert agg.status == 'disabled'
        assert agg.expires_at is None

    def test_update_unknown_token_fails(self, handlers):
        cmd_h, _ = handlers
        from auth_service.application.commands.access_token_commands import (
            UpdateAccessTokenCommand,
        )
        from auth_service.domain.exceptions import AuthDomainError
        from shared.models.common_enums import AuthErrorCode
        with pytest.raises(AuthDomainError) as ei:
            cmd_h.handle_update(UpdateAccessTokenCommand(
                token_id=999999, user_id=_user_id(), name='x'))
        assert ei.value.error_code == AuthErrorCode.ACCESS_TOKEN_NOT_FOUND

    def test_delete_unknown_token_fails(self, handlers):
        cmd_h, _ = handlers
        from auth_service.application.commands.access_token_commands import (
            DeleteAccessTokenCommand,
        )
        from auth_service.domain.exceptions import AuthDomainError
        from shared.models.common_enums import AuthErrorCode
        with pytest.raises(AuthDomainError) as ei:
            cmd_h.handle_delete(DeleteAccessTokenCommand(
                token_id=999999, user_id=_user_id()))
        assert ei.value.error_code == AuthErrorCode.ACCESS_TOKEN_NOT_FOUND

    def test_ownership_enforced_on_get(self, handlers):
        _, qry_h = handlers
        from auth_service.application.queries.access_token_queries import (
            GetAccessTokenQuery,
        )
        from auth_service.domain.exceptions import AuthDomainError
        from shared.models.common_enums import AuthErrorCode
        # u1 名下没有 999999，且即便存在也不属于 u2
        with pytest.raises(AuthDomainError) as ei:
            qry_h.handle_get(GetAccessTokenQuery(token_id=999999, user_id=_user_id()))
        assert ei.value.error_code == AuthErrorCode.ACCESS_TOKEN_NOT_FOUND


# ============================================================
# gRPC servicer
# ============================================================

class TestAccessTokenGrpc:

    def _servicer(self, db):
        from auth_service.interfaces.grpc.servicers import AuthServicer
        from shared.proto import auth_service_pb2 as auth_pb
        return AuthServicer(), auth_pb

    def test_validate_rpc_success(self, handlers, db):
        cmd_h, _ = handlers
        from auth_service.application.commands.access_token_commands import (
            CreateAccessTokenCommand,
        )
        svc, pb = self._servicer(db)
        uid = _user_id()
        _, plaintext = cmd_h.handle_create(CreateAccessTokenCommand(
            user_id=uid, name='rpc-token', scopes=['task:read']))
        resp = svc.ValidateAccessToken(pb.ValidateAccessTokenRequest(
            token=plaintext, ip='1.2.3.4'))
        assert resp.success is True, resp.message
        data = json.loads(resp.data)
        assert data['valid'] is True
        assert data['token']['user_id'] == uid
        assert data['token']['scopes'] == ['task:read']
        assert data['token']['last_used_at']

    def test_validate_rpc_disabled(self, handlers, db):
        cmd_h, _ = handlers
        from auth_service.application.commands.access_token_commands import (
            CreateAccessTokenCommand, UpdateAccessTokenCommand,
        )
        from shared.models.common_enums import AuthErrorCode
        svc, pb = self._servicer(db)
        uid = _user_id()
        token_id, plaintext = cmd_h.handle_create(CreateAccessTokenCommand(
            user_id=uid, name='rpc-disable'))
        cmd_h.handle_update(UpdateAccessTokenCommand(
            token_id=token_id, user_id=uid, status='disabled'))
        resp = svc.ValidateAccessToken(pb.ValidateAccessTokenRequest(token=plaintext))
        assert resp.success is False
        data = json.loads(resp.data)
        assert data['error_code'] == AuthErrorCode.ACCESS_TOKEN_DISABLED.value

    def test_get_by_hash_rpc(self, handlers, db, repo):
        cmd_h, _ = handlers
        from auth_service.application.commands.access_token_commands import (
            CreateAccessTokenCommand,
        )
        from auth_service.domain.entities.access_token import hash_token
        svc, pb = self._servicer(db)
        uid = _user_id()
        _, plaintext = cmd_h.handle_create(CreateAccessTokenCommand(
            user_id=uid, name='rpc-by-hash'))
        resp = svc.GetAccessTokenByHash(pb.GetAccessTokenByHashRequest(
            token_hash=hash_token(plaintext)))
        assert resp.success is True, resp.message
        data = json.loads(resp.data)
        assert data['token']['user_id'] == uid
        assert data['token']['name'] == 'rpc-by-hash'
        assert 'token_hash' not in data['token']

    def test_get_by_hash_rpc_not_found(self, db):
        svc, pb = self._servicer(db)
        resp = svc.GetAccessTokenByHash(pb.GetAccessTokenByHashRequest(
            token_hash='ab' * 32))
        assert resp.success is False


# ============================================================
# HTTP CRUD（X-User-Id 鉴权=当前登录用户本人）
# ============================================================

class TestAccessTokenHttp:

    @pytest.fixture()
    def client(self, db):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from auth_service.interfaces.api.routes import access_token_router
        app = FastAPI()
        app.include_router(access_token_router)
        with TestClient(app) as c:
            yield c

    def _headers(self):
        return {'X-User-Id': str(_user_id())}

    def test_http_create_returns_plaintext_once(self, client, repo):
        uid = _user_id()
        resp = client.post('/api/v1/auth/access-tokens',
                           headers=self._headers(),
                           json={'name': 'http-token', 'scopes': ['task:read']})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body['success'] is True
        data = body['data']
        assert data['token'].startswith('at_')
        assert data['token_hint'] == data['token'][-4:]
        assert data['scopes'] == ['task:read']
        # 库中只有哈希，无明文
        from auth_service.domain.entities.access_token import hash_token
        agg = repo.get_by_id(data['id'], uid)
        assert agg.token_hash == hash_token(data['token'])
        # 列表不再返回明文
        resp2 = client.get('/api/v1/auth/access-tokens', headers=self._headers())
        items = resp2.json()['data']['items']
        assert 'token' not in items[0]
        assert all('token_hash' not in i for i in items)

    def test_http_create_expires_at_never(self, client):
        resp = client.post('/api/v1/auth/access-tokens',
                           headers=self._headers(),
                           json={'name': 'never-token', 'expires_at': 0})
        assert resp.status_code == 200, resp.text
        assert resp.json()['data']['expires_at'] == 0

    def test_http_create_requires_auth(self, client):
        resp = client.post('/api/v1/auth/access-tokens',
                           json={'name': 'no-user'})
        assert resp.status_code == 401

    def test_http_create_invalid_scope(self, client):
        resp = client.post('/api/v1/auth/access-tokens',
                           headers=self._headers(),
                           json={'name': 'bad-scope', 'scopes': ['nope:xxx']})
        assert resp.status_code == 400  # PERMISSION_NOT_FOUND 未归类 → 400
        assert resp.json()['detail']

    def test_http_update_and_delete(self, client, repo):
        uid = _user_id()
        created = client.post('/api/v1/auth/access-tokens',
                              headers=self._headers(),
                              json={'name': 'upd-me'}).json()['data']
        token_id = created['id']
        resp = client.patch(f'/api/v1/auth/access-tokens/{token_id}',
                            headers=self._headers(),
                            json={'name': 'upd-after', 'status': 'disabled',
                                  'expires_at': 0})
        assert resp.status_code == 200, resp.text
        agg = repo.get_by_id(token_id, uid)
        assert agg.name == 'upd-after'
        assert agg.status == 'disabled'
        assert agg.expires_at is None  # 0=永不过期
        resp = client.delete(f'/api/v1/auth/access-tokens/{token_id}',
                             headers=self._headers())
        assert resp.status_code == 200, resp.text
        assert repo.get_by_id(token_id, uid).deleted_at is not None
        # 软删后详情归属校验仍可查（含软删行）
        resp = client.get(f'/api/v1/auth/access-tokens/{token_id}',
                          headers=self._headers())
        assert resp.status_code == 200, resp.text

    def test_http_list_excludes_soft_deleted(self, client):
        uid = _user_id()
        created = client.post('/api/v1/auth/access-tokens',
                              headers=self._headers(),
                              json={'name': 'del-then-list'}).json()['data']
        token_id = created['id']
        resp = client.delete(f'/api/v1/auth/access-tokens/{token_id}',
                             headers=self._headers())
        assert resp.status_code == 200, resp.text
        resp = client.get('/api/v1/auth/access-tokens', headers=self._headers())
        assert resp.status_code == 200, resp.text
        data = resp.json()['data']
        # 软删行不再出现在列表（total 同口径），且未泄露 deleted_at 字段
        assert all(i['id'] != token_id for i in data['items'])
        assert data['total'] == len(data['items'])
        assert all('deleted_at' not in i for i in data['items'])

    def test_http_patch_unknown_token(self, client):
        resp = client.patch('/api/v1/auth/access-tokens/999999',
                            headers=self._headers(), json={'name': 'x'})
        assert resp.status_code == 404

    def test_http_delete_unknown_token(self, client):
        resp = client.delete('/api/v1/auth/access-tokens/999999',
                             headers=self._headers())
        assert resp.status_code == 404
