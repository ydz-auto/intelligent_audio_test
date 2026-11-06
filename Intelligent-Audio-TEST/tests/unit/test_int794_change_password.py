# -*- coding: utf-8 -*-
"""INT-794 自助改密端点（方案 A）自测。

覆盖两层（对照卡面验收标准）：
- auth_service servicer 层（真实 SQLAlchemy/SQLite + 真实 bcrypt，模式对齐
  test_auth_servicer_sqlite_e2e）：原密码校验成功/失败、用户不存在、
  OAuth 无本地密码用户、审计事件 AUTH_PASSWORD_CHANGED、改密后旧密码失效；
- api_gateway HTTP 层（真实 FastAPI 路由 + 真实 AuthMiddleware + 真实
  AuthServicer 代理注入，对齐 test_g3_auth_http_e2e / test_int147_auth_alignment）：
  注册→登录→RSA 加密改密全流程、原密码错误 401+code:106、新密码长度不足
  400、缺密文 400、未登录 401、改密后新密码可登录。

验收标准对应：
- 端点存在且鉴权为「当前登录用户本人」（非 admin 管他人）→ HTTP 层用
  JWT 注入 user_id，不走 user:update；
- 当前密码错误 401 / 长度不足 400 → HTTP 层断言；
- 校验原密码 → 更新密码 → 返回统一信封 → servicer + HTTP 层断言；
- 不破坏既有登录/鉴权链路 → 改密后新密码登录成功 + 既有 /auth/me 仍可用。
"""
import json
import os
import tempfile
import threading
import time
import uuid

import httpx
import pytest

os.environ.setdefault('DATABASE_URL',
                      'sqlite:///' + tempfile.mkdtemp(prefix='int794_')
                      + '/auth.db')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from sqlalchemy import BigInteger
from sqlalchemy.ext.compiler import compiles

from shared.models.database import init_db, get_db_session, get_engine, remove_db_session

from api_gateway.utils.error_codes import ErrorCode

_RUN = uuid.uuid4().hex[:8]

# 本模块固定名夹具（共享库 DATABASE_URL 已显式设置时 setdefault 失效）：
# teardown 按名清残留，用户名带 run tag 避免跨复跑撞历史数据。
# 注意 servicer 层与 HTTP 层共用同一 SQLite 库，用户名前缀须互不重叠。
_PURGE_USERS = [
    # servicer 层
    f'chpw_ok_{_RUN}', f'chpw_wrong_{_RUN}', f'chpw_missing_{_RUN}',
    f'chpw_oauth_{_RUN}',
    # HTTP 层
    f'chpw_http_ok_{_RUN}', f'chpw_http_wrong_{_RUN}',
    f'chpw_http_short_{_RUN}', f'chpw_http_cipher_{_RUN}',
    f'chpw_http_plain_{_RUN}',
]


@compiles(BigInteger, 'sqlite')
def _render_bigint_as_integer_sqlite(type_, compiler, **kw):
    """SQLite 不支持 BigInteger 主键自增，建表时渲染为 INTEGER。"""
    return 'INTEGER'


@pytest.fixture(scope='module', autouse=True)
def _purge_int794_fixtures():
    """模块 teardown 清固定名夹具：共享库下不留测试残留（INT-185 纪律）。"""
    yield
    from auth_service.infrastructure.persistence.models import User
    session = get_db_session()
    try:
        session.query(User).filter(User.username.in_(_PURGE_USERS)).delete(
            synchronize_session=False)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        remove_db_session()


@pytest.fixture(scope='module')
def svc():
    """真实 AuthServicer + 真实 SQLite 库（auth 相关表）。"""
    init_db(pool_size=3)
    # INT-55 夹具自证：文件型 sqlite（gRPC 线程跨线程共享表，
    # :memory: 下每 engine 独立空库必报 no such table）
    engine = get_engine()
    assert ':memory:' not in str(engine.url), \
        f'INT-794 需要文件型 sqlite（跨线程共享表），实际绑定 {engine.url}'
    remove_db_session()  # 清先序模块残留的主线程 session，建表与请求同库
    from shared.models.database import Base
    from auth_service.infrastructure.persistence.models import (
        Role, Permission, RolePermission, UserPermission, User,
    )
    Base.metadata.create_all(
        bind=engine,
        tables=[Role.__table__, Permission.__table__,
                RolePermission.__table__, UserPermission.__table__,
                User.__table__],
    )
    from auth_service.interfaces.grpc.servicers import AuthServicer
    servicer = AuthServicer()
    yield servicer
    remove_db_session()


