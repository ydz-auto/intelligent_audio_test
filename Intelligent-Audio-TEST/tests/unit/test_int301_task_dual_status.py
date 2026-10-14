# -*- coding: utf-8 -*-
"""INT-301 专项：任务级执行/评估双状态（评估状态与执行状态完全分离）。

覆盖：
1. derive_task_dual_status（Python 派生器）语义矩阵——评估推进（含重新评估
   evaluating/reevaluate_queued/reevaluating）只落评估侧，执行侧保持不动；
2. SQL 派生表达式（task_dual_status_expr）与 Python 派生器互锁：真实 SQLite
   种子行下两口径对每个任务输出一致，且 evaluation_status 筛选命中行 = 徽章
   展示值（展示与筛选同口径）；
3. task_read_model.search_tasks 列表行携带双状态 + 评估状态过滤分页正确。

DB：进程级 SQLite（tests/conftest.py 注入），按需 create_all，用例内自行清理，
对齐 test_int141 / test_int200 口径。
"""
import os

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from shared.models.database import (
    Base, init_db, get_engine, get_db_session, remove_db_session,
)
from shared.utils.status_utils import derive_task_dual_status


# ---------------- 1) Python 派生器语义矩阵 ----------------

def test_reevaluate_does_not_touch_execution_side():
    """重新评估流转（queued/reevaluating→终态）只落评估徽章，执行侧恒 completed。"""
    base = dict(has_exec_active=False, has_exec_failed=False, has_exec_stopped=False,
                exec_all_terminal=True, has_eval_completed=True)
    # 重评排队
    exec_s, eval_s = derive_task_dual_status('reevaluate_queued',
        has_eval_in_progress=False, has_eval_failed=False, **base)
    assert (exec_s, eval_s) == ('completed', 'evaluating')
    # 重评进行中（用例评估 queued/running）
    exec_s, eval_s = derive_task_dual_status('reevaluating',
        has_eval_in_progress=True, has_eval_failed=False, **base)
    assert (exec_s, eval_s) == ('completed', 'evaluating')
    # 重评完成收敛（全终态 completed）
    exec_s, eval_s = derive_task_dual_status('completed',
        has_eval_in_progress=False, has_eval_failed=False, **base)
    assert (exec_s, eval_s) == ('completed', 'completed')


def test_evaluating_transition_does_not_fall_into_execution_side():
    """引擎 evaluating 过渡态（执行全部完成、评估进行中）：执行徽章 completed。"""
    exec_s, eval_s = derive_task_dual_status('evaluating',
        has_exec_active=False, has_exec_failed=False, has_exec_stopped=False,
        exec_all_terminal=True, has_eval_in_progress=True, has_eval_failed=False,
        has_eval_completed=False)
    assert (exec_s, eval_s) == ('completed', 'evaluating')


def test_parallel_execution_eval_running():
    """并行模式：执行中 + 已完成用例评估进行中 → 执行 running、评估 evaluating。"""
    exec_s, eval_s = derive_task_dual_status('running',
        has_exec_active=True, has_exec_failed=False, has_exec_stopped=False,
        exec_all_terminal=False, has_eval_in_progress=True, has_eval_failed=False,
        has_eval_completed=False)
    assert (exec_s, eval_s) == ('running', 'evaluating')


def test_pending_task_and_queued_task():
    """未启动任务：双侧均 pending；排队任务：执行 queued、评估 pending。"""
    for task_status, exec_expect in (('pending', 'pending'), ('queued', 'queued')):
        exec_s, eval_s = derive_task_dual_status(task_status,
            has_exec_active=False, has_exec_failed=False, has_exec_stopped=False,
            exec_all_terminal=False, has_eval_in_progress=False, has_eval_failed=False,
            has_eval_completed=False)
        assert (exec_s, eval_s) == (exec_expect, 'pending')


