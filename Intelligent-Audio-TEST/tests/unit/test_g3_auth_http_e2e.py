# -*- coding: utf-8 -*-
"""G3 登录体系改造网关 HTTP 层端到端验收（INT-51 测试工程师独立验收）。

开发自测覆盖 servicer 层（sqlite e2e）与 mock httpx 编排层；本文件补
网关 HTTP 路由层验收缺口：真实 FastAPI 路由 + 真实 AuthMiddleware 白名单
+ 真实 gRPC servicer（直连真实 SQLAlchemy/SQLite，bcrypt 真实校验），
并起本地 mock IdP HTTP 服务验证真实授权回调（验收标准 2「本地 mock
provider 验证」要求，mock IdP 为真实 TCP 服务而非 monkeypatch）。

覆盖（对照验收标准）：
- AC1 注册→登录→me 全流程（HTTP 层 201→token→me）；关闭注册开关 403
- AC2 管理端配置提供方 → /oauth/providers 公开可见（无凭证字段）→
  authorize 跳转 → 本地 mock IdP 真实回调 30x oauth_token → me 可用；
  state 篡改 → 30x oauth_error；管理端 CRUD 走 HTTP（201/409 掩码）
- AC2 权限回归：guest 访问 /oauth-providers 403；admin 200
- AC3 华为云预置：/auth/login 入口在 DB 无记录时回退环境预置提供方
  （30x 授权 URL 等效旧硬编码行为，state 可验签）
- seed_custom_oauth_providers 幂等（二次执行不覆盖/不重复；未配置环境
  变量时跳过）

不依赖外部服务：auth_config_service 代理以真实 AuthServicer 注入
（进程内直连，与 test_g3_oauth_provider_management 同款模式）。
"""
import importlib.util
import json
import os
import tempfile
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

# 网关 RedirectResponse 默认 307（与旧 /login 行为一致，GET 语义等效 302）
_REDIRECT_STATUSES = (301, 302, 303, 307, 308)


def _assert_redirect(resp):
    """断言响应为重定向并返回 Location。"""
    assert resp.status_code in _REDIRECT_STATUSES, resp.text
    return resp.headers['location']


os.environ.setdefault('DATABASE_URL',
                      'sqlite:///' + tempfile.mkdtemp(prefix='int51http_')
                      + '/auth.db')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from sqlalchemy import BigInteger
from sqlalchemy import create_engine
from sqlalchemy.ext.compiler import compiles

from shared.models.database import init_db, get_db_session, remove_db_session

_RUN = uuid.uuid4().hex[:8]


@compiles(BigInteger, 'sqlite')
def _render_bigint_as_integer_sqlite(type_, compiler, **kw):
    """SQLite 不支持 BigInteger 主键自增，建表时渲染为 INTEGER。"""
    return 'INTEGER'


@pytest.fixture(scope='module')
def svc():
    """真实 AuthServicer + 真实 SQLite 库（auth 相关表）。"""
    init_db(pool_size=3)
    from shared.models.database import Base
    from auth_service.infrastructure.persistence.models import (
        Role, Permission, RolePermission, UserPermission, User,
        CustomOAuthProvider,
    )
    Base.metadata.create_all(
        bind=get_db_session().get_bind(),
        tables=[Role.__table__, Permission.__table__,
                RolePermission.__table__, UserPermission.__table__,
                User.__table__, CustomOAuthProvider.__table__],
    )
    from auth_service.interfaces.grpc.servicers import AuthServicer
    servicer = AuthServicer()
    yield servicer
    remove_db_session()


@pytest.fixture(scope='module')
def seeded(svc):
    """RBAC 种子：guest（注册默认角色）/ admin（绑定 auth:manage_provider）。"""
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
def client(seeded, svc):
    """最小网关应用：真实路由 + 真实中间件；gRPC 代理直连真实 servicer。"""
    from auth_service.interfaces.grpc.servicers import AuthServicer
    proxy = type('P', (), {'stub': AuthServicer()})()
    import api_gateway.infrastructure.grpc_proxies as proxies_pkg
    import api_gateway.application.services.auth.management_common as mc
    mp = pytest.MonkeyPatch()
    mp.setattr(proxies_pkg, 'auth_config_service', proxy)
    # management_common 在模块导入期绑定代理对象，需同步替换模块绑定
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
    # 真实 uvicorn 服务（仓库既有验收模式，INT-29 同款）：持久事件循环 +
    # anyio worker 线程跨请求复用，等效生产 gRPC worker 的会话驻留边界。
    # 不用 starlette TestClient：每请求新线程会让 scoped session 失去
    # DbScopeInterceptor 清理语义而耗尽连接池（非生产形态）。
    import time
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
    # trust_env=False：Windows 系统代理会劫持 localhost 请求（见 tests/api/conftest）
    yield httpx.Client(base_url=f'http://{host}:{port}',
                       trust_env=False, follow_redirects=False,
                       timeout=15)
    server.should_exit = True
    thread.join(timeout=5)
    mp.undo()


