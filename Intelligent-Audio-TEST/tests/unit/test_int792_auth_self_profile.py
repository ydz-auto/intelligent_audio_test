# -*- coding: utf-8 -*-
"""INT-792 用户自我资料更新端点验收（PUT /auth/self + /auth/me 扩展 email）。

契约基准：INT-753 FEAT 契约审查结论（2026-10-18 17:43）——
- 路径 `PUT /api/v1/auth/self`（网关 auth_bp，JWT 必填、非白名单）；
  鉴权取 request.state.user_id 为本人（operator_id 同值），不要求 user:update；
- 可编辑字段仅 email；username 平台口径不可改，改动作 400/403 拒绝；
- 空串语义对齐 admin UpdateUser「空串=不修改」；后端校验 email 格式；
- 落库走 auth_service gRPC，审计 AUTH_USER_UPDATED（operator=target=self）；
- /auth/me 扩展 email 走方案 B（GetUser 合并）+ RPC 失败回退 request.state。

覆盖：
- servicer 层：字段白名单（仅 email）/ 空串不修改 / 邮箱格式校验 /
  用户不存在 USER_NOT_FOUND / AUTH_USER_UPDATED 审计（operator=target）
- 网关 HTTP 层：真实路由 + AuthMiddleware + 进程内真实 servicer——
  更新本人 email 成功 / body 带 username 400 / 非法邮箱 400 / 空串不修改 /
  未认证 401 / /auth/me 实时返回 email / GetUser 失败回退保持 200
"""
import os
import tempfile
import threading
import time
import uuid

import pytest

os.environ.setdefault('DATABASE_URL',
                      'sqlite:///' + tempfile.mkdtemp(prefix='int792_')
                      + '/auth.db')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from sqlalchemy import BigInteger  # noqa: E402
from sqlalchemy.ext.compiler import compiles  # noqa: E402

from shared.models.database import init_db, get_db_session, get_engine, remove_db_session  # noqa: E402

_RUN = uuid.uuid4().hex[:8]


@compiles(BigInteger, 'sqlite')
def _render_bigint_as_integer_sqlite(type_, compiler, **kw):
    """SQLite 不支持 BigInteger 主键自增，建表时渲染为 INTEGER。"""
    return 'INTEGER'


@pytest.fixture(scope='module', autouse=True)
def _purge_int792_fixtures():
    """模块 teardown 清本模块 run-tag 用户名残留（共享库下不留测试残留）。"""
    yield
    from auth_service.infrastructure.persistence.models import User
    session = get_db_session()
    try:
        session.query(User).filter(
            User.username.like(f'%_{_RUN}')).delete(synchronize_session=False)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        remove_db_session()


@pytest.fixture(scope='module')
def db():
    """初始化 SQLite 库并建 RBAC 相关表。"""
    init_db(pool_size=3)
    engine = get_engine()
    assert ':memory:' not in str(engine.url), \
        f'INT-792 需要文件型 sqlite（跨线程共享表），实际绑定 {engine.url}'
    remove_db_session()
    from shared.models.database import Base
    from auth_service.infrastructure.persistence.models import (
        Role, Permission, RolePermission, UserPermission, User,
    )
    Base.metadata.create_all(
        bind=engine,
        tables=[Role.__table__, Permission.__table__, RolePermission.__table__,
                UserPermission.__table__, User.__table__],
    )
    yield
    remove_db_session()


@pytest.fixture()
def servicer(db, seeded):
    """真实 AuthServicer + auth_pb（servicer 层直驱；guest 角色种子就绪）。"""
    from auth_service.interfaces.grpc.servicers import AuthServicer
    from shared.proto import auth_service_pb2 as auth_pb
    return AuthServicer(), auth_pb


@pytest.fixture(scope='module')
def seeded(db):
    """RBAC 种子：guest（注册默认角色）/ admin。"""
    session = get_db_session()
    from auth_service.infrastructure.persistence.models import Role
    if session.query(Role).filter(Role.name == 'guest').count() == 0:
        session.add(Role(name='guest', description='注册默认角色'))
    if session.query(Role).filter(Role.name == 'admin').count() == 0:
        session.add(Role(name='admin', description='验收管理员角色'))
    session.commit()
    return True


def _register_and_login(client, username, email=None, password='pass123456'):
    resp = client.post('/api/v1/auth/register',
                       json={'username': username, 'password': password,
                             'email': email or f'{username}@example.com'})
    assert resp.status_code == 201, resp.text
    resp = client.post('/api/v1/auth/login',
                       data={'username': username, 'password': password})
    assert resp.status_code == 200, resp.text
    token = resp.json()['access_token']
    return {'Authorization': f'Bearer {token}'}


