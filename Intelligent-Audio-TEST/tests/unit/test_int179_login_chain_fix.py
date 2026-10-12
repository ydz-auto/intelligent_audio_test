# -*- coding: utf-8 -*-
"""INT-179 登录链路三连断修复回归。

网关 HTTP 层端到端（真实路由 + 真实 AuthMiddleware 白名单 + 真实
AuthServicer，模式对齐 test_g3_auth_http_e2e）：

- 公钥端点双路径免认证可达（/login/encryption-key 与旧库别名
  /encryption-key），register / refresh 不被网关误挡（refresh 路由
  自解析 Bearer 并自验签）
- 登录请求体双格式兼容：表单编码（前端契约）与 JSON body 均可达
  凭据校验；加密开启时 JSON 密文链路语义与表单一致（明文无回退）
- 公开提供方列表仅回已启用项（无凭证字段）；夹具清理 helper 按
  run tag 精确清除且不误伤他行（测试残留不落共享库）
"""
import os
import threading
import time
import uuid

import httpx
import pytest
from sqlalchemy import BigInteger
from sqlalchemy import create_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from shared.models.database import init_db, get_db_session, get_engine, remove_db_session


@compiles(BigInteger, 'sqlite')
def _render_bigint_as_integer_sqlite(type_, compiler, **kw):
    """SQLite 不支持 BigInteger 主键自增，建表时渲染为 INTEGER。"""
    return 'INTEGER'


_RUN = uuid.uuid4().hex[:8]


@pytest.fixture(scope='module')
def rsa_key_path(tmp_path_factory):
    """RSA 私钥写入模块级临时目录（不落仓库 data/）。"""
    return str(tmp_path_factory.mktemp('int179_rsa') / 'auth_key.pem')


@pytest.fixture(scope='module')
def svc(rsa_key_path):
    init_db(pool_size=3)
    engine = get_engine()
    assert ':memory:' not in str(engine.url), \
        'INT-179 e2e 需要文件型 sqlite（跨线程共享表）'
    remove_db_session()
    from shared.models.database import Base
    from auth_service.infrastructure.persistence.models import (
        Role, Permission, RolePermission, UserPermission, User,
        CustomOAuthProvider, UserOAuthBinding,
    )
    Base.metadata.create_all(
        bind=engine,
        tables=[Role.__table__, Permission.__table__,
                RolePermission.__table__, UserPermission.__table__,
                User.__table__, CustomOAuthProvider.__table__,
                UserOAuthBinding.__table__],
    )
    from auth_service.interfaces.grpc.servicers import AuthServicer
    yield AuthServicer()
    remove_db_session()


@pytest.fixture(scope='module')
def seeded(svc):
    """RBAC 种子：guest（注册默认角色）/ admin（auth:manage_provider）。"""
    session = get_db_session()
    from auth_service.infrastructure.persistence.models import (
        Role, Permission, RolePermission,
    )
    if session.query(Role).filter(Role.name == 'guest').count() == 0:
        session.add(Role(name='guest', description='注册默认角色'))
    if session.query(Role).filter(Role.name == 'admin').count() == 0:
        role = Role(name='admin', description='验收管理员角色')
        session.add(role)
        session.flush()
        perm = Permission(name='auth:manage_provider',
                          description='管理自定义 OAuth 提供方')
        session.add(perm)
        session.flush()
        session.add(RolePermission(role_id=role.id, permission_id=perm.id))
    session.commit()
    return True