@pytest.fixture(scope='module', autouse=True)
def seeded(svc):
    """RBAC 种子：guest（注册默认角色）/ admin（模块自动生效，servicer 与 HTTP 层共用）。"""
    session = get_db_session()
    from auth_service.infrastructure.persistence.models import Role
    if session.query(Role).filter(Role.name == 'guest').count() == 0:
        session.add(Role(name='guest', description='注册默认角色'))
    if session.query(Role).filter(Role.name == 'admin').count() == 0:
        session.add(Role(name='admin', description='验收管理员角色'))
    session.commit()
    return True


@pytest.fixture(scope='module')
def rsa_key_path(tmp_path_factory):
    """RSA 私钥写入模块级临时目录（不落仓库 data/）。"""
    return str(tmp_path_factory.mktemp('int794_rsa') / 'auth_key.pem')


@pytest.fixture(scope='module')
def client(seeded, svc, rsa_key_path):
    """最小网关应用：真实路由 + 真实中间件；gRPC 代理直连真实 servicer。"""
    from api_gateway.config.config import Config
    mp = pytest.MonkeyPatch()
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

    app = FastAPI()
    app.add_middleware(RequestAdapterMiddleware)
    app.add_middleware(AuthMiddleware, auth_mode='dev')
    app.include_router(auth_router, prefix='/api/v1/auth')
    app.include_router(user_router, prefix='/api/v1/auth')

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
    assert server.started, 'INT-794 最小网关应用 uvicorn 启动失败'
    host, port = server.servers[0].sockets[0].getsockname()[:2]
    yield httpx.Client(base_url=f'http://{host}:{port}',
                       trust_env=False, follow_redirects=False,
                       timeout=15)
    server.should_exit = True
    thread.join(timeout=5)
    mp.undo()


# ---- 辅助 ----

def _fetch_key(client):
    resp = client.get('/api/v1/auth/login/encryption-key')
    assert resp.status_code == 200, resp.text
    body = resp.json()
    if not body.get('enabled'):
        return None, None  # 加密开关关闭（回退明文）
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


def _register(client, username, password='pass123456'):
    """注册：加密开启时携 RSA 密文，关闭时回退明文（双模式 helper）。"""
    kid, public_pem = _fetch_key(client)
    payload = {'username': username, 'password': password,
               'email': f'{username}@example.com'}
    if kid:
        payload['password_encrypted'] = _encrypt_password(public_pem, password)
        payload['encryption_key_id'] = kid
    resp = client.post('/api/v1/auth/register', json=payload)
    assert resp.status_code == 201, resp.text
    return username


def _login(client, username, password='pass123456'):
    """登录：加密开启时携 RSA 密文，关闭时回退明文（双模式 helper）。"""
    kid, public_pem = _fetch_key(client)
    data = {'username': username, 'password': password}
    if kid:
        data['password_encrypted'] = _encrypt_password(public_pem, password)
        data['encryption_key_id'] = kid
    resp = client.post('/api/v1/auth/login', data=data)
    assert resp.status_code == 200, resp.text
    return {'Authorization': f'Bearer {resp.json()["access_token"]}'}


def _change_password(client, headers, current, new, kid, public_pem):
    """携 RSA 密文调自助改密端点。"""
    return client.post('/api/v1/auth/change-password', headers=headers, json={
        'current_password_encrypted': _encrypt_password(public_pem, current),
        'new_password_encrypted': _encrypt_password(public_pem, new),
        'encryption_key_id': kid,
    })


# ===== auth_service servicer 层 =====

