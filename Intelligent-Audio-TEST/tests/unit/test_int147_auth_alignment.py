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

from api_gateway.utils.error_codes import ErrorCode


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


@pytest.fixture(scope='module', autouse=True)
def _purge_oauth_fixtures():
    """模块 teardown 按 run tag 清夹具：共享库（DATABASE_URL 已显式设置
    时 setdefault 失效）下不留验收残留（INT-179）。"""
    yield
    from tests.unit.oauth_fixture_cleanup import purge_oauth_test_fixtures
    purge_oauth_test_fixtures(_RUN)


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
    """RSA 加密密码注册（复用服务端下发的公钥）。

    INT-285：注册邮箱必填，email 缺省时按 run tag 派生（网关 400 校验）。
    """
    kid, public_pem = _fetch_key(client)
    body = {'username': username,
            'password_encrypted': _encrypt_password(public_pem, password),
            'encryption_key_id': kid,
            'email': email or f'{username}@example.com'}
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


def _oauth_token_from_redirect(location: str) -> str:
    """从回调成功跳转 {base}/#/login?oauth_token=... 提取 JWT。

    注意 query 位于 # fragment 内（前端路由），urlparse().query 取不到。
    """
    from urllib.parse import parse_qs, urlparse
    fragment = urlparse(location).fragment
    qs = fragment.split('?', 1)[1] if '?' in fragment else ''
    return parse_qs(qs)['oauth_token'][0]


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
        body = resp.json()
        # INT-188：加密载荷无效与凭证错误 401 语义区分（引导刷新，非
        # 「用户名或密码错误」误导文案）；仍为 401 保持防枚举基线
        assert body['detail'] == '登录加密校验失败，请刷新页面重试'
        assert body['code'] == ErrorCode.AUTH_ENCRYPTION_INVALID
        tampered = good[:-4] + ('AAAA' if good[-4:] != 'AAAA' else 'BBBB')
        resp = _login(client, username=username,
                      password_encrypted=tampered,
                      encryption_key_id=_fetch_key(client)[0])
        assert resp.status_code == 401

    def test_login_401_semantics_distinguished(self, client):
        """INT-188：加密载荷无效 vs 凭证错误 401 以 code 区分语义。

        - 密文合法但密码错 → AUTH_CREDENTIALS_INVALID「用户名或密码错误」
        - 明文提交（旧缓存包/明文回退请求）→ 落入加密载荷无效分支
          AUTH_ENCRYPTION_INVALID「请刷新页面重试」
        """
        username = f'int188_semantic_{_RUN}'
        _register_encrypted(client, username, 'Secret-147!')
        kid, public_pem = _fetch_key(client)
        resp = _login(client, username=username,
                      password_encrypted=_encrypt_password(public_pem,
                                                           'Wrong-188!'),
                      encryption_key_id=kid)
        assert resp.status_code == 401
        body = resp.json()
        assert body['code'] == ErrorCode.AUTH_CREDENTIALS_INVALID
        assert body['detail'] == '用户名或密码错误'
        # 明文字段在加密开启时同样落入加密载荷无效分支
        resp = _login(client, username=username, password='Secret-147!')
        assert resp.status_code == 401
        body = resp.json()
        assert body['code'] == ErrorCode.AUTH_ENCRYPTION_INVALID
        assert '刷新' in body['detail']

    def test_encryption_disabled_falls_back_to_plaintext(self, client):
        from api_gateway.config.config import Config
        username = f'int147_plain_{_RUN}'
        mp = pytest.MonkeyPatch()
        mp.setattr(Config, 'AUTH_PASSWORD_ENCRYPTION_ENABLED', False)
        try:
            resp = client.get('/api/v1/auth/login/encryption-key')
            assert resp.status_code == 200
            assert resp.json() == {'enabled': False}
            # 明文注册 + 明文登录（开关关闭语义；INT-285 邮箱必填同适用）
            resp = client.post('/api/v1/auth/register',
                               json={'username': username,
                                     'password': 'Secret-147!',
                                     'email': f'{username}@example.com'})
            assert resp.status_code == 201, resp.text
            resp = _login(client, username=username, password='Secret-147!')
            assert resp.status_code == 200, resp.text
        finally:
            mp.undo()


# ---- 审计 P3：公钥端点异常不回传 str(e) ----

