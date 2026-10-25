# -*- coding: utf-8 -*-
"""INT-1590 用户管理入口密码长度 8–128 自测。

背景：admin 建号 / admin 改资料带密码此前无下限校验（1 位、7 位直接 201
落库），>72 字节时由 bcrypt 5.0 的字节上限副作用抛错（400 + 英文原文），
不是契约。本文件覆盖三层：

- 网关层 user_management_service.create_user / update_user：边界
  7 / 8 / 128 / 129，非法长度 400 + code 203 且不触发 gRPC；
- auth_service 应用层兜底：handle_create_user（admin 路径，registered
  =False）与 handle_update_user 密码路径，gRPC 直连同样拒绝；自助注册
  （registered=True，6 位）与自助改密不受影响（两个产品面，不统一）；
- 真实链路（sqlite + 真实 AuthServicer + 真实 bcrypt + 真实 HTTP 路由）：
  POST / PUT /api/v1/auth/users 的验收口径，含 128 位可登录、7 位改密
  失败后旧密码仍可登录、注册 6 位仍 201；
- bcrypt 72 字节截断语义：73 / 128 位密码可哈希可校验（显式截断接受）。

不依赖 Postgres / 外部服务。
"""
import json
import os
import tempfile
import threading
import time
import uuid

import pytest

os.environ.setdefault('DATABASE_URL',
                      'sqlite:///' + tempfile.mkdtemp(prefix='int1590_')
                      + '/auth.db')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

PASSWORD_ERR = '密码长度需为 8–128 位'
_RUN = uuid.uuid4().hex[:8]
PREFIX = '接线测试_'

from sqlalchemy import BigInteger
from sqlalchemy.ext.compiler import compiles

from shared.models.common_enums import AuthErrorCode
from auth_service.domain.exceptions import AuthDomainError
from auth_service.domain.entities.user import UserAggregate
from auth_service.domain.entities.role import RoleEntity
import auth_service.application.handlers.auth_handlers as auth_handlers
from auth_service.application.commands.auth_commands import (
    ChangePasswordCommand,
    CreateUserCommand,
    RegisterUserCommand,
    UpdateUserCommand,
)


@compiles(BigInteger, 'sqlite')
def _render_bigint_as_integer_sqlite(type_, compiler, **kw):
    """SQLite 不支持 BigInteger 主键自增，建表时渲染为 INTEGER。"""
    return 'INTEGER'


# ============================================================
# 网关层：长度边界 + 非法长度不触发 RPC
# ============================================================

