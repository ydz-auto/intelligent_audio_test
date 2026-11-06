# -*- coding: utf-8 -*-
"""INT-161 回归：API 用例失败后任务级计数/状态聚合与启动恢复信息保全。

原缺陷（INT-95 第 7 轮主链实机验收）：API 任务用例执行即败（如「找不到API配置」）
时，api_test_service 失败路径只回写用例 execution_status，evaluation_status 停留
pending——被 task_service 主循环计入活跃评估集合（ACTIVE_EVALUATION_STATUSES 含
PENDING），任务死等不收敛（test_case_wait_time=3000 / evaluation_hang_timeout=600
内无任何聚合），任务行长期停留 running(0/0/0)；进程重启后启动恢复又把已终态用例
的真实失败原因覆盖为「服务重启导致任务中断」。

修复语义（本文件覆盖）：
- api_test_service 失败路径补写评估终态并发布 CASE_FAILED
  （_fail_tc_rel 校验失败路径 / create_test_result 执行失败分支）；
- task_service 引擎在用例事件侧原子刷新任务行计数（_on_case_event）；
- 启动恢复不覆盖已终态用例的既有 error_message / completed_at
  （mark_interrupted_tasks_failed）。

隔离方式：ACL / EventBus 用 MagicMock 替身（不触 gRPC / Redis / 文件）；
mark_interrupted_tasks_failed 用独立 sqlite 内存库建 Task/TaskCase/TestResult 三表。
"""
import os
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

# BaseConfig 在 import 时校验环境变量（本用例纯单测不触库，与仓库既有测试同款兜底）
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import api_test_service.core.api_executor as api_executor_module
import api_test_service.core.api_result_processor as api_result_processor_module
import task_service.infrastructure.persistence._task_lifecycle_mixin as lifecycle_module
from api_test_service.core.api_executor import APIExecutor
from api_test_service.core.api_result_processor import APIResultProcessor
from shared.utils.status_constants import (
    EvaluationStatus, ExecutionStatus, TaskCaseStatus,
)
from shared.utils.redis_pubsub import EventChannel, EventType
from task_service.core.execution_engine import ExecutionEngine
from task_service.infrastructure.persistence._task_lifecycle_mixin import TaskLifecycleMixin
from task_service.infrastructure.persistence.models import Task, TaskCase, TestResult

TASK_ID = 420
INTERRUPTED_MESSAGE = '服务重启导致任务中断'


def _patch_event_bus(monkeypatch):
    """替换 EventBus 为记录型替身，返回 (published, worker_id 替身)。"""
    published = []

    class _FakeBus:
        def publish(self, channel, event_type, payload):
            published.append((channel, event_type, payload))

    monkeypatch.setattr('shared.utils.redis_pubsub.EventBus', _FakeBus)
    monkeypatch.setattr('shared.infrastructure.worker_context.get_worker_instance_id',
                        lambda: 'inst-test')
    return published


def _make_executor(monkeypatch):
    executor = APIExecutor.__new__(APIExecutor)
    monkeypatch.setattr(executor, '_log', MagicMock())
    return executor


