# -*- coding: utf-8 -*-
"""INT-161 验收补充（测试工程师）：失败链真库集成——写路径→收敛判定→计数聚合。

开发者单测（test_int161_api_failure_task_aggregation.py）以 MagicMock 桩覆盖了
api_test_service 两处失败路径的补写/发布语义与 _on_case_event 的调度顺序；
本文件补齐其未覆盖的真库链路（均针对原缺陷任务行 0/0/0 卡 running 的回归点）：

1. task_service 侧用例状态写路径（update_task_case_status，gRPC servicer 同款
   实现）：失败补写后复合状态推导落 failed、error_message/completed_at 落库；
2. 事件侧 _on_case_event → 真实 refresh_task_counts_atomic（原生 SQL 原子聚合）
   → test_tasks 行 failed_cases/completed_cases 收敛；
3. 主循环收敛判定 _active_cases_snapshot：修复后失败用例（execution=failed/
   evaluation=completed）不再计入活跃集合——主循环下一拍即可退出；
   对照组保留原缺陷机制反证（evaluation 停留 pending 会被计入活跃集合死等），
   锁定 ACTIVE_EVALUATION_STATUSES 语义，防止后续改动重开死等。

隔离方式：sqlite 内存库（StaticPool）建 Task/TaskCase/TestResult 三表，
不触 gRPC / Redis；ACL 层为 gRPC 传输设施，由开发者单测桩覆盖，不在本文件范围。
"""
import os
from datetime import datetime

# BaseConfig 在 import 时校验环境变量（纯单测不触库，与仓库既有测试同款兜底）
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import shared.models.database as shared_database
import task_service.core.execution_engine.mixins.evaluation_arbiter as arbiter_module
import task_service.infrastructure.persistence._task_case_stats_mixin as stats_mixin_module
from shared.models.database import Base
from shared.utils.status_constants import (
    EvaluationStatus, ExecutionStatus, TaskCaseStatus,
)
from task_service.core.execution_engine import ExecutionEngine
from task_service.core.execution_engine.mixins.evaluation_arbiter import EvaluationArbiterMixin
from task_service.infrastructure.persistence._task_case_stats_mixin import TaskCaseStatsMixin
from task_service.infrastructure.persistence.models import Task, TaskCase, TestResult

TASK_ID = 420161
REAL_FAIL_MESSAGE = '找不到API配置'


def _build_db(monkeypatch):
    """独立 sqlite 内存库 + 打桩三个模块级 DB 入口，返回 session 工厂。"""
    engine = create_engine(
        'sqlite://',
        connect_args={'check_same_thread': False},
        poolclass=StaticPool)
    Base.metadata.create_all(bind=engine, tables=[
        Task.__table__, TaskCase.__table__, TestResult.__table__])
    factory = sessionmaker(bind=engine)
    # refresh_task_counts_atomic 函数体内 from ... import get_engine → 补源头
    monkeypatch.setattr(shared_database, 'get_engine', lambda: engine)
    monkeypatch.setattr(stats_mixin_module, 'get_db_session', factory)
    monkeypatch.setattr(arbiter_module, 'get_db_session', factory)
    return factory


def _seed_stuck_task(factory, evaluation_status='completed'):
    """复现原缺陷形态：任务行 running 0/0/0，用例执行已失败（评估态可参数化）。"""
    session = factory()
    try:
        session.add(Task(id=TASK_ID, name='API 任务', status='running',
                         total_cases=1, completed_cases=0, failed_cases=0))
        session.add(TaskCase(task_id=TASK_ID, test_case_id='case-1',
                             status='failed', execution_status='failed',
                             evaluation_status=evaluation_status,
                             error_message=REAL_FAIL_MESSAGE,
                             completed_at=datetime(2026, 10, 12, 11, 39, 30)))
        session.commit()
    finally:
        session.close()


