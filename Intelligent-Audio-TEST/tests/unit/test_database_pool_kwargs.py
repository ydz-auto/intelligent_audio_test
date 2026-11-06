# -*- coding: utf-8 -*-
"""init_db 连接池参数按池类条件化装配回归守卫（INT-48）。

修复前：init_db 无条件向 create_engine 传 pool_size/max_overflow，
SQLite 内存库默认池类 SingletonThreadPool 拒绝 QueuePool 专属参数 →
TypeError，全量回归固定 17 errors（DATABASE_URL import 期污染组合）。

锁定三点：
- 根因回归：sqlite:// 与 sqlite:///:memory: 下装配参数不含 QueuePool
  专属项，且 init_db 内存库全链路（建表/插入/查询）真实可用
- 生产行为不变（验收标准 3）：SQLite 文件库 / PostgreSQL / MySQL 仍传
  pool_size/max_overflow
- 装配依据不漂移：_pool_kwargs 的池类判定与 create_engine 实际选用
  的池类一致
"""
import os
import tempfile

os.environ.setdefault('DATABASE_URL',
                      'sqlite:///' + tempfile.mkdtemp(prefix='int48_') + '/guard.db')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.pool import QueuePool, SingletonThreadPool

from shared.models.database import _pool_kwargs, init_db, get_db_session, remove_db_session


QUEUE_ONLY = ('pool_size', 'max_overflow')


@pytest.mark.parametrize('uri', ['sqlite://', 'sqlite:///:memory:'])
def test_memory_sqlite_excludes_queuepool_only_params(uri):
    """SQLite 内存库（SingletonThreadPool）：仅传 Pool 基类参数。"""
    kw = _pool_kwargs(uri, 3)
    assert not any(k in kw for k in QUEUE_ONLY), f'内存库不得传 QueuePool 专属参数: {kw}'
    assert kw['pool_recycle'] == 3600
    assert kw['pool_pre_ping'] is True


@pytest.mark.parametrize('uri', [
    'sqlite:///./int48_guard_tmp.db',
    'postgresql://u:p@localhost:5432/audit',
    'postgresql+psycopg2://u:p@localhost:5432/audit',
    'mysql+pymysql://u:p@localhost:3306/audit',
])
def test_queuepool_urls_keep_size_and_overflow(uri):
    """QueuePool 池类（生产 PostgreSQL/MySQL、SQLite 文件库）：参数照传。"""
    kw = _pool_kwargs(uri, 7)
    assert kw['pool_size'] == 7
    assert kw['max_overflow'] == 5
    assert kw['pool_recycle'] == 3600
    assert kw['pool_pre_ping'] is True


@pytest.mark.parametrize('uri,expect_pool', [
    ('sqlite:///:memory:', SingletonThreadPool),
    ('sqlite:///./int48_guard_tmp.db', QueuePool),
    ('postgresql://u:p@localhost:5432/audit', QueuePool),
])
def test_pool_kwargs_match_actual_engine_pool_class(uri, expect_pool):
    """_pool_kwargs 池类判定与 create_engine 实际选用的池类一致。"""
    eng = create_engine(uri, **_pool_kwargs(uri, 3))
    try:
        assert isinstance(eng.pool, expect_pool)
    finally:
        eng.dispose()


def test_init_db_memory_sqlite_end_to_end(monkeypatch):
    """污染场景全链路：DATABASE_URL 冻结为内存库时 init_db 不炸且可用。"""
    from shared.infrastructure.config import BaseConfig
    from shared.models import database as dbmod

    monkeypatch.setattr(BaseConfig, 'DATABASE_URL', 'sqlite:///:memory:')
    dbmod.init_db(pool_size=3)
    try:
        assert isinstance(dbmod.get_engine().pool, SingletonThreadPool)
        get_db_session().execute(
            text('CREATE TABLE int48_probe (id INTEGER PRIMARY KEY, v TEXT)'))
        get_db_session().execute(text("INSERT INTO int48_probe (v) VALUES ('ok')"))
        row = get_db_session().execute(text('SELECT v FROM int48_probe')).fetchone()
        assert row[0] == 'ok'
        get_db_session().commit()
    finally:
        remove_db_session()
