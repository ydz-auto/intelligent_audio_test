# -*- coding: utf-8 -*-
"""INT-1465：GET /auth/users 列表响应瘦身 + 消除 N+1 回归钉。

缺陷（2026-10-23 压测）：10 条用户列表 34KB（单条 ~3.4KB），并发 40
avg 1006ms。根因两条，均在本卡修复：
1. 列表 DTO 携带每个用户的生效权限码全集（权限明细只有详情页需要）；
2. 仓储 list_users 逐用户查权限（角色权限 + override 2 次）与角色名（1 次），
   一页 10 条即 30 次额外查询，并发下打满连接池。

本用例钉住：
A. 列表项不含 permissions / overrides，带 permission_count（生效权限数），
   其余字段（role_name 等）照常；
B. 列表查询 SQL 条数与页大小无关（权限按整页批量查，不逐用户查、无 N+1）；
C. 详情 GetUser 仍返回 permissions + overrides（列表瘦身不回退详情契约）。
"""
import json
import os

import pytest

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from sqlalchemy import BigInteger, event  # noqa: E402
from sqlalchemy.ext.compiler import compiles  # noqa: E402

from shared.models.database import (  # noqa: E402
    Base, get_db_session, get_engine, init_db, remove_db_session,
)
from auth_service.infrastructure.persistence.models import (  # noqa: E402
    Permission, Role, RolePermission, User, UserPermission,
)

_PREFIX = 'int1465_'


@compiles(BigInteger, 'sqlite')
def _render_bigint_as_integer_sqlite(type_, compiler, **kw):
    """SQLite 不支持 BigInteger 主键自增，建表时渲染为 INTEGER。"""
    return 'INTEGER'


@pytest.fixture(scope='module')
def seeded_db():
    """建 RBAC 表并种一页用户（20 人同角色 + 1 条 override 明细）。"""
    init_db(pool_size=3)
    engine = get_engine()
    assert ':memory:' not in str(engine.url), \
        f'本用例需要文件型 sqlite（跨请求共享表），实际绑定 {engine.url}'
    remove_db_session()
    Base.metadata.create_all(
        bind=engine,
        tables=[Role.__table__, Permission.__table__, RolePermission.__table__,
                UserPermission.__table__, User.__table__],
    )
    session = get_db_session()
    role = Role(name=_PREFIX + 'role', description='INT-1465')
    session.add(role)
    session.flush()
    perms = []
    for code in ('audio:read', 'task:read', 'report:read'):
        perm = Permission(name=_PREFIX + code, description=code)
        session.add(perm)
        perms.append(perm)
    session.flush()
    for perm in perms:
        session.add(RolePermission(role_id=role.id, permission_id=perm.id))
    role_id = role.id
    for i in range(20):
        session.add(User(
            username=f'{_PREFIX}user_{i:02d}', email=f'{_PREFIX}{i:02d}@x.com',
            role_id=role_id, status='active', display_name=f'用户{i}',
        ))
    session.flush()
    target = session.query(User).filter_by(username=_PREFIX + 'user_00').first()
    session.add(UserPermission(
        user_id=target.id, permission_id=perms[0].id, granted=False))
    session.commit()
    yield {'role_id': role_id, 'user_id': target.id, 'perm_codes': perms}
    # 清理本用例夹具（共享库下也不留残留）
    session = get_db_session()
    try:
        user_ids = [r[0] for r in session.query(User.id).filter(
            User.username.like(_PREFIX + '%')).all()]
        if user_ids:
            session.query(UserPermission).filter(
                UserPermission.user_id.in_(user_ids)).delete(
                synchronize_session=False)
        session.query(RolePermission).filter(
            RolePermission.role_id == role_id).delete(synchronize_session=False)
        session.query(User).filter(User.username.like(_PREFIX + '%')).delete(
            synchronize_session=False)
        session.query(Role).filter(Role.name == _PREFIX + 'role').delete(
            synchronize_session=False)
        session.query(Permission).filter(
            Permission.name.like(_PREFIX + '%')).delete(
            synchronize_session=False)
        session.commit()
    finally:
        remove_db_session()