def _register_and_login(client, username, password='pass123456'):
    resp = client.post('/api/v1/auth/register',
                       json={'username': username, 'password': password})
    assert resp.status_code == 201, resp.text
    resp = client.post('/api/v1/auth/login',
                       data={'username': username, 'password': password})
    assert resp.status_code == 200, resp.text
    token = resp.json()['access_token']
    return {'Authorization': f'Bearer {token}'}


def _create_provider_http(client, headers, slug, token_url='https://t/x',
                          userinfo_url='https://u/x', enabled=True):
    return client.post('/api/v1/auth/oauth-providers', headers=headers,
                       json={'name': '验收提供方', 'slug': slug,
                             'client_id': 'cid-acc', 'client_secret': 'sec-acc',
                             'authorize_url': 'https://idp.example.com/authorize',
                             'token_url': token_url,
                             'userinfo_url': userinfo_url,
                             'enabled': enabled})


class _MockIdPHandler(BaseHTTPRequestHandler):
    """本地 mock OAuth IdP：/token 发 token，/userinfo 校验 Bearer 后回用户信息。"""
    userinfo = {'sub': 'ext-1001', 'preferred_username': 'zhangsan',
                'name': '张三', 'email': 'zhangsan@example.com'}

    def do_POST(self):
        length = int(self.headers.get('Content-Length', 0))
        if length:
            self.rfile.read(length)
        body = json.dumps({'access_token': 'mock-access-token',
                           'token_type': 'Bearer'}).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if not self.headers.get('Authorization', '')\
                .startswith('Bearer mock-access-token'):
            self.send_response(401)
            self.end_headers()
            return
        body = json.dumps(type(self).userinfo).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # 静默访问日志
        pass


@pytest.fixture()
def mock_idp():
    server = ThreadingHTTPServer(('127.0.0.1', 0), _MockIdPHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_address[1]}'
    finally:
        server.shutdown()
        server.server_close()


class TestRegistrationLoginMeHttp:
    """AC1：注册→登录→me 全流程（HTTP 层）；关闭注册开关 403。"""

    def test_register_login_me_full_flow(self, client, seeded):
        username = f'e2e_reg_{_RUN}'
        headers = _register_and_login(client, username)
        resp = client.get('/api/v1/auth/me', headers=headers)
        assert resp.status_code == 200, resp.text
        assert resp.json()['username'] == username

    def test_register_duplicate_username_rejected(self, client, seeded):
        username = f'e2e_dup_{_RUN}'
        assert client.post('/api/v1/auth/register', json={
            'username': username, 'password': 'pass123456'}).status_code == 201
        assert client.post('/api/v1/auth/register', json={
            'username': username, 'password': 'pass123456'}).status_code == 400

    def test_register_disabled_returns_403(self, client, seeded,
                                           monkeypatch):
        from api_gateway.config.config import Config
        monkeypatch.setattr(Config, 'AUTH_REGISTRATION_ENABLED', False)
        resp = client.post('/api/v1/auth/register', json={
            'username': f'e2e_closed_{_RUN}', 'password': 'pass123456'})
        assert resp.status_code == 403

    def test_login_wrong_password_rejected(self, client, seeded):
        username = f'e2e_wrongpw_{_RUN}'
        _register_and_login(client, username)
        resp = client.post('/api/v1/auth/login',
                           data={'username': username,
                                 'password': 'not-the-pass'})
        assert resp.status_code == 401


