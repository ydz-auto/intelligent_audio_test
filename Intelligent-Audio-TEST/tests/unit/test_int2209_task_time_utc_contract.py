# -*- coding: utf-8 -*-
"""INT-2209：task_service 时间写入口径（UTC naive）契约测试。

缺陷：执行引擎把 aware CST 写进 naive 列、读回 naive 值后又
`.replace(tzinfo=utc_plus_8)` 写回 ORM 属性，PostgreSQL（session TimeZone=UTC）
每次往返再转一次，`test_tasks.started_at` 出现 -8h / -16h 偏移，
`started_at < created_at`、`actual_duration` 虚高（真实库 173/408 条）。

本文件覆盖写侧三条 started_at 路径 + TaskCase 边界归一：

1. 正常执行：`TaskLifecycleMixin._run_task` 写 `task.started_at`；
2. 兜底：`TaskFinalizeMixin._finalize_task_status` 重算时长时**不得**改写
   started_at（历史 -8h/-16h 的成因就是它把补了 tz 的值写回列）；
3. 派发失败补写：`CaseExecutionMixin._execute_api_case` 异常分支补
   started_at / completed_at / duration；
4. gRPC 边界：`update_task_case_status` 收到执行器上报的 aware ISO8601
   （+08:00）后落库为 UTC naive，而不是本地墙钟。

断言统一为：`created_at <= started_at <= completed_at`、写出的值 tzinfo 为
None、duration 与墙钟一致。
"""
import os
import threading
from datetime import datetime, timedelta, timezone

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

CST = timezone(timedelta(hours=8))


# ============================================================
# 纯函数：口径助手
# ============================================================

class TestTimeUtilsContract:
    def test_utcnow_is_naive_utc(self):
        from task_service.core.time_utils import utcnow

        now = utcnow()
        assert now.tzinfo is None
        # 与当前 UTC 时刻差 < 5 秒（naive 值即 UTC 墙钟）
        delta = abs((datetime.now(timezone.utc).replace(tzinfo=None) - now).total_seconds())
        assert delta < 5

    def test_to_utc_naive_converts_aware_cst(self):
        from task_service.core.time_utils import to_utc_naive

        aware = datetime(2026, 10, 31, 9, 8, 32, 42294, tzinfo=CST)
        assert to_utc_naive(aware) == datetime(2026, 10, 31, 1, 8, 32, 42294)
        assert to_utc_naive(aware).tzinfo is None

    def test_to_utc_naive_parses_iso_with_offset(self):
        from task_service.core.time_utils import to_utc_naive

        assert to_utc_naive('2026-10-31T09:08:32.042294+08:00') == \
            datetime(2026, 10, 31, 1, 8, 32, 42294)
        assert to_utc_naive('2026-10-31T01:08:32Z') == datetime(2026, 10, 31, 1, 8, 32)

    def test_to_utc_naive_keeps_naive_untouched(self):
        from task_service.core.time_utils import to_utc_naive

        naive = datetime(2026, 10, 31, 1, 8, 32)
        assert to_utc_naive(naive) == naive
        assert to_utc_naive(None) is None
        assert to_utc_naive('') is None

    def test_elapsed_seconds_mixes_naive_and_aware(self):
        from task_service.core.time_utils import elapsed_seconds

        start = datetime(2026, 10, 31, 1, 0, 0)
        end_aware = datetime(2026, 10, 31, 9, 0, 30, tzinfo=CST)  # = 01:00:30 UTC
        assert elapsed_seconds(start, end_aware) == 30
        assert elapsed_seconds(None, end_aware) is None


# ============================================================
# sqlite 夹具（进程级临时文件库，见 tests/conftest.py）
# ============================================================

@pytest.fixture(scope='module')
def int2209_db():
    from shared.models.database import Base, get_engine, init_db, remove_db_session
    from task_service.infrastructure.persistence.models.task_models import Task, TaskCase

    init_db(pool_size=2)
    Base.metadata.create_all(
        bind=get_engine(), tables=[Task.__table__, TaskCase.__table__])
    yield
    remove_db_session()