def test_all_done_but_task_still_running_converges_both():
    """全部完成但任务 running 残留（引擎等待循环窗口）：双侧 completed。"""
    exec_s, eval_s = derive_task_dual_status('running',
        has_exec_active=False, has_exec_failed=False, has_exec_stopped=False,
        exec_all_terminal=True, has_eval_in_progress=False, has_eval_failed=False,
        has_eval_completed=True)
    assert (exec_s, eval_s) == ('completed', 'completed')


def test_eval_failed_and_exec_failed_boundaries():
    """执行失败优先承载失败；评估失败仅执行未失败用例上的评估失败才落评估侧。"""
    # 执行失败任务（评估未启动收口 completed）：执行 failed、评估 completed
    exec_s, eval_s = derive_task_dual_status('completed',
        has_exec_active=False, has_exec_failed=True, has_exec_stopped=False,
        exec_all_terminal=False, has_eval_in_progress=False, has_eval_failed=False,
        has_eval_completed=True)
    assert (exec_s, eval_s) == ('failed', 'completed')
    # 执行成功而评估失败：执行 completed、评估 failed
    exec_s, eval_s = derive_task_dual_status('completed',
        has_exec_active=False, has_exec_failed=False, has_exec_stopped=False,
        exec_all_terminal=True, has_eval_in_progress=False, has_eval_failed=True,
        has_eval_completed=True)
    assert (exec_s, eval_s) == ('completed', 'failed')


def test_stopped_task_eval_skipped():
    """手动停止：执行 stopped、评估 skipped（评估被中断）。"""
    exec_s, eval_s = derive_task_dual_status('stopped',
        has_exec_active=False, has_exec_failed=False, has_exec_stopped=True,
        exec_all_terminal=False, has_eval_in_progress=False, has_eval_failed=False,
        has_eval_completed=False)
    assert (exec_s, eval_s) == ('stopped', 'skipped')


def test_paused_task_execution_side():
    """暂停任务：执行 paused（评估侧 pending）。"""
    exec_s, eval_s = derive_task_dual_status('paused',
        has_exec_active=True, has_exec_failed=False, has_exec_stopped=False,
        exec_all_terminal=False, has_eval_in_progress=False, has_eval_failed=False,
        has_eval_completed=False)
    assert (exec_s, eval_s) == ('paused', 'pending')


# ---------------- 2) SQL 派生表达式 + 列表过滤（真实 SQLite） ----------------

_TASK_TABLES = None


def _ensure_task_tables():
    global _TASK_TABLES
    if _TASK_TABLES is None:
        init_db(pool_size=2)
        from task_service.infrastructure.persistence.models import (
            Task, TaskCase, TaskMergeRelation, TaskDevice, TaskAPI, Favorite,
            Tag, TaskTag, TestCase,
        )
        _TASK_TABLES = [t.__table__ for t in (
            Task, TaskCase, TaskMergeRelation, TaskDevice, TaskAPI, Favorite,
            Tag, TaskTag, TestCase,
        )]
        Base.metadata.create_all(bind=get_engine(), tables=_TASK_TABLES)
    return _TASK_TABLES


def _cleanup(tables):
    session = get_db_session()
    try:
        for table in tables:
            session.execute(table.delete())
        session.commit()
    finally:
        remove_db_session()


@pytest.fixture()
def db():
    tables = _ensure_task_tables()
    _cleanup(tables)
    yield tables
    _cleanup(tables)


def _seed(tasks_with_cases):
    """种子 [(Task, [(execution_status, evaluation_status), ...]), ...]。"""
    from task_service.infrastructure.persistence.models import TaskCase
    session = get_db_session()
    try:
        ids = []
        for task, cases in tasks_with_cases:
            session.add(task)
            session.flush()
            ids.append(task.id)
            for i, (es, evs) in enumerate(cases):
                session.add(TaskCase(task_id=task.id, test_case_id=f'{task.name}-c{i}',
                                     execution_status=es, evaluation_status=evs))
        session.commit()
        return ids
    finally:
        remove_db_session()