class TestCustomOAuthCallbackHttp:
    """AC2：自定义提供方登录页可见 → 真实 mock IdP 授权回调 → 建号登录。"""

    def test_public_provider_list_no_secret(self, client, seeded, svc):
        from shared.proto import auth_service_pb2 as auth_pb
        slug = f'pub-idp-{_RUN}'
        resp = svc.CreateOAuthProvider(auth_pb.CreateOAuthProviderRequest(
            name='公开提供方', slug=slug, icon='', enabled=True,
            client_id='cid', client_secret='sec',
            authorize_url='https://a', token_url='https://t',
            userinfo_url='https://ui', operator_id=1))
        assert resp.success, resp.message
        resp = client.get('/api/v1/auth/oauth/providers')  # 无认证头（白名单）
        assert resp.status_code == 200, resp.text
        providers = resp.json()['providers']
        target = [p for p in providers if p['slug'] == slug]
        assert target, f'公开列表缺少 {slug}'
        assert 'client_secret' not in target[0]

    def test_authorize_then_real_callback_creates_user(self, client, seeded,
                                                       svc, mock_idp):
        from shared.proto import auth_service_pb2 as auth_pb
        from api_gateway.config.config import Config
        slug = f'cb-idp-{_RUN}'
        resp = svc.CreateOAuthProvider(auth_pb.CreateOAuthProviderRequest(
            name='回调验收提供方', slug=slug, icon='', enabled=True,
            client_id='cid-cb', client_secret='sec-cb',
            authorize_url=f'{mock_idp}/authorize',
            token_url=f'{mock_idp}/token',
            userinfo_url=f'{mock_idp}/userinfo',
            user_id_field='sub', username_field='preferred_username',
            display_name_field='name', email_field='email',
            operator_id=1))
        assert resp.success, resp.message

        # 授权跳转（白名单端点，无认证头）：30x → IdP 授权页，state 可验签
        loc = _assert_redirect(
            client.get(f'/api/v1/auth/oauth/{slug}/authorize'))
        assert loc.startswith(f'{mock_idp}/authorize')
        state = parse_qs(urlparse(loc).query)['state'][0]
        from api_gateway.application.services.auth.oauth_provider_service import (
            OAuthProviderService,
        )
        OAuthProviderService._verify_state(state, slug)

        # 真实回调（mock IdP 为真实 TCP 服务）：换 token → 拉 userinfo → 30x
        resp = client.get(
            f'/api/v1/auth/oauth/{slug}/callback',
            params={'code': 'good-code', 'state': state})
        loc = _assert_redirect(resp)
        assert loc.startswith(
            f"{Config.OAUTH_REDIRECT_BASE.rstrip('/')}/#/login?oauth_token=")
        token = parse_qs(
            urlparse(loc).fragment.split('?', 1)[1])['oauth_token'][0]

        # 签发的 JWT 可直接访问 me
        import jwt as pyjwt
        claims = pyjwt.decode(token, Config.JWT_SECRET,
                              algorithms=[Config.JWT_ALGORITHM])
        assert claims['username'] == 'zhangsan'
        resp = client.get('/api/v1/auth/me',
                          headers={'Authorization': f'Bearer {token}'})
        assert resp.status_code == 200, resp.text
        assert resp.json()['username'] == 'zhangsan'

        # OAuth 用户落库：oauth_provider=slug、oauth_id=外部标识
        from auth_service.infrastructure.persistence.models import User
        session = get_db_session()
        row = (session.query(User)
               .filter(User.username == 'zhangsan').one_or_none())
        assert row is not None
        assert row.oauth_provider == slug
        assert row.oauth_id == 'ext-1001'

    def test_callback_tampered_state_redirects_error(self, client, seeded,
                                                     svc, mock_idp):
        from shared.proto import auth_service_pb2 as auth_pb
        slug = f'bad-idp-{_RUN}'
        resp = svc.CreateOAuthProvider(auth_pb.CreateOAuthProviderRequest(
            name='防伪验收提供方', slug=slug, icon='', enabled=True,
            client_id='cid', client_secret='sec',
            authorize_url=f'{mock_idp}/authorize',
            token_url=f'{mock_idp}/token',
            userinfo_url=f'{mock_idp}/userinfo', operator_id=1))
        assert resp.success, resp.message
        loc = _assert_redirect(
            client.get(f'/api/v1/auth/oauth/{slug}/authorize'))
        state = parse_qs(urlparse(loc).query)['state'][0]
        resp = client.get(f'/api/v1/auth/oauth/{slug}/callback',
                          params={'code': 'c', 'state': state + 'x'})
        fragment = urlparse(_assert_redirect(resp)).fragment
        assert 'oauth_error=' in fragment
        assert 'oauth_token' not in fragment


