# -*- coding: utf-8 -*-
"""INT-148 缺陷#2 回归：failed/stopped 任务重启清理残留 TestResult。

原缺陷：V9.7.10 重启将关联 TestResult 重置 pending；V9.7.31 重启路径
（reset_task_for_start）仅重置 TaskCase，TestResult 残留旧行——执行/评估
提交侧（SubmitResult）为无条件 INSERT，重跑后同一 (task_id, test_case_id)
出现重复/脏结果行。

修复语义（本文件覆盖）：
- reset_task_for_start 在重置 TaskCase 的同一事务内删除该任务全部
  TestResult（与 retry 路径未完成用例的清理语义 preserve_test_result=False
  对齐——重跑将以 INSERT 产生全新结果行）；
- 提交后清理 case_pcm 旧文件，防旧残留干扰新一轮采集。

隔离方式：独立 sqlite 内存库建 Task/TaskCase/TestResult 三表
（与 test_int161 启动恢复测试同款隔离）；pcm 清理以 monkeypatch 记录调用。
"""
import os

# BaseConfig 在 import 时校验环境变量（测试环境无 .env），先补齐必需项
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import task_service.infrastructure.persistence._task_lifecycle_mixin as lifecycle_module
from task_service.infrastructure.persistence._task_lifecycle_mixin import TaskLifecycleMixin
from task_service.infrastructure.persistence.models import Task, TaskCase, TestResult


def _build_session(monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    engine = create_engine(
        'sqlite://',
        connect_args={'check_same_thread': False},
        poolclass=StaticPool)
    from shared.models.database import Base
    Base.metadata.create_all(bind=engine, tables=[
        Task.__table__, TaskCase.__table__, TestResult.__table__])
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr(lifecycle_module, 'get_db_session', factory)
    return factory


def _seed_failed_task(factory):
    """failed 任务：两个用例各带一条终态 TestResult + 计数残留。"""
    session = factory()
    try:
        session.add(Task(id=420, name='失败任务', status='failed',
                         total_cases=2, completed_cases=1, failed_cases=1,
                         started_at=None, completed_at=None))
        session.add(TaskCase(task_id=420, test_case_id='case-1',
                             status='completed', execution_status='completed',
                             evaluation_status='completed'))
        session.add(TaskCase(task_id=420, test_case_id='case-2',
                             status='failed', execution_status='failed',
                             evaluation_status='failed',
                             error_message='API 等待超时'))
        session.add(TestResult(task_id=420, test_case_id='case-1',
                               execution_status='completed',
                               algorithm_result={'rounds': []}))
        session.add(TestResult(task_id=420, test_case_id='case-2',
                               execution_status='failed',
                               error_message='API 等待超时'))
        session.commit()
    finally:
        session.close()


class TestResetTaskForStartClearsTestResults:
    """重启路径 TestResult 清理（INT-148 缺陷#2 核心回归）。"""

    def test_reset_deletes_all_test_results_and_resets_cases(self, monkeypatch):
        factory = _build_session(monkeypatch)
        _seed_failed_task(factory)
        monkeypatch.setattr(TaskLifecycleMixin, '_cleanup_case_pcm_dirs',
                            staticmethod(lambda task_id, case_ids: None))
        repo = TaskLifecycleMixin()

        assert repo.reset_task_for_start(420) is True

        session = factory()
        try:
            # 关键回归点：TestResult 旧行全部删除，重跑 INSERT 不再产生重复行
            remaining = session.query(TestResult).filter_by(task_id=420).all()
            assert remaining == []

            task = session.get(Task, 420)
            assert task.status == 'pending'
            assert task.completed_cases == 0
            assert task.failed_cases == 0

            cases = session.query(TaskCase).filter_by(task_id=420).all()
            assert len(cases) == 2
            for tc in cases:
                assert tc.execution_status == 'pending'
                assert tc.evaluation_status == 'pending'
                assert tc.error_message is None
        finally:
            session.close()

    def test_reset_cleans_case_pcm_dirs_after_commit(self, monkeypatch):
        factory = _build_session(monkeypatch)
        _seed_failed_task(factory)
        pcm_calls = []
        monkeypatch.setattr(TaskLifecycleMixin, '_cleanup_case_pcm_dirs',
                            staticmethod(lambda task_id, case_ids: pcm_calls.append((task_id, case_ids))))
        repo = TaskLifecycleMixin()

        assert repo.reset_task_for_start(420) is True

        assert pcm_calls == [(420, ['case-1', 'case-2'])]

    def test_reset_missing_task_returns_false(self, monkeypatch):
        factory = _build_session(monkeypatch)
        monkeypatch.setattr(TaskLifecycleMixin, '_cleanup_case_pcm_dirs',
                            staticmethod(lambda task_id, case_ids: None))
        repo = TaskLifecycleMixin()

        assert repo.reset_task_for_start(9999) is False

    def test_task_without_results_still_resets(self, monkeypatch):
        """无 TestResult 的任务重启正常重置（清理为空操作）。"""
        factory = _build_session(monkeypatch)
        session = factory()
        try:
            session.add(Task(id=421, name='停止任务', status='stopped',
                             total_cases=1, completed_cases=0, failed_cases=1))
            session.add(TaskCase(task_id=421, test_case_id='case-9',
                                 status='stopped', execution_status='stopped',
                                 evaluation_status='stopped'))
            session.commit()
        finally:
            session.close()
        pcm_calls = []
        monkeypatch.setattr(TaskLifecycleMixin, '_cleanup_case_pcm_dirs',
                            staticmethod(lambda task_id, case_ids: pcm_calls.append((task_id, case_ids))))
        repo = TaskLifecycleMixin()

        assert repo.reset_task_for_start(421) is True

        session = factory()
        try:
            assert session.query(TestResult).filter_by(task_id=421).count() == 0
            assert session.get(Task, 421).status == 'pending'
        finally:
            session.close()
        assert pcm_calls == [(421, ['case-9'])]