class TestChangePasswordServicer:
    """servicer 层：原密码校验 → 更新哈希 → 审计；不破坏登录链路。"""

    @staticmethod
    def _create_user(svc, username, password):
        from shared.proto import auth_service_pb2 as auth_pb
        resp = svc.CreateUser(auth_pb.CreateUserRequest(
            username=username, email=f'{username}@example.com',
            password=password, role_name='guest'))
        assert resp.success, resp.message
        return json.loads(resp.data)['user_id']

    def test_change_password_success_and_relogin(self, svc):
        """改密成功后旧密码失效、新密码可登录（LoginWithPassword 验证）。"""
        from shared.proto import auth_service_pb2 as auth_pb
        user_id = self._create_user(svc, f'chpw_ok_{_RUN}', 'Old-Pass-1!')
        resp = svc.ChangePassword(auth_pb.ChangePasswordRequest(
            user_id=user_id, current_password='Old-Pass-1!',
            new_password='New-Pass-2!'))
        assert resp.success, resp.message
        assert json.loads(resp.data) == {}

        # 旧密码登录失败（防枚举语义：失败返回 None，servicer _fail 无 error_code）
        resp = svc.LoginWithPassword(auth_pb.LoginWithPasswordRequest(
            username=f'chpw_ok_{_RUN}', password='Old-Pass-1!'))
        assert resp.success is False, '改密后旧密码仍可登录'
        # 新密码登录成功
        resp = svc.LoginWithPassword(auth_pb.LoginWithPasswordRequest(
            username=f'chpw_ok_{_RUN}', password='New-Pass-2!'))
        assert resp.success, resp.message
        assert json.loads(resp.data)['username'] == f'chpw_ok_{_RUN}'

    def test_change_password_wrong_current_returns_credentials_invalid(self, svc):
        """原密码错误 → AUTH_CREDENTIALS_INVALID（网关映射 401 + code:106）。"""
        from shared.proto import auth_service_pb2 as auth_pb
        user_id = self._create_user(svc, f'chpw_wrong_{_RUN}', 'Real-Pass-1!')
        resp = svc.ChangePassword(auth_pb.ChangePasswordRequest(
            user_id=user_id, current_password='Wrong-Pass-X',
            new_password='New-Pass-2!'))
        assert resp.success is False
        assert json.loads(resp.data) == {'error_code': 'AUTH_CREDENTIALS_INVALID'}
        # 密码未被改写
        resp = svc.LoginWithPassword(auth_pb.LoginWithPasswordRequest(
            username=f'chpw_wrong_{_RUN}', password='Real-Pass-1!'))
        assert resp.success, '原密码错误场景下不应改写密码'

    def test_change_password_user_not_found(self, svc):
        """用户不存在 → USER_NOT_FOUND。"""
        from shared.proto import auth_service_pb2 as auth_pb
        resp = svc.ChangePassword(auth_pb.ChangePasswordRequest(
            user_id=999999, current_password='X', new_password='Y'))
        assert resp.success is False
        assert json.loads(resp.data) == {'error_code': 'USER_NOT_FOUND'}

    def test_change_password_oauth_user_no_password(self, svc):
        """无本地密码（OAuth 用户）→ AUTH_CREDENTIALS_INVALID（同防枚举语义）。"""
        from shared.proto import auth_service_pb2 as auth_pb
        resp = svc.CreateUser(auth_pb.CreateUserRequest(
            username=f'chpw_oauth_{_RUN}', email=f'chpw_oauth_{_RUN}@example.com',
            oauth_provider='huawei', oauth_subject='ext-794',
            role_name='guest'))
        assert resp.success, resp.message
        user_id = json.loads(resp.data)['user_id']
        resp = svc.ChangePassword(auth_pb.ChangePasswordRequest(
            user_id=user_id, current_password='anything',
            new_password='New-Pass-2!'))
        assert resp.success is False
        assert json.loads(resp.data) == {'error_code': 'AUTH_CREDENTIALS_INVALID'}

    def test_change_password_emits_password_changed_audit(self, svc, monkeypatch):
        """成功改密落 AUTH_PASSWORD_CHANGED 审计（handler 层捕获，旁路）。"""
        import auth_service.application.handlers.auth_handlers as ah
        captured = []

        def _capture(event, module, content):
            captured.append({'event': event, 'module': module, 'content': content})

        monkeypatch.setattr(ah, 'write_auth_audit', _capture)
        from shared.proto import auth_service_pb2 as auth_pb
        user_id = self._create_user(svc, f'chpw_missing_{_RUN}', 'Old-Pass-1!')
        resp = svc.ChangePassword(auth_pb.ChangePasswordRequest(
            user_id=user_id, current_password='Old-Pass-1!',
            new_password='New-Pass-2!'))
        assert resp.success, resp.message
        assert captured, 'ChangePassword 未触发审计'
        password_events = [
            c for c in captured if c['event'].value == 'AUTH_PASSWORD_CHANGED']
        assert password_events, (
            f'未捕获 AUTH_PASSWORD_CHANGED（实际: '
            f'{[(c["event"].value, c["module"]) for c in captured]}）')
        content = password_events[0]['content']
        assert content['operator_id'] == user_id
        assert content['target_id'] == user_id
        assert content['delta']['password_changed'] is True


# ===== api_gateway HTTP 层 =====

