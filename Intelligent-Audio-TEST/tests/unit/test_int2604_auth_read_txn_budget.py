# -*- coding: utf-8 -*-
"""INT-2604：auth_service 只读 HTTP 路由的事务收口守卫。

事故（2026-11-14T12:25Z 资源巡检）：`intelligent_audio_test` 主库出现 4 小时
以上的 `idle in transaction` 会话（auth_service 容器发起，持 `access_tokens`
及其索引的 `AccessShareLock`）。根因是 auth_service 的 FastAPI 应用工厂没有
注册 `DbSessionScopeMiddleware`，只读路由 SELECT 完既不 commit 也不
rollback，uvicorn 线程池线程回落到线程级 session，事务与连接一直挂在请求
结束之后（pool_size=5 的连接池被逐步吃满，长期 ACCESS SHARE 把 vacuum / DDL
顶进锁队列）。

本文件守两层：
1. 接线：`auth_service.app.create_app()` 的 `user_middleware` 必须含
   `DbSessionScopeMiddleware`（照 INT-1652 algorithm_service /
   INT-1691 evaluation_service 的写法）。
2. 行为：真实 app + TestClient 打只读路由，断言请求收尾时该请求的 session
   确实被 `remove_db_session()` 从 scope 移除、事务被关闭 —— 而不是留在
   `idle in transaction` 里。
"""
import os
import tempfile

os.environ.setdefault('DATABASE_URL',
                      'sqlite:///' + tempfile.mkdtemp(prefix='int2604_') + '/guard.db')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest
from fastapi.testclient import TestClient

from shared.models.database import (
    Base,
    _scoped_session,
    get_engine,
    init_db,
)
import auth_service.infrastructure.persistence.models  # noqa: F401  （注册 PO）


@pytest.fixture(scope='module', autouse=True)
def _db():
    init_db()
    Base.metadata.create_all(get_engine())
    # 种一个 id=1 的用户：GET /users/{id} 走真实查询路径（否则域层抛
    # USER_NOT_FOUND，测不到「只读路由 + 请求级 session」这条主链）
    from auth_service.infrastructure.persistence.models import User
    from shared.models.database import get_db_session
    session = get_db_session()
    if session.get(User, 1) is None:
        session.add(User(id=1, username='int2604_user', status='active'))
        session.commit()
    session.remove()
    yield


def test_auth_service_registers_request_scope_middleware():
    """HTTP 边界必须挂请求级 session scope（本卡缺陷就是应用工厂漏接线）。"""
    from shared.infrastructure.db_session_middleware import DbSessionScopeMiddleware
    from auth_service.app import create_app

    app = create_app()
    assert any(m.cls is DbSessionScopeMiddleware for m in app.user_middleware), \
        'auth_service 未注册 DbSessionScopeMiddleware：只读路由会遗留 idle in transaction'


@pytest.mark.parametrize('path,headers', [
    # 事故现场路由（INT-2603 实测 SELECT 出自 access_tokens.list_by_user）
    ('/api/v1/auth/access-tokens', {'X-User-Id': '1'}),
    # 卡内要求顺带核对的其它只读路由（同一中间件收口）
    ('/api/auth/users', {}),
    ('/api/auth/users/1', {}),
    ('/api/auth/roles', {}),
])
def test_read_only_route_releases_request_session(path, headers, monkeypatch):
    """只读路由返回后：该请求的 session 被移除、事务关闭（不留 idle in transaction）。"""
    import shared.models.database as db

    from auth_service.app import create_app

    records = []
    real_remove = db.remove_db_session

    def spy_remove():
        """记录 remove 前后的 scope 状态：请求内应有开事务的 session，remove 后被清空。"""
        had = _scoped_session.registry.has()
        session = _scoped_session() if had else None
        tx_before = session.in_transaction() if session is not None else None
        real_remove()
        still_there = _scoped_session.registry.has()
        tx_after = session.in_transaction() if session is not None else None
        records.append({
            'had_session': had,
            'tx_before': tx_before,
            'still_there': still_there,
            'tx_after': tx_after,
        })

    monkeypatch.setattr(db, 'remove_db_session', spy_remove)

    client = TestClient(create_app())
    resp = client.get(path, headers=headers)
    # 只读路由本身能正常应答（不被授权/表结构挡住，确保真的走了 DB 读路径）
    assert resp.status_code == 200, resp.text

    assert records, f'{path} 请求结束未调用 remove_db_session —— DbSessionScopeMiddleware 未生效'
    # 至少有一次清理发生在「本请求持有开事务 session」的 scope 内
    hits = [r for r in records
            if r['had_session'] and r['tx_before'] is True
            and r['still_there'] is False and r['tx_after'] is False]
    assert hits, f'{path} 请求收尾未释放开事务的 session：{records}'
