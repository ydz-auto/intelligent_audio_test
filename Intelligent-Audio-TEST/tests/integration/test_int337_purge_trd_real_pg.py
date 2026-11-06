# -*- coding: utf-8 -*-
"""INT-337 实方言验收：任务/用例 purge 孙代下探（TRD）在真实 PostgreSQL 上复核。

tests/unit/test_int337_purge_trd_cascade.py 已在 SQLite 上验证语义（含红绿：
摘除修复后 2 例失败、恢复后全绿）；本文件按 INT-364 验收同款方式（真实
Postgres 临时库，用后即删）复核生产方言行为：

- 下探 DELETE 的 IN 子查询 + expanding bindparam 在 PostgreSQL 语义一致；
- BIGSERIAL 自增主键链路（test_results.id → TRD.test_result_id）真实取号，
  不依赖 SQLite 显式 id 造数；
- 非 purge 目标（其他任务）的 test_results / TRD 不受影响。

DB：pg_db 夹具整库创建 → 全模型建表 → 用后即删（测试数据不落库外）。
"""
import uuid

import pytest

from tests.integration.test_task_execute_real_chain import (
    pg_db,       # noqa: F401  pytest 夹具（真实 Postgres 临时库，模块级，用后即删）
    storage_env, # noqa: F401  pg_db 依赖（单独运行本文件时需显式注册）
)


@pytest.fixture(autouse=True)
def _fresh_main_thread_session():
    """清主线程 session scope（同 test_int364 口径）：其他单测文件先行运行时
    会在主线程 scope 里缓存默认 engine（sqlite）绑定的 session，pg_db 的
    _SessionFactory rebind 只影响新建 session——用例前后各清一次，保证临时
    PG 库绑定生效。"""
    from shared.models.database import remove_db_session
    remove_db_session()
    yield
    remove_db_session()


def _seed_task_with_trd(task_name, soft_delete=True):
    """造任务 + 2 条 task_case + 2 条 test_results + 每结果 1 条 TRD。

    PG 上 BIGSERIAL 自增，无需显式 id。soft_delete=False 时保持活跃行
    （供「无关任务不受影响」对照）。返回 (task_id, [result_id], [trd_id])。
    """
    from task_service.infrastructure.persistence.models import (
        Task, TaskCase, TestResult,
    )
    from evaluation_service.infrastructure.persistence.models import (
        TestResultDimension,
    )
    from shared.models.database import get_db_session, remove_db_session

    session = get_db_session()
    try:
        task = Task(name=task_name, status='completed', total_cases=2,
                    created_by_user_id=1)
        session.add(task)
        session.flush()
        session.add_all([
            TaskCase(task_id=task.id, test_case_id=f'{task_name}_CASE_A',
                     execution_status='completed', evaluation_status='completed'),
            TaskCase(task_id=task.id, test_case_id=f'{task_name}_CASE_B',
                     execution_status='completed', evaluation_status='completed'),
        ])
        session.flush()
        results = [
            TestResult(task_id=task.id, test_case_id=f'{task_name}_CASE_A',
                       algorithm_type='asr', execution_status='completed'),
            TestResult(task_id=task.id, test_case_id=f'{task_name}_CASE_B',
                       algorithm_type='asr', execution_status='completed'),
        ]
        session.add_all(results)
        session.flush()
        trds = [
            TestResultDimension(test_result_id=results[0].id, algorithm_type='asr',
                                score=0.88, status='passed',
                                evaluation_status='completed'),
            TestResultDimension(test_result_id=results[1].id, algorithm_type='asr',
                                score=0.9, status='passed',
                                evaluation_status='completed'),
        ]
        session.add_all(trds)
        session.commit()
        task_id = task.id
        result_ids = [r.id for r in results]
        trd_ids = [t.id for t in trds]
    finally:
        remove_db_session()

    if soft_delete:
        from task_service.infrastructure.persistence.task_repository import (
            task_repository,
        )
        from shared.infrastructure.user_context import set_current_user_id
        set_current_user_id(1)  # owner（created_by_user_id=1）
        try:
            task_repository.soft_delete(task_id)
        finally:
            set_current_user_id(None)
    return task_id, result_ids, trd_ids