def _servicer():
    from auth_service.interfaces.grpc.servicers import AuthServicer
    return AuthServicer()


def test_list_items_drop_permissions(seeded_db):
    """A：列表项无 permissions/overrides，带生效权限数，role_name 等展示字段保留。"""
    from shared.proto import auth_service_pb2 as auth_pb
    svc = _servicer()
    resp = svc.ListUsers(auth_pb.ListUsersRequest(
        page=1, page_size=10, keyword=_PREFIX))
    assert resp.success, resp.message
    data = json.loads(resp.data)
    items = data['items']
    assert len(items) == 10
    for item in items:
        assert 'permissions' not in item, '列表项不得携带权限码全集'
        assert 'overrides' not in item, '列表项不得携带 override 明细'
        assert item['role_name'] == _PREFIX + 'role'
        assert {'id', 'username', 'email', 'role_id', 'status', 'is_active',
                'display_name', 'created_at', 'permission_count'} <= set(item)
    # 生效权限数：角色基线 3 个；user_00 被撤销 audio:read → 2
    by_name = {item['username']: item for item in items}
    assert by_name[_PREFIX + 'user_00']['permission_count'] == 2
    assert by_name[_PREFIX + 'user_01']['permission_count'] == 3
    # 瘦身后整页响应远小于原 34KB 量级（本夹具 10 条 < 8KB）
    assert len(resp.data.encode('utf-8')) < 8 * 1024


def test_list_query_count_independent_of_page_size(seeded_db, monkeypatch):
    """B：列表 SQL 条数固定（count + 分页 + 角色名 + 权限数批量 2 条），与页大小无关。

    权限不逐用户查：整页 role_permissions / user_permissions 各 1 条批量查询，
    aggregate.permissions 仍为空（只带 permission_count）。
    """
    from auth_service.infrastructure.persistence import user_repository as ur

    engine = get_engine()
    counts = {}

    for page_size in (5, 20):
        statements = []

        def _record(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement)

        event.listen(engine, 'before_cursor_execute', _record)
        try:
            total, users = ur.user_repository.list_users(
                page=1, page_size=page_size, keyword=_PREFIX)
        finally:
            event.remove(engine, 'before_cursor_execute', _record)
        assert total == 20 and len(users) == page_size
        assert all(u.role_name == _PREFIX + 'role' for u in users)
        # 权限明细在列表场景不加载：只带计数，不带权限码
        assert all(u.permissions == [] for u in users)
        assert all(
            u.permission_count == (2 if u.username == _PREFIX + 'user_00' else 3)
            for u in users
        )
        counts[page_size] = len(statements)

    # 单页不分大小都是固定 5 条 SQL（原实现 1 + 1 + N×3）
    assert counts[5] == counts[20] <= 5, counts
    # 权限相关表只允许整页批量查询：每张表最多 1 次，不随用户数增长
    statements = []

    def _record_sql(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(engine, 'before_cursor_execute', _record_sql)
    try:
        ur.user_repository.list_users(page=1, page_size=20, keyword=_PREFIX)
    finally:
        event.remove(engine, 'before_cursor_execute', _record_sql)
    touched = ' '.join(statements).lower()
    assert touched.count('from user_permissions') <= 1, touched
    assert touched.count('from role_permissions') <= 1, touched


def test_detail_still_returns_permissions_and_overrides(seeded_db):
    """C：详情 GetUser 契约不回退（权限 + overrides 仍返回）。"""
    from shared.proto import auth_service_pb2 as auth_pb
    svc = _servicer()
    resp = svc.GetUser(auth_pb.GetUserRequest(user_id=seeded_db['user_id']))
    assert resp.success, resp.message
    data = json.loads(resp.data)
    codes = set(data['permissions'])
    # 角色基线 3 个权限码；override 撤销了 audio:read
    assert _PREFIX + 'report:read' in codes
    assert _PREFIX + 'audio:read' not in codes
    assert data['overrides'] == [{
        'permission_id': seeded_db['perm_codes'][0].id,
        'code': _PREFIX + 'audio:read',
        'granted': False,
    }]
