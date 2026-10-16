# -*- coding: utf-8 -*-
"""VEGA-49 防回归（审计 P1）：``committed_rows`` 收尾必须先删引用方再删被引用方。

审计实测的竞态：``_delete_committed_rows`` 原先按 id 删 test_tasks / test_cases，
而 ``logs`` 表有指向这两张表的外键且**无 ON DELETE CASCADE**，后台 log_worker
线程恰好会为这些用例写带 ``task_id`` 的日志行。只要刷盘边界落在"首条带 task_id
的日志入队"到"收尾 DELETE 开始"之间（实测窗口 20–35ms，刷盘周期 1.0s），
DELETE 就抛 ForeignKeyViolation —— 断言全过却在 teardown 报 ERROR。

本文件的用例把那条 logs 行**在测试体内 commit**，即把"刚好刷盘"这个概率前提变成
确定性前提：修复前 teardown 必抛 ForeignKeyViolation，修复后必过。不靠"多跑 N 轮
碰概率"（对 2–3% 的抖动只有约一半把握命中）。
"""
from datetime import datetime


def _log_row(**kwargs):
    """构造一条 logs 行（等价于 log_worker 落库的那一条）。"""
    from backend.models.models import Log

    return Log(
        time=datetime.now(),
        level='INFO',
        category='Task',
        module='log_worker',
        source='backend',
        content='VEGA-49 P1 防回归：引用本测试 commit 的行的日志',
        **kwargs,
    )


def _seed_task_case_group(group_id, case_id):
    """建一个"本测试自己 commit 的"分组/用例/任务，返回 (task, case, group)。"""
    from backend.models.database import db
    from backend.models.models import Task, TestCase, TestCaseGroup

    group = TestCaseGroup(id=group_id, name='分组')
    case = TestCase(id=case_id, name='用例', group_id=group.id, config={})
    task = Task(name='任务', type='api', status='running', total_cases=1, config={})
    db.session.add_all([group, case, task])
    db.session.commit()
    return task, case, group


def _insert_late_log(task_id):
    """用一条**独立连接**插入日志行（后台线程就是这么写的，不受本测试事务影响）。"""
    from sqlalchemy import create_engine

    import conftest
    from backend.models.models import Log

    engine = create_engine(conftest._get_test_database_uri())
    try:
        with engine.begin() as conn:
            conn.execute(
                Log.__table__.insert().values(
                    time=datetime.now(),
                    level='INFO',
                    category='Task',
                    module='log_worker',
                    source='backend',
                    content='VEGA-49 P1：中途落下的日志行',
                    task_id=task_id,
                )
            )
    finally:
        engine.dispose()


def test_teardown_deletes_logs_pointing_at_committed_task(committed_rows):
    """logs.task_id → test_tasks 的引用必须先被删（否则收尾撞 logs_task_id_fkey）。

    通过判据就是 **teardown 不报 ERROR**：fixture 收尾在测试函数返回之后执行，
    修复前这里必然是 `ForeignKeyViolation: logs_task_id_fkey`。
    """
    from backend.app import create_app
    from backend.models.database import db
    from backend.models.models import Log

    app = create_app("testing")
    with app.app_context():
        try:
            task, _case, _group = _seed_task_case_group("g-fk-1", "tc-fk-1")
            committed_rows(task_id=task.id, case_ids=["tc-fk-1"], group_ids=["g-fk-1"])

            db.session.add(_log_row(task_id=task.id))
            db.session.commit()
            # 前置条件必须成立，否则收尾无从撞外键、本用例会空过
            assert db.session.query(Log).filter(Log.task_id == task.id).count() == 1
        finally:
            db.session.remove()


def test_teardown_deletes_logs_pointing_at_committed_case(committed_rows):
    """logs.test_case_id → test_cases 的引用同样必须先删。"""
    from backend.app import create_app
    from backend.models.database import db
    from backend.models.models import Log

    app = create_app("testing")
    with app.app_context():
        try:
            task, _case, _group = _seed_task_case_group("g-fk-2", "tc-fk-2")
            committed_rows(task_id=task.id, case_ids=["tc-fk-2"], group_ids=["g-fk-2"])

            # 只带 test_case_id：删 test_cases 时同样会撞 logs_test_case_id_fkey
            db.session.add(_log_row(test_case_id="tc-fk-2"))
            db.session.commit()
            assert db.session.query(Log).filter(Log.test_case_id == "tc-fk-2").count() == 1
        finally:
            db.session.remove()