class TestGatewayPasswordLength:

    def _stub(self, monkeypatch, body):
        import api_gateway.application.services.auth.user_management_service as ums
        calls = []

        def _fake_rpc(name, req, default_error='', **kwargs):
            calls.append((name, req))
            return {}, None

        monkeypatch.setattr(ums, '_json_body', lambda: body)
        monkeypatch.setattr(ums, 'call_auth_rpc', _fake_rpc)
        monkeypatch.setattr(ums, 'current_operator_id', lambda: 1)
        monkeypatch.setattr(ums, 'with_notice', lambda r: r)
        return ums, calls

    # ---- create_user ----

    @pytest.mark.parametrize('length', [1, 7, 129])
    def test_create_user_rejects_out_of_range_without_rpc(
            self, monkeypatch, length):
        ums, calls = self._stub(monkeypatch, {
            'username': 'newuser', 'password': 'x' * length})
        payload, http_code = ums.UserManagementService.create_user()
        assert http_code == 400
        assert payload['code'] == 203
        assert payload['message'] == PASSWORD_ERR
        assert payload['success'] is False
        assert calls == []      # 非法长度不得触达 auth_service

    @pytest.mark.parametrize('length', [8, 128])
    def test_create_user_accepts_boundary(self, monkeypatch, length):
        ums, calls = self._stub(monkeypatch, {
            'username': 'newuser', 'password': 'x' * length})
        payload, http_code = ums.UserManagementService.create_user()
        assert http_code == 201
        assert [c[0] for c in calls] == ['CreateUser']
        assert calls[0][1].password == 'x' * length

    def test_create_user_without_password_unchanged(self, monkeypatch):
        """OAuth 用户可不带密码：空密码不校验，仍走 CreateUser。"""
        ums, calls = self._stub(monkeypatch, {'username': 'oauthuser'})
        payload, http_code = ums.UserManagementService.create_user()
        assert http_code == 201
        assert [c[0] for c in calls] == ['CreateUser']
        assert calls[0][1].password == ''

    def test_create_user_missing_username_before_password_check(
            self, monkeypatch):
        """username 必填优先：空 username 仍报必填（既有语义不变）。"""
        ums, calls = self._stub(monkeypatch, {'username': '', 'password': 'x'})
        payload, http_code = ums.UserManagementService.create_user()
        assert http_code == 400
        assert 'username' in payload['message']
        assert calls == []

    # ---- update_user ----

    @pytest.mark.parametrize('length', [1, 7, 129])
    def test_update_user_rejects_out_of_range_without_rpc(
            self, monkeypatch, length):
        ums, calls = self._stub(monkeypatch, {'password': 'x' * length})
        payload, http_code = ums.UserManagementService.update_user(7)
        assert http_code == 400
        assert payload['code'] == 203
        assert payload['message'] == PASSWORD_ERR
        assert calls == []      # 非法长度不得触达 auth_service（哈希不变）

    @pytest.mark.parametrize('length', [8, 128])
    def test_update_user_accepts_boundary(self, monkeypatch, length):
        ums, calls = self._stub(monkeypatch, {'password': 'x' * length})
        payload, http_code = ums.UserManagementService.update_user(7)
        assert http_code == 200
        assert [c[0] for c in calls] == ['UpdateUser']
        assert calls[0][1].password == 'x' * length

    def test_update_user_without_password_key_unchanged(self, monkeypatch):
        """PUT 不带 password = 不修改（语义不变，不触发长度校验）。"""
        ums, calls = self._stub(monkeypatch, {'email': 'n@x.com'})
        payload, http_code = ums.UserManagementService.update_user(7)
        assert http_code == 200
        assert [c[0] for c in calls] == ['UpdateUser']
        assert calls[0][1].password == ''

    def test_update_user_empty_password_unchanged(self, monkeypatch):
        """PUT password='' = 不修改（既有语义）。"""
        ums, calls = self._stub(monkeypatch, {'password': ''})
        payload, http_code = ums.UserManagementService.update_user(7)
        assert http_code == 200
        assert [c[0] for c in calls] == ['UpdateUser']

    def test_bounds_follow_config(self, monkeypatch):
        """边界走 Config（.env 可配）：min 调到 10 后 8 位被拒。"""
        from api_gateway.config.config import Config
        monkeypatch.setattr(Config, 'AUTH_USER_ADMIN_PASSWORD_MIN_LENGTH', 10)
        monkeypatch.setattr(Config, 'AUTH_PASSWORD_MAX_LENGTH', 20)
        ums, calls = self._stub(monkeypatch, {
            'username': 'newuser', 'password': 'x' * 8})
        payload, http_code = ums.UserManagementService.create_user()
        assert http_code == 400
        assert payload['message'] == '密码长度需为 10–20 位'
        assert calls == []


# ============================================================
# auth_service 应用层兜底（gRPC 直连路径）
# ============================================================

class _FakeUserRepository:
    def __init__(self):
        self.users = {}
        self.by_name = {}
        self.written_passwords = []
        self.next_id = 1

    def seed(self, user_id, username='u', role_id=None):
        agg = UserAggregate(id=user_id, username=username, role_id=role_id)
        self.users[user_id] = agg
        self.by_name[username] = agg
        return agg

    def get_by_id(self, user_id):
        return self.users.get(user_id)

    def get_by_username(self, username):
        return self.by_name.get(username)

    def count_all(self):
        return len(self.users)

    def add(self, aggregate, password=None):
        aggregate.id = self.next_id
        self.next_id += 1
        self.users[aggregate.id] = aggregate
        self.by_name[aggregate.username] = aggregate
        self.written_passwords.append(password)
        return aggregate.id

    def update_user_fields(self, user_id, username=None, email=None,
                           status=None, password=None, display_name=None):
        self.written_passwords.append(password)
        return True


class _FakeRoleRepository:
    def __init__(self):
        self.roles = {}
        self.by_name = {}

    def seed_role(self, role_id, name):
        role = RoleEntity(id=role_id, name=name)
        self.roles[role_id] = role
        self.by_name[name] = role

    def get_by_name(self, name):
        return self.by_name.get(name)

    def get_by_id(self, role_id):
        return self.roles.get(role_id)


