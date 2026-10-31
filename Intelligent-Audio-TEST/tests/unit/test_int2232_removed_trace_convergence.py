# -*- coding: utf-8 -*-
"""INT-2232 回归守卫：移除留痕行不参与任务收敛计数与双状态派生。

缺陷（INT-305 遗漏）：用例软删留痕（``task_case_relations.error_message =
'用例已被移除'``）在以下四处未被剔除，导致「已完成任务里移除唯一失败用例后
任务仍判 failed」，与 ``task_case_stats.refresh_task_counts_atomic`` 的计数
口径（留痕行不参与任何统计）自相矛盾：

1. ``TaskFinalizeMixin._update_post_loop_status`` 的 failed/completed 计数；
2. ``TaskFinalizeMixin._finalize_task_status`` 的 failed 计数；
3. ``TaskFinalizeMixin._has_evaluating_cases`` 的评估等待判据（留痕行停在
   评估未提交态时等待循环只能靠超时兜底退出）；
4. ``task_dual_status_expr`` 的 EXISTS 聚合（徽章/筛选仍判 failed；移除的
   pending 行让 ``EXEC_ALL_TERMINAL`` 永远为假）。

验收口径：任务 2 用例（1 completed / 1 failed）→ 移除 failed 用例 →
任务 status=completed、execution_status=completed、failed_cases=0。

DB：进程级 SQLite（tests/conftest.py 注入），仅建 test_tasks /
task_case_relations，用例内自行清理，对齐 test_int2209 / test_int301 口径。
"""
import os
from datetime import datetime, timedelta, timezone

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

REMOVED_MSG = '用例已被移除'
BASE_ID = 2232000


# ============================================================
# sqlite 夹具与种子
# ============================================================

@pytest.fixture(scope='module')
def _tables():
    from shared.models.database import Base, get_engine, init_db, remove_db_session
    from task_service.infrastructure.persistence.models.task_models import Task, TaskCase

    init_db(pool_size=2)
    Base.metadata.create_all(
        bind=get_engine(), tables=[Task.__table__, TaskCase.__table__])
    _purge()
    yield
    _purge()
    remove_db_session()


@pytest.fixture()
def db(_tables):
    yield
    _purge()


def _purge():
    from shared.models.database import get_db_session, remove_db_session
    from task_service.infrastructure.persistence.models.task_models import Task, TaskCase

    session = get_db_session()
    try:
        session.query(TaskCase).filter(TaskCase.task_id >= BASE_ID).delete(
            synchronize_session=False)
        session.query(Task).filter(Task.id >= BASE_ID).delete(synchronize_session=False)
        session.commit()
    finally:
        remove_db_session()


def _utcnow_naive():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _seed_task(task_id, *, status='running'):
    from shared.models.database import get_db_session, remove_db_session
    from task_service.infrastructure.persistence.models.task_models import Task

    now = _utcnow_naive() - timedelta(seconds=60)
    session = get_db_session()
    try:
        session.add(Task(id=task_id, name=f'int2232-{task_id}', status=status,
                         total_cases=0, completed_cases=0, failed_cases=0,
                         created_at=now, updated_at=now, started_at=now))
        session.commit()
    finally:
        remove_db_session()


def _seed_case(tc_id, task_id, case_id, *, status='pending',
               execution_status='pending', evaluation_status='pending',
               error_message=None):
    from shared.models.database import get_db_session, remove_db_session
    from task_service.infrastructure.persistence.models.task_models import TaskCase

    session = get_db_session()
    try:
        session.add(TaskCase(
            id=tc_id, task_id=task_id, test_case_id=case_id, status=status,
            execution_status=execution_status, evaluation_status=evaluation_status,
            error_message=error_message))
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


def _get_case(tc_id):
    from shared.models.database import get_db_session, remove_db_session
    from task_service.infrastructure.persistence.models.task_models import TaskCase

    session = get_db_session()
    try:
        return session.get(TaskCase, tc_id)
    finally:
        remove_db_session()


class _Engine:
    """最小执行引擎组合：recount 走真实 refresh_task_counts_atomic，外部依赖打桩。"""

    def __init__(self):
        self.logs = []
        self.progress = 0

    def _log(self, **kwargs):
        self.logs.append(kwargs)

    def _emit_progress(self, *args, **kwargs):
        self.progress += 1

    def refresh_task_counts_atomic(self, task_id):
        from task_service.domain.services.task_case_stats import refresh_task_counts_atomic
        refresh_task_counts_atomic(task_id)


def _make_engine(mixin_cls):
    return type('_E', (mixin_cls, _Engine), {})()


def _seed_done_with_removed_failure(task_id):
    """验收场景：2 用例（1 completed / 1 failed 且已被移除）。"""
    _seed_task(task_id, status='running')
    _seed_case(task_id * 10 + 1, task_id, f'{task_id}-c1',
               status='completed', execution_status='completed',
               evaluation_status='completed')
    _seed_case(task_id * 10 + 2, task_id, f'{task_id}-c2',
               status='failed', execution_status='failed',
               evaluation_status='completed', error_message=REMOVED_MSG)


# ============================================================
# 1) 收敛：_finalize_task_status / _update_post_loop_status
# ============================================================

def test_finalize_converges_completed_after_removing_failed_case(db):
    """移除唯一失败用例后，最终收敛路径判 completed（缺陷 1）。"""
    import threading
    from task_service.core.execution_engine.mixins.task_finalize import TaskFinalizeMixin

    task_id = BASE_ID + 1
    _seed_done_with_removed_failure(task_id)

    eng = _make_engine(TaskFinalizeMixin)
    eng._finalize_task_status(task_id, _get_task(task_id), threading.Event())

    task = _get_task(task_id)
    assert task.status == 'completed'
    assert task.total_cases == 1
    assert task.completed_cases == 1
    assert task.failed_cases == 0
    # 留痕行不被「未处理用例标记失败」分支改写，移除语义保留
    assert _get_case(task_id * 10 + 2).error_message == REMOVED_MSG