class TestEncryptionKeyErrorMasking:

    def test_key_load_failure_returns_fixed_message(self, client):
        """密钥路径不可加载 → 500 固定文案，异常细节只进日志。"""
        from api_gateway.config.config import Config
        # 以同名目录占位密钥文件路径，使加载必败（open(dir) 必抛）
        block_dir = os.path.join(
            tempfile.mkdtemp(prefix='int147_keyblk_'), 'auth_key.pem')
        os.makedirs(block_dir)
        mp = pytest.MonkeyPatch()
        mp.setattr(Config, 'AUTH_RSA_KEY_PATH', block_dir)
        try:
            resp = client.get('/api/v1/auth/login/encryption-key')
            assert resp.status_code == 500
            assert resp.json() == {'detail': '登录加密公钥不可用'}
        finally:
            mp.undo()


# ---- INT-186：注册缺密文字段 400 文案按实际缺失字段区分 ----

class TestRegisterErrorMessages:
    """加密开启时注册缺密文字段的错误语义（INT-186）。

    旧行为回「请输入用户名、邮箱和密码」，username/email/password 实际
    都已填写，缺的是 RSA 密文字段，排障误导；修复后逐字段点名密文缺失，
    明文模式原有文案不回退（INT-156：明文提交仍拒绝，无明文回退）。
    夹具用户名带模块级 run tag，模块 teardown 统一清理（不落共享库）。
    """

    def test_missing_ciphertext_names_fields_not_basic(self, client):
        """加密开启 + 仅明文 password（无密文字段）→ 400 密文缺失文案，
        指向 password_encrypted/encryption_key_id，不再误导用户名/邮箱/密码。"""
        from api_gateway.application.services.auth.user_management_service import (
            REGISTER_ERR_MISSING_CIPHERTEXT,
        )
        resp = client.post('/api/v1/auth/register', json={
            'username': f'int186_enc_{_RUN}',
            'email': f'int186_enc_{_RUN}@example.com',
            'password': 'Secret-186!'})
        assert resp.status_code == 400, resp.text
        body = resp.json()
        assert body['message'] == REGISTER_ERR_MISSING_CIPHERTEXT.format(
            fields='password_encrypted、encryption_key_id')
        assert body['code'] == ErrorCode.INVALID_PARAMS
        assert '请输入用户名' not in body['message']

    def test_missing_key_id_only_names_key_id(self, client):
        """仅缺 encryption_key_id（密文已在）→ 文案逐字段只点名 key id。"""
        _, public_pem = _fetch_key(client)
        from api_gateway.application.services.auth.user_management_service import (
            REGISTER_ERR_MISSING_CIPHERTEXT,
        )
        resp = client.post('/api/v1/auth/register', json={
            'username': f'int186_kid_{_RUN}',
            'password_encrypted': _encrypt_password(public_pem,
                                                    'Secret-186!')})
        assert resp.status_code == 400, resp.text
        assert resp.json()['message'] == REGISTER_ERR_MISSING_CIPHERTEXT.format(
            fields='encryption_key_id')

    def test_missing_ciphertext_only_names_ciphertext(self, client):
        """仅缺 password_encrypted（key id 已在）→ 文案逐字段只点名密文。"""
        from api_gateway.application.services.auth.user_management_service import (
            REGISTER_ERR_MISSING_CIPHERTEXT,
        )
        resp = client.post('/api/v1/auth/register', json={
            'username': f'int186_ct_{_RUN}',
            'encryption_key_id': 'x' * 32})
        assert resp.status_code == 400, resp.text
        assert resp.json()['message'] == REGISTER_ERR_MISSING_CIPHERTEXT.format(
            fields='password_encrypted')

    def test_missing_username_with_valid_ciphertext(self, client):
        """加密开启 + 缺 username（密文合法）→ 基础必填文案，非密文文案。"""
        from api_gateway.application.services.auth.user_management_service import (
            REGISTER_ERR_MISSING_BASIC_FIELDS,
        )
        kid, public_pem = _fetch_key(client)
        resp = client.post('/api/v1/auth/register', json={
            'password_encrypted': _encrypt_password(public_pem, 'Secret-186!'),
            'encryption_key_id': kid})
        assert resp.status_code == 400, resp.text
        assert resp.json()['message'] == REGISTER_ERR_MISSING_BASIC_FIELDS

    def test_plaintext_mode_missing_fields_keeps_original_message(self, client):
        """明文模式（开关关闭）缺字段 → 原有文案不回退（验收 AC3）。"""
        from api_gateway.application.services.auth.user_management_service import (
            REGISTER_ERR_MISSING_BASIC_FIELDS,
        )
        from api_gateway.config.config import Config
        mp = pytest.MonkeyPatch()
        mp.setattr(Config, 'AUTH_PASSWORD_ENCRYPTION_ENABLED', False)
        try:
            resp = client.post('/api/v1/auth/register',
                               json={'username': f'int186_plain_{_RUN}'})
            assert resp.status_code == 400, resp.text
            assert resp.json()['message'] == REGISTER_ERR_MISSING_BASIC_FIELDS
        finally:
            mp.undo()

    def test_plaintext_password_still_rejected_when_encryption_on(self, client):
        """INT-156 语义不回退：加密开启时明文 password 不被接受（AC4）。"""
        resp = client.post('/api/v1/auth/register', json={
            'username': f'int156_plain_{_RUN}',
            'password': 'Secret-186!'})
        assert resp.status_code == 400, resp.text
        assert 'password_encrypted' in resp.json()['message']

    def test_encrypted_register_happy_path_unchanged(self, client):
        """修复不动注册流程：密文齐全仍 201 注册成功（对照基线）。"""
        _register_encrypted(client, f'int186_ok_{_RUN}', 'Secret-186!')