@pytest.fixture()
def handler(monkeypatch):
    users, roles = _FakeUserRepository(), _FakeRoleRepository()
    roles.seed_role(2, 'guest')
    audits = []

    def _audit(event, module, content):
        audits.append({'event': event, 'content': content})

    monkeypatch.setattr(auth_handlers, 'user_repository', users)
    monkeypatch.setattr(auth_handlers, 'role_repository', roles)
    monkeypatch.setattr(auth_handlers, 'write_auth_audit', _audit)
    return {'handler': auth_handlers.AuthCommandHandler(),
            'users': users, 'roles': roles, 'audits': audits}


class TestHandlerPasswordFallback:

    @pytest.mark.parametrize('length', [1, 7, 129])
    def test_create_user_admin_path_rejects_out_of_range(self, handler, length):
        with pytest.raises(AuthDomainError) as ei:
            handler['handler'].handle_create_user(CreateUserCommand(
                username='admin_made', email=None, oauth_provider='',
                oauth_subject='', password='x' * length))
        assert ei.value.error_code == AuthErrorCode.INVALID_PARAMS
        assert PASSWORD_ERR == ei.value.message
        assert handler['users'].written_passwords == []   # 未落库

    @pytest.mark.parametrize('length', [8, 128])
    def test_create_user_admin_path_accepts_boundary(self, handler, length):
        uid = handler['handler'].handle_create_user(CreateUserCommand(
            username='admin_made', email=None, oauth_provider='',
            oauth_subject='', password='x' * length))
        assert uid
        assert handler['users'].written_passwords == ['x' * length]

    def test_create_user_without_password_allowed(self, handler):
        """OAuth 建号不校验密码（空密码保持现状）。"""
        assert handler['handler'].handle_create_user(CreateUserCommand(
            username='oauth_made', email=None, oauth_provider='github',
            oauth_subject='s1')) > 0

    def test_registration_path_keeps_six_char_minimum(self, handler):
        """自助注册走 registered=True：6 位不受用户管理口径影响。"""
        assert handler['handler'].handle_create_user(CreateUserCommand(
            username='self_reg', email='a@b.c', oauth_provider='',
            oauth_subject='', password='x' * 6, registered=True)) > 0

    def test_register_handler_marks_registered_and_keeps_six(self, handler):
        """handle_register_user 必须走 registered=True（否则 8–128 会误伤注册）。"""
        assert handler['handler'].handle_register_user(RegisterUserCommand(
            username='self_reg2', email='a@b.c', password='x' * 6)) > 0
        assert handler['audits'][0]['event'].value == 'AUTH_USER_REGISTERED'

    @pytest.mark.parametrize('length', [1, 7, 129])
    def test_update_user_password_rejects_out_of_range(self, handler, length):
        handler['users'].seed(1, username='alice')
        with pytest.raises(AuthDomainError) as ei:
            handler['handler'].handle_update_user(UpdateUserCommand(
                user_id=1, password='x' * length))
        assert ei.value.error_code == AuthErrorCode.INVALID_PARAMS
        assert handler['users'].written_passwords == []   # 哈希未变

    @pytest.mark.parametrize('length', [8, 128])
    def test_update_user_password_accepts_boundary(self, handler, length):
        handler['users'].seed(1, username='alice')
        handler['handler'].handle_update_user(UpdateUserCommand(
            user_id=1, password='x' * length))
        assert handler['users'].written_passwords == ['x' * length]

    def test_update_user_without_password_unchanged(self, handler):
        handler['users'].seed(1, username='alice')
        handler['handler'].handle_update_user(UpdateUserCommand(
            user_id=1, email='n@x.com'))
        assert handler['users'].written_passwords == [None]

    def test_self_change_password_keeps_six_char_minimum(self, handler):
        """自助改密走 handle_change_password：6 位不受用户管理口径影响。"""
        users = handler['users']
        users.seed(1, username='alice')
        users.verify_password_by_user_id = lambda uid, pwd: True
        handler['handler'].handle_change_password(ChangePasswordCommand(
            user_id=1, current_password='old', new_password='x' * 6))
        assert users.written_passwords == ['x' * 6]


# ============================================================
# bcrypt 72 字节截断语义（本卡目标 3 的实测结论固化）
# ============================================================

