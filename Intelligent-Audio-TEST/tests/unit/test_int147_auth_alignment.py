# -*- coding: utf-8 -*-
"""INT-147 认证域对齐验收（RSA 加密登录 / 邮箱登录 / 第三方绑定 / Discovery / 首个用户 admin）。

网关 HTTP 层端到端：真实 FastAPI 路由 + 真实 AuthMiddleware 白名单 + 真实
gRPC servicer（直连真实 SQLAlchemy/SQLite，bcrypt 真实校验），模式对齐
test_g3_auth_http_e2e（auth_config_service 代理以真实 AuthServicer 注入）。

覆盖（对照验收标准）：
- AC1 RSA 加密链路：公钥下发 → 注册/登录携 password_encrypted +
  encryption_key_id；明文 password 在加密开启时被拒（抓包无明文等价语义，
  服务端不回退）；kid 不匹配/密文篡改 → 统一 401；开关关闭回退明文
- AC2 邮箱登录：email 与 username 等价登录
- AC2 绑定/解绑端点：绑定票据完成绑定（幂等）、列表、解绑（幂等）、
  身份冲突 400、未登录 401
- AC4 Discovery：issuer_url 拉取 OIDC 文档（admin 200 / guest 403 / 匿名 401）
- AC3 首个注册用户 admin + 后续 guest（实测；共享库快照/恢复，不影响他例）
"""
import json
import os
import tempfile
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import pytest

os.environ.setdefault('DATABASE_URL',
                      'sqlite:///' + tempfile.mkdtemp(prefix='int147http_')
                      + '/auth.db')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from sqlalchemy import BigInteger
from sqlalchemy.ext.compiler import compiles

from shared.models.database import init_db, get_db_session, get_engine, remove_db_session


@compiles(BigInteger, 'sqlite')
def _render_bigint_as_integer_sqlite(type_, compiler, **kw):
    """SQLite 不支持 BigInteger 主键自增，建表时渲染为 INTEGER。"""
    return 'INTEGER'


@pytest.fixture(scope='module')
def rsa_key_path(tmp_path_factory):
    """RSA 私钥写入模块级临时目录（不落仓库 data/）。"""
    return str(tmp_path_factory.mktemp('int147_rsa') / 'auth_key.pem')