class TestFailTcRelTerminalAndEvent:
    """校验失败路径（_fail_tc_rel）：评估终态补写 + CASE_FAILED 事件。"""

    def _acl_with_case(self, monkeypatch, evaluation_status='pending'):
        acl = MagicMock(name='task_data_acl')
        acl.get_task_case_by_ids.return_value = [{
            'id': 'tc-rel-1', 'test_case_id': 'case-1',
            'execution_status': 'running', 'evaluation_status': evaluation_status,
        }]
        monkeypatch.setattr(api_executor_module, '_task_data_acl', acl)
        return acl

    def test_validation_failure_completes_evaluation_and_publishes_event(self, monkeypatch):
        """复现路径回归：找不到API配置 → 用例双终态 + 任务收敛事件。"""
        published = _patch_event_bus(monkeypatch)
        acl = self._acl_with_case(monkeypatch)
        executor = _make_executor(monkeypatch)

        executor._fail_tc_rel('tc-rel-1', '找不到API配置', task_id=TASK_ID)

        assert acl.update_task_case_status.call_count == 1
        kwargs = acl.update_task_case_status.call_args.kwargs
        assert kwargs['task_id'] == TASK_ID
        assert kwargs['case_id'] == 'case-1'
        assert kwargs['status'] == TaskCaseStatus.FAILED
        assert kwargs['execution_status'] == ExecutionStatus.FAILED
        # 关键回归点：评估停留 pending 会让 task_service 主循环死等不收敛
        assert kwargs['evaluation_status'] == EvaluationStatus.COMPLETED
        assert kwargs['error_message'] == '找不到API配置'
        assert kwargs['completed_at']

        assert len(published) == 1
        channel, event_type, payload = published[0]
        assert channel == EventChannel.CASE_EVENTS
        assert event_type == EventType.CASE_FAILED
        assert payload['task_id'] == str(TASK_ID)
        assert payload['test_case_id'] == 'case-1'
        assert payload['success'] is False

    def test_running_evaluation_not_overwritten(self, monkeypatch):
        """评估已启动（running）时补写会覆盖评估域事实 → 不写（空串跳过）。"""
        published = _patch_event_bus(monkeypatch)
        acl = self._acl_with_case(monkeypatch, evaluation_status='running')
        executor = _make_executor(monkeypatch)

        executor._fail_tc_rel('tc-rel-1', '执行失败', task_id=TASK_ID)

        kwargs = acl.update_task_case_status.call_args.kwargs
        assert kwargs['evaluation_status'] == ''
        assert len(published) == 1


class TestCreateTestResultFailureBranch:
    """执行失败分支（create_test_result success=False）：评估终态 + 失败原因落用例行。"""

    def _processor(self, monkeypatch, execution_status='running'):
        acl = MagicMock(name='task_data_acl')
        acl.submit_result.return_value = 101
        acl.get_task_case_by_ids.return_value = [{
            'id': 'tc-rel-1', 'test_case_id': 'case-1',
            'execution_status': execution_status,
        }]
        monkeypatch.setattr(api_result_processor_module, '_task_data_acl', acl)
        monkeypatch.setattr(api_result_processor_module, 'write_result_data_file',
                            MagicMock(return_value='local://result-data/x.json'))
        processor = APIResultProcessor(SimpleNamespace(_log=MagicMock(),
                                                       execution_engine=MagicMock()))
        return processor, acl

    def test_failure_marks_case_terminal_with_reason(self, monkeypatch):
        """执行失败（评估不会被提交）→ evaluation_status 补 completed + 原因落库。"""
        published = _patch_event_bus(monkeypatch)
        processor, acl = self._processor(monkeypatch)

        processor.create_test_result(
            task_id=TASK_ID, test_case_id='case-1', api_config_id='api-1',
            success=False, error_msg='API 等待超时', algo_result_dict={},
            latency=0, final_result_result={}, algorithm_type='translation')

        kwargs = acl.update_task_case_status.call_args.kwargs
        assert kwargs['task_id'] == TASK_ID
        assert kwargs['case_id'] == 'case-1'
        assert kwargs['execution_status'] == ExecutionStatus.FAILED
        assert kwargs['evaluation_status'] == EvaluationStatus.COMPLETED
        assert kwargs['error_message'] == 'API 等待超时'
        assert kwargs['completed_at']

        assert len(published) == 1
        assert published[0][1] == EventType.CASE_FAILED

    def test_success_keeps_evaluation_pending(self, monkeypatch):
        """成功路径回归：评估随后由 evaluation_service 推进，不补写评估终态。"""
        published = _patch_event_bus(monkeypatch)
        processor, acl = self._processor(monkeypatch)

        processor.create_test_result(
            task_id=TASK_ID, test_case_id='case-1', api_config_id='api-1',
            success=True, error_msg=None, algo_result_dict={'answer': 'ok'},
            latency=12, final_result_result={}, algorithm_type='translation')

        kwargs = acl.update_task_case_status.call_args.kwargs
        assert kwargs['execution_status'] == ExecutionStatus.COMPLETED
        assert 'evaluation_status' not in kwargs
        assert published[0][1] == EventType.CASE_EXECUTION_COMPLETED


