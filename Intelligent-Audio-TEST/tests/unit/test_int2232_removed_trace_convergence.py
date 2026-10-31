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

返工轮（测试打回）补齐两处：
1. 移除链路 ``task_lifecycle_service.remove_case`` 原先只重算计数、不回写
   ``Task.status``，终态任务移除唯一失败用例后 stored status 仍是 failed
   （``/tasks/stats`` 按 stored status 分组 → 页面统计与徽章互相矛盾）；
2. 用例被全部移除（INT-305 允许删到为空）时 ``EXEC_ALL_TERMINAL`` 恒为假，
   徽章从 completed 退化为 pending —— 空任务改按任务终态派生（SQL 与
   Python 派生器同口径）。

DB：进程级 SQLite（tests/conftest.py 注入），仅建 test_tasks /
task_case_relations / test_results，用例内自行清理，对齐 test_int2209 /
test_int301 口径。
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
    from task_service.infrastructure.persistence.models.result_models import TestResult

    init_db(pool_size=2)
    Base.metadata.create_all(
        bind=get_engine(),
        tables=[Task.__table__, TaskCase.__table__, TestResult.__table__])
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


# ============================================================
# 3) 返工轮：移除链路回写任务状态（打回失败项 1）
# ============================================================

def _remove_via_service(task_id, case_id):
    """走真实 remove_case 服务链（跨服务审计/报告重算打桩）。"""
    from task_service.application.task.task_lifecycle_service import TaskLifecycleService

    svc = TaskLifecycleService()
    svc._check_control_visible = lambda task: None
    svc._publish_removal_audit = lambda *a, **k: None
    svc._trigger_report_recalculate = lambda tid: False
    return svc.remove_case(task_id, case_id)


def test_remove_case_converges_failed_task_to_completed(db):
    """卡面验收：终态任务移除唯一失败用例 → stored status=completed（失败项 1）。

    移除链路原先只重算计数不回写 Task.status，/tasks/stats 按 stored status
    分组仍计「执行失败 1」，与任务行 completed 徽章 + 1/1/0 计数矛盾。
    """
    task_id = BASE_ID + 11
    _seed_task(task_id, status='failed')
    _seed_case(task_id * 10 + 1, task_id, f'{task_id}-c1',
               status='completed', execution_status='completed',
               evaluation_status='completed')
    _seed_case(task_id * 10 + 2, task_id, f'{task_id}-c2',
               status='failed', execution_status='failed',
               evaluation_status='completed')
    from task_service.domain.services.task_case_stats import refresh_task_counts_atomic
    refresh_task_counts_atomic(task_id)

    result = _remove_via_service(task_id, f'{task_id}-c2')
    assert result['success'] is True

    task = _get_task(task_id)
    assert task.status == 'completed'
    assert (task.total_cases, task.completed_cases, task.failed_cases) == (1, 1, 0)
    assert _derive(task_id) == ('completed', 'completed')
    # 留痕行保留（INT-305 审计语义不被回写覆盖）
    assert _get_case(task_id * 10 + 2).error_message == REMOVED_MSG


def test_remove_case_keeps_failed_when_another_failed_case_remains(db):
    """对照：仍有未移除的失败用例时任务保持 failed（不误判 completed）。"""
    task_id = BASE_ID + 12
    _seed_task(task_id, status='failed')
    _seed_case(task_id * 10 + 1, task_id, f'{task_id}-c1',
               status='failed', execution_status='failed',
               evaluation_status='completed')
    _seed_case(task_id * 10 + 2, task_id, f'{task_id}-c2',
               status='failed', execution_status='failed',
               evaluation_status='completed')

    result = _remove_via_service(task_id, f'{task_id}-c2')
    assert result['success'] is True
    assert _get_task(task_id).status == 'failed'
    assert _derive(task_id)[0] == 'failed'


def test_remove_case_preserves_stopped_task_status(db):
    """停止语义不被移除改写：stopped 任务移除用例后仍为 stopped。"""
    task_id = BASE_ID + 13
    _seed_task(task_id, status='stopped')
    _seed_case(task_id * 10 + 1, task_id, f'{task_id}-c1',
               status='failed', execution_status='stopped',
               evaluation_status='stopped')

    result = _remove_via_service(task_id, f'{task_id}-c1')
    assert result['success'] is True
    assert _get_task(task_id).status == 'stopped'