@pytest.fixture(scope='module')
def svc(rsa_key_path):
    init_db(pool_size=3)
    engine = get_engine()
    assert ':memory:' not in str(engine.url), \
        'INT-147 e2e 需要文件型 sqlite（跨线程共享表）'
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
    server_errors = []

    def _run_server():
        try:
            server.run()
        except Exception as e:  # noqa: BLE001 — fixture 诊断用
            server_errors.append(e)

    thread = threading.Thread(target=_run_server, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    assert server.started, (f'INT-147 最小网关应用 uvicorn 启动失败: '
                            f'{server_errors!r}')
    host, port = server.servers[0].sockets[0].getsockname()[:2]
    yield httpx.Client(base_url=f'http://{host}:{port}',
                       trust_env=False, follow_redirects=False,
                       timeout=15)
    server.should_exit = True
    thread.join(timeout=5)
    mp.undo()


# ---- 辅助 ----

_RUN = uuid.uuid4().hex[:8]


def _fetch_key(client):
    resp = client.get('/api/v1/auth/login/encryption-key')
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body['enabled'] is True
    assert body['kid'] and 'BEGIN PUBLIC KEY' in body['public_key']
    return body['kid'], body['public_key']


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


def _register_encrypted(client, username, password, email=None):
    """RSA 加密密码注册（复用服务端下发的公钥）。"""
    kid, public_pem = _fetch_key(client)
    body = {'username': username,
            'password_encrypted': _encrypt_password(public_pem, password),
            'encryption_key_id': kid}
    if email:
        body['email'] = email
    resp = client.post('/api/v1/auth/register', json=body)
    assert resp.status_code == 201, resp.text
    return resp


def _login(client, **fields):
    return client.post('/api/v1/auth/login', data=fields)


def _token_for(user_id, username, role_id=1, permissions=None):
    from api_gateway.application.services.auth.token_service import TokenService
    token = TokenService.create_token(
        user_id=user_id, username=username, role_id=role_id,
        permissions=permissions if permissions is not None else ['*'])
    return f'Bearer {token}'


def _create_provider(client, headers, slug):
    resp = client.post('/api/v1/auth/oauth-providers', headers=headers,
                       json={'name': 'INT-147 绑定验收', 'slug': slug,
                             'client_id': 'cid-147', 'client_secret': 'sec-147',
                             'authorize_url': 'https://idp.example.com/authorize',
                             'token_url': 'https://idp.example.com/token',
                             'userinfo_url': 'https://idp.example.com/userinfo',
                             'enabled': True})
    assert resp.status_code == 201, resp.text
    body = resp.json()
    provider_id = (body.get('data') or {}).get('provider_id') or body.get('provider_id')
    assert provider_id, resp.text
    return int(provider_id)


# ---- intent=bind 票据链路（纯密码学/签名层，无 HTTP）----

class TestBindStateAndTicket:

    def test_state_intent_roundtrip_and_mismatch(self):
        from api_gateway.application.services.auth.oauth_provider_service import (
            OAuthProviderError, OAuthProviderService,
        )
        state_bind = OAuthProviderService._sign_state('int147-idp', intent='bind')
        assert OAuthProviderService.verify_state_intent(
            state_bind, 'int147-idp') == 'bind'
        state_login = OAuthProviderService._sign_state('int147-idp')
        assert OAuthProviderService.verify_state_intent(
            state_login, 'int147-idp') == 'login'
        # bind 流程不得用 login 意图的 state 通过回调校验
        with pytest.raises(OAuthProviderError):
            OAuthProviderService._verify_state(state_login, 'int147-idp',
                                               intent='bind')

    def test_bind_ticket_roundtrip(self):
        from api_gateway.application.services.auth.oauth_provider_service import (
            OAuthProviderError, OAuthProviderService,
        )
        ticket = OAuthProviderService.sign_bind_ticket(
            provider_id=7, slug='int147-idp',
            provider_user_id='ext-147', display_name='张三')
        identity = OAuthProviderService.verify_bind_ticket(ticket)
        assert identity == {'provider_id': 7, 'slug': 'int147-idp',
                            'provider_user_id': 'ext-147',
                            'display_name': '张三'}
        with pytest.raises(OAuthProviderError):
            OAuthProviderService.verify_bind_ticket('garbage')
        with pytest.raises(OAuthProviderError):
            # state 不能当绑定票据用（purpose 不同）
            OAuthProviderService.verify_bind_ticket(
                OAuthProviderService._sign_state('int147-idp'))


# ---- AC1：RSA 加密链路 ----

class TestPasswordEncryptionLogin:

    def test_encryption_key_endpoint_shape(self, client):
        kid1, _ = _fetch_key(client)
        kid2, _ = _fetch_key(client)
        assert kid1 == kid2  # 同一私钥 kid 稳定

    def test_register_and_login_with_encrypted_password(self, client):
        username = f'int147_rsa_{_RUN}'
        _register_encrypted(client, username, 'Secret-147!')
        resp = _login(client, username=username,
                      password_encrypted='ignored-by-encryption-mode')
        assert resp.status_code == 401  # 仅明文字段在加密开启时必须拒绝
        kid, public_pem = _fetch_key(client)
        resp = _login(client, username=username,
                      password_encrypted=_encrypt_password(public_pem, 'Secret-147!'),
                      encryption_key_id=kid)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body['user']['username'] == username
        assert body['access_token']

    def test_login_by_email(self, client):
        username = f'int147_mail_{_RUN}'
        email = f'{username}@example.com'
        _register_encrypted(client, username, 'Secret-147!', email=email)
        kid, public_pem = _fetch_key(client)
        # 用户名登录
        resp = _login(client, username=username,
                      password_encrypted=_encrypt_password(public_pem, 'Secret-147!'),
                      encryption_key_id=kid)
        assert resp.status_code == 200, resp.text
        # 邮箱登录（等价）
        resp = _login(client, username=email,
                      password_encrypted=_encrypt_password(public_pem, 'Secret-147!'),
                      encryption_key_id=kid)
        assert resp.status_code == 200, resp.text
        assert resp.json()['user']['username'] == username

    def test_login_rejects_wrong_kid_and_tampered(self, client):
        username = f'int147_tamper_{_RUN}'
        _register_encrypted(client, username, 'Secret-147!')
        _, public_pem = _fetch_key(client)
        good = _encrypt_password(public_pem, 'Secret-147!')
        resp = _login(client, username=username,
                      password_encrypted=good, encryption_key_id='f' * 32)
        assert resp.status_code == 401
        assert resp.json()['detail'] == '用户名或密码错误'  # 防枚举统一话术
        tampered = good[:-4] + ('AAAA' if good[-4:] != 'AAAA' else 'BBBB')
        resp = _login(client, username=username,
                      password_encrypted=tampered,
                      encryption_key_id=_fetch_key(client)[0])
        assert resp.status_code == 401

    def test_encryption_disabled_falls_back_to_plaintext(self, client):
        from api_gateway.config.config import Config
        username = f'int147_plain_{_RUN}'
        mp = pytest.MonkeyPatch()
        mp.setattr(Config, 'AUTH_PASSWORD_ENCRYPTION_ENABLED', False)
        try:
            resp = client.get('/api/v1/auth/login/encryption-key')
            assert resp.status_code == 200
            assert resp.json() == {'enabled': False}
            # 明文注册 + 明文登录（开关关闭语义）
            resp = client.post('/api/v1/auth/register',
                               json={'username': username, 'password': 'Secret-147!'})
            assert resp.status_code == 201, resp.text
            resp = _login(client, username=username, password='Secret-147!')
            assert resp.status_code == 200, resp.text
        finally:
            mp.undo()


# ---- AC2：第三方账号绑定 ----

@pytest.fixture(scope='module')
def binding_env(client):
    """admin token + 提供方 + 两个已注册用户 + 绑定票据。"""
    run = uuid.uuid4().hex[:8]
    admin_headers = {'Authorization': _token_for(999999, 'int147_admin')}

    username1 = f'int147_bind_{run}'
    _register_encrypted(client, username1, 'Secret-147!')
    kid, public_pem = _fetch_key(client)
    user1_id = int(_login(client, username=username1,
                          password_encrypted=_encrypt_password(public_pem, 'Secret-147!'),
                          encryption_key_id=kid).json()['user']['id'])

    username2 = f'int147_other_{run}'
    _register_encrypted(client, username2, 'Secret-147!')
    user2_id = int(_login(client, username=username2,
                          password_encrypted=_encrypt_password(public_pem, 'Secret-147!'),
                          encryption_key_id=kid).json()['user']['id'])

    provider_id = _create_provider(client, admin_headers, f'int147-bind-{run}')
    from api_gateway.application.services.auth.oauth_provider_service import (
        OAuthProviderService,
    )
    ticket = OAuthProviderService.sign_bind_ticket(
        provider_id=provider_id, slug=f'int147-bind-{run}',
        provider_user_id='ext-user-147', display_name='绑定验收')
    return {
        'admin_headers': admin_headers,
        'user1_headers': {'Authorization': _token_for(user1_id, username1)},
        'user2_headers': {'Authorization': _token_for(user2_id, username2)},
        'provider_id': provider_id,
        'ticket': ticket,
        'username1': username1,
    }


class TestOAuthBindings:

    def test_bind_requires_auth(self, client, binding_env):
        resp = client.get('/api/v1/auth/oauth/bindings')
        assert resp.status_code == 401
        resp = client.post('/api/v1/auth/oauth/bindings', json={'bind_ticket': 'x'})
        assert resp.status_code == 401
        resp = client.delete('/api/v1/auth/oauth/bindings/1')
        assert resp.status_code == 401

    def test_complete_bind_and_list(self, client, binding_env):
        resp = client.post('/api/v1/auth/oauth/bindings',
                           headers=binding_env['user1_headers'],
                           json={'bind_ticket': binding_env['ticket']})
        assert resp.status_code == 200, resp.text
        binding = resp.json().get('data') or resp.json()
        assert binding['provider_id'] == binding_env['provider_id']
        assert binding['provider_user_id'] == 'ext-user-147'
        # 幂等：同一用户重复提交同一票据 → 仍成功
        resp = client.post('/api/v1/auth/oauth/bindings',
                           headers=binding_env['user1_headers'],
                           json={'bind_ticket': binding_env['ticket']})
        assert resp.status_code == 200, resp.text
        # 列表可见
        resp = client.get('/api/v1/auth/oauth/bindings',
                          headers=binding_env['user1_headers'])
        assert resp.status_code == 200
        bindings = (resp.json().get('data') or resp.json())['bindings']
        assert any(b['provider_id'] == binding_env['provider_id']
                   and b['provider_user_id'] == 'ext-user-147'
                   for b in bindings)

    def test_identity_conflict_with_other_user(self, client, binding_env):
        resp = client.post('/api/v1/auth/oauth/bindings',
                           headers=binding_env['user2_headers'],
                           json={'bind_ticket': binding_env['ticket']})
        assert resp.status_code == 400, resp.text
        assert '已被其他用户绑定' in json.dumps(resp.json(), ensure_ascii=False)

    def test_invalid_ticket_rejected(self, client, binding_env):
        resp = client.post('/api/v1/auth/oauth/bindings',
                           headers=binding_env['user1_headers'],
                           json={'bind_ticket': 'not-a-jwt'})
        assert resp.status_code == 400
        resp = client.post('/api/v1/auth/oauth/bindings',
                           headers=binding_env['user1_headers'], json={})
        assert resp.status_code == 400

    def test_unbind_idempotent(self, client, binding_env):
        resp = client.delete(
            f"/api/v1/auth/oauth/bindings/{binding_env['provider_id']}",
            headers=binding_env['user1_headers'])
        assert resp.status_code == 200, resp.text
        bindings = (client.get('/api/v1/auth/oauth/bindings',
                               headers=binding_env['user1_headers']).json()
                    .get('data') or {}).get('bindings', [])
        assert not any(b['provider_id'] == binding_env['provider_id']
                       for b in bindings)
        # 幂等：重复解绑仍 200（对齐旧库语义）
        resp = client.delete(
            f"/api/v1/auth/oauth/bindings/{binding_env['provider_id']}",
            headers=binding_env['user1_headers'])
        assert resp.status_code == 200


# ---- AC4：OIDC Discovery ----

class _MockDiscoveryHandler(BaseHTTPRequestHandler):
    discovery_doc = {
        'issuer': 'https://idp.example.com',
        'authorization_endpoint': 'https://idp.example.com/authorize',
        'token_endpoint': 'https://idp.example.com/token',
        'userinfo_endpoint': 'https://idp.example.com/userinfo',
        'jwks_uri': 'https://idp.example.com/jwks',
        'scopes_supported': ['openid', 'profile', 'email'],
    }

    def do_GET(self):
        body = json.dumps(type(self).discovery_doc).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


@pytest.fixture()
def mock_discovery():
    server = ThreadingHTTPServer(('127.0.0.1', 0), _MockDiscoveryHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{server.server_address[1]}'
    finally:
        server.shutdown()
        server.server_close()


class TestOAuthAdminDiscovery:

    def test_discovery_requires_auth(self, client):
        resp = client.post('/api/v1/auth/oauth/admin/discovery',
                           json={'issuer_url': 'https://x'})
        assert resp.status_code == 401

    def test_discovery_requires_admin(self, client):
        guest_headers = {'Authorization': _token_for(888888, 'int147_guest',
                                                     permissions=[])}
        resp = client.post('/api/v1/auth/oauth/admin/discovery',
                           headers=guest_headers,
                           json={'issuer_url': 'https://x'})
        assert resp.status_code == 403

    def test_discovery_fetches_document(self, client, mock_discovery):
        admin_headers = {'Authorization': _token_for(999999, 'int147_admin')}
        resp = client.post('/api/v1/auth/oauth/admin/discovery',
                           headers=admin_headers,
                           json={'issuer_url': mock_discovery})
        assert resp.status_code == 200, resp.text
        data = resp.json().get('data') or resp.json()
        assert data['well_known_url'] == f'{mock_discovery}/.well-known/openid-configuration'
        assert data['discovery']['authorization_endpoint'] == 'https://idp.example.com/authorize'
        # 显式 well_known_url 直取
        resp = client.post('/api/v1/auth/oauth/admin/discovery',
                           headers=admin_headers,
                           json={'well_known_url': f'{mock_discovery}/.well-known/openid-configuration'})
        assert resp.status_code == 200
        data = resp.json().get('data') or resp.json()
        assert data['discovery']['token_endpoint'] == 'https://idp.example.com/token'

    def test_discovery_missing_url_rejected(self, client):
        admin_headers = {'Authorization': _token_for(999999, 'int147_admin')}
        resp = client.post('/api/v1/auth/oauth/admin/discovery',
                           headers=admin_headers, json={})
        assert resp.status_code == 400


# ---- AC3：首个注册用户角色策略（破坏共享库用例放模块末尾 + 快照恢复）----

class TestFirstUserAdminPolicy:

    def test_first_registered_user_becomes_admin_then_guest(self, client):
        run = uuid.uuid4().hex[:8]
        first_name = f'int147_first_{run}'
        second_name = f'int147_second_{run}'

        from shared.models.database import get_db_session as _gds
        from auth_service.infrastructure.persistence.models import (
            User, UserPermission, UserOAuthBinding,
        )
        session = _gds()
        snapshot = [{
            'id': r.id, 'username': r.username, 'password_hash': r.password_hash,
            'email': r.email, 'role_id': r.role_id, 'status': r.status,
            'oauth_provider': r.oauth_provider, 'oauth_id': r.oauth_id,
            'oauth_unionid': r.oauth_unionid, 'oauth_nickname': r.oauth_nickname,
            'oauth_avatar_url': r.oauth_avatar_url,
            'last_login_at': r.last_login_at, 'last_login_ip': r.last_login_ip,
            'created_at': r.created_at, 'updated_at': r.updated_at,
        } for r in session.query(User).all()]
        try:
            # 清空用户使「首个用户」判定成立（共享进程库；快照在 finally 恢复，
            # 不影响同库其他用例）
            session.query(UserPermission).delete(synchronize_session=False)
            session.query(UserOAuthBinding).delete(synchronize_session=False)
            session.query(User).delete(synchronize_session=False)
            session.commit()

            _register_encrypted(client, first_name, 'Secret-147!')
            kid, public_pem = _fetch_key(client)
            enc = _encrypt_password(public_pem, 'Secret-147!')
            body = _login(client, username=first_name,
                          password_encrypted=enc,
                          encryption_key_id=kid).json()
            assert body['user']['role_name'] == 'admin', body['user']

            _register_encrypted(client, second_name, 'Secret-147!')
            body = _login(client, username=second_name,
                          password_encrypted=enc,
                          encryption_key_id=kid).json()
            assert body['user']['role_name'] == 'guest', body['user']
        finally:
            session = _gds()
            session.query(User).filter(
                User.username.in_([first_name, second_name])
            ).delete(synchronize_session=False)
            for row in snapshot:
                session.add(User(**row))
            session.commit()