@pytest.fixture(scope='module')
def client(seeded, db):
    """最小网关应用：真实路由 + 真实中间件；gRPC 代理直连真实 servicer。"""
    from auth_service.interfaces.grpc.servicers import AuthServicer

    _servicer = AuthServicer()

    class _Proxy:
        @property
        def stub(self):
            return _servicer

    proxy = _Proxy()
    import api_gateway.infrastructure.grpc_proxies as proxies_pkg
    import api_gateway.application.services.auth.management_common as mc
    mp = pytest.MonkeyPatch()
    from api_gateway.config.config import Config
    # INT-147：登录/注册密码默认走 RSA 加密传输；本文件验证基础契约，
    # 关闭加密开关保持明文契约（加密链路由 test_int147_* 覆盖）
    mp.setattr(Config, 'AUTH_PASSWORD_ENCRYPTION_ENABLED', False)
    mp.setattr(proxies_pkg, 'auth_config_service', proxy)
    mp.setattr(mc, 'auth_config_service', proxy)

    from fastapi import FastAPI
    from api_gateway.middleware import RequestAdapterMiddleware, AuthMiddleware
    from api_gateway.routes.auth_bp import router as auth_router
    from api_gateway.routes.user_bp import router as user_router

    app = FastAPI()
    app.add_middleware(RequestAdapterMiddleware)
    app.add_middleware(AuthMiddleware, auth_mode='dev')
    app.include_router(auth_router, prefix='/api/v1/auth')
    app.include_router(user_router, prefix='/api/v1/auth')
    # 真实 uvicorn 服务（仓库既有验收模式，test_g3_auth_http_e2e 同款）
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
    import httpx
    yield httpx.Client(base_url=f'http://{host}:{port}',
                       trust_env=False, follow_redirects=False, timeout=15)
    server.should_exit = True
    thread.join(timeout=5)
    mp.undo()


class TestUpdateSelfProfileServicer:
    """servicer 层：字段白名单 / 空串不修改 / 邮箱校验 / USER_NOT_FOUND / 审计。"""

    def _create_user(self, svc, pb, username, email):
        resp = svc.CreateUser(pb.CreateUserRequest(
            username=username, email=email, role_name='guest', operator_id=1))
        assert resp.success, resp.message
        import json as _json
        return _json.loads(resp.data)['user_id']

    def test_update_email_success(self, servicer):
        """更新本人 email 成功，operator_id=user_id（self 语义）。"""
        svc, pb = servicer
        uid = self._create_user(svc, pb, f'self_mail_{_RUN}', 'old@example.com')
        resp = svc.UpdateSelfProfile(pb.UpdateSelfProfileRequest(
            user_id=uid, email='new@example.com', operator_id=uid))
        assert resp.success, resp.message
        session = get_db_session()
        from auth_service.infrastructure.persistence.models import User
        row = session.query(User).filter_by(id=uid).one()
        assert row.email == 'new@example.com'

    def test_update_email_empty_means_no_change(self, servicer):
        """空串=不修改（对齐 admin UpdateUser 空串语义）。"""
        svc, pb = servicer
        uid = self._create_user(svc, pb, f'self_empty_{_RUN}', 'keep@example.com')
        resp = svc.UpdateSelfProfile(pb.UpdateSelfProfileRequest(
            user_id=uid, email='', operator_id=uid))
        assert resp.success, resp.message
        session = get_db_session()
        from auth_service.infrastructure.persistence.models import User
        row = session.query(User).filter_by(id=uid).one()
        assert row.email == 'keep@example.com'

    def test_update_email_invalid_rejected(self, servicer):
        """非法邮箱格式 → 失败（网关侧同时 400 前置校验）。"""
        svc, pb = servicer
        uid = self._create_user(svc, pb, f'self_badmail_{_RUN}', 'a@b.com')
        resp = svc.UpdateSelfProfile(pb.UpdateSelfProfileRequest(
            user_id=uid, email='not-an-email', operator_id=uid))
        assert resp.success is False
        assert '邮箱格式不正确' in resp.message

    def test_update_self_user_not_found(self, servicer):
        """目标用户不存在 → USER_NOT_FOUND。"""
        svc, pb = servicer
        resp = svc.UpdateSelfProfile(pb.UpdateSelfProfileRequest(
            user_id=999999, email='x@y.com', operator_id=999999))
        assert resp.success is False
        import json as _json
        assert _json.loads(resp.data) == {'error_code': 'USER_NOT_FOUND'}

    def test_update_self_emits_auth_user_updated_audit(self, servicer, monkeypatch):
        """落 AUTH_USER_UPDATED 审计，operator_id=target_id=user_id（self）。"""
        import auth_service.application.handlers.auth_handlers as ah
        captured = []

        def _capture(event, module, content):
            captured.append({'event': event, 'module': module, 'content': content})

        monkeypatch.setattr(ah, 'write_auth_audit', _capture)
        svc, pb = servicer
        uid = self._create_user(svc, pb, f'self_audit_{_RUN}', 'a@b.com')
        captured.clear()  # CreateUser 的 AUTH_USER_CREATED 不计入本次断言
        resp = svc.UpdateSelfProfile(pb.UpdateSelfProfileRequest(
            user_id=uid, email='a@b.com', operator_id=uid))
        assert resp.success, resp.message
        assert captured, 'UpdateSelfProfile 未触发审计'
        assert captured[0]['event'].value == 'AUTH_USER_UPDATED'
        assert captured[0]['content']['operator_id'] == uid
        assert captured[0]['content']['target_id'] == uid
        assert captured[0]['content']['delta']['email'] == 'a@b.com'