def test_post_loop_converges_completed_after_removing_failed_case(db):
    """移除唯一失败用例后，提前收敛路径判 completed（缺陷 2）。"""
    from task_service.core.execution_engine.mixins.task_finalize import TaskFinalizeMixin

    task_id = BASE_ID + 2
    _seed_done_with_removed_failure(task_id)

    eng = _make_engine(TaskFinalizeMixin)
    task = eng._update_post_loop_status(task_id)

    assert task is not None and task.status == 'completed'
    assert task.total_cases == 1
    assert task.completed_cases == 1
    assert task.failed_cases == 0


def test_post_loop_converges_when_removed_row_left_pending(db):
    """留痕行停在 pending（移除时未执行）不阻止收敛，也不阻塞评估等待（缺陷 3）。"""
    from task_service.core.execution_engine.mixins.task_finalize import TaskFinalizeMixin

    task_id = BASE_ID + 3
    _seed_task(task_id, status='running')
    _seed_case(task_id * 10 + 1, task_id, f'{task_id}-c1',
               status='completed', execution_status='completed',
               evaluation_status='completed')
    _seed_case(task_id * 10 + 2, task_id, f'{task_id}-c2',
               status='pending', execution_status='pending',
               evaluation_status='pending', error_message=REMOVED_MSG)

    eng = _make_engine(TaskFinalizeMixin)
    task = eng._update_post_loop_status(task_id)

    assert task.status == 'completed'
    assert task.total_cases == 1


def test_has_evaluating_cases_ignores_removed_rows(db):
    """评估等待判据剔除留痕行（缺陷 3）。"""
    from shared.models.database import get_db_session, remove_db_session
    from task_service.core.execution_engine.mixins.task_finalize import TaskFinalizeMixin

    task_id = BASE_ID + 4
    _seed_task(task_id, status='running')
    _seed_case(task_id * 10 + 1, task_id, f'{task_id}-c1',
               evaluation_status='pending', error_message=REMOVED_MSG)

    eng = _make_engine(TaskFinalizeMixin)
    session = get_db_session()
    try:
        assert eng._has_evaluating_cases(task_id, session) is False
        # 对照：未移除的评估未提交行仍然判「评估中」
        _seed_case(task_id * 10 + 2, task_id, f'{task_id}-c2',
                   evaluation_status='queued')
        session.expire_all()
        assert eng._has_evaluating_cases(task_id, session) is True
    finally:
        session.close()
        remove_db_session()


# ============================================================
# 2) 双状态派生（SQL 表达式）：徽章与筛选同口径
# ============================================================

def _derive(task_id):
    from shared.models.database import get_db_session, remove_db_session
    from task_service.infrastructure.persistence.models.task_models import Task
    from task_service.infrastructure.read_models.task_dual_status_expr import (
        EXECUTION_STATUS_EXPR, EVALUATION_STATUS_EXPR,
    )

    session = get_db_session()
    try:
        row = session.query(EXECUTION_STATUS_EXPR, EVALUATION_STATUS_EXPR).filter(
            Task.id == task_id).one()
        return row[0], row[1]
    finally:
        remove_db_session()


def test_dual_status_ignores_removed_failed_row(db):
    """移除失败用例后执行徽章 completed（缺陷 4：HAS_EXEC_FAILED 不再误判）。"""
    task_id = BASE_ID + 5
    _seed_done_with_removed_failure(task_id)
    assert _derive(task_id) == ('completed', 'completed')


def test_dual_status_all_terminal_ignores_removed_pending_row(db):
    """移除的 pending 行不再让 EXEC_ALL_TERMINAL 恒为假（缺陷 4）。"""
    task_id = BASE_ID + 6
    _seed_task(task_id, status='completed')
    _seed_case(task_id * 10 + 1, task_id, f'{task_id}-c1',
               status='completed', execution_status='completed',
               evaluation_status='completed')
    _seed_case(task_id * 10 + 2, task_id, f'{task_id}-c2',
               status='pending', execution_status='pending',
               evaluation_status='pending', error_message=REMOVED_MSG)
    assert _derive(task_id) == ('completed', 'completed')


def test_execution_filter_ignores_removed_failure(db):
    """执行状态筛选与徽章同口径：移除的失败行不得命中原任务（缺陷 4）。"""
    from shared.models.database import get_db_session, remove_db_session
    from task_service.infrastructure.persistence.models.task_models import Task
    from task_service.infrastructure.read_models.task_dual_status_expr import (
        execution_filter_condition,
    )

    hit_id, miss_id = BASE_ID + 7, BASE_ID + 8
    _seed_done_with_removed_failure(hit_id)
    _seed_task(miss_id, status='completed')
    _seed_case(miss_id * 10 + 1, miss_id, f'{miss_id}-c1',
               status='completed', execution_status='completed',
               evaluation_status='completed')
    _seed_case(miss_id * 10 + 2, miss_id, f'{miss_id}-c2',
               status='failed', execution_status='failed',
               evaluation_status='completed')  # 未移除的真实失败行

    session = get_db_session()
    try:
        hit = {t.id for t in session.query(Task).filter(
            Task.id.in_([hit_id, miss_id]), execution_filter_condition('failed')).all()}
    finally:
        remove_db_session()
    assert hit == {miss_id}