class TestProviderManagementPermissionHttp:
    """AC2 权限回归：guest 403 / admin 200（client_secret 掩去）。"""

    def test_guest_cannot_manage_providers(self, client, seeded):
        username = f'e2e_guest_{_RUN}'
        headers = _register_and_login(client, username)
        resp = client.get('/api/v1/auth/oauth-providers', headers=headers)
        assert resp.status_code == 403, resp.text

    def test_admin_can_manage_and_secret_masked(self, client, seeded, svc):
        from shared.proto import auth_service_pb2 as auth_pb
        username = f'e2e_admin_{_RUN}'
        resp = svc.CreateUser(auth_pb.CreateUserRequest(
            username=username, password='admin-pass-123',
            role_name='admin', operator_id=1))
        assert resp.success, resp.message
        resp = client.post('/api/v1/auth/login',
                           data={'username': username,
                                 'password': 'admin-pass-123'})
        assert resp.status_code == 200, resp.text
        headers = {'Authorization':
                   f"Bearer {resp.json()['access_token']}"}

        slug = f'managed-idp-{_RUN}'
        resp = _create_provider_http(client, headers, slug)
        assert resp.status_code == 201, resp.text
        assert resp.json()['data']['provider_id']

        # 重复 slug → 409（OAUTH_SLUG_DUPLICATED 的网关映射）
        resp = _create_provider_http(client, headers, slug)
        assert resp.status_code == 409, resp.text

        resp = client.get('/api/v1/auth/oauth-providers', headers=headers)
        assert resp.status_code == 200, resp.text
        providers = resp.json()['data']['providers']
        target = [p for p in providers if p['slug'] == slug]
        assert target, '管理端列表缺少新建提供方'
        assert 'client_secret' not in target[0]
        assert target[0]['has_client_secret'] is True


class TestHuaweiPresetHttpEntry:
    """AC3：DB 无 huawei 记录时 /auth/login 入口回退环境预置提供方。"""

    def test_login_entry_falls_back_to_env_preset(self, client, seeded,
                                                  monkeypatch):
        from api_gateway.config.config import Config
        monkeypatch.setattr(Config, 'AUTH_MODE', 'prod')
        monkeypatch.setattr(Config, 'HW_OAUTH_CLIENT_ID', 'hw-acc-1')
        monkeypatch.setattr(Config, 'HW_OAUTH_CLIENT_SECRET', 'hw-sec-1')
        monkeypatch.setattr(Config, 'HW_OAUTH_AUTHORIZE_URL',
                            'https://oauth.huaweicloud.com/oauth2/authorize')
        monkeypatch.setattr(Config, 'HW_OAUTH_REDIRECT_URI',
                            'http://localhost:8000/api/v1/auth/callback')
        resp = client.get('/api/v1/auth/login')
        loc = _assert_redirect(resp)
        parsed = urlparse(loc)
        assert (f'{parsed.scheme}://{parsed.netloc}{parsed.path}'
                == 'https://oauth.huaweicloud.com/oauth2/authorize')
        qs = parse_qs(parsed.query)
        assert qs['client_id'] == ['hw-acc-1']
        assert qs['response_type'] == ['code']
        assert qs['redirect_uri'] == [
            'http://localhost:8000/api/v1/auth/callback']
        from api_gateway.application.services.auth.oauth_provider_service import (
            OAuthProviderService,
        )
        OAuthProviderService._verify_state(qs['state'][0], 'huawei')


class TestSeedCustomOAuthProvidersScript:
    """seed_custom_oauth_providers.py：幂等 + 未配置环境变量跳过。"""

    def _load_seed_module(self):
        path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            '..', '..', 'scripts', 'migrations', '202610',
            'seed_custom_oauth_providers.py')
        spec = importlib.util.spec_from_file_location(
            f'seed_custom_oauth_providers_{_RUN}', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def _make_db(self, tmp_path, name):
        from shared.models.database import Base
        from auth_service.infrastructure.persistence.models import (
            CustomOAuthProvider,
        )
        engine = create_engine(
            f'sqlite:///{tmp_path / name}')
        Base.metadata.create_all(bind=engine,
                                 tables=[CustomOAuthProvider.__table__])
        return engine

    def _count(self, engine):
        from sqlalchemy import text
        with engine.begin() as conn:
            return conn.execute(text(
                'SELECT COUNT(*) FROM custom_oauth_providers')).scalar()

    def test_seed_idempotent_and_skip_without_env(self, tmp_path,
                                                  monkeypatch):
        module = self._load_seed_module()
        monkeypatch.setenv('HW_OAUTH_CLIENT_ID', 'hw-seed-1')
        monkeypatch.setenv('HW_OAUTH_CLIENT_SECRET', 'hw-seed-secret')

        engine = self._make_db(tmp_path, 'seed.db')
        with engine.begin() as conn:
            module.seed_providers(conn)
        assert self._count(engine) == 1

        # 二次执行：slug 已存在 → 跳过（不覆盖、不重复）
        with engine.begin() as conn:
            module.seed_providers(conn)
        assert self._count(engine) == 1

        # 未配置 HW_OAUTH_CLIENT_ID → 跳过插入
        monkeypatch.delenv('HW_OAUTH_CLIENT_ID', raising=False)
        engine2 = self._make_db(tmp_path, 'seed2.db')
        with engine2.begin() as conn:
            module.seed_providers(conn)
        assert self._count(engine2) == 0