class TestUpdateSelfProfileHttp:
    """网关 HTTP 层：鉴权本人 / 仅 email / 邮箱格式 / 空串 / 未认证。"""

    def test_update_self_email_success_and_me_reflects(self, client, seeded):
        """注册→登录→PUT /auth/self 更新邮箱成功；/auth/me 实时返回新 email。"""
        username = f'e2e_self_{_RUN}'
        headers = _register_and_login(client, username,
                                      email='first@example.com')
        resp = client.put('/api/v1/auth/self', headers=headers,
                          json={'email': 'updated@example.com'})
        assert resp.status_code == 200, resp.text
        assert resp.json()['success'] is True
        resp = client.get('/api/v1/auth/me', headers=headers)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body['username'] == username
        assert body['email'] == 'updated@example.com'

    def test_update_self_rejects_username_field(self, client, seeded):
        """body 携带 username → 400（username 平台口径不可改）。"""
        username = f'e2e_self_rej_{_RUN}'
        headers = _register_and_login(client, username)
        resp = client.put('/api/v1/auth/self', headers=headers,
                          json={'username': 'hacked'})
        assert resp.status_code == 400, resp.text
        assert 'username' in resp.json()['message']

    def test_update_self_rejects_invalid_email(self, client, seeded):
        """非法邮箱格式 → 400。"""
        username = f'e2e_self_inv_{_RUN}'
        headers = _register_and_login(client, username)
        resp = client.put('/api/v1/auth/self', headers=headers,
                          json={'email': 'not-an-email'})
        assert resp.status_code == 400, resp.text
        assert '邮箱格式不正确' in resp.json()['message']

    def test_update_self_empty_email_no_change(self, client, seeded):
        """空串 email = 不修改（200，原邮箱保留）。"""
        username = f'e2e_self_emp_{_RUN}'
        headers = _register_and_login(client, username,
                                      email='orig@example.com')
        resp = client.put('/api/v1/auth/self', headers=headers, json={'email': ''})
        assert resp.status_code == 200, resp.text
        resp = client.get('/api/v1/auth/me', headers=headers)
        assert resp.json()['email'] == 'orig@example.com'

    def test_update_self_unauthenticated_401(self, client, seeded):
        """dev 模式无 Bearer token → 401（PUT /auth/self 非白名单）。"""
        resp = client.put('/api/v1/auth/self', json={'email': 'x@y.com'})
        assert resp.status_code == 401, resp.text


class TestMeEmailExtension:
    """/auth/me 扩展 email：实时合并 + GetUser 失败回退保持可用。"""

    def test_me_returns_registered_email(self, client, seeded):
        """注册邮箱落库 → /auth/me 返回 email（经 GetUser 实时合并）。"""
        username = f'e2e_me_{_RUN}'
        headers = _register_and_login(client, username,
                                      email='me@example.com')
        resp = client.get('/api/v1/auth/me', headers=headers)
        assert resp.status_code == 200, resp.text
        assert resp.json()['email'] == 'me@example.com'

    def test_me_falls_back_when_get_user_fails(self, client, seeded, monkeypatch):
        """GetUser RPC 失败 → 回退 request.state，/auth/me 仍 200（email 空串）。"""
        # 先注册登录（此时代理可用），再模拟 auth_service 抖动破坏 GetUser
        username = f'e2e_me_fb_{_RUN}'
        headers = _register_and_login(client, username,
                                      email='fb@example.com')
        import api_gateway.infrastructure.grpc_proxies as proxies_pkg
        import api_gateway.application.services.auth.management_common as mc

        class _Broken:
            @property
            def stub(self):
                raise RuntimeError('auth_service 不可达')

        monkeypatch.setattr(proxies_pkg, 'auth_config_service', _Broken())
        monkeypatch.setattr(mc, 'auth_config_service', _Broken())
        resp = client.get('/api/v1/auth/me', headers=headers)
        assert resp.status_code == 200, resp.text
        assert resp.json()['email'] == ''
        assert resp.json()['username'] == username