def _derive_all_rows():
    """SQL 派生列逐行结果（同一次查询口径）。"""
    from task_service.infrastructure.persistence.models import Task
    from task_service.infrastructure.read_models.task_dual_status_expr import (
        EXECUTION_STATUS_EXPR, EVALUATION_STATUS_EXPR,
    )
    session = get_db_session()
    try:
        rows = session.query(Task.id, Task.status, EXECUTION_STATUS_EXPR, EVALUATION_STATUS_EXPR).all()
        return {tid: (task_status, es, evs) for tid, task_status, es, evs in rows}
    finally:
        remove_db_session()


def test_sql_expr_matches_python_deriver(db):
    """SQL 派生与 Python 派生器互锁：种子全场景两口径一致。"""
    from task_service.infrastructure.persistence.models import Task

    _seed([
        # A: 执行完成 + 评估完成，任务收敛
        (Task(name='int301-a', status='completed', total_cases=1),
         [('completed', 'completed')]),
        # B: 重新评估中（引擎过渡态，用例评估 running）
        (Task(name='int301-b', status='reevaluating', total_cases=1),
         [('completed', 'running')]),
        # C: 引擎 evaluating 过渡（执行全完成、评估 calculating）
        (Task(name='int301-c', status='evaluating', total_cases=1),
         [('completed', 'calculating')]),
        # D: 并行模式（执行 running、已完成用例评估 running）
        (Task(name='int301-d', status='running', total_cases=2),
         [('completed', 'running'), ('running', 'pending')]),
        # E: 执行失败（评估未启动收口 completed）
        (Task(name='int301-e', status='completed', total_cases=1),
         [('failed', 'completed')]),
        # F: 执行成功而评估失败
        (Task(name='int301-f', status='completed', total_cases=1),
         [('completed', 'failed')]),
        # G: 手动停止（执行 stopped、评估 stopped）
        (Task(name='int301-g', status='stopped', total_cases=1),
         [('stopped', 'stopped')]),
        # H: 未启动
        (Task(name='int301-h', status='pending', total_cases=1),
         [('pending', 'pending')]),
    ])

    expected = {
        'int301-a': ('completed', 'completed'),
        'int301-b': ('completed', 'evaluating'),
        'int301-c': ('completed', 'evaluating'),
        'int301-d': ('running', 'evaluating'),
        'int301-e': ('failed', 'completed'),
        'int301-f': ('completed', 'failed'),
        'int301-g': ('stopped', 'skipped'),
        'int301-h': ('pending', 'pending'),
    }

    from task_service.infrastructure.persistence.models import Task as T, TaskCase as TC
    session = get_db_session()
    try:
        cases_by_task = {}
        for tc in session.query(TC).all():
            cases_by_task.setdefault(tc.task_id, []).append(tc)
        tasks_by_name = {t.name: t for t in session.query(T).all()}
    finally:
        remove_db_session()

    sql_map = _derive_all_rows()
    for name, (exec_expect, eval_expect) in expected.items():
        task = tasks_by_name[name]
        sql_exec, sql_eval = sql_map[task.id][1], sql_map[task.id][2]
        assert (sql_exec, sql_eval) == (exec_expect, eval_expect), (
            f'{name}: SQL=({sql_exec}, {sql_eval})')
        # Python 派生器同输入同输出
        tcs = cases_by_task[task.id]
        py_exec, py_eval = derive_task_dual_status(
            task.status,
            has_exec_active=any(tc.execution_status in ('queued', 'running') for tc in tcs),
            has_exec_failed=any(tc.execution_status == 'failed' for tc in tcs),
            has_exec_stopped=any(tc.execution_status == 'stopped' for tc in tcs),
            exec_all_terminal=bool(tcs) and all(
                tc.execution_status in ('completed', 'failed', 'stopped') for tc in tcs),
            has_eval_in_progress=any(tc.evaluation_status in ('queued', 'running', 'calculating')
                                     for tc in tcs),
            has_eval_failed=any(tc.evaluation_status == 'failed'
                                and tc.execution_status not in ('failed', 'stopped') for tc in tcs),
            has_eval_completed=any(tc.evaluation_status == 'completed' for tc in tcs),
        )
        assert (py_exec, py_eval) == (sql_exec, sql_eval), f'{name}: PY=({py_exec}, {py_eval})'