# ============================================================
# 4) 返工轮：移除最后一个用例后的空任务口径（打回失败项 2）
# ============================================================

def test_dual_status_empty_completed_task_not_pending(db):
    """移除最后一个用例：空任务沿任务终态，徽章不得退化为 pending（失败项 2）。"""
    task_id = BASE_ID + 14
    _seed_task(task_id, status='completed')
    _seed_case(task_id * 10 + 1, task_id, f'{task_id}-c1',
               status='completed', execution_status='completed',
               evaluation_status='completed')

    result = _remove_via_service(task_id, f'{task_id}-c1')
    assert result['success'] is True

    task = _get_task(task_id)
    assert (task.total_cases, task.completed_cases, task.failed_cases) == (0, 0, 0)
    assert task.status == 'completed'
    assert _derive(task_id) == ('completed', 'completed')


def test_dual_status_empty_stopped_task_falls_back(db):
    """空任务兜底同样覆盖 stopped / failed 终态（口径与任务 stored status 一致）。"""
    completed_id, stopped_id = BASE_ID + 15, BASE_ID + 16
    for task_id, status in ((completed_id, 'completed'), (stopped_id, 'stopped')):
        _seed_task(task_id, status=status)
        _seed_case(task_id * 10 + 1, task_id, f'{task_id}-c1',
                   status='completed', execution_status='completed',
                   evaluation_status='completed', error_message=REMOVED_MSG)

    assert _derive(completed_id) == ('completed', 'completed')
    assert _derive(stopped_id) == ('stopped', 'skipped')


def test_dual_status_empty_failed_task_keeps_failed(db):
    """兜底不掩盖失败：仅剩留痕行的 failed 任务执行侧仍 failed。"""
    task_id = BASE_ID + 17
    _seed_task(task_id, status='failed')
    _seed_case(task_id * 10 + 1, task_id, f'{task_id}-c1',
               status='failed', execution_status='failed',
               evaluation_status='completed', error_message=REMOVED_MSG)

    assert _derive(task_id) == ('failed', 'skipped')


def test_derive_dual_status_empty_cases_falls_back_to_task_status():
    """Python 派生器与 SQL 同构：has_cases=False 时按任务终态派生。"""
    from shared.utils.status_utils import derive_task_dual_status

    empty = dict(has_exec_active=False, has_exec_failed=False, has_exec_stopped=False,
                 exec_all_terminal=False, has_eval_in_progress=False,
                 has_eval_failed=False, has_eval_completed=False, has_cases=False)
    assert derive_task_dual_status('completed', **empty) == ('completed', 'completed')
    assert derive_task_dual_status('failed', **empty) == ('failed', 'skipped')
    assert derive_task_dual_status('stopped', **empty) == ('stopped', 'skipped')
    # 对照：非终态任务保持 pending；has_cases=True 保持旧口径（不混淆「全 pending」）
    assert derive_task_dual_status('running', **empty) == ('pending', 'pending')
    assert derive_task_dual_status('completed', **{**empty, 'has_cases': True}) == \
        ('pending', 'pending')


def test_execution_filter_empty_completed_task_matches_completed(db):
    """空任务筛选同口径：completed 筛选命中、failed 不命中。"""
    from shared.models.database import get_db_session, remove_db_session
    from task_service.infrastructure.persistence.models.task_models import Task
    from task_service.infrastructure.read_models.task_dual_status_expr import (
        execution_filter_condition,
    )

    task_id = BASE_ID + 18
    _seed_task(task_id, status='completed')
    _seed_case(task_id * 10 + 1, task_id, f'{task_id}-c1',
               status='completed', execution_status='completed',
               evaluation_status='completed', error_message=REMOVED_MSG)

    session = get_db_session()
    try:
        matched_completed = session.query(Task).filter(
            Task.id == task_id, execution_filter_condition('completed')).count()
        matched_failed = session.query(Task).filter(
            Task.id == task_id, execution_filter_condition('failed')).count()
    finally:
        remove_db_session()
    assert (matched_completed, matched_failed) == (1, 0)