def _utcnow_naive():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _seed_task(task_id, *, status='pending', created_at=None,
               started_at=None, completed_at=None):
    from shared.models.database import get_db_session, remove_db_session
    from task_service.infrastructure.persistence.models.task_models import Task

    created_at = created_at or (_utcnow_naive() - timedelta(seconds=10))
    session = get_db_session()
    try:
        session.add(Task(
            id=task_id, name=f'int2209-task-{task_id}', status=status,
            total_cases=1, completed_cases=0, failed_cases=0,
            created_at=created_at, updated_at=created_at,
            started_at=started_at, completed_at=completed_at))
        session.commit()
    finally:
        remove_db_session()


def _seed_task_case(tc_id, task_id, *, case_id='int2209-case', status='pending',
                    execution_status='pending', evaluation_status='pending',
                    created_at=None, started_at=None, completed_at=None):
    from shared.models.database import get_db_session, remove_db_session
    from task_service.infrastructure.persistence.models.task_models import TaskCase

    created_at = created_at or (_utcnow_naive() - timedelta(seconds=10))
    session = get_db_session()
    try:
        session.add(TaskCase(
            id=tc_id, task_id=task_id, test_case_id=case_id, status=status,
            execution_status=execution_status, evaluation_status=evaluation_status,
            device_type='http_api', device_id='1',
            created_at=created_at, started_at=started_at, completed_at=completed_at))
        session.commit()
    finally:
        remove_db_session()


def _get_task(task_id):
    from shared.models.database import get_db_session, remove_db_session
    from task_service.infrastructure.persistence.models.task_models import Task

    session = get_db_session()
    try:
        return session.get(Task, task_id)
    finally:
        remove_db_session()


def _get_task_case(tc_id):
    from shared.models.database import get_db_session, remove_db_session
    from task_service.infrastructure.persistence.models.task_models import TaskCase

    session = get_db_session()
    try:
        return session.get(TaskCase, tc_id)
    finally:
        remove_db_session()


class _Engine:
    """最小执行引擎组合：只挂本卡涉及的 Mixin，外部依赖打桩。"""

    def __init__(self):
        self.logs = []

    def _log(self, **kwargs):
        self.logs.append(kwargs)

    def _emit_progress(self, *args, **kwargs):
        pass

    def _emit_alert(self, *args, **kwargs):
        pass

    def refresh_task_counts_atomic(self, task_id):
        pass

    def _cleanup_task_resources(self, task_id, stop_event):
        pass

    def _finalize_dispatch_failure(self, tc_rel):
        tc_rel.execution_status = 'failed'
        tc_rel.evaluation_status = 'completed'
        tc_rel.status = 'failed'


def _make_engine(mixin_cls, **overrides):
    cls = type('_E', (mixin_cls, _Engine), {})
    eng = cls()
    for name, value in overrides.items():
        setattr(eng, name, value)
    return eng


# ============================================================
# 1) 正常执行路径：_run_task 写 task.started_at
# ============================================================

def test_run_task_writes_utc_naive_started_at(int2209_db):
    from task_service.core.execution_engine.mixins.task_lifecycle import TaskLifecycleMixin

    task_id = 2209001
    created_at = _utcnow_naive() - timedelta(seconds=5)
    _seed_task(task_id, created_at=created_at)

    eng = _make_engine(TaskLifecycleMixin, _init_task_execution=lambda _tid: False)
    eng._run_task(task_id, threading.Event(), threading.Event())

    task = _get_task(task_id)
    assert task.started_at is not None
    assert task.started_at.tzinfo is None, 'started_at 必须写 UTC naive，不得带时区'
    assert task.created_at <= task.started_at, 'started_at 不得早于 created_at'
    delay = (task.started_at - task.created_at).total_seconds()
    assert 0 <= delay < 30, f'开始时刻应接近创建时刻，实际差 {delay:.1f}s'
    assert task.status == 'running'


# ============================================================
# 2) 兜底路径：_finalize_task_status 不得改写 started_at
# ============================================================