@pytest.fixture(scope='module')
def client(seeded, svc, rsa_key_path):
    """最小网关应用：真实路由 + 真实中间件；gRPC 代理直连真实 servicer。"""
    mp = pytest.MonkeyPatch()
    from api_gateway.config.config import Config
    mp.setattr(Config, 'AUTH_RSA_KEY_PATH', rsa_key_path)
    # 本文件登录用例以明文契约为主（JSON/表单双格式可达性）；加密链路
    # 语义单列加密用例组内临时开启（对齐 test_g3_auth_http_e2e 模式）
    mp.setattr(Config, 'AUTH_PASSWORD_ENCRYPTION_ENABLED', False)

    proxy = type('P', (), {'stub': svc})()
    import api_gateway.infrastructure.grpc_proxies as proxies_pkg
    import api_gateway.application.services.auth.management_common as mc
    mp.setattr(proxies_pkg, 'auth_config_service', proxy)
    mp.setattr(mc, 'auth_config_service', proxy)

    from fastapi import FastAPI
    from api_gateway.middleware import RequestAdapterMiddleware, AuthMiddleware
    from api_gateway.routes.auth_bp import router as auth_router
    from api_gateway.routes.user_bp import router as user_router
    from api_gateway.routes.oauth_bp import router as oauth_router

    app = FastAPI()
    app.add_middleware(RequestAdapterMiddleware)
    app.add_middleware(AuthMiddleware, auth_mode='dev')
    app.include_router(auth_router, prefix='/api/v1/auth')
    app.include_router(user_router, prefix='/api/v1/auth')
    app.include_router(oauth_router, prefix='/api/v1/auth')

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
    assert server.started, 'INT-179 最小网关应用 uvicorn 启动失败'
    host, port = server.servers[0].sockets[0].getsockname()[:2]
    yield httpx.Client(base_url=f'http://{host}:{port}',
                       trust_env=False, follow_redirects=False,
                       timeout=15)
    server.should_exit = True
    thread.join(timeout=5)
    mp.undo()


@pytest.fixture(scope='module', autouse=True)
def _purge_oauth_fixtures():
    """模块 teardown 按 run tag 清夹具：共享库下不留验收残留（INT-179）。"""
    yield
    from tests.unit.oauth_fixture_cleanup import purge_oauth_test_fixtures
    purge_oauth_test_fixtures(_RUN)


# ---- 辅助 ----

@pytest.fixture()
def encryption_on(client):
    """临时开启登录密码加密（模块默认关闭，双格式明文契约为主）。"""
    from api_gateway.config.config import Config
    mp = pytest.MonkeyPatch()
    mp.setattr(Config, 'AUTH_PASSWORD_ENCRYPTION_ENABLED', True)
    yield
    mp.undo()


def _register(client, username, password='pass179'):
    resp = client.post('/api/v1/auth/register',
                       json={'username': username, 'password': password})
    assert resp.status_code == 201, resp.text
    return resp


def _encrypt_password(public_pem: str, password: str) -> str:
    import base64
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    public_key = serialization.load_pem_public_key(public_pem.encode('utf-8'))
    ciphertext = public_key.encrypt(
        password.encode('utf-8'),
        padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()),
                     algorithm=hashes.SHA256(), label=None),
    )
    return base64.b64encode(ciphertext).decode()


# ---- 缺陷一：公钥端点/refresh 免认证可达 ----