def test_search_tasks_carries_dual_status(db):
    """search_tasks 列表行携带 execution_status/evaluation_status。"""
    from task_service.infrastructure.persistence.models import Task
    from task_service.infrastructure.read_models.task_read_model import task_read_model

    _seed([
        (Task(name='INT301列表-完成', status='completed', total_cases=1),
         [('completed', 'completed')]),
        (Task(name='INT301列表-重评', status='reevaluating', total_cases=1),
         [('completed', 'running')]),
    ])

    result = task_read_model.search_tasks(page=1, per_page=10)
    by_name = {item['name']: item for item in result['items']}
    done = by_name['INT301列表-完成']
    reeval = by_name['INT301列表-重评']
    assert done['status'] == 'completed'
    assert done['execution_status'] == 'completed'
    assert done['evaluation_status'] == 'completed'
    # 重评任务：执行侧保持 completed，评估侧 evaluating——重评在列表可见
    assert reeval['execution_status'] == 'completed'
    assert reeval['evaluation_status'] == 'evaluating'


def test_search_tasks_evaluation_filter(db):
    """evaluation_status 过滤命中行与徽章展示值一致（展示/筛选同口径）。"""
    from task_service.infrastructure.persistence.models import Task
    from task_service.infrastructure.read_models.task_read_model import task_read_model

    _seed([
        (Task(name='INT301筛选-评估中', status='reevaluating', total_cases=1),
         [('completed', 'running')]),
        (Task(name='INT301筛选-全完成', status='completed', total_cases=1),
         [('completed', 'completed')]),
        (Task(name='INT301筛选-评估失败', status='completed', total_cases=1),
         [('completed', 'failed')]),
        (Task(name='INT301筛选-未启动', status='pending', total_cases=1),
         [('pending', 'pending')]),
    ])

    all_rows = task_read_model.search_tasks(page=1, per_page=50)['items']

    for value in ('pending', 'evaluating', 'completed', 'failed', 'skipped'):
        filtered = task_read_model.search_tasks(page=1, per_page=50,
                                                evaluation_status=value)['items']
        names = {i['name'] for i in filtered}
        # 过滤命中行的徽章值必须等于筛选值（口径一致）
        for item in filtered:
            assert item['evaluation_status'] == value, \
                f"筛选 {value} 命中了评估徽章为 {item['evaluation_status']} 的 {item['name']}"
        # 全量行里评估值等于筛选值的行恰好全部命中
        expected_names = {i['name'] for i in all_rows if i['evaluation_status'] == value}
        assert names == expected_names, \
            f'筛选 {value}: 命中 {names} != 展示口径 {expected_names}'

    # evaluating 过滤命中重评任务（回归验收：重评触发后列表按评估侧可见）
    evaluating = task_read_model.search_tasks(page=1, per_page=50,
                                              evaluation_status='evaluating')['items']
    assert {i['name'] for i in evaluating} == {'INT301筛选-评估中'}


def test_search_tasks_status_filter_still_works(db):
    """回归：原 status（Task.status）过滤行为不变（历史入口兼容；INT-301 F1
    UX 审计裁定执行域筛选改走 execution_status 派生参数，status 参数保留原文
    匹配语义，原始过渡态值仍按 Task.status 命中）。"""
    from task_service.infrastructure.persistence.models import Task
    from task_service.infrastructure.read_models.task_read_model import task_read_model

    _seed([
        (Task(name='INT301回归-完成', status='completed', total_cases=1),
         [('completed', 'completed')]),
        (Task(name='INT301回归-重评', status='reevaluating', total_cases=1),
         [('completed', 'running')]),
    ])

    result = task_read_model.search_tasks(page=1, per_page=10, status='reevaluating')
    names = {i['name'] for i in result['items']}
    assert names == {'INT301回归-重评'}