class TestPurgeTaskTrdRealPG:
    """任务 purge 孙代下探（真实 PostgreSQL 方言）。"""

    def test_purge_task_cascades_trd_zero_residue(self, pg_db):
        from task_service.infrastructure.persistence.models import (
            Task, TaskCase, TestResult,
        )
        from task_service.infrastructure.persistence.trash_repository import (
            trash_repository,
        )
        from evaluation_service.infrastructure.persistence.models import (
            TestResultDimension,
        )
        from shared.models.database import get_db_session, remove_db_session

        run = uuid.uuid4().hex[:8]
        task_id, result_ids, _ = _seed_task_with_trd(f'INT337PG_DEL_{run}')
        # 无关活跃任务：自己的结果 + TRD，purge 目标之外不受影响
        other_id, other_result_ids, other_trd_ids = _seed_task_with_trd(
            f'INT337PG_KEEP_{run}', soft_delete=False)

        purged = trash_repository.purge_tasks([task_id], user_id=1, is_admin=True)
        assert purged == 1

        session = get_db_session()
        try:
            # purge 目标全链零残留：task / task_case / test_results / TRD
            assert session.get(Task, task_id) is None
            assert session.query(TaskCase).filter_by(task_id=task_id).count() == 0
            assert session.query(TestResult).filter_by(task_id=task_id).count() == 0
            assert session.query(TestResultDimension).filter(
                TestResultDimension.test_result_id.in_(result_ids)).count() == 0
            # 无关任务链路原样保留
            assert session.get(Task, other_id) is not None
            assert session.query(TestResult).filter_by(
                task_id=other_id).count() == 2
            assert session.query(TestResultDimension).filter(
                TestResultDimension.test_result_id.in_(other_result_ids)).count() == 2
            assert [t.id for t in session.query(TestResultDimension)
                    .filter(TestResultDimension.id.in_(other_trd_ids)).all()] == other_trd_ids
        finally:
            remove_db_session()


class TestPurgeTestcaseTrdRealPG:
    """用例 purge 孙代下探（真实 PostgreSQL 方言）。"""

    def test_purge_testcase_cascades_trd_zero_residue(self, pg_db):
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
        from shared.models.database import (
            get_db_session, remove_db_session,
        )
        from shared.infrastructure.user_context import set_current_user_id

        case_id = f'INT337PG_CASE_{uuid.uuid4().hex[:8]}'
        keep_case_id = f'INT337PG_KEEP_{uuid.uuid4().hex[:8]}'
        session = get_db_session()
        try:
            session.add(TestCase(id=case_id, name='INT337PG 用例', config={},
                                 created_by_user_id=1))
            session.add(TestCase(id=keep_case_id, name='INT337PG 保留用例',
                                 config={}, created_by_user_id=1))
            session.flush()
            results = [
                TestResult(task_id=1, test_case_id=case_id,
                           algorithm_type='asr', execution_status='completed'),
                TestResult(task_id=1, test_case_id=case_id,
                           algorithm_type='asr', execution_status='completed'),
            ]
            session.add_all(results)
            session.flush()
            trds = [
                TestResultDimension(test_result_id=results[0].id,
                                    algorithm_type='asr', score=0.9,
                                    evaluation_status='completed'),
                TestResultDimension(test_result_id=results[1].id,
                                    algorithm_type='asr', score=0.85,
                                    evaluation_status='completed'),
            ]
            session.add_all(trds)
            session.flush()
            # 其他用例：自己的结果 + TRD（purge 目标之外，须原样保留）
            keep_result = TestResult(task_id=1, test_case_id=keep_case_id,
                                     algorithm_type='asr',
                                     execution_status='completed')
            session.add(keep_result)
            session.flush()
            keep_trd = TestResultDimension(test_result_id=keep_result.id,
                                           algorithm_type='asr', score=0.7,
                                           evaluation_status='completed')
            session.add(keep_trd)
            session.commit()
            result_ids = [r.id for r in results]
            keep_result_id, keep_trd_id = keep_result.id, keep_trd.id
        finally:
            remove_db_session()

        set_current_user_id(1)
        try:
            testcase_repository.soft_delete_testcases_by_ids([case_id])
            testcase_repository.commit()
        finally:
            set_current_user_id(None)

        purged = trash_repository.purge_testcases([case_id], user_id=1, is_admin=True)
        assert purged == 1

        session = get_db_session()
        try:
            assert session.get(TestCase, case_id) is None
            assert session.query(TestResult).filter_by(
                test_case_id=case_id).count() == 0
            assert session.query(TestResultDimension).filter(
                TestResultDimension.test_result_id.in_(result_ids)).count() == 0
            # 其他用例的 test_results / TRD 不动（下探限定本次删除的 test_results）
            assert session.get(TestCase, keep_case_id) is not None
            assert session.get(TestResult, keep_result_id) is not None
            assert session.get(TestResultDimension, keep_trd_id) is not None
        finally:
            remove_db_session()
