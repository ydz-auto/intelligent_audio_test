# -*- coding: utf-8 -*-
"""INT-337 专项：任务/用例 purge 级联下探孙代 TRD（test_result_dimensions）。

背景（INT-308 复验报告第四节）：任务 purge 的级联删除覆盖
task → task_case_relations → test_results，但未下探孙代 TRD——删除带评估
结果的任务后，test_result_dimensions 行残留，指向已不存在的 test_result
（孤儿）。评估侧 cleaner 的孤儿兜底是 24h 周期任务，purge 作为同步用户
操作须即时清理。

修复口径：trash_repository.purge_tasks / purge_testcases 在删 test_results
之前，先按本次将被删除的 test_results 下探删除其子代 TRD（子→父顺序，
同库内显式 DELETE；非 owner 过滤外的行不受影响）。

验收（原卡）：
1. purge 含评估结果（test_results + TRD）的任务后 TRD 零残留；
2. 既有 purge/删除相关单测回归通过（test_int141 全量回归）。

DB：进程级 SQLite（tests/conftest.py 注入），按需 create_all 涉及表
（TRD 归属 evaluation_service，此处一并建表），用例内自行清理，
对齐 test_int141_favorites_trash_operator.py 口径。
"""
import os

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from shared.infrastructure.user_context import set_current_user_id
from shared.models.database import (
    Base, init_db, get_engine, get_db_session, remove_db_session,
)


_TABLES = None


def _ensure_tables():
    init_db(pool_size=2)
    global _TABLES
    if _TABLES is None:
        # purge 级联链触达的全部表（关联表无行也必须在库，否则 DELETE 报
        # no such table）；TRD 归属 evaluation_service，同库一并建表
        from task_service.infrastructure.persistence.models import (
            Task, TaskTag, TaskCase, TaskDevice, TaskAPI, TaskMergeRelation,
            TestResult, Favorite, Log, TestCase, TestCaseTag,
        )
        from evaluation_service.infrastructure.persistence.models import (
            TestResultDimension,
        )
        _TABLES = [t.__table__ for t in (
            Task, TaskTag, TaskCase, TaskDevice, TaskAPI, TaskMergeRelation,
            TestResult, TestResultDimension, Favorite, Log, TestCase,
            TestCaseTag,
        )]
        Base.metadata.create_all(bind=get_engine(), tables=_TABLES)
    return _TABLES


def _cleanup_tables():
    session = get_db_session()
    try:
        # 子→父清理，避免残留影响其他用例
        for table in _TABLES:
            session.execute(table.delete())
        session.commit()
    finally:
        remove_db_session()


def _make_soft_deleted_task_with_results(task_name='INT337_任务'):
    """造任务 + task_case_relations + test_results + TRD，返回 (task_id, case_id)。

    步骤：插活跃行 → soft_delete（盖 deleted_by_user_id，满足 owner 校验）。
    TRD 挂在其中一条 test_result 下，模拟真实评估产出。
    """
    from task_service.infrastructure.persistence.models import (
        Task, TaskCase, TestResult,
    )
    from task_service.infrastructure.persistence.task_repository import (
        task_repository,
    )
    from evaluation_service.infrastructure.persistence.models import (
        TestResultDimension,
    )

    session = get_db_session()
    try:
        task = Task(name=task_name, status='completed', total_cases=2,
                    created_by_user_id=1)
        session.add(task)
        session.flush()
        session.add_all([
            TaskCase(task_id=task.id, test_case_id='INT337_CASE_A',
                     status='completed', execution_status='completed',
                     evaluation_status='completed'),
            TaskCase(task_id=task.id, test_case_id='INT337_CASE_B',
                     status='completed', execution_status='completed',
                     evaluation_status='completed'),
        ])
        session.flush()
        results = [
            TestResult(task_id=task.id, test_case_id='INT337_CASE_A',
                       algorithm_type='asr', execution_status='completed'),
            TestResult(task_id=task.id, test_case_id='INT337_CASE_B',
                       algorithm_type='asr', execution_status='completed'),
        ]
        session.add_all(results)
        session.flush()
        # SQLite 对 BIGINT 主键不做行ID自增（INT-169 同款），显式给 id
        trd = TestResultDimension(
            id=1, test_result_id=results[0].id, algorithm_type='asr',
            score=0.88, status='passed', evaluation_status='completed')
        session.add(trd)
        session.commit()
        task_id, result_id = task.id, results[0].id
    finally:
        remove_db_session()

    set_current_user_id(1)  # owner（created_by_user_id=1）
    try:
        task_repository.soft_delete(task_id)
    finally:
        set_current_user_id(None)
    return task_id, result_id


