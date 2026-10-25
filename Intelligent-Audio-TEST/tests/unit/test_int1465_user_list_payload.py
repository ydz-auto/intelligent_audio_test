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
    # 第 4 个权限点不挂角色，只用于用户 granted override
    extra_perm = Permission(name=_PREFIX + 'device:read', description='device:read')
    session.add(extra_perm)
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
    by_name = {
        po.username: po
        for po in session.query(User).filter(
            User.username.like(_PREFIX + '%')).all()
    }
    # user_00：撤销角色内的一个权限 → 3 - 1 = 2
    session.add(UserPermission(
        user_id=by_name[_PREFIX + 'user_00'].id,
        permission_id=perms[0].id, granted=False))
    # user_02：授予角色外权限 → 3 + 1 = 4
    session.add(UserPermission(
        user_id=by_name[_PREFIX + 'user_02'].id,
        permission_id=extra_perm.id, granted=True))
    # user_03：授予角色内已有权限 → 去重后仍是 3
    session.add(UserPermission(
        user_id=by_name[_PREFIX + 'user_03'].id,
        permission_id=perms[1].id, granted=True))
    # user_04：同一条角色外权限既授予又撤销 → 撤销优先，仍是 3
    session.add(UserPermission(
        user_id=by_name[_PREFIX + 'user_04'].id,
        permission_id=extra_perm.id, granted=True))
    session.add(UserPermission(
        user_id=by_name[_PREFIX + 'user_04'].id,
        permission_id=extra_perm.id, granted=False))
    session.commit()
    yield {
        'role_id': role_id,
        'user_id': by_name[_PREFIX + 'user_00'].id,
        'perm_codes': perms,
    }
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
    # 生效权限数口径 = 角色基线 3 个 + granted 追加 - revoked 撤销（deny 优先）
    by_name = {item['username']: item for item in items}
    assert by_name[_PREFIX + 'user_00']['permission_count'] == 2  # 撤销角色内 1 个
    assert by_name[_PREFIX + 'user_01']['permission_count'] == 3  # 无 override
    assert by_name[_PREFIX + 'user_02']['permission_count'] == 4  # 授予角色外 1 个
    assert by_name[_PREFIX + 'user_03']['permission_count'] == 3  # 授予角色内已有权限，去重
    assert by_name[_PREFIX + 'user_04']['permission_count'] == 3  # 授予又撤销，撤销优先
    # 瘦身后整页响应远小于原 34KB 量级（本夹具 10 条 < 8KB）
    assert len(resp.data.encode('utf-8')) < 8 * 1024


def test_list_query_count_independent_of_page_size(seeded_db, monkeypatch):
    """B：列表 SQL 条数固定（1 条分页主查询），与页大小无关。

    角色名走 LEFT JOIN、生效权限数走相关标量子查询、总数走 count(*) OVER ()，
    整页只发 1 条 SQL；不再为计数额外发批量查询，也不额外发 count 往返。
    """
    from auth_service.infrastructure.persistence import user_repository as ur

    engine = get_engine()
    counts = {}
    expected_counts = {
        _PREFIX + 'user_00': 2,
        _PREFIX + 'user_02': 4,
        _PREFIX + 'user_04': 3,
    }

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
            u.permission_count == expected_counts.get(u.username, 3)
            for u in users
        )
        counts[page_size] = len(statements)

    # 整页固定 1 条 SQL（原实现 1 + 1 + N×3）
    assert counts[5] == counts[20] == 1, counts
    # 权限表的读取只发生在这一条分页主查询里（相关子查询），没有额外批量往返
    statements = []

    def _record_sql(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(engine, 'before_cursor_execute', _record_sql)
    try:
        ur.user_repository.list_users(page=1, page_size=20, keyword=_PREFIX)
    finally:
        event.remove(engine, 'before_cursor_execute', _record_sql)
    assert len(statements) == 1, statements
    assert sum('from user_permissions' in s.lower() for s in statements) == 1, statements
    assert sum('from role_permissions' in s.lower() for s in statements) == 1, statements


def test_empty_page_falls_back_to_count(seeded_db):
    """B2：翻到空页时窗口计数无行可承载，回退 1 次 count，total 仍正确。"""
    from auth_service.infrastructure.persistence import user_repository as ur

    engine = get_engine()
    statements = []

    def _record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(engine, 'before_cursor_execute', _record)
    try:
        total, users = ur.user_repository.list_users(
            page=99, page_size=10, keyword=_PREFIX)
    finally:
        event.remove(engine, 'before_cursor_execute', _record)
    assert total == 20 and users == []
    assert len(statements) == 2, statements


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
