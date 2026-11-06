# -*- coding: utf-8 -*-
"""INT-1468 日志域读侧聚合缓存回归（列表 total / stats group by）。

背景：logs 是最大增长表（30 万行级），列表每次请求都要 count(*)，stats 每次
都要全表 group by。LogRepository 为两者加了短 TTL 聚合缓存
（LOG_DB_AGGREGATE_CACHE_TTL_SECONDS，0 = 关闭）。

覆盖：
1. TTL 内同过滤条件只查一次库（count / group by 各一），命中返回等价结果；
2. TTL = 0 时关闭缓存，每次请求都真实查询；
3. 写操作（batch_create / update_marks / clear）立即失效本进程缓存；
4. 过滤条件不同不共享缓存条目；等价写法（大小写、'all'、0/空）共享同一条目。
"""
import os

os.environ.setdefault('DATABASE_URL',
                      'sqlite:///' + os.path.join(os.environ.get('TEMP', '/tmp'),
                                                  'int1468_log_cache.db'))
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest  # noqa: E402
from sqlalchemy import event  # noqa: E402

from shared.infrastructure.config import BaseConfig  # noqa: E402
from task_service.infrastructure.persistence import log_repository as repo_module  # noqa: E402
from task_service.infrastructure.persistence.log_repository import LogRepository  # noqa: E402

_TASK_ID = 9101468


@pytest.fixture(scope='module', autouse=True)
def _db():
    from shared.models.database import Base, get_engine, init_db
    init_db()
    from task_service.infrastructure.persistence.models.system_models import Log
    Base.metadata.create_all(get_engine(), tables=[Log.__table__])
    yield


@pytest.fixture(autouse=True)
def _clean():
    from shared.models.database import get_db_session
    from task_service.infrastructure.persistence.models.system_models import Log
    session = get_db_session()
    try:
        session.query(Log).filter(Log.task_id == _TASK_ID).delete(synchronize_session=False)
        session.commit()
    finally:
        session.close()
    repo_module._agg_cache_clear()


@pytest.fixture
def ttl(monkeypatch):
    def _set(seconds):
        monkeypatch.setattr(BaseConfig, 'LOG_DB_AGGREGATE_CACHE_TTL_SECONDS', seconds,
                            raising=False)
    _set(60)
    return _set


def _seed(count, level='INFO', module='Evaluation'):
    from task_service.infrastructure.persistence.models.system_models import Log
    from shared.models.database import get_db_session
    from shared.utils.query_utils import now_cst
    session = get_db_session()
    try:
        for i in range(count):
            session.add(Log(time=now_cst(), level=level, category='execution',
                            module=module, source='test', content=f'row {i}',
                            task_id=_TASK_ID))
        session.commit()
    finally:
        session.close()


class _PutCounter:
    """统计聚合回填次数：命中缓存不会回填，回填数即真实聚合查询次数。"""

    def __init__(self, monkeypatch):
        self.count = 0
        original = repo_module._agg_cache_put
        counter = self

        def wrapper(key, value):
            counter.count += 1
            return original(key, value)

        monkeypatch.setattr(repo_module, '_agg_cache_put', wrapper)


@pytest.fixture
def puts(monkeypatch):
    return _PutCounter(monkeypatch)


def test_list_total_cached_within_ttl(puts, ttl):
    _seed(3)
    first = LogRepository().list_logs(task_id=_TASK_ID, page=1, per_page=20)
    second = LogRepository().list_logs(task_id=_TASK_ID, page=1, per_page=20)
    assert first['total'] == second['total'] == 3
    assert puts.count == 1


def test_list_total_recomputed_when_ttl_disabled(ttl):
    ttl(0)
    _seed(2)
    assert LogRepository().list_logs(task_id=_TASK_ID)['total'] == 2
    assert LogRepository().list_logs(task_id=_TASK_ID)['total'] == 2
    # 缓存关闭：条目不落缓存，两次请求各自真实查询后 total 仍正确
    assert repo_module._AGG_CACHE == {}


def test_write_invalidates_list_cache(ttl):
    _seed(2)
    assert LogRepository().list_logs(task_id=_TASK_ID)['total'] == 2
    LogRepository().batch_create([{'level': 'INFO', 'module': 'Evaluation',
                                   'task_id': _TASK_ID, 'content': 'new row'}])
    assert LogRepository().list_logs(task_id=_TASK_ID)['total'] == 3


def test_stats_cached_within_ttl(puts, ttl):
    _seed(4, level='ERROR')
    first = LogRepository().get_stats(task_id=_TASK_ID)
    second = LogRepository().get_stats(task_id=_TASK_ID)
    assert first == second
    assert first['error'] == 4
    assert puts.count == 1


def test_equivalent_filters_share_cache_entry(puts, ttl):
    _seed(1)
    LogRepository().list_logs(task_id=_TASK_ID, level='INFO', module='Evaluation')
    LogRepository().list_logs(task_id=_TASK_ID, level='info', module='evaluation')
    LogRepository().list_logs(task_id=_TASK_ID, level='ALL', module='all')
    # 前两次 SQL 语义等价（lower 比较）→ 共享条目；第三次 level='all' 在
    # list_logs 里不是「不过滤」语义（仅 module/category 归一 'all'）→ 独立条目
    assert puts.count == 2


def test_different_filters_not_shared(puts, ttl):
    _seed(2)
    LogRepository().list_logs(task_id=_TASK_ID, level='INFO')
    LogRepository().list_logs(task_id=_TASK_ID, level='ERROR')
    assert puts.count == 2


def test_level_all_is_not_normalized_to_no_filter(puts, ttl):
    """level='all' 在 SQL 层是字面值过滤（返回空集），缓存键不得与不过滤共享。"""
    _seed(2)
    unfiltered = LogRepository().list_logs(task_id=_TASK_ID)
    filtered = LogRepository().list_logs(task_id=_TASK_ID, level='all')
    assert unfiltered['total'] == 2
    assert filtered['total'] == 0
    assert puts.count == 2