class TestPurgeTaskCascadesToTrd:
    """任务 purge：test_results + TRD 零残留（原卡验收①）。"""

    def setup_method(self):
        _ensure_tables()

    def teardown_method(self):
        _cleanup_tables()

    def test_purge_task_removes_trd_rows(self):
        from task_service.infrastructure.persistence.trash_repository import (
            trash_repository,
        )
        from task_service.infrastructure.persistence.models import (
            Task, TaskCase, TestResult,
        )
        from evaluation_service.infrastructure.persistence.models import (
            TestResultDimension,
        )

        task_id, result_id = _make_soft_deleted_task_with_results()
        # 前置：软删任务 + 结果 + TRD 均在库
        session = get_db_session()
        try:
            assert session.get(Task, task_id) is not None
            assert session.query(TestResult).filter_by(
                task_id=task_id).count() == 2
            assert session.query(TestResultDimension).filter_by(
                test_result_id=result_id).count() == 1
        finally:
            remove_db_session()

        # purge（owner=1, admin）
        purged = trash_repository.purge_tasks([task_id], user_id=1, is_admin=True)
        assert purged == 1

        # 验收：task / task_case / test_results / TRD 全链零残留
        session = get_db_session()
        try:
            assert session.get(Task, task_id) is None
            assert session.query(TaskCase).filter_by(task_id=task_id).count() == 0
            assert session.query(TestResult).filter_by(task_id=task_id).count() == 0
            assert session.query(TestResultDimension).filter_by(
                test_result_id=result_id).count() == 0
            assert session.query(TestResultDimension).count() == 0
        finally:
            remove_db_session()

    def test_purge_task_keeps_unrelated_trd(self):
        """其他任务的 TRD 不受影响（下探限定本次删除的 test_results）。"""
        from task_service.infrastructure.persistence.trash_repository import (
            trash_repository,
        )
        from evaluation_service.infrastructure.persistence.models import (
            TestResultDimension,
        )

        task_id, _ = _make_soft_deleted_task_with_results('INT337_待删任务')
        # 无关任务的结果 + TRD（不 purge）
        session = get_db_session()
        try:
            from task_service.infrastructure.persistence.models import TestResult
            other = TestResult(task_id=999999, test_case_id='INT337_CASE_X',
                               algorithm_type='asr', execution_status='completed')
            session.add(other)
            session.flush()
            other_trd = TestResultDimension(
                id=2, test_result_id=other.id, algorithm_type='asr',
                score=0.5, evaluation_status='completed')
            session.add(other_trd)
            session.commit()
            other_trd_id = other_trd.id
        finally:
            remove_db_session()

        trash_repository.purge_tasks([task_id], user_id=1, is_admin=True)

        session = get_db_session()
        try:
            assert session.get(TestResultDimension, other_trd_id) is not None
        finally:
            remove_db_session()


class TestPurgeTestcaseCascadesToTrd:
    """用例 purge：test_results + TRD 零残留（同口径下探）。"""

    def setup_method(self):
        _ensure_tables()

    def teardown_method(self):
        _cleanup_tables()

    def test_purge_testcase_removes_trd_rows(self):
        from task_service.infrastructure.persistence.models import (
            TestCase, TestResult,
        )
        from task_service.infrastructure.persistence.testcase_repository import (
            testcase_repository,
        )
        from task_service.infrastructure.persistence.trash_repository import (
            trash_repository,
        )
        from evaluation_service.infrastructure.persistence.models import (
            TestResultDimension,
        )

        session = get_db_session()
        try:
            session.add(TestCase(id='INT337_PURGE_CASE', name='用例', config={},
                                 created_by_user_id=1))
            session.flush()
            result = TestResult(task_id=1, test_case_id='INT337_PURGE_CASE',
                                algorithm_type='asr', execution_status='completed')
            session.add(result)
            session.flush()
            trd = TestResultDimension(
                id=10, test_result_id=result.id, algorithm_type='asr',
                score=0.9, evaluation_status='completed')
            session.add(trd)
            session.commit()
            result_id, trd_id = result.id, trd.id
        finally:
            remove_db_session()

        # 软删用例（owner=1）后 purge
        set_current_user_id(1)
        try:
            testcase_repository.soft_delete_testcases_by_ids(['INT337_PURGE_CASE'])
            testcase_repository.commit()
        finally:
            set_current_user_id(None)
        purged = trash_repository.purge_testcases(
            ['INT337_PURGE_CASE'], user_id=1, is_admin=True)
        assert purged == 1

        session = get_db_session()
        try:
            assert session.get(TestCase, 'INT337_PURGE_CASE') is None
            assert session.query(TestResult).filter_by(
                test_case_id='INT337_PURGE_CASE').count() == 0
            assert session.query(TestResultDimension).filter_by(
                id=trd_id).count() == 0
            assert session.query(TestResultDimension).filter_by(
                test_result_id=result_id).count() == 0
        finally:
            remove_db_session()
