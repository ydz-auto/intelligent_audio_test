# -*- coding: utf-8 -*-
"""INT-2283：任务时间字段口径统一（写库 UTC naive）契约测试。

缺陷：执行链路（started_at / completed_at）自 INT-2209 起写 UTC naive，但
创建链路仍把 aware +8 写进 ``timestamp without time zone`` 列——部署库会话
时区是 Asia/Shanghai，落库成 +8 墙钟。于是同一任务 created_at 比 started_at
晚 8 小时（跨日表现为 16 小时级脏值），used_time / 展示口径随之错乱。

本文件锁住三条：
1. PO 默认值（created_at / updated_at）与显式写入口径都是 UTC naive；
2. 本地语义只在边界转换：展示串走 ``to_local_naive``，用户日期筛选走
   ``local_naive_to_utc_naive``，趋势分桶按东八区自然日；
3. ``test_result_dimensions.created_at`` 同口径（评估维度写入）。
"""
import os
from datetime import datetime, timedelta, timezone
from inspect import unwrap

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

CST = timezone(timedelta(hours=8))


# ============================================================
# 1) 口径助手
# ============================================================

class TestTimeUtilsContract:
    def test_utcnow_is_naive_utc(self):
        from shared.utils.time_utils import utcnow as shared_utcnow
        from task_service.core.time_utils import utcnow

        shared_now = shared_utcnow()
        assert shared_now.tzinfo is None
        assert abs((datetime.now(timezone.utc).replace(tzinfo=None)
                    - shared_now).total_seconds()) < 5
        # 服务门面与 shared 同一实现
        assert abs((utcnow() - shared_utcnow()).total_seconds()) < 5

    def test_to_local_naive_shifts_to_cst(self):
        from task_service.core.time_utils import to_local_naive

        # 库内 UTC naive 17:30 → 东八区次日 01:30
        assert to_local_naive(datetime(2026, 10, 31, 17, 30)) == \
            datetime(2026, 11, 1, 1, 30)
        # aware 输入按绝对时刻换算
        assert to_local_naive(datetime(2026, 10, 31, 17, 30, tzinfo=timezone.utc)) == \
            datetime(2026, 11, 1, 1, 30)
        assert to_local_naive(None) is None

    def test_local_naive_to_utc_naive(self):
        from task_service.core.time_utils import local_naive_to_utc_naive

        # 用户选的本地 00:00 = 库内 UTC 前一日 16:00
        assert local_naive_to_utc_naive(datetime(2026, 11, 1, 0, 0)) == \
            datetime(2026, 10, 31, 16, 0)
        # 带时区后缀的按绝对时刻归一
        assert local_naive_to_utc_naive('2026-11-01T00:00:00+08:00') == \
            datetime(2026, 10, 31, 16, 0)
        assert local_naive_to_utc_naive(None) is None
        assert local_naive_to_utc_naive('') is None

    def test_elapsed_seconds_across_display_boundary(self):
        from task_service.core.time_utils import elapsed_seconds

        # 两侧同为库内 UTC naive：时长与展示时区无关
        assert elapsed_seconds(datetime(2026, 10, 31, 17, 38, 44),
                               datetime(2026, 10, 31, 17, 40, 44)) == 120


# ============================================================
# 2) PO 默认值：写库 UTC naive
# ============================================================

def _assert_utc_naive(value):
    assert value is not None
    assert value.tzinfo is None
    assert abs((datetime.now(timezone.utc).replace(tzinfo=None)
                - value).total_seconds()) < 10


def _default_fn(column):
    """列默认值背后的原始函数（SQLAlchemy 会包一层 context 兼容壳）。"""
    default = column.default or column.onupdate
    assert default is not None, column
    return unwrap(default.arg)


class TestModelDefaultsWriteUtc:
    def test_task_defaults_are_utcnow(self):
        from shared.utils.time_utils import utcnow
        from task_service.infrastructure.persistence.models.task_models import (
            Task, TaskCase, TaskLaboratoryRelation, TaskMergeRelation, TaskTag,
        )

        for table in (Task, TaskCase, TaskTag,
                      TaskLaboratoryRelation, TaskMergeRelation):
            assert _default_fn(table.__table__.c.created_at) is utcnow, table.__name__
        assert _default_fn(Task.__table__.c.updated_at) is utcnow

    def test_result_and_review_defaults_are_utcnow(self):
        from shared.utils.time_utils import utcnow
        from task_service.infrastructure.persistence.models.result_models import TestResult
        from task_service.infrastructure.persistence.models.review_models import (
            TestResultReview,
        )

        assert _default_fn(TestResult.__table__.c.created_at) is utcnow
        assert _default_fn(TestResultReview.__table__.c.created_at) is utcnow

    def test_evaluation_dimension_default_is_utcnow(self):
        from shared.utils.time_utils import utcnow
        from evaluation_service.infrastructure.persistence.models.result_models import (
            TestResultDimension,
        )

        assert _default_fn(TestResultDimension.__table__.c.created_at) is utcnow


