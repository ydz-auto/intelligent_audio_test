# -*- coding: utf-8 -*-
"""INT-79 打回修复回归：GetTaskStats 分组统计不再触碰已删除的 Task.type 列。

背景：db8db540 删除 Task.type 列后，_get_task_stats_grouped 的 allowed
映射仍急切引用 Task.type → 任何带 group_by 的 GetTaskStats 调用
（含 stats_cache 的 group_by='status'）都 AttributeError，运行库峰值
28 条/分钟失败刷屏（INT-95 实机验收发现）。

- group_by='status' 正常返回分组计数（stats_cache 主路径）
- group_by='type' 不触碰已删除的 Task.type 列（INT-200 起为 device_type 派生分布）
- 无 group_by 返回 total
"""
import os
import tempfile

import pytest

os.environ.setdefault('DATABASE_URL',
                      'sqlite:///' + tempfile.mkdtemp(prefix='int79_stats_') + '/stats.db')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from shared.models.database import (
    Base, get_db_session, get_engine, init_db, remove_db_session,
)
from task_service.infrastructure.persistence.models import Task
from sqlalchemy import BigInteger
from sqlalchemy.ext.compiler import compiles


@compiles(BigInteger, 'sqlite')
def _render_bigint_as_integer_sqlite(type_, compiler, **kw):
    """SQLite 不支持 BigInteger 主键自增，建表时渲染为 INTEGER。"""
    return 'INTEGER'


@pytest.fixture(scope='module')
def db():
    """初始化 SQLite 库并建 test_tasks 表，种子两条任务。

    全量跑时共享引擎可能已被先前用例建表/插数（单例 engine，
    setdefault 的 DATABASE_URL 不生效），故各断言均以种子前基线为参照，
    不假设库为空。
    """
    init_db(pool_size=3)
    engine = get_engine()
    assert ':memory:' not in str(engine.url), \
        f'stats sqlite 需要文件型 sqlite，实际绑定 {engine.url}'
    remove_db_session()
    # INT-200：group_by='type' 改为用例级 device_type 派生分布，需 task_case 表
    from task_service.infrastructure.persistence.models import TaskCase
    Base.metadata.create_all(bind=engine, tables=[Task.__table__, TaskCase.__table__])

    repo = _repo()
    baseline_total = int(repo.get_task_stats().get('total', 0) or 0)
    baseline_status = {item['key']: int(item['count'])
                       for item in repo.get_task_stats(group_by='status').get('items', [])}
    baseline_type = {item['key']: int(item['count'])
                     for item in repo.get_task_stats(group_by='type').get('items', [])}

    session = get_db_session()
    session.add(Task(name='t-running', status='running', total_cases=0))
    session.add(Task(name='t-completed', status='completed', total_cases=0))
    session.commit()
    session.close()
    yield {'baseline_total': baseline_total, 'baseline_status': baseline_status,
           'baseline_type': baseline_type}
    remove_db_session()


def _repo():
    from task_service.infrastructure.persistence.task_repository import task_repository
    return task_repository


def test_group_by_status_works(db):
    """stats_cache 主路径：group_by='status' 不再因 Task.type 缺失而 AttributeError。"""
    result = _repo().get_task_stats(group_by='status')
    items = {item['key']: item['count'] for item in result.get('items', [])}
    assert items.get('running') == db['baseline_status'].get('running', 0) + 1
    assert items.get('completed') == db['baseline_status'].get('completed', 0) + 1


def test_group_by_type_derived_distribution(db):
    """INT-200 后 group_by='type' 改为用例级 device_type 派生分布（不触碰已删除的
    Task.type 列）；本模块种子任务无用例行，按前端口径计入 api。"""
    result = _repo().get_task_stats(group_by='type')
    assert 'error' not in result
    counts = {item['key']: int(item['count']) for item in result.get('items', [])}
    assert counts.get('api', 0) - db['baseline_type'].get('api', 0) == 2
    assert set(counts) <= {'api', 'e2e', 'mixed'}


def test_total_without_group_by(db):
    result = _repo().get_task_stats()
    assert result == {'total': db['baseline_total'] + 2}
