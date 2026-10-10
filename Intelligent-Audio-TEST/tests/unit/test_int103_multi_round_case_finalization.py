# -*- coding: utf-8 -*-
"""INT-103 守卫：API 多轮会话结果落库后必须回写 TaskCase 终态并通知执行引擎。

原缺陷：create_multi_round_test_result 仅 submit_result + log 后 return，不回写
TaskCase 状态、不 _emit_progress / notify_case_completed、不发布 CASE_EVENTS。
TaskCase 停留 running，引擎主循环 _count_in_progress_cases 持续 > 0，
_handle_no_pending_case 忙等「等待 N 个执行中/评估中的用例完成」，任务永不收敛
（INT-95 实证：任务 478 结果三轮全成功落库，task_case_relations 8989 停留
running/pending，同秒刷 334 条等待日志）。

修复语义（对齐单轮 create_test_result 链路 + INT-42 失败逃生门）：
- 回写 COMPLETED 当且仅当「结果已保存且全轮成功」（与执行器提交评估的条件
  一致，评估侧稍后推进 evaluation_status 收口）；
- 否则 execution_status=FAILED 且 evaluation_status 补写 COMPLETED——pending
  计入活跃评估集合（ACTIVE_EVALUATION_STATUSES 含 PENDING），不补写则引擎
  死等不收敛，失败由 execution_status 承载；
- stopped 保护：任务已停止不回写、不广播事件；
- 结果保存失败（result_id=None）同样收敛为 FAILED，不留悬挂用例。

本文件覆盖（纯单测，不触真实 DB/gRPC/OSS/Redis）：
- 成功 / 失败 / 保存失败三条路径的回写字段矩阵与引擎通知、事件发布；
- stopped 保护跳过回写与事件；
- executor 无 execution_engine 属性时不崩（INT-44 集成用例 StubExecutor 兼容）；
- 收敛不变量：回写后的状态组合必不落入活跃执行/评估集合。
"""
import os
from unittest.mock import MagicMock

# BaseConfig 在 import 时校验环境变量（本用例纯单测不触库，与仓库既有测试同款兜底）
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

import api_test_service.core.api_result_processor as proc_mod
from shared.utils.status_constants import (
    ACTIVE_EVALUATION_STATUSES,
    ACTIVE_EXECUTION_STATUSES,
    EvaluationStatus,
    ExecutionStatus,
)


class _StubExecutor:
    """与 INT-44 集成用例同款最小执行器替身（仅 _log，无 execution_engine）。"""

    def __init__(self, engine=None):
        self._engine = engine

    def _log(self, **kwargs):
        pass

    @property
    def execution_engine(self):
        if self._engine is None:
            raise AttributeError('execution_engine')
        return self._engine


@pytest.fixture()
def acl_mock(monkeypatch):
    acl = MagicMock()
    monkeypatch.setattr(proc_mod, '_task_data_acl', acl)
    acl.submit_result.return_value = 4851
    return acl


@pytest.fixture()
def event_bus_mock(monkeypatch):
    """EventBus 在方法内 import，补丁 shared.utils.redis_pubsub.EventBus 类属性。"""
    import shared.utils.redis_pubsub as pubsub_mod

    instance = MagicMock()
    bus_cls = MagicMock(return_value=instance)
    monkeypatch.setattr(pubsub_mod, 'EventBus', bus_cls)
    return instance


@pytest.fixture()
def storage_mock(monkeypatch):
    monkeypatch.setattr(proc_mod, 'write_result_data_file', lambda *a, **k: 'oss/fake.json')
    monkeypatch.setattr(proc_mod, 'split_result_data', lambda d: (d, False))


def _aggregated(all_success=True):
    rounds = [
        {'round_number': i, 'success': all_success, 'output': f'out{i}', 'latency': 0.2}
        for i in range(1, 4)
    ]
    return {
        'success': all_success,
        'algorithm_result': {
            'text_output': 'a b c', 'round_count': 3,
            'success_count': 3 if all_success else 2,
            'total_latency': 0.6, 'avg_latency': 0.2,
            'session_id': 's-1', 'rounds': rounds,
        },
        'total_latency': 0.6, 'round_count': 3,
        'session_summary': {},
    }