class TestEncryptionKeyReachable:

    def test_alias_path_no_auth(self, client, encryption_on):
        """旧库路径 GET /auth/encryption-key 无 token → 200 公钥信息。"""
        resp = client.get('/api/v1/auth/encryption-key')
        assert resp.status_code == 200, resp.text
        body = resp.json().get('data') or resp.json()
        assert body['enabled'] is True
        assert body['kid'] and 'BEGIN PUBLIC KEY' in body['public_key']

    def test_login_prefix_path_no_auth(self, client, encryption_on):
        """/login/encryption-key 语义不回退（INT-156 RSA 实测基线）。"""
        resp = client.get('/api/v1/auth/login/encryption-key')
        assert resp.status_code == 200, resp.text
        body = resp.json().get('data') or resp.json()
        assert body['enabled'] is True

    def test_alias_disabled_flag_semantics(self, client):
        """加密开关关闭时两路径一致回 {enabled: false}（前端回退明文）。"""
        for path in ('/api/v1/auth/encryption-key',
                     '/api/v1/auth/login/encryption-key'):
            resp = client.get(path)
            assert resp.status_code == 200, resp.text
            body = resp.json().get('data') or resp.json()
            assert body == {'enabled': False}

    def test_register_not_blocked(self, client):
        """注册端点白名单内可达（401 缺少认证令牌即回归失败）。"""
        _register(client, f'int179_reg_{_RUN}')

    def test_refresh_reaches_route_not_middleware(self, client):
        """无 token POST /refresh → 路由级 401（自验签），非网关拦截文案。"""
        resp = client.post('/api/v1/auth/refresh')
        assert resp.status_code == 401, resp.text
        assert '刷新' in resp.json()['detail']
        # 有效 token → 200 换发新 token
        _register(client, f'int179_ref_{_RUN}')
        resp = client.post('/api/v1/auth/login',
                           data={'username': f'int179_ref_{_RUN}',
                                 'password': 'pass179'})
        token = resp.json()['access_token']
        resp = client.post('/api/v1/auth/refresh',
                           headers={'Authorization': f'Bearer {token}'})
        assert resp.status_code == 200, resp.text
        body = resp.json().get('data') or resp.json()
        assert body['access_token']


# ---- 缺陷二：登录请求体双格式兼容 ----

class TestLoginDualFormat:

    def test_json_body_login(self, client):
        """JSON body 登录可达凭据校验（修复前 422 Field required）。"""
        username = f'int179_json_{_RUN}'
        _register(client, username)
        resp = client.post('/api/v1/auth/login',
                           json={'username': username, 'password': 'pass179'})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body['user']['username'] == username
        assert body['access_token']

    def test_json_body_wrong_password_401(self, client):
        username = f'int179_json_bad_{_RUN}'
        _register(client, username)
        resp = client.post('/api/v1/auth/login',
                           json={'username': username,
                                 'password': 'not-the-pass'})
        assert resp.status_code == 401

    def test_form_body_login_regression(self, client):
        """表单编码契约（前端 URLSearchParams）不回退。"""
        username = f'int179_form_{_RUN}'
        _register(client, username)
        resp = client.post('/api/v1/auth/login',
                           data={'username': username, 'password': 'pass179'})
        assert resp.status_code == 200, resp.text

    def test_json_encrypted_password_chain(self, client):
        """加密开启时 JSON 密文链路与表单语义一致（明文无回退）。

        注册先于开关闭明文完成（加密开启时注册也须密文字段）。"""
        from api_gateway.config.config import Config
        username = f'int179_jsenc_{_RUN}'
        _register(client, username)
        mp = pytest.MonkeyPatch()
        mp.setattr(Config, 'AUTH_PASSWORD_ENCRYPTION_ENABLED', True)
        try:
            resp = client.get('/api/v1/auth/encryption-key')
            body = resp.json().get('data') or resp.json()
            kid, public_pem = body['kid'], body['public_key']
            # JSON 明文在加密开启时必须拒绝（无明文回退）
            resp = client.post('/api/v1/auth/login',
                               json={'username': username,
                                     'password': 'pass179'})
            assert resp.status_code == 401
            resp = client.post(
                '/api/v1/auth/login',
                json={'username': username,
                      'password_encrypted': _encrypt_password(public_pem,
                                                              'pass179'),
                      'encryption_key_id': kid})
            assert resp.status_code == 200, resp.text
            assert resp.json()['user']['username'] == username
        finally:
            mp.undo()


# ---- 缺陷三：公开提供方仅回已启用项 ----