def test_cleanup_removes_logs_and_target_rows_together(committed_rows):
    """显式跑一遍收尾：logs 与本测试的行都必须消失，不留残留。

    上面两个用例只能证明"收尾没报错"；这里直接调 ``_delete_committed_rows``，
    把"引用方和被引用方都真的删掉了"也钉住。
    """
    import conftest
    from backend.app import create_app
    from backend.models.database import db
    from backend.models.models import Log, Task, TaskCase, TestCase, TestCaseGroup

    app = create_app("testing")
    with app.app_context():
        try:
            task, _case, _group = _seed_task_case_group("g-fk-3", "tc-fk-3")
            committed_rows(task_id=task.id, case_ids=["tc-fk-3"], group_ids=["g-fk-3"])
            task_id = task.id

            db.session.add(TaskCase(task_id=task_id, test_case_id="tc-fk-3"))
            db.session.add(_log_row(task_id=task_id))
            db.session.add(_log_row(test_case_id="tc-fk-3"))
            db.session.commit()
        finally:
            db.session.remove()

        conftest._delete_committed_rows(
            {'task_ids': [task_id], 'case_ids': ['tc-fk-3'], 'group_ids': ['g-fk-3']}
        )

        assert db.session.query(Log).filter(
            (Log.task_id == task_id) | (Log.test_case_id == 'tc-fk-3')
        ).count() == 0
        assert db.session.query(TaskCase).filter(TaskCase.task_id == task_id).count() == 0
        assert db.session.query(Task).filter(Task.id == task_id).count() == 0
        assert db.session.query(TestCase).filter(TestCase.id == 'tc-fk-3').count() == 0
        assert db.session.query(TestCaseGroup).filter(
            TestCaseGroup.id == 'g-fk-3'
        ).count() == 0


def test_cleanup_retries_when_a_log_row_lands_mid_sequence(monkeypatch, committed_rows):
    """后台线程在两条语句之间又落一条引用行时，收尾必须重跑而不是报错。

    直接构造那次交错：第一次执行到 logs 语句之后，往 logs 补一条引用本任务的日志行
    （模拟后台线程的刷盘正好落在窗口里），第二次执行才真正删干净。
    修复前（无重试）这里会抛 ForeignKeyViolation。
    """
    import conftest
    from backend.app import create_app
    from backend.models.database import db
    from backend.models.models import Log, Task, TestCase, TestCaseGroup

    app = create_app("testing")
    with app.app_context():
        try:
            task, _case, _group = _seed_task_case_group("g-fk-4", "tc-fk-4")
            committed_rows(task_id=task.id, case_ids=["tc-fk-4"], group_ids=["g-fk-4"])
            task_id = task.id

            state = {'injected': False}
            real_execute = conftest._execute_cleanup_statements

            def _execute_with_late_log(conn, statements):
                # 逐条执行，并在 logs 刚删完、test_tasks 还没删的那个瞬间插进一行
                # （后台线程的刷盘落在这个窗口里就是审计实测的交错）
                for statement in statements:
                    conn.execute(statement)
                    if not state['injected'] and getattr(statement.table, 'name', '') == 'logs':
                        state['injected'] = True
                        _insert_late_log(task_id)

            monkeypatch.setattr(conftest, '_execute_cleanup_statements', _execute_with_late_log)
            conftest._delete_committed_rows(
                {'task_ids': [task_id], 'case_ids': ['tc-fk-4'], 'group_ids': ['g-fk-4']}
            )
            monkeypatch.undo()

            assert state['injected'] is True, '用例没有真的构造出"中途落行"的交错'
            assert db.session.query(Log).filter(Log.task_id == task_id).count() == 0
            assert db.session.query(Task).filter(Task.id == task_id).count() == 0
            assert db.session.query(TestCase).filter(TestCase.id == 'tc-fk-4').count() == 0
            assert db.session.query(TestCaseGroup).filter(
                TestCaseGroup.id == 'g-fk-4'
            ).count() == 0
        finally:
            db.session.remove()