class TestBcryptTruncation:

    def test_hash_accepts_73_and_128_char_passwords(self):
        from auth_service.infrastructure.persistence.user_repository import (
            _hash_password,
        )
        import bcrypt
        from auth_service.infrastructure.persistence.user_repository import (
            _bcrypt_input,
        )
        for n in (72, 73, 128):
            pwd = 'x' * n
            hashed = _hash_password(pwd)
            assert bcrypt.checkpw(_bcrypt_input(pwd),
                                  hashed.encode('utf-8')) is True

    def test_truncation_semantics_documented(self):
        """前 72 字节相同即同一密码（bcrypt 算法口径，非本卡新增行为）。"""
        from auth_service.infrastructure.persistence.user_repository import (
            _bcrypt_input, _hash_password,
        )
        import bcrypt
        hashed = _hash_password('x' * 72 + 'tail-a')
        assert bcrypt.checkpw(_bcrypt_input('x' * 72 + 'tail-b'),
                              hashed.encode('utf-8')) is True


# ============================================================
# 真实链路：HTTP 路由 → 网关服务 → AuthServicer → 真实仓储/bcrypt
# ============================================================

@pytest.fixture(scope='module')
def _db():
    from shared.models.database import (
        init_db, get_engine, remove_db_session, Base,
    )
    init_db(pool_size=3)
    engine = get_engine()
    assert ':memory:' not in str(engine.url), \
        f'本链路需文件型 sqlite（跨线程共享表），实际绑定 {engine.url}'
    remove_db_session()
    from auth_service.infrastructure.persistence.models import (
        Role, Permission, RolePermission, UserPermission, User,
    )
    Base.metadata.create_all(
        bind=engine,
        tables=[Role.__table__, Permission.__table__,
                RolePermission.__table__, UserPermission.__table__,
                User.__table__],
    )
    from shared.models.database import get_db_session
    session = get_db_session()
    if session.query(Role).filter(Role.name == 'guest').count() == 0:
        session.add(Role(name='guest', description='默认角色'))
        session.commit()
    yield True
    remove_db_session()


@pytest.fixture(scope='module')
def client(_db):
    from auth_service.interfaces.grpc.servicers import AuthServicer
    from api_gateway.config.config import Config
    proxy = type('P', (), {'stub': AuthServicer()})()
    import api_gateway.infrastructure.grpc_proxies as proxies_pkg
    import api_gateway.application.services.auth.management_common as mc
    mp = pytest.MonkeyPatch()
    mp.setattr(Config, 'AUTH_PASSWORD_ENCRYPTION_ENABLED', False)
    mp.setattr(proxies_pkg, 'auth_config_service', proxy)
    mp.setattr(mc, 'auth_config_service', proxy)

    from fastapi import FastAPI
    from api_gateway.middleware import RequestAdapterMiddleware, AuthMiddleware
    from api_gateway.routes.auth_bp import router as auth_router
    from api_gateway.routes.user_bp import router as user_router

    app = FastAPI()
    app.add_middleware(RequestAdapterMiddleware)
    # off：中间件注入 ['*']，admin 端点免 token（与 :15000 现网 AUTH_MODE=off 一致）
    app.add_middleware(AuthMiddleware, auth_mode='off')
    app.include_router(auth_router, prefix='/api/v1/auth')
    app.include_router(user_router, prefix='/api/v1/auth')

    import httpx
    import uvicorn
    config = uvicorn.Config(app, host='127.0.0.1', port=0,
                            lifespan='off', log_level='error')
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    assert server.started, '网关最小应用 uvicorn 启动失败'
    host, port = server.servers[0].sockets[0].getsockname()[:2]
    # trust_env=False：Windows 系统代理会劫持 localhost 请求
    yield httpx.Client(base_url=f'http://{host}:{port}',
                       trust_env=False, follow_redirects=False, timeout=30)
    server.should_exit = True
    thread.join(timeout=5)
    mp.undo()


def _login(client, username, password):
    return client.post('/api/v1/auth/login',
                       data={'username': username, 'password': password})


def _create(client, username, password=None):
    body = {'username': username}
    if password is not None:
        body['password'] = password
    return client.post('/api/v1/auth/users', json=body)


def _hash_of(username):
    from shared.models.database import get_db_session
    from auth_service.infrastructure.persistence.models import User
    session = get_db_session()
    po = session.query(User).filter(User.username == username).first()
    return po.password_hash if po else None