class TestPublicProvidersEnabledOnly:

    def test_enabled_only_no_secret(self, client, svc):
        from shared.proto import auth_service_pb2 as auth_pb
        enabled_slug = f'int179-on-{_RUN}'
        disabled_slug = f'int179-off-{_RUN}'
        for slug, enabled in ((enabled_slug, True), (disabled_slug, False)):
            resp = svc.CreateOAuthProvider(auth_pb.CreateOAuthProviderRequest(
                name=f'INT-179 {slug}', slug=slug, icon='', enabled=enabled,
                client_id='cid', client_secret='sec',
                authorize_url='https://a', token_url='https://t',
                userinfo_url='https://u', operator_id=1))
            assert resp.success, resp.message
        resp = client.get('/api/v1/auth/oauth/providers')  # 无认证头（白名单）
        assert resp.status_code == 200, resp.text
        providers = resp.json()['providers']
        slugs = [p['slug'] for p in providers]
        assert enabled_slug in slugs
        assert disabled_slug not in slugs
        for p in providers:
            assert 'client_secret' not in p


# ---- 夹具清理 helper（共享库不留残留，且不误伤他行） ----

class TestOAuthFixturePurge:

    def test_purge_scoped_to_tag(self, tmp_path):
        """tag 行清除、无 tag 行保留；提供方连带绑定一并清理。"""
        from auth_service.infrastructure.persistence.models import (
            CustomOAuthProvider, User, UserOAuthBinding, UserPermission,
        )
        from shared.models.database import Base
        import tests.unit.oauth_fixture_cleanup as cleanup_mod
        from tests.unit.oauth_fixture_cleanup import purge_oauth_test_fixtures

        engine = create_engine(f'sqlite:///{tmp_path / "purge.db"}')
        Base.metadata.create_all(
            bind=engine,
            tables=[CustomOAuthProvider.__table__, User.__table__,
                    UserOAuthBinding.__table__, UserPermission.__table__])
        Session = sessionmaker(bind=engine)

        tag = uuid.uuid4().hex[:8]
        with Session.begin() as s:
            s.add(CustomOAuthProvider(
                name='tagged', slug=f'p-{tag}', icon='', enabled=True,
                client_id='c', client_secret='s',
                authorize_url='https://a', token_url='https://t',
                userinfo_url='https://u'))
            s.add(CustomOAuthProvider(
                name='keeper', slug=f'keep-{uuid.uuid4().hex[:8]}', icon='',
                enabled=False, client_id='c', client_secret='s',
                authorize_url='https://a', token_url='https://t',
                userinfo_url='https://u'))
            s.flush()
            tagged_provider_id = s.query(CustomOAuthProvider).filter_by(
                slug=f'p-{tag}').one().id
            keeper_provider_id = s.query(CustomOAuthProvider).filter_by(
                name='keeper').one().id
            tagged_user = User(username=f'u-{tag}', status='active')
            keeper_user = User(username=f'keeper-{uuid.uuid4().hex[:8]}',
                               status='active')
            s.add_all([tagged_user, keeper_user])
            s.flush()
            s.add(UserOAuthBinding(user_id=tagged_user.id,
                                   provider_id=tagged_provider_id,
                                   provider_user_id='ext-tag'))
            s.add(UserOAuthBinding(user_id=keeper_user.id,
                                   provider_id=keeper_provider_id,
                                   provider_user_id='ext-keep'))

        mp = pytest.MonkeyPatch()
        mp.setattr(cleanup_mod, 'get_db_session', Session)
        mp.setattr(cleanup_mod, 'remove_db_session', lambda: None)
        try:
            deleted = purge_oauth_test_fixtures(tag)
        finally:
            mp.undo()

        assert deleted['providers'] == 1
        assert deleted['users'] == 1
        with Session() as s:
            assert s.query(CustomOAuthProvider).filter_by(
                slug=f'p-{tag}').count() == 0
            assert s.query(CustomOAuthProvider).filter_by(
                id=keeper_provider_id).count() == 1
            assert s.query(User).filter(
                User.username.like(f'%{tag}')).count() == 0
            assert s.query(User).filter(
                User.username.like('keeper-%')).count() == 1
            assert s.query(UserOAuthBinding).filter_by(
                provider_id=tagged_provider_id).count() == 0
            assert s.query(UserOAuthBinding).filter_by(
                provider_id=keeper_provider_id).count() == 1