def test_search_tasks_execution_filter_matches_badge(db):
    """INT-301 F1（UX 审计打回）：execution_status 过滤命中行执行徽章 == 筛选值。

    锁定口径：原始 status=completed 但派生执行态=failed 的任务（评估失败拉低）
    不得被 execution_status=completed 命中；原始态与派生态错位的行按派生口径
    归类。执行域七值逐一核对「命中 == 展示」。
    """
    from task_service.infrastructure.persistence.models import Task
    from task_service.infrastructure.read_models.task_read_model import task_read_model

    _seed([
        (Task(name='INT301执行筛选-全完成', status='completed', total_cases=1),
         [('completed', 'completed')]),
        (Task(name='INT301执行筛选-执行失败', status='completed', total_cases=1),
         [('failed', 'completed')]),
        (Task(name='INT301执行筛选-执行中', status='running', total_cases=2),
         [('running', 'pending'), ('completed', 'running')]),
        (Task(name='INT301执行筛选-停止', status='stopped', total_cases=1),
         [('stopped', 'stopped')]),
        (Task(name='INT301执行筛选-排队', status='queued', total_cases=1),
         [('queued', 'pending')]),
        (Task(name='INT301执行筛选-未启动', status='pending', total_cases=1),
         [('pending', 'pending')]),
    ])

    all_rows = task_read_model.search_tasks(page=1, per_page=50)['items']

    for value in ('pending', 'queued', 'running', 'completed', 'failed', 'stopped'):
        filtered = task_read_model.search_tasks(page=1, per_page=50,
                                                execution_status=value)['items']
        names = {i['name'] for i in filtered}
        # 过滤命中行的执行徽章值必须等于筛选值（展示与筛选同口径）
        for item in filtered:
            assert item['execution_status'] == value, \
                f"执行筛选 {value} 命中了执行徽章为 {item['execution_status']} 的 {item['name']}"
        expected_names = {i['name'] for i in all_rows if i['execution_status'] == value}
        assert names == expected_names, \
            f'执行筛选 {value}: 命中 {names} != 展示口径 {expected_names}'

    # 关键错位场景：原始 status=completed 但执行徽章 failed 的任务不被
    # execution_status=completed 命中（原始态裸匹配的历史缺陷锁定）
    completed_hit = {i['name'] for i in task_read_model.search_tasks(
        page=1, per_page=50, execution_status='completed')['items']}
    assert 'INT301执行筛选-执行失败' not in completed_hit
    assert 'INT301执行筛选-全完成' in completed_hit


def test_execution_filter_legacy_status_param_unchanged(db):
    """回归锁定：status 参数与 execution_status 参数语义并存不互染。

    status='completed'（原始态）命中原始态行；execution_status='failed'
    （派生态）命中派生执行失败行——两参数同传时取交集（AND）。
    """
    from task_service.infrastructure.persistence.models import Task
    from task_service.infrastructure.read_models.task_read_model import task_read_model

    _seed([
        (Task(name='INT301并存-原始完成执行失败', status='completed', total_cases=1),
         [('failed', 'completed')]),
        (Task(name='INT301并存-全完成', status='completed', total_cases=1),
         [('completed', 'completed')]),
    ])

    both = task_read_model.search_tasks(
        page=1, per_page=10, status='completed', execution_status='failed')['items']
    assert {i['name'] for i in both} == {'INT301并存-原始完成执行失败'}


def test_detail_read_model_carries_dual_status(db):
    """find_by_id_with_relations 详情行携带双状态。"""
    from task_service.infrastructure.persistence.models import Task
    from task_service.infrastructure.read_models.task_read_model import task_read_model

    (tid,) = _seed([
        (Task(name='INT301详情', status='reevaluating', total_cases=1),
         [('completed', 'running')]),
    ])

    detail = task_read_model.find_by_id_with_relations(tid)
    assert detail is not None
    assert detail['status'] == 'reevaluating'
    assert detail['execution_status'] == 'completed'
    assert detail['evaluation_status'] == 'evaluating'
