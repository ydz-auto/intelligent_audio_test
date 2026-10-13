# -*- coding: utf-8 -*-
"""auth_service HTTP 管理面写命令事务边界回归（INT-315）。

缺陷背景：仓储层按约定只 flush，事务边界在 interfaces 层——gRPC servicer
写命令成功后显式 _commit()，而 HTTP 路由层此前无任何 commit，写命令返回
success:true + user_id 但 flush 拿到的自增 ID 随请求级 session 销毁回滚
（幻影用户）。本文件用真实 FastAPI 路由 + 真实仓储（文件型 SQLite）锁死：

- HTTP register → 同进程直接查 DB 可见（缺陷主回归，TestClient 每请求
  独立线程，等价生产 :5009 直连的请求作用域销毁路径）
- grant/revoke 权限真实落 user_permissions 表且请求结束后行仍在
- 软删除请求结束后 status='deleted' 持久
- 失败路径 rollback：重复用户名 400 且首个用户仍独存（无半写状态）
- AuthDomainError → HTTP 状态码映射（404 USER_NOT_FOUND / 403 SELF_OPERATION_FORBIDDEN）
- 读命令不受影响（GET /users 回写成功用户）

既有 test_auth_servicer_sqlite_e2e 走 gRPC servicer（同进程线程级 session），
覆盖不到「HTTP 请求作用域销毁后提交是否落库」这一路径，故补本文件。
"""
import os
import tempfile
import uuid

import pytest

os.environ.setdefault('DATABASE_URL',
                      'sqlite:///' + tempfile.mkdtemp(prefix='int315_')
                      + '/auth.db')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from sqlalchemy import BigInteger
from sqlalchemy.ext.compiler import compiles

from shared.models.database import (
    get_db_session, get_engine, init_db, remove_db_session,
)

from auth_service.infrastructure.persistence.models import (
    Permission, Role, RolePermission, User, UserPermission,
)

_RUN_TAG = 'int315_' + uuid.uuid4().hex[:8]


@compiles(BigInteger, 'sqlite')
def _render_bigint_as_integer_sqlite(type_, compiler, **kw):
    """SQLite 不支持 BigInteger 主键自增，建表时渲染为 INTEGER。"""
    return 'INTEGER'


@pytest.fixture(scope='module')
def client():
    """真实 auth HTTP 路由 + 文件型 SQLite（users/roles/permissions 等表）。

    TestClient 每请求经 anyio 线程池执行 sync 路由：请求作用域 session 随
    响应结束销毁，写命令若不 commit 即产生与本缺陷相同的幻影行——测试自证
    与生产 :5009 直连同路径。
    """
    init_db(pool_size=3)
    engine = get_engine()
    assert ':memory:' not in str(engine.url), \
        f'INT-315 回归需要文件型 sqlite（跨线程共享表），实际绑定 {engine.url}'
    remove_db_session()  # 清先序模块残留的主线程 session，保证建表与请求同库
    from shared.models.database import Base
    Base.metadata.create_all(
        bind=engine,
        tables=[Role.__table__, Permission.__table__,
                RolePermission.__table__, UserPermission.__table__,
                User.__table__],
    )
    # guest 角色（注册默认角色解析需存在；resolve 不到也不阻断——role_id=None）
    session = get_db_session()
    if session.query(Role).filter(Role.name == 'guest').count() == 0:
        session.add(Role(name='guest', description='注册默认角色'))
    session.commit()
    remove_db_session()

    from fastapi import FastAPI
    from auth_service.interfaces.api.routes import router
    app = FastAPI()
    app.include_router(router)
    from fastapi.testclient import TestClient
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    remove_db_session()


@pytest.fixture(scope='module', autouse=True)
def _purge_int315_fixtures():
    """模块 teardown 按 run tag 清夹具：显式 DATABASE_URL（共享库）下不留残留。"""
    yield
    from sqlalchemy import inspect
    session = get_db_session()
    try:
        present = set(inspect(session.get_bind()).get_table_names())
        usernames = [f'{_RUN_TAG}_u1', f'{_RUN_TAG}_u2', f'{_RUN_TAG}_dup']
        user_ids = [r[0] for r in session.query(User.id).filter(
            User.username.in_(usernames)).all()]
        if user_ids and 'user_permissions' in present:
            session.query(UserPermission).filter(
                UserPermission.user_id.in_(user_ids)).delete(
                synchronize_session=False)
        if user_ids:
            session.query(User).filter(User.id.in_(user_ids)).delete(
                synchronize_session=False)
        if 'permissions' in present:
            session.query(Permission).filter(
                Permission.name == f'{_RUN_TAG}_perm').delete(
                synchronize_session=False)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        remove_db_session()


def _seed_permission(code):
    """按名幂等补种权限点（grant 用例依赖），返回权限码。"""
    session = get_db_session()
    if session.query(Permission).filter_by(name=code).first() is None:
        session.add(Permission(name=code, description='INT-315 夹具'))
        session.commit()
    return code