def _task_case_row(execution_status=ExecutionStatus.RUNNING,
                   evaluation_status=EvaluationStatus.PENDING):
    return {
        'id': 8989, 'task_id': 478, 'test_case_id': 'case-1',
        'execution_status': execution_status,
        'evaluation_status': evaluation_status,
    }


class TestInt103FinalizeWriteBack:
    """回写字段矩阵：成功只回写执行终态，失败必须补写评估终态。"""

    def test_success_writes_execution_completed_without_evaluation_status(
            self, acl_mock, event_bus_mock, storage_mock):
        acl_mock.get_task_case_by_ids.return_value = [_task_case_row()]
        engine = MagicMock()
        processor = proc_mod.APIResultProcessor(_StubExecutor(engine))

        result_id = processor.create_multi_round_test_result(
            task_id=478, test_case_id='case-1', api_config_id=1,
            algorithm_type='voice_llm', aggregated=_aggregated(True), success=True)

        assert result_id == 4851
        acl_mock.update_task_case_status.assert_called_once_with(
            task_id=478, case_id='case-1',
            execution_status=ExecutionStatus.COMPLETED,
        )
        engine._emit_progress.assert_called_once_with(478, force=True)
        engine.notify_case_completed.assert_called_once_with(478)

    def test_failed_rounds_write_failed_and_bump_evaluation_status(
            self, acl_mock, event_bus_mock, storage_mock):
        acl_mock.get_task_case_by_ids.return_value = [_task_case_row()]
        engine = MagicMock()
        processor = proc_mod.APIResultProcessor(_StubExecutor(engine))

        processor.create_multi_round_test_result(
            task_id=478, test_case_id='case-1', api_config_id=1,
            algorithm_type='voice_llm', aggregated=_aggregated(False), success=False)

        kwargs = acl_mock.update_task_case_status.call_args.kwargs
        assert kwargs['execution_status'] == ExecutionStatus.FAILED
        assert kwargs['evaluation_status'] == EvaluationStatus.COMPLETED
        assert kwargs['completed_at']
        engine._emit_progress.assert_called_once_with(478, force=True)
        engine.notify_case_completed.assert_called_once_with(478)

    def test_submit_failure_still_converges_case_to_failed(
            self, acl_mock, event_bus_mock, storage_mock):
        """结果保存失败（gRPC 异常）时用例同样收敛为 FAILED，不留悬挂 running。"""
        acl_mock.submit_result.side_effect = RuntimeError('grpc unavailable')
        acl_mock.get_task_case_by_ids.return_value = [_task_case_row()]
        engine = MagicMock()
        processor = proc_mod.APIResultProcessor(_StubExecutor(engine))

        result_id = processor.create_multi_round_test_result(
            task_id=478, test_case_id='case-1', api_config_id=1,
            algorithm_type='voice_llm', aggregated=_aggregated(True), success=True)

        assert result_id is None
        kwargs = acl_mock.update_task_case_status.call_args.kwargs
        assert kwargs['execution_status'] == ExecutionStatus.FAILED
        assert kwargs['evaluation_status'] == EvaluationStatus.COMPLETED

    def test_missing_task_case_row_still_notifies_and_publishes(
            self, acl_mock, event_bus_mock, storage_mock):
        """查不到 TaskCase（空列表）不阻断回写链路：状态更新照发、事件照发。"""
        acl_mock.get_task_case_by_ids.return_value = []
        engine = MagicMock()
        processor = proc_mod.APIResultProcessor(_StubExecutor(engine))

        processor.create_multi_round_test_result(
            task_id=478, test_case_id='case-1', api_config_id=1,
            algorithm_type='voice_llm', aggregated=_aggregated(True), success=True)

        acl_mock.update_task_case_status.assert_called_once()
        engine.notify_case_completed.assert_called_once_with(478)