def test_finalize_keeps_started_at_and_computes_wall_clock_duration(int2209_db):
    from task_service.core.execution_engine.mixins.task_finalize import TaskFinalizeMixin

    task_id, tc_id = 2209002, 22090002
    started_at = _utcnow_naive() - timedelta(seconds=120)
    _seed_task(task_id, status='running',
               created_at=started_at - timedelta(seconds=60), started_at=started_at)
    _seed_task_case(tc_id, task_id, status='completed', execution_status='completed',
                    evaluation_status='completed', created_at=started_at,
                    started_at=started_at,
                    completed_at=started_at + timedelta(seconds=100))

    eng = _make_engine(TaskFinalizeMixin)
    stop_event = threading.Event()

    # 收尾会走两次（主循环提前收敛 + 最终收敛），历史缺陷每次往返叠加 -8h
    eng._finalize_task_status(task_id, _get_task(task_id), stop_event)
    first = _get_task(task_id)
    assert first.started_at == started_at, '收尾不得改写 started_at（写回补了 tz 的值即 -8h 漂移）'
    first_duration = first.actual_duration

    eng._finalize_task_status(task_id, _get_task(task_id), stop_event)

    task = _get_task(task_id)
    assert task.started_at == started_at
    assert task.started_at.tzinfo is None
    assert task.completed_at is not None and task.completed_at.tzinfo is None
    assert task.created_at <= task.started_at <= task.completed_at
    assert 115 <= first_duration <= 130, f'实际时长应接近 120s，实际 {first_duration}'
    assert 115 <= task.actual_duration <= first_duration + 30


# ============================================================
# 3) 派发失败补写：_execute_api_case 异常分支
# ============================================================

def test_api_dispatch_failure_fallback_writes_utc_naive(int2209_db, monkeypatch):
    from task_service.core.execution_engine.mixins import case_execution

    class _FailingAcl:
        @staticmethod
        def start_api_test(**kwargs):
            raise RuntimeError('dispatch down')

    monkeypatch.setattr(case_execution, 'api_test_acl_repository', _FailingAcl)

    task_id, tc_id = 2209003, 22090003
    created_at = _utcnow_naive() - timedelta(seconds=10)
    _seed_task(task_id, status='running', created_at=created_at)
    _seed_task_case(tc_id, task_id, created_at=created_at)

    eng = _make_engine(case_execution.CaseExecutionMixin)
    assert eng._execute_api_case(task_id, tc_id) is False

    tc = _get_task_case(tc_id)
    assert tc.started_at is not None and tc.started_at.tzinfo is None
    assert tc.completed_at is not None and tc.completed_at.tzinfo is None
    assert tc.created_at <= tc.started_at <= tc.completed_at
    assert tc.duration is not None and tc.duration >= 0
    assert tc.duration == int((tc.completed_at - tc.started_at).total_seconds())


# ============================================================
# 4) gRPC 边界：执行器上报 aware ISO8601 → 落库 UTC naive
# ============================================================

def test_update_task_case_status_normalizes_aware_iso_to_utc(int2209_db):
    from task_service.infrastructure.persistence.task_repository import task_repository

    task_id, tc_id = 2209004, 22090004
    created_at = datetime(2026, 10, 31, 1, 0, 0)
    _seed_task(task_id, status='running', created_at=created_at)
    _seed_task_case(tc_id, task_id, created_at=created_at)

    # 执行器（api_test_service）上报的是本地时间 +08:00 的 ISO 串
    ok = task_repository.update_task_case_status(
        task_id, 'int2209-case',
        execution_status='running',
        started_at='2026-10-31T09:08:32.042294+08:00',
        tc_rel_id=tc_id,
    )
    assert ok is True

    tc = _get_task_case(tc_id)
    assert tc.started_at == datetime(2026, 10, 31, 1, 8, 32, 42294)
    assert tc.started_at.tzinfo is None
    assert tc.created_at <= tc.started_at, 'TaskCase.started_at 不得晚于创建时刻 +8h'