class TestAdminPasswordChain:

    @pytest.mark.parametrize('length', [1, 7, 129])
    def test_create_out_of_range_rejected(self, client, length):
        resp = _create(client, f'{PREFIX}短_{length}_{_RUN}', 'x' * length)
        assert resp.status_code == 400, resp.text
        body = resp.json()
        assert body['code'] == 203
        assert body['message'] == PASSWORD_ERR
        # 未落库
        from shared.models.database import get_db_session
        from auth_service.infrastructure.persistence.models import User
        assert get_db_session().query(User).filter(
            User.username == f'{PREFIX}短_{length}_{_RUN}').count() == 0

    def test_create_8_accepted(self, client):
        username = f'{PREFIX}8位_{_RUN}'
        resp = _create(client, username, 'x' * 8)
        assert resp.status_code == 201, resp.text
        assert _login(client, username, 'x' * 8).status_code == 200

    def test_create_128_accepted_and_can_login(self, client):
        """上限显式校验：128 位能 201 且能登录（bcrypt 72 字节截断接受）。"""
        username = f'{PREFIX}128位_{_RUN}'
        pwd = 'p' * 128
        resp = _create(client, username, pwd)
        assert resp.status_code == 201, resp.text
        assert _login(client, username, pwd).status_code == 200

    def test_create_73_accepted_and_can_login(self, client):
        """73 位同样 201（此前是 bcrypt 英文原始异常 400）。"""
        username = f'{PREFIX}73位_{_RUN}'
        pwd = 'q' * 73
        resp = _create(client, username, pwd)
        assert resp.status_code == 201, resp.text
        assert _login(client, username, pwd).status_code == 200

    def test_create_without_password_accepted(self, client):
        username = f'{PREFIX}无密_{_RUN}'
        resp = _create(client, username)
        assert resp.status_code == 201, resp.text

    def test_update_short_password_rejected_and_hash_unchanged(self, client):
        username = f'{PREFIX}改密_{_RUN}'
        old_pwd = 'o' * 10
        assert _create(client, username, old_pwd).status_code == 201
        uid = _uid(client, username)
        before = _hash_of(username)

        resp = client.put(f'/api/v1/auth/users/{uid}',
                          json={'password': 'x' * 7})
        assert resp.status_code == 400, resp.text
        assert resp.json()['code'] == 203
        assert resp.json()['message'] == PASSWORD_ERR

        assert _hash_of(username) == before          # 哈希未变
        assert _login(client, username, old_pwd).status_code == 200

    def test_update_128_password_accepted(self, client):
        username = f'{PREFIX}改128_{_RUN}'
        old_pwd = 'o' * 10
        assert _create(client, username, old_pwd).status_code == 201
        uid = _uid(client, username)

        new_pwd = 'n' * 128
        resp = client.put(f'/api/v1/auth/users/{uid}',
                          json={'password': new_pwd})
        assert resp.status_code == 200, resp.text
        assert _login(client, username, new_pwd).status_code == 200
        assert _login(client, username, old_pwd).status_code == 401

    def test_update_without_password_keeps_hash(self, client):
        username = f'{PREFIX}不改密_{_RUN}'
        old_pwd = 'o' * 10
        assert _create(client, username, old_pwd).status_code == 201
        uid = _uid(client, username)
        before = _hash_of(username)
        resp = client.put(f'/api/v1/auth/users/{uid}',
                          json={'email': f'{username}@example.com'})
        assert resp.status_code == 200, resp.text
        assert _hash_of(username) == before
        assert _login(client, username, old_pwd).status_code == 200

    def test_register_six_char_password_still_accepted(self, client):
        """注册入口仍按 AUTH_PASSWORD_MIN_LENGTH（默认 6），不被本卡口径波及。"""
        username = f'{PREFIX}注册_{_RUN}'
        resp = client.post('/api/v1/auth/register',
                           json={'username': username,
                                 'password': 'x' * 6,
                                 'email': f'{username}@example.com'})
        assert resp.status_code == 201, resp.text


def _uid(client, username):
    from shared.models.database import get_db_session
    from auth_service.infrastructure.persistence.models import User
    po = get_db_session().query(User).filter(
        User.username == username).first()
    assert po is not None, f'用户未落库: {username}'
    return po.id