# ---- AC2：第三方账号绑定 ----

@pytest.fixture(scope='module')
def binding_env(client):
    """admin token + 提供方 + 两个已注册用户 + 绑定票据。"""
    run = _RUN  # 复用模块级 tag：模块 teardown 按 _RUN 清夹具（INT-179）
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
    slug = f'int147-bind-{run}'
    ticket = OAuthProviderService.sign_bind_ticket(
        provider_id=provider_id, slug=slug,
        provider_user_id='ext-user-147', display_name='绑定验收')
    return {
        'admin_headers': admin_headers,
        'user1_headers': {'Authorization': _token_for(user1_id, username1)},
        'user2_headers': {'Authorization': _token_for(user2_id, username2)},
        'provider_id': provider_id,
        'slug': slug,
        'ticket': ticket,
        'username1': username1,
        'username2': username2,
        'user1_id': user1_id,
        'user2_id': user2_id,
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


# ---- 审计 P1：绑定身份参与 OAuth 登录（绑定→登出→OAuth 登录回原账号）----

class TestOAuthLoginRespectsBinding:
    """绑定过的第三方身份 OAuth 登录必须命中原账号（INT-147 审计 P1）。

    回归锁定：修复前 GetUserByOAuth 只查 users.oauth 字段，绑定表不参与
    登录 → 第三方登录稳定建孤儿号、占用身份后自锁绑定。
    """

    def test_bound_identity_logs_back_into_original_account(
            self, client, binding_env, monkeypatch):
        from api_gateway.application.services.auth.oauth_provider_service import (
            OAuthProviderService,
        )
        from api_gateway.application.services.auth.token_service import (
            TokenService,
        )
        from api_gateway.domain.value_objects.auth_value_objects import UserInfo

        # 前序解绑用例已移除绑定：重新绑定（bind 幂等，票据仍有效）
        resp = client.post('/api/v1/auth/oauth/bindings',
                           headers=binding_env['user1_headers'],
                           json={'bind_ticket': binding_env['ticket']})
        assert resp.status_code == 200, resp.text

        slug = binding_env['slug']

        def _fake_handle_callback(s, code, state, redirect_uri):
            # 打桩免真实 IdP 往返；回传第三方身份 = 绑定身份 ext-user-147
            assert s == slug
            return UserInfo(username=binding_env['username1'],
                            external_id='ext-user-147')

        monkeypatch.setattr(OAuthProviderService, 'handle_callback',
                            _fake_handle_callback)
        # 「登出后」= 无登录态直调 IdP 回调（/oauth 前缀在免认证白名单内）
        resp = client.get(
            f'/api/v1/auth/oauth/{slug}/callback',
            params={'code': 'auth-code-x',
                    'state': OAuthProviderService._sign_state(slug)},
            follow_redirects=False)
        assert resp.status_code in (302, 307), resp.text
        location = resp.headers['location']
        assert 'oauth_error' not in location, location
        payload = TokenService.verify(_oauth_token_from_redirect(location))
        assert payload['user_id'] == binding_env['user1_id']
        assert payload['username'] == binding_env['username1']

    def test_unbound_identity_still_creates_own_account(
            self, client, binding_env, monkeypatch):
        """对照：未绑定身份走原路径（自定义提供方不合并、建独立账号）。"""
        from api_gateway.application.services.auth.oauth_provider_service import (
            OAuthProviderService,
        )
        from api_gateway.domain.value_objects.auth_value_objects import UserInfo

        slug = binding_env['slug']
        fresh_name = f"fresh-idp-{uuid.uuid4().hex[:8]}"

        def _fake_handle_callback(s, code, state, redirect_uri):
            return UserInfo(username=fresh_name,
                            external_id='ext-brand-new')

        monkeypatch.setattr(OAuthProviderService, 'handle_callback',
                            _fake_handle_callback)
        try:
            resp = client.get(
                f'/api/v1/auth/oauth/{slug}/callback',
                params={'code': 'auth-code-y',
                        'state': OAuthProviderService._sign_state(slug)},
                follow_redirects=False)
            assert resp.status_code in (302, 307), resp.text
            assert 'oauth_error' not in resp.headers['location'], \
                resp.headers['location']
            from shared.models.database import get_db_session
            from auth_service.infrastructure.persistence.models import User
            session = get_db_session()
            po = session.query(User).filter_by(oauth_id='ext-brand-new').first()
            assert po is not None, '未绑定身份应新建独立账号'
            assert po.oauth_provider == slug
            assert po.username.startswith(fresh_name)
        finally:
            session = get_db_session()
            session.query(User).filter_by(oauth_id='ext-brand-new').delete(
                synchronize_session=False)
            session.commit()


class TestOAuthLookupServicerSemantics:
    """servicer 直驱：绑定命中/字段回退语义与数据不一致收口。"""

    def test_oauth_field_user_without_binding_still_found(self, svc):
        """未绑定身份：users.oauth 字段查找保持可用（huawei 存量兼容）。"""
        from shared.proto import auth_service_pb2 as auth_pb
        from shared.utils.grpc_json import loads as grpc_loads
        from shared.models.database import get_db_session
        from auth_service.infrastructure.persistence.models import User
        session = get_db_session()
        marker = uuid.uuid4().hex[:8]
        po = User(username=f'int147_legacy_{marker}', role_id=1,
                  status='active', oauth_provider='huawei',
                  oauth_id=f'legacy-ext-{marker}')
        session.add(po)
        session.commit()
        try:
            resp = svc.GetUserByOAuth(auth_pb.GetUserByOAuthRequest(
                provider='huawei', subject=f'legacy-ext-{marker}'))
            assert resp.success, resp.message
            data = grpc_loads(resp.data, {}) or {}
            assert data['username'] == f'int147_legacy_{marker}'
        finally:
            session.query(User).filter_by(id=po.id).delete(
                synchronize_session=False)
            session.commit()

    def test_dangling_binding_rejected_not_silently_orphaned(self, svc):
        """绑定行存在而用户缺失 → 显式失败（不得放行使网关另建孤儿号）。"""
        from shared.proto import auth_service_pb2 as auth_pb
        from shared.models.database import get_db_session
        from auth_service.infrastructure.persistence.models import (
            CustomOAuthProvider, UserOAuthBinding,
        )
        session = get_db_session()
        marker = uuid.uuid4().hex[:8]
        prov = CustomOAuthProvider(
            name=f'ghost-{marker}', slug=f'ghost-{marker}',
            client_id='cid', client_secret='sec',
            authorize_url='https://x/authorize',
            token_url='https://x/token',
            userinfo_url='https://x/userinfo', enabled=True)
        session.add(prov)
        session.flush()
        binding = UserOAuthBinding(user_id=2147483000,
                                   provider_id=prov.id,
                                   provider_user_id='ghost-subject')
        session.add(binding)
        session.commit()
        try:
            resp = svc.GetUserByOAuth(auth_pb.GetUserByOAuthRequest(
                provider=f'ghost-{marker}', subject='ghost-subject'))
            assert not resp.success
            assert '绑定用户不存在' in resp.message
        finally:
            session.query(UserOAuthBinding).filter_by(id=binding.id).delete(
                synchronize_session=False)
            session.query(CustomOAuthProvider).filter_by(id=prov.id).delete(
                synchronize_session=False)
            session.commit()