# ============================================================
# 3) 落库链路（sqlite 进程级临时库，见 tests/conftest.py）
# ============================================================

@pytest.fixture(scope='module')
def int2283_db():
    from shared.models.database import Base, get_engine, init_db, remove_db_session
    from task_service.infrastructure.persistence.models.task_models import (
        Task, TaskCase,
    )

    init_db(pool_size=2)
    Base.metadata.create_all(
        bind=get_engine(), tables=[Task.__table__, TaskCase.__table__])
    yield
    remove_db_session()


def _session():
    from shared.models.database import get_db_session
    return get_db_session()


def test_orm_created_at_is_utc_naive(int2283_db):
    """不显式传时间：created_at / updated_at 由默认值写 UTC naive。"""
    from shared.models.database import remove_db_session
    from task_service.infrastructure.persistence.models.task_models import Task

    session = _session()
    try:
        task = Task(id=2283001, name='INT-2283 默认值任务', status='pending',
                    total_cases=1, completed_cases=0, failed_cases=0)
        session.add(task)
        session.commit()
        _assert_utc_naive(task.created_at)
        _assert_utc_naive(task.updated_at)
    finally:
        remove_db_session()


def test_created_at_not_later_than_started_at(int2283_db):
    """创建后启动：created_at <= started_at，两者同口径（不再差 8 小时）。"""
    from shared.models.database import remove_db_session
    from task_service.domain.entities import TaskAggregate
    from task_service.domain.services.task_state_machine import TaskStateMachine
    from task_service.infrastructure.persistence.models.task_models import Task

    session = _session()
    try:
        task = Task(id=2283002, name='INT-2283 启动顺序', status='pending',
                    total_cases=1, completed_cases=0, failed_cases=0)
        session.add(task)
        session.commit()
        created_at = task.created_at

        aggregate = TaskAggregate(id=task.id, name=task.name, status='pending')
        TaskStateMachine.apply_action(aggregate, 'start')

        # 状态机默认 now 也是 UTC naive
        assert aggregate.started_at.tzinfo is None
        assert aggregate.started_at >= created_at
        assert (aggregate.started_at - created_at).total_seconds() < 60
    finally:
        remove_db_session()


def test_trend_bucket_uses_local_calendar_day(int2283_db):
    """趋势图 key 按东八区自然日：UTC 17:30 属本地次日。

    进程级 sqlite 库可能已被其他用例插入数据（见 tests/conftest.py），
    期望值按库内全量已完成任务现算，不假设库为空。
    """
    from shared.models.database import remove_db_session
    from task_service.infrastructure.persistence._task_case_stats_mixin import (
        TaskCaseStatsMixin,
    )
    from task_service.infrastructure.persistence.models.task_models import Task

    session = _session()
    try:
        session.add_all([
            # UTC 2026-10-31 17:30 = 本地 2026-11-01 01:30
            Task(id=2283010, name='跨日任务', status='completed',
                 total_cases=1, completed_cases=1, failed_cases=0,
                 created_at=datetime(2026, 10, 31, 17, 30),
                 updated_at=datetime(2026, 10, 31, 17, 30)),
            # UTC 2026-10-31 08:00 = 本地 2026-10-31 16:00
            Task(id=2283011, name='同日任务', status='completed',
                 total_cases=1, completed_cases=1, failed_cases=0,
                 created_at=datetime(2026, 10, 31, 8, 0),
                 updated_at=datetime(2026, 10, 31, 8, 0)),
        ])
        session.commit()

        expected = {}
        for (created_at,) in session.query(Task.created_at).filter(
                Task.deleted == False,  # noqa: E712
                Task.status == 'completed').all():
            key = (created_at + timedelta(hours=8)).strftime('%Y-%m-%d')
            expected[key] = expected.get(key, 0) + 1

        buckets = TaskCaseStatsMixin._get_task_trend_buckets(
            session, status='completed', algorithm_type=None, granularity='day')
        items = {i['key']: i['count'] for i in buckets['items']}
        assert items == expected
        # 跨日那条落在本地次日，而非 UTC 当日
        assert items.get('2026-11-01', 0) >= 1
    finally:
        remove_db_session()


def test_cherry_pick_iso_filter_is_converted_to_utc():
    """挑选合并的日期筛选：本地墙钟入参 → UTC naive 进 SQL。"""
    from task_service.application.task.cherry_pick_service import CherryPickService

    assert CherryPickService._parse_iso_dt('2026-11-01T00:00:00') == \
        datetime(2026, 10, 31, 16, 0)
    assert CherryPickService._parse_iso_dt('') is None
    assert CherryPickService._parse_iso_dt('not-a-date') is None