class TestOnCaseEventRefreshCounts:
    """task_service 引擎：用例事件 → 任务行计数原子刷新（INT-161 聚合点）。"""

    def _engine_stub(self):
        stub = SimpleNamespace(task_completion_events={})
        stub.emitted = []
        stub.scheduler_checks = []
        stub.refreshed = []
        stub._emit_progress = lambda task, force=False: stub.emitted.append((task, force))
        stub.trigger_scheduler_check = lambda: stub.scheduler_checks.append(True)
        stub.refresh_task_counts_atomic = lambda task_id: stub.refreshed.append(task_id)
        return stub

    def test_case_event_refreshes_task_counts(self):
        stub = self._engine_stub()
        ExecutionEngine._on_case_event(stub, {'task_id': str(TASK_ID)})
        assert stub.refreshed == [TASK_ID]
        assert stub.emitted == [(TASK_ID, True)]
        assert stub.scheduler_checks == [True]

    def test_non_int_task_id_skips_refresh(self):
        """INT-133 防御回归：非整型任务键丢弃，不触发计数刷新。"""
        stub = self._engine_stub()
        ExecutionEngine._on_case_event(stub, {'task_id': 'task-1'})
        assert stub.refreshed == []
        assert stub.emitted == []


class TestRecoveryPreservesRealFailureInfo:
    """启动恢复：已终态用例的既有 error_message / completed_at 不被覆盖。"""

    def _build_session(self, monkeypatch):
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

    def test_terminal_failed_case_keeps_error_and_completed_at(self, monkeypatch):
        factory = self._build_session(monkeypatch)
        fail_completed_at = datetime(2026, 10, 12, 11, 39, 30)
        session = factory()
        try:
            session.add(Task(id=TASK_ID, name='API 任务', status='running',
                             total_cases=1, completed_cases=0, failed_cases=0))
            # 用例 A：复现形态——执行已失败落真实原因，评估停留 pending
            session.add(TaskCase(task_id=TASK_ID, test_case_id='case-1',
                                 status='failed', execution_status='failed',
                                 evaluation_status='pending',
                                 error_message='找不到API配置',
                                 completed_at=fail_completed_at))
            # 用例 B：真中断形态——执行挂起、无失败原因
            session.add(TaskCase(task_id=TASK_ID, test_case_id='case-2',
                                 status='running', execution_status='running',
                                 evaluation_status='pending', error_message=None))
            session.add(TestResult(task_id=TASK_ID, test_case_id='case-2',
                                   execution_status='running'))
            session.commit()
        finally:
            session.close()

        class _Repo(TaskLifecycleMixin):
            pass

        counts = _Repo().mark_interrupted_tasks_failed(instance_id=None)

        assert counts['task'] == 1
        session = factory()
        try:
            task = session.get(Task, TASK_ID)
            assert task.status == 'failed'
            assert task.completed_at is not None

            case_a = session.query(TaskCase).filter_by(test_case_id='case-1').one()
            # 关键回归点：真实失败原因与既有完成时间不被启动恢复改写
            assert case_a.error_message == '找不到API配置'
            assert case_a.completed_at == fail_completed_at
            assert case_a.evaluation_status == EvaluationStatus.FAILED
            assert case_a.status == TaskCaseStatus.FAILED

            case_b = session.query(TaskCase).filter_by(test_case_id='case-2').one()
            assert case_b.error_message == INTERRUPTED_MESSAGE
            assert case_b.completed_at is not None
            assert case_b.evaluation_status == EvaluationStatus.FAILED

            result = session.query(TestResult).filter_by(task_id=TASK_ID).one()
            assert result.execution_status == ExecutionStatus.FAILED
            assert result.error_message == INTERRUPTED_MESSAGE
        finally:
            session.close()