class TestInt103StoppedProtection:
    """stopped 保护：任务停止后不回写状态、不广播事件（对齐单轮路径）。"""

    def test_stopped_case_skips_writeback_and_events(
            self, acl_mock, event_bus_mock, storage_mock):
        acl_mock.get_task_case_by_ids.return_value = [
            _task_case_row(execution_status=ExecutionStatus.STOPPED)]
        engine = MagicMock()
        processor = proc_mod.APIResultProcessor(_StubExecutor(engine))

        result_id = processor.create_multi_round_test_result(
            task_id=478, test_case_id='case-1', api_config_id=1,
            algorithm_type='voice_llm', aggregated=_aggregated(True), success=True)

        assert result_id == 4851
        acl_mock.update_task_case_status.assert_not_called()
        event_bus_mock.publish.assert_not_called()
        engine._emit_progress.assert_not_called()


class TestInt103EngineNotificationAndEvents:
    """引擎通知与 CASE_EVENTS 发布：唤醒 _wait_completion_event 等待线程。"""

    def test_success_publishes_case_execution_completed(
            self, acl_mock, event_bus_mock, storage_mock):
        from shared.utils.redis_pubsub import EventChannel, EventType

        acl_mock.get_task_case_by_ids.return_value = [_task_case_row()]
        processor = proc_mod.APIResultProcessor(_StubExecutor(MagicMock()))

        processor.create_multi_round_test_result(
            task_id=478, test_case_id='case-1', api_config_id=1,
            algorithm_type='voice_llm', aggregated=_aggregated(True), success=True)

        event_bus_mock.publish.assert_called_once()
        channel, event_type, payload = event_bus_mock.publish.call_args.args
        assert channel == EventChannel.CASE_EVENTS
        assert event_type == EventType.CASE_EXECUTION_COMPLETED
        assert payload['task_id'] == '478'
        assert payload['test_case_id'] == 'case-1'
        assert payload['result_id'] == '4851'
        assert payload['success'] is True

    def test_failure_publishes_case_failed(
            self, acl_mock, event_bus_mock, storage_mock):
        from shared.utils.redis_pubsub import EventChannel, EventType

        acl_mock.get_task_case_by_ids.return_value = [_task_case_row()]
        processor = proc_mod.APIResultProcessor(_StubExecutor(MagicMock()))

        processor.create_multi_round_test_result(
            task_id=478, test_case_id='case-1', api_config_id=1,
            algorithm_type='voice_llm', aggregated=_aggregated(False), success=False)

        channel, event_type, payload = event_bus_mock.publish.call_args.args
        assert channel == EventChannel.CASE_EVENTS
        assert event_type == EventType.CASE_FAILED
        assert payload['success'] is False

    def test_stub_executor_without_engine_does_not_crash(
            self, acl_mock, event_bus_mock, storage_mock):
        """INT-44 集成用例 StubExecutor（无 execution_engine）兼容：回写不炸。"""
        acl_mock.get_task_case_by_ids.return_value = [_task_case_row()]
        processor = proc_mod.APIResultProcessor(_StubExecutor())

        result_id = processor.create_multi_round_test_result(
            task_id=478, test_case_id='case-1', api_config_id=1,
            algorithm_type='voice_llm', aggregated=_aggregated(True), success=True)

        assert result_id == 4851
        acl_mock.update_task_case_status.assert_called_once()


class TestInt103ConvergenceInvariant:
    """收敛不变量：回写后的状态组合必不落入引擎主循环活跃集合。"""

    def test_finalized_combos_never_active(self, acl_mock, event_bus_mock, storage_mock):
        for success in (True, False):
            acl_mock.get_task_case_by_ids.return_value = [_task_case_row()]
            acl_mock.update_task_case_status.reset_mock()
            processor = proc_mod.APIResultProcessor(_StubExecutor(MagicMock()))

            processor.create_multi_round_test_result(
                task_id=478, test_case_id='case-1', api_config_id=1,
                algorithm_type='voice_llm', aggregated=_aggregated(success),
                success=success)

            kwargs = acl_mock.update_task_case_status.call_args.kwargs
            assert kwargs['execution_status'] not in ACTIVE_EXECUTION_STATUSES, \
                '回写后 execution_status 不得再被 _count_in_progress_cases 计入'
            if not success:
                assert kwargs['evaluation_status'] not in ACTIVE_EVALUATION_STATUSES, \
                    '无评估提交路径回写后 evaluation_status 不得再被 _count_evaluating_cases 计入'