class TestChangePasswordHttp:
    """HTTP 层：端点存在、鉴权当前用户本人、错误语义、RSA 密文、统一信封。"""

    def test_change_password_full_flow(self, client, seeded):
        """注册→登录→RSA 改密→200+notice→旧密码登录失败→新密码登录成功。"""
        username = _register(client, f'chpw_http_ok_{_RUN}', 'Old-Pass-1!')
        headers = _login(client, username, 'Old-Pass-1!')
        kid, public_pem = _fetch_key(client)

        resp = _change_password(client, headers, 'Old-Pass-1!', 'New-Pass-2!',
                                kid, public_pem)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body['message'] == '密码修改成功，请重新登录'
        assert 'notice' in body and '重新登录' in body['notice']

        # 旧密码登录失败
        resp = client.post('/api/v1/auth/login',
                           data={'username': username, 'password': 'Old-Pass-1!'})
        assert resp.status_code == 401
        # 新密码登录成功
        headers_new = _login(client, username, 'New-Pass-2!')
        resp = client.get('/api/v1/auth/me', headers=headers_new)
        assert resp.status_code == 200, resp.text
        assert resp.json()['username'] == username

    def test_change_password_wrong_current_401_code106(self, client, seeded):
        """原密码错误 → 401 + code:106 AUTH_CREDENTIALS_INVALID。"""
        username = _register(client, f'chpw_http_wrong_{_RUN}', 'Real-Pass-1!')
        headers = _login(client, username, 'Real-Pass-1!')
        kid, public_pem = _fetch_key(client)

        resp = _change_password(client, headers, 'Wrong-Pass-X', 'New-Pass-2!',
                                kid, public_pem)
        assert resp.status_code == 401, resp.text
        body = resp.json()
        assert body['code'] == ErrorCode.AUTH_CREDENTIALS_INVALID
        # 密码未被改写
        assert _login(client, username, 'Real-Pass-1!').get('Authorization')

    def test_change_password_short_new_password_400(self, client, seeded):
        """新密码长度不足（<AUTH_PASSWORD_MIN_LENGTH 默认 6）→ 400。"""
        from api_gateway.application.services.auth.user_management_service import (
            AUTH_PASSWORD_MIN_LENGTH, REGISTER_ERR_PASSWORD_TOO_SHORT,
        )
        username = _register(client, f'chpw_http_short_{_RUN}', 'Old-Pass-1!')
        headers = _login(client, username, 'Old-Pass-1!')
        kid, public_pem = _fetch_key(client)

        resp = _change_password(client, headers, 'Old-Pass-1!',
                                'x' * (AUTH_PASSWORD_MIN_LENGTH - 1),
                                kid, public_pem)
        assert resp.status_code == 400, resp.text
        assert resp.json()['message'] == REGISTER_ERR_PASSWORD_TOO_SHORT
        # 边界：恰好 min 长度通过
        resp = _change_password(client, headers, 'Old-Pass-1!',
                                'x' * AUTH_PASSWORD_MIN_LENGTH, kid, public_pem)
        assert resp.status_code == 200, resp.text

    def test_change_password_missing_ciphertext_400(self, client, seeded):
        """加密开启时缺密文（逐字段点名）→ 400。"""
        from api_gateway.application.services.auth.user_management_service import (
            CHANGE_PASSWORD_ERR_MISSING_CIPHERTEXT,
        )
        username = _register(client, f'chpw_http_cipher_{_RUN}', 'Old-Pass-1!')
        headers = _login(client, username, 'Old-Pass-1!')
        kid, public_pem = _fetch_key(client)

        resp = client.post('/api/v1/auth/change-password', headers=headers, json={
            'new_password_encrypted': _encrypt_password(public_pem, 'New-Pass-2!'),
            'encryption_key_id': kid,
        })
        assert resp.status_code == 400, resp.text
        assert resp.json()['message'] == CHANGE_PASSWORD_ERR_MISSING_CIPHERTEXT.format(
            fields='current_password_encrypted')

    def test_change_password_no_auth_401(self, client, seeded):
        """未登录（无 Bearer）→ 401（dev 模式 AuthMiddleware 拦截）。"""
        kid, public_pem = _fetch_key(client)
        resp = _change_password(client, {}, 'Old-Pass-1!', 'New-Pass-2!',
                                kid, public_pem)
        assert resp.status_code == 401, resp.text

    def test_change_password_plaintext_fallback(self, client, seeded,
                                                monkeypatch):
        """加密开关关闭时回退明文 current_password/new_password。"""
        from api_gateway.config.config import Config
        monkeypatch.setattr(Config, 'AUTH_PASSWORD_ENCRYPTION_ENABLED', False)
        username = _register(client, f'chpw_http_plain_{_RUN}', 'Old-Pass-1!')
        headers = _login(client, username, 'Old-Pass-1!')

        resp = client.post('/api/v1/auth/change-password', headers=headers, json={
            'current_password': 'Old-Pass-1!',
            'new_password': 'New-Pass-2!',
        })
        assert resp.status_code == 200, resp.text
        # 新密码可登录
        assert _login(client, username, 'New-Pass-2!').get('Authorization')