class TestTaskCaseWritePathTerminal:
    """task_service 侧写路径（gRPC servicer 同款 update_task_case_status）。"""

    def test_failure_write_lands_terminal_and_reason(self, monkeypatch):
        """_fail_tc_rel 同款实参经真实写路径：复合状态/原因/完成时间落库。"""
        factory = _build_db(monkeypatch)
        _seed_stuck_task(factory)

        TaskCaseStatsMixin().update_task_case_status(
            task_id=TASK_ID, case_id='case-1',
            status=TaskCaseStatus.FAILED,
            execution_status=ExecutionStatus.FAILED,
            evaluation_status=EvaluationStatus.COMPLETED,
            error_message=REAL_FAIL_MESSAGE,
            started_at='2026-10-12T11:39:24+08:00',
            completed_at='2026-10-12T11:39:25+08:00')

        session = factory()
        try:
            tc = session.query(TaskCase).filter_by(test_case_id='case-1').one()
            assert tc.execution_status == 'failed'
            assert tc.evaluation_status == 'completed'
            assert tc.status == 'failed'
            assert tc.error_message == REAL_FAIL_MESSAGE
            assert tc.completed_at is not None
        finally:
            session.close()

    def test_failure_write_without_status_derives_failed(self, monkeypatch):
        """未显式传 status 时由 execution/evaluation 推导：failed+completed → failed。"""
        factory = _build_db(monkeypatch)
        _seed_stuck_task(factory)

        TaskCaseStatsMixin().update_task_case_status(
            task_id=TASK_ID, case_id='case-1',
            execution_status=ExecutionStatus.FAILED,
            evaluation_status=EvaluationStatus.COMPLETED,
            error_message=REAL_FAIL_MESSAGE)

        session = factory()
        try:
            tc = session.query(TaskCase).filter_by(test_case_id='case-1').one()
            assert tc.status == 'failed'
        finally:
            session.close()


class TestEventSideCountAggregation:
    """事件侧 _on_case_event → 真实 refresh_task_counts_atomic → 任务行计数。"""

    def test_case_failed_event_aggregates_task_row(self, monkeypatch):
        """原缺陷直接回归点：任务行从 0/0/0 聚合出 failed_cases=1。"""
        import threading
        factory = _build_db(monkeypatch)
        _seed_stuck_task(factory, evaluation_status='completed')

        stub = SimpleNamespaceStub()
        stub.refreshed = []
        wakeup = threading.Event()
        stub.task_completion_events[TASK_ID] = wakeup
        # 包装真实静态方法：既记录调用，计数聚合又走与生产同一条原生 UPDATE
        real_refresh = ExecutionEngine.refresh_task_counts_atomic

        def _recording_refresh(task_id):
            stub.refreshed.append(task_id)
            real_refresh(task_id)

        stub.refresh_task_counts_atomic = _recording_refresh
        ExecutionEngine._on_case_event(stub, {
            'task_id': str(TASK_ID), 'test_case_id': 'case-1', 'success': False})

        assert stub.refreshed == [TASK_ID]
        assert wakeup.is_set()
        session = factory()
        try:
            task = session.get(Task, TASK_ID)
            assert task.failed_cases == 1
            assert task.completed_cases == 0
        finally:
            session.close()

    def test_refresh_is_idempotent_on_repeated_events(self, monkeypatch):
        """重复事件（重放/多服务发布）幂等：计数不累加、结果稳定。"""
        factory = _build_db(monkeypatch)
        _seed_stuck_task(factory, evaluation_status='completed')

        refresh = ExecutionEngine.refresh_task_counts_atomic
        refresh(TASK_ID)
        refresh(TASK_ID)

        session = factory()
        try:
            task = session.get(Task, TASK_ID)
            assert task.failed_cases == 1
            assert task.completed_cases == 0
        finally:
            session.close()


class TestConvergenceDecision:
    """主循环收敛判定：修复后失败用例不再计入活跃集合（对照机制反证锁定）。"""

    def _snapshot_actives(self, factory):
        snapshot = EvaluationArbiterMixin._active_cases_snapshot(None, TASK_ID)
        return EvaluationArbiterMixin._count_snapshot_actives(snapshot)

    def test_failed_case_not_in_active_snapshot(self, monkeypatch):
        """修复后用例终态（failed+completed）→ 活跃集合空 → 主循环下一拍退出。"""
        factory = _build_db(monkeypatch)
        _seed_stuck_task(factory, evaluation_status='completed')
        assert self._snapshot_actives(factory) == (0, 0)

    def test_pending_evaluation_counts_as_active(self, monkeypatch):
        """机制反证锁定：evaluation 停留 pending 会被计入活跃集合（原缺陷死等根因）。

        修复的正确性依赖此前提：失败路径必须补写评估终态，否则本判定恒为
        有活跃 → 死等。若 ACTIVE_EVALUATION_STATUSES 语义变化，此处显式暴露。
        """
        factory = _build_db(monkeypatch)
        _seed_stuck_task(factory, evaluation_status='pending')
        assert self._snapshot_actives(factory) == (0, 1)


class SimpleNamespaceStub:
    """_on_case_event 的最小宿主：其余行为记录为元组列表。"""

    def __init__(self):
        self.task_completion_events = {}
        self.completion_woken = []

    def _emit_progress(self, task_id, force=False):
        self.completion_woken.append(('progress', task_id, force))

    def trigger_scheduler_check(self):
        self.completion_woken.append(('scheduler',))