class TestHttpRegisterPersists:
    """缺陷主回归：HTTP 写命令请求结束后必须真实落库。"""

    def test_register_user_queryable_after_request(self, client):
        """register 200 → 同进程直查 users 表可见（幻影用户回归）。"""
        username = f'{_RUN_TAG}_u1'
        resp = client.post('/api/auth/register', json={
            'username': username, 'password': 'pass123456',
            'email': f'{username}@example.com',
        })
        assert resp.status_code == 200, resp.text
        user_id = resp.json()['data']['user_id']

        session = get_db_session()
        row = session.query(User).filter_by(id=user_id).first()
        assert row is not None, \
            f'HTTP register 返回 user_id={user_id} 但 users 表零落库（INT-315 幻影用户）'
        assert row.username == username
        assert row.status == 'active'
        assert row.password_hash, '注册密码未哈希落库'

    def test_register_duplicate_rolls_back_first(self, client):
        """重复用户名 400；首个用户仍独存——失败路径 rollback 无半写。"""
        username = f'{_RUN_TAG}_dup'
        resp1 = client.post('/api/auth/register', json={
            'username': username, 'password': 'pass123456',
            'email': f'{username}@example.com',
        })
        assert resp1.status_code == 200, resp1.text
        first_id = resp1.json()['data']['user_id']

        resp2 = client.post('/api/auth/register', json={
            'username': username, 'password': 'pass123456',
            'email': f'{username}@example.com',
        })
        assert resp2.status_code == 400, resp2.text
        assert resp2.json()['detail'] == f'用户名已存在: {username}'

        session = get_db_session()
        rows = session.query(User).filter_by(username=username).all()
        assert len(rows) == 1 and rows[0].id == first_id

    def test_create_user_persists(self, client):
        """POST /users（OAuth 建用户）请求结束后行仍在。"""
        username = f'{_RUN_TAG}_u2'
        resp = client.post('/api/auth/users', json={
            'username': username, 'email': f'{username}@example.com',
            'oauth_provider': 'test', 'oauth_subject': f'{_RUN_TAG}_sub',
        })
        assert resp.status_code == 200, resp.text
        user_id = resp.json()['data']['user_id']
        session = get_db_session()
        row = session.query(User).filter_by(id=user_id).first()
        assert row is not None and row.username == username


class TestHttpPermissionCommandsPersist:
    """权限授予/撤销真实落 user_permissions 表（请求结束后行仍在）。"""

    def test_grant_and_revoke_persist(self, client):
        username = f'{_RUN_TAG}_u1'
        session = get_db_session()
        user = session.query(User).filter_by(username=username).first()
        assert user is not None
        _seed_permission(f'{_RUN_TAG}_perm')

        resp = client.post(f'/api/auth/users/{user.id}/permissions',
                           json={'permission': f'{_RUN_TAG}_perm'})
        assert resp.status_code == 200, resp.text
        row = (
            session.query(UserPermission)
            .filter_by(user_id=user.id)
            .join(Permission, Permission.id == UserPermission.permission_id)
            .filter(Permission.name == f'{_RUN_TAG}_perm')
            .first()
        )
        assert row is not None and row.granted is True, \
            'HTTP 授权返回成功但 user_permissions 零落库（INT-315）'

        resp = client.request('DELETE', f'/api/auth/users/{user.id}/permissions',
                              json={'permission': f'{_RUN_TAG}_perm'})
        assert resp.status_code == 200, resp.text
        remaining = (
            session.query(UserPermission)
            .filter_by(user_id=user.id)
            .join(Permission, Permission.id == UserPermission.permission_id)
            .filter(Permission.name == f'{_RUN_TAG}_perm')
            .count()
        )
        assert remaining == 0, 'HTTP 撤销返回成功但 override 行未删（INT-315）'


class TestHttpStatusAndDeletePersist:
    """状态变更/软删除请求结束后持久。"""

    def test_status_update_persists(self, client):
        username = f'{_RUN_TAG}_u2'
        session = get_db_session()
        user = session.query(User).filter_by(username=username).first()
        assert user is not None

        resp = client.put(f'/api/auth/users/{user.id}/status',
                          json={'status': 'locked'})
        assert resp.status_code == 200, resp.text
        # 主线程 scoped session 与各测试间长活：驱逐 identity map 缓存，
        # 强制从库重读（否则读到的是本 session 早前缓存的旧快照对象）
        session.expire_all()
        row = session.query(User).filter_by(id=user.id).first()
        assert row is not None and row.status == 'locked', \
            'HTTP 状态变更返回成功但未落库（INT-315）'

    def test_soft_delete_persists(self, client):
        username = f'{_RUN_TAG}_u2'
        session = get_db_session()
        user = session.query(User).filter_by(username=username).first()
        assert user is not None

        resp = client.delete(f'/api/auth/users/{user.id}')
        assert resp.status_code == 200, resp.text
        session.expire_all()
        row = session.query(User).filter_by(id=user.id).first()
        assert row is not None and row.status == 'deleted', \
            'HTTP 软删除返回成功但未落库（INT-315）'


class TestHttpErrorMapping:
    """AuthDomainError → HTTP 状态码映射（对齐网关口径）。"""

    def test_update_missing_user_404(self, client):
        resp = client.put('/api/auth/users/999999999/status',
                          json={'status': 'active'})
        assert resp.status_code == 404, resp.text

    def test_grant_unknown_permission_404(self, client):
        username = f'{_RUN_TAG}_u1'
        session = get_db_session()
        user = session.query(User).filter_by(username=username).first()
        resp = client.post(f'/api/auth/users/{user.id}/permissions',
                           json={'permission': f'{_RUN_TAG}_no_such_perm'})
        assert resp.status_code == 404, resp.text

    def test_grant_wildcard_400(self, client):
        username = f'{_RUN_TAG}_u1'
        session = get_db_session()
        user = session.query(User).filter_by(username=username).first()
        resp = client.post(f'/api/auth/users/{user.id}/permissions',
                           json={'permission': '*'})
        assert resp.status_code == 400, resp.text


class TestHttpReadSideUnaffected:
    """读命令不产生副作用（CQRS）：列表/详情可读已提交用户。"""

    def test_list_users_sees_committed_register(self, client):
        username = f'{_RUN_TAG}_u1'
        resp = client.get('/api/auth/users', params={'page': 1, 'page_size': 100})
        assert resp.status_code == 200, resp.text
        users = resp.json()['data']['users']
        assert any(u['username'] == username for u in users)
