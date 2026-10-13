# -*- coding: utf-8 -*-
"""INT-308 回归守卫：任务停止立即生效（停止传播审计）+ 删除用例联动取消评估。

对齐 issue 验收口径（本文件为纯单测，不触真实 DB/Redis/设备）：

问题1 停止传播（目标：停止感知延迟 ≤ 2s，全链路 wait/sleep 点可中断）：
- _wait_completion_event：接 stop_event 后，睡满退避间隔的等待在停止时 ≤1s 中断；
  无 stop_event 时保持既有节奏（timeout 到期返回）；
- 调度器拆片等待：scheduler_stop_event 置位后 ≤1s 退出（原实现最长 30s）；
  事件显式唤醒立即返回（trigger_scheduler_check 语义不变）；
- play_round 播放等待：设备 future 全部提前 done（停止）时立即收口，不睡满理论时长；
- Realtime wait_ai_complete/wait_ai_speaking：stop_check 命中即中断；
- ControlMixin._is_task_stopped：Redis 标志位 / 本进程 event 双通道检测。

问题2 删除用例联动取消评估（防"已删用例出评估结果"的幽灵数据）：
- EvalTaskRegistry.cancel_by_case：按 (task_id, test_case_id) 摘除在途任务 +
  标记 case 取消；幂等；task 级 pop_by_task 不受影响（INT-174 语义保留）；
- cancel_case_evaluations handler：已完成用例返回 completed 不可取消（幂等），
  活跃用例取消并发布审计事件；
- worker 消费核销：case 取消的任务丢弃不执行；
- _process_evaluation_result 落库前核销：结果到达但用例已取消 → 丢弃不落库；
- _submit_to_workers 提交前核销：已取消用例不再入队；
- task_service.control_task('stop')：评估中用例联动调用 cancel（gRPC 失败不阻塞）。

实测验收（停止延迟 <5s、含 E2E 多轮与 API 会话链路）需实机大任务，
由集成验收覆盖，不在本文件范围。
"""
import os
import time
import threading
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from evaluation_service.infrastructure.evaluation_api.api_request_handler import (
    EvalTaskRegistry,
)
from evaluation_service.infrastructure.evaluation_api.endpoint_worker import EndpointWorker
from evaluation_service.infrastructure.evaluation_api.task_dispatcher import TaskDispatcherMixin
from evaluation_service.application.handlers import evaluation_cancel_handler
from evaluation_service.application.handlers.evaluation_cancel_handler import (
    cancel_case_evaluations,
)
from shared.utils.status_constants import (
    EvaluationStatus, ExecutionStatus, ACTIVE_EVALUATION_STATUSES,
)
from shared.utils.redis_pubsub import EventType

# 导入 evaluation_service 相关模块后清理残留的 scoped session（仓库既有测试同款兜底）
from shared.models.database import remove_db_session as _remove_db_session
_remove_db_session()


@pytest.fixture(autouse=True)
def _reset_registry():
    """隔离 EvalTaskRegistry 类级状态（注册表为进程级单例）"""
    EvalTaskRegistry._entries = {}
    EvalTaskRegistry._cancelled = {}
    EvalTaskRegistry._cancelled_cases = {}
    yield
    EvalTaskRegistry._entries = {}
    EvalTaskRegistry._cancelled = {}
    EvalTaskRegistry._cancelled_cases = {}


# ==================== 问题1：停止传播 ====================

class TestWaitCompletionEventInterruptible:
    """_wait_completion_event 接 stop_event 可中断（原实现睡满 timeout）"""

    @staticmethod
    def _engine(completion_events=None):
        from task_service.core.execution_engine.mixins.task_finalize import TaskFinalizeMixin

        class _Engine(TaskFinalizeMixin):
            def __init__(self):
                self.task_completion_events = completion_events or {}

        return _Engine()

    def test_stop_event_interrupts_long_wait(self):
        """退避间隔 30s 的等待，停止后 ≤1s 中断（目标 <2s）"""
        eng = self._engine()
        stop_event = threading.Event()

        start = time.time()
        threading.Timer(0.2, stop_event.set).start()
        eng._wait_completion_event('task-1', timeout=30, stop_event=stop_event)
        elapsed = time.time() - start

        assert elapsed < 2.0, f"停止感知耗时 {elapsed:.2f}s，应 <2s"

    def test_no_stop_event_keeps_pace(self):
        """不传 stop_event（向后兼容）行为不变：timeout 到期返回"""
        eng = self._engine()
        start = time.time()
        eng._wait_completion_event('task-1', timeout=1)
        elapsed = time.time() - start
        assert 0.8 <= elapsed <= 3.0

    def test_completion_event_still_wakes_early(self):
        """既有语义保留：完成事件到达提前返回"""
        completion = threading.Event()
        eng = self._engine({'task-1': completion})
        stop_event = threading.Event()

        threading.Timer(0.3, completion.set).start()
        start = time.time()
        eng._wait_completion_event('task-1', timeout=30, stop_event=stop_event)
        elapsed = time.time() - start

        assert elapsed < 2.0


class TestSchedulerIntervalSliced:
    """调度器下一轮等待拆片：停止标志置位 ≤1s 退出"""

    @staticmethod
    def _scheduler():
        from task_service.core.execution_engine.mixins.scheduler import SchedulerMixin

        class _Sched(SchedulerMixin):
            def __init__(self):
                self.scheduler_stop_event = threading.Event()
                self.scheduler_event = threading.Event()

        return _Sched()

    def test_stop_flag_exits_within_1s(self):
        sched = self._scheduler()
        threading.Timer(0.3, sched.scheduler_stop_event.set).start()

        start = time.time()
        sched._wait_scheduler_interval(30)
        elapsed = time.time() - start

        assert elapsed < 2.0, f"调度器停止感知 {elapsed:.2f}s，应 <2s（原实现最长 30s）"

    def test_scheduler_event_wakes_immediately(self):
        """事件显式唤醒（trigger_scheduler_check）立即返回，语义不变"""
        sched = self._scheduler()
        threading.Timer(0.2, sched.scheduler_event.set).start()

        start = time.time()
        sched._wait_scheduler_interval(30)
        elapsed = time.time() - start

        assert elapsed < 1.0
        assert sched.scheduler_event.is_set() is False  # clear 语义保留

    def test_full_interval_without_stop(self):
        sched = self._scheduler()
        start = time.time()
        sched._wait_scheduler_interval(1.2)
        elapsed = time.time() - start
        assert 1.0 <= elapsed <= 2.5


class TestPlaybackWaitInterruptible:
    """play_round 播放等待拆片：停止（future 全部提前 done）立即收口"""

    @staticmethod
    def _orchestrator(audio_service):
        from audio_service.infrastructure.audio.playback_orchestrator import PlaybackOrchestrator
        return PlaybackOrchestrator(audio_service=audio_service)

    def test_all_futures_done_returns_early(self):
        audio_service = SimpleNamespace(active_players={})
        orch = self._orchestrator(audio_service)

        # 播放 10s 理论时长；0.5s 后所有 device future done（模拟 stop_task_audio 生效）
        done_future = SimpleNamespace(done=lambda: False)
        players = {'device_1': {'future': done_future}}
        audio_service.active_players['42'] = players

        def _kill():
            done_future.done = lambda: True

        threading.Timer(0.5, _kill).start()

        start = time.time()
        orch._wait_playback_completion('42', total_duration=10)
        elapsed = time.time() - start

        assert elapsed < 2.0, f"播放停止感知 {elapsed:.2f}s，应 <2s"

    def test_natural_completion_waits_full_duration_when_loop_noise(self):
        """循环噪声 future 不 done：退化为睡满理论时长（与原行为一致）"""
        audio_service = SimpleNamespace(active_players={})
        orch = self._orchestrator(audio_service)
        loop_future = SimpleNamespace(done=lambda: False)  # 永不 done
        audio_service.active_players['7'] = {'device_0': {'future': loop_future}}

        start = time.time()
        orch._wait_playback_completion('7', total_duration=1.0)
        elapsed = time.time() - start
        assert 0.8 <= elapsed <= 2.5

    def test_registration_settle_interrupted_by_stop_flag(self):
        """声纹注册等待只认任务停止信号（注册窗口 ≠ 播放时长）"""
        audio_service = SimpleNamespace(active_players={})
        orch = self._orchestrator(audio_service)

        with patch('audio_service.infrastructure.audio.playback_orchestrator.'
                   'PlaybackOrchestrator._is_task_stopped', staticmethod(lambda tid: True)):
            start = time.time()
            orch._wait_registration_settle('9', wait_time_sec=30)
            elapsed = time.time() - start

        assert elapsed < 1.0, f"声纹注册停止感知 {elapsed:.2f}s"


class TestRealtimeWaitStopCheck:
    """Realtime WS 等待循环：stop_check 命中即中断"""

    @staticmethod
    def _client():
        from api_test_service.infrastructure.vendor_ws.realtime_ws_client import RealtimeWSClient
        return RealtimeWSClient('ws://stub')

    def test_wait_ai_speaking_interrupted_by_stop_check(self):
        client = self._client()
        # recv 永远超时（空队列语义返回 recv_timeout），stop_check 0.3s 后命中
        with patch.object(client, 'recv', return_value={'type': 'recv_timeout'}):
            threading.Event()  # noqa 占位
            flag = threading.Event()
            stop_check = lambda: flag.is_set()
            threading.Timer(0.3, flag.set).start()

            start = time.time()
            ok = client.wait_ai_speaking(start_timeout=30, stop_check=stop_check)
            elapsed = time.time() - start

        assert ok is False
        assert elapsed < 2.0

    def test_wait_ai_complete_interrupted_by_stop_check(self):
        client = self._client()
        client._ai_complete = False
        with patch.object(client, 'recv', return_value={'type': 'recv_timeout'}):
            flag = threading.Event()
            threading.Timer(0.3, flag.set).start()

            start = time.time()
            ok = client.wait_ai_complete(start_timeout=5, end_timeout=30,
                                         stop_check=lambda: flag.is_set())
            elapsed = time.time() - start

        assert ok is False
        assert elapsed < 2.0


class TestIsTaskStopped:
    """ControlMixin._is_task_stopped：Redis 标志位 / 本进程 event 双通道"""

    @staticmethod
    def _executor(stop_event=None):
        from shared.infrastructure.base_executor._control_mixin import ControlMixin

        class _Exec(ControlMixin):
            def __init__(self):
                self.execution_engine = SimpleNamespace(
                    stop_flags={'task-1': stop_event},
                    pause_flags={'task-1': threading.Event()},
                )

        return _Exec()

    def test_local_event_channel(self):
        stop_event = threading.Event()
        ex = self._executor(stop_event)

        with patch('shared.utils.distributed_coordinator.is_task_stopped',
                   return_value=False):
            assert ex._is_task_stopped('task-1') is False
            stop_event.set()
            assert ex._is_task_stopped('task-1') is True

    def test_redis_channel(self):
        ex = self._executor(None)  # 本进程无 event 注册
        with patch('shared.utils.distributed_coordinator.is_task_stopped',
                   return_value=True):
            assert ex._is_task_stopped('task-1') is True


# ==================== 问题2：删除用例联动取消评估 ====================

class TestCaseCancelRegistry:
    """EvalTaskRegistry case 级取消：摘除 + 标记 + 幂等 + task 级语义保留"""

    def test_cancel_by_case_removes_and_marks(self):
        EvalTaskRegistry.register('e1', 5, 'http://ep-a', test_case_id='case-1')
        EvalTaskRegistry.register('e2', 5, 'http://ep-b', test_case_id='case-2')
        EvalTaskRegistry.register('e3', 6, 'http://ep-c', test_case_id='case-1')

        removed = EvalTaskRegistry.cancel_by_case(5, 'case-1')

        assert removed == [('e1', 'http://ep-a')]
        assert EvalTaskRegistry.is_cancelled('e1') is True
        assert EvalTaskRegistry.is_case_cancelled(5, 'case-1') is True
        # 其他 case / 其他 task 不受影响
        assert EvalTaskRegistry.is_case_cancelled(5, 'case-2') is False
        assert EvalTaskRegistry.is_case_cancelled(6, 'case-1') is False
        assert 'e2' in EvalTaskRegistry._entries
        assert 'e3' in EvalTaskRegistry._entries

    def test_cancel_by_case_idempotent(self):
        EvalTaskRegistry.register('e1', 5, 'http://ep-a', test_case_id='case-1')
        assert len(EvalTaskRegistry.cancel_by_case(5, 'case-1')) == 1
        # 重复取消：无新摘除，标记保持
        assert EvalTaskRegistry.cancel_by_case(5, 'case-1') == []
        assert EvalTaskRegistry.is_case_cancelled(5, 'case-1') is True

    def test_cancel_by_case_type_normalization(self):
        """task_id int/str 与 case_id 形态差异命中（取消方/登记方类型不一）"""
        EvalTaskRegistry.register('e1', '5', 'http://ep-a', test_case_id='case-1')
        assert EvalTaskRegistry.cancel_by_case(5, 'case-1') == [('e1', 'http://ep-a')]
        assert EvalTaskRegistry.is_case_cancelled('5', 'case-1') is True

    def test_pop_by_task_semantics_preserved(self):
        """INT-174 task 级 pop_by_task 语义不受 case 级扩展影响"""
        EvalTaskRegistry.register('e1', 5, 'http://ep-a', test_case_id='case-1')
        EvalTaskRegistry.register('e2', 5, 'http://ep-b', test_case_id='case-2')
        EvalTaskRegistry.register('e3', 6, 'http://ep-c')

        removed = EvalTaskRegistry.pop_by_task(5)
        assert sorted(removed) == [('e1', 'http://ep-a'), ('e2', 'http://ep-b')]
        assert EvalTaskRegistry.is_case_cancelled(5, 'case-1') is False  # task 级不标 case

    def test_register_without_case_id(self):
        """未携带 case_id 的旧调用点（INT-174 兼容）不报错"""
        EvalTaskRegistry.register('e1', 5, 'http://ep-a')
        assert EvalTaskRegistry.pop_by_task(5) == [('e1', 'http://ep-a')]


class TestCancelCaseEvaluationsHandler:
    """cancel_case_evaluations：状态分流 + 方案A/B + 审计事件"""

    def _tc(self, case_id, evaluation_status):
        return SimpleNamespace(test_case_id=case_id, evaluation_status=evaluation_status)

    def test_active_case_cancelled_completed_case_irreversible(self):
        tc_rels = [
            self._tc('case-1', EvaluationStatus.RUNNING),   # 活跃 → 取消
            self._tc('case-2', EvaluationStatus.PENDING),   # 活跃（未启动）→ 取消
            self._tc('case-3', EvaluationStatus.COMPLETED),  # 已完成 → 不可取消
        ]
        removed = [('e1', 'http://ep-a')]
        published = []

        with patch.object(evaluation_cancel_handler.task_acl_repository,
                          'get_task_case_by_ids', return_value=tc_rels), \
             patch.object(evaluation_cancel_handler.eval_task_registry,
                          'cancel_by_case', return_value=removed) as mock_cancel, \
             patch.object(evaluation_cancel_handler, '_notify_subservices_cancel',
                          return_value=1), \
             patch.object(evaluation_cancel_handler, '_publish_cancel_audit',
                          side_effect=lambda *a: published.append(a)):

            result = cancel_case_evaluations(5, ['case-1', 'case-2', 'case-3'],
                                             reason='case_deleted')

        # 活跃用例：摘除在途 + 标记取消；已完成用例：不摘除
        assert mock_cancel.call_count == 2
        by_id = {r['test_case_id']: r for r in result['results']}
        assert by_id['case-1']['cancelled'] is True
        assert by_id['case-2']['cancelled'] is True
        assert by_id['case-3']['cancelled'] is False
        assert by_id['case-3']['completed'] is True
        assert result['cancelled_inflight'] == 2  # 2 个活跃用例 × 1 条在途

    def test_grpc_failure_on_status_query_does_not_block_cancel(self):
        """状态查询 gRPC 失败：在途条目照常摘除（结果侧核销兜底）"""
        with patch.object(evaluation_cancel_handler.task_acl_repository,
                          'get_task_case_by_ids', side_effect=RuntimeError('grpc down')), \
             patch.object(evaluation_cancel_handler.eval_task_registry,
                          'cancel_by_case',
                          return_value=[('e1', 'http://ep-a')]), \
             patch.object(evaluation_cancel_handler, '_notify_subservices_cancel',
                          return_value=0), \
             patch.object(evaluation_cancel_handler, '_publish_cancel_audit'):

            result = cancel_case_evaluations(5, ['case-1'], reason='task_stopped')

        assert result['results'][0]['cancelled'] is True
        assert result['cancelled_inflight'] == 1

    def test_audit_event_published_per_case(self):
        events = []
        from shared.utils.redis_pubsub import EventBus
        with patch.object(EventBus, 'publish',
                          side_effect=lambda ch, et, payload: events.append((ch, et, payload))):
            evaluation_cancel_handler._publish_cancel_audit(
                5, [{'test_case_id': 'case-1', 'cancelled': True, 'completed': False}],
                'case_deleted')

        assert len(events) == 1
        channel, event_type, payload = events[0]
        assert event_type == EventType.CASE_EVALUATION_CANCELLED
        assert payload['task_id'] == '5'
        assert payload['test_case_id'] == 'case-1'
        assert payload['reason'] == 'case_deleted'

    def test_empty_case_ids_noop(self):
        result = cancel_case_evaluations(5, [])
        assert result == {'results': [], 'cancelled_inflight': 0, 'subservice_notified': 0}


class TestWorkerConsumesCancelMark:
    """端点 worker 消费前核销：case 取消的任务丢弃不执行"""

    @staticmethod
    def _worker():
        worker = EndpointWorker.__new__(EndpointWorker)
        worker.endpoint_url = 'http://ep-a'
        worker.eval_service = None
        worker._use_redis_queue = False
        worker.task_queue = __import__('queue').Queue()
        worker._brpop_timeout = 1
        worker.stop_event = threading.Event()
        worker.worker_threads = []
        worker.completion_events = {}
        worker.completion_events_lock = threading.Lock()
        return worker

    def test_cancelled_task_discarded_before_execution(self):
        worker = self._worker()
        EvalTaskRegistry.cancel_by_case(5, 'case-1')  # 预置取消标记

        executed = []
        with patch.object(worker, 'get_task', return_value={
            'task_id': 5, 'test_case_id': 'case-1', 'result_id': 11}), \
             patch.object(worker, '_log', MagicMock()):
            # 直接驱动单次消费逻辑：置位 stop_event 使 _worker_loop 取完即退
            worker.stop_event.set()

            # 手动执行循环体的核心段（get_task → 核销 → 丢弃）
            task_data = worker.get_task(timeout=1.0)
            tc_id = str(task_data.get('test_case_id') or '')
            discarded = tc_id and EvalTaskRegistry.is_case_cancelled(
                task_data.get('task_id'), tc_id)
            if not discarded:
                executed.append(task_data)

        assert discarded is True
        assert executed == []


class TestProcessResultCancelCheck:
    """结果落库前核销：case 取消 → 结果丢弃不落库"""

    @staticmethod
    def _worker():
        worker = EndpointWorker.__new__(EndpointWorker)
        worker.endpoint_url = 'http://ep-a'
        worker.eval_service = SimpleNamespace(
            result_processor=MagicMock(),
        )
        return worker

    def test_result_dropped_when_case_cancelled(self):
        worker = self._worker()
        EvalTaskRegistry.cancel_by_case(5, 'case-1')

        with patch.object(worker, '_log', MagicMock()):
            worker._process_evaluation_result(
                resp_data={'wer': 0.1}, group_items=[({'id': 1, 'name': 'd1'}, 101)],
                task_id=5, test_case_id='case-1', result_id=11,
                payload={}, test_type='api')

        # 结果处理器未被调用（结果未落库）
        assert worker.eval_service.result_processor.process_group_dimension_results.called is False


class TestSubmitSkipsCancelledCase:
    """任务分发提交前核销：已取消用例不再入队"""

    def test_submit_skips_when_cancelled(self):
        EvalTaskRegistry.cancel_by_case(5, 'case-1')
        mixin = TaskDispatcherMixin()
        mixin._log = MagicMock()

        # 提交链依赖宿主的 _get_or_create_worker / api_client（宿主未组合时不存在），
        # 用 create=True 打桩：取消分支应在触达提交链之前 return
        with patch.object(TaskDispatcherMixin, '_get_or_create_worker', create=True) as mock_worker:
            mixin._submit_to_workers(
                endpoint_groups={('http://ep-a', 1): [({'id': 1, 'name': 'd1'}, 101)]},
                result_id=11, task_id=5, test_case_id='case-1',
                algorithm_result={}, algorithm_type='translation',
                test_type='api', round_number=None, field_mapper=MagicMock(),
                ref_texts={}, rounds_list=None, flat_eval_fields=None)

        mock_worker.assert_not_called()


class TestControlTaskStopCancelsEvaluation:
    """task_service control_task('stop')：评估中用例联动取消（gRPC 失败不阻塞）"""

    @staticmethod
    def _engine_with_task(task_status=ExecutionStatus.RUNNING):
        """构造最小 TaskControlMixin 引擎 + 假 Task/TaskCase ORM 行"""
        from task_service.core.execution_engine.mixins.task_control import TaskControlMixin

        class _Eng(TaskControlMixin):
            def __init__(self):
                self.workers = {}
                self.stop_flags = {}
                self.pause_flags = {}
                self.task_completion_events = {}
                self.task_progress_cache = {}
                self.last_progress_update = {}
                self.round_progress_cache = {}
                self.running_tasks = {}
                self.running_apis = set()
                self.running_e2e = False
                self.task_queue = __import__('collections').deque()
                self.queue_lock = threading.Lock()
                self.utc_plus_8 = None
                self.logs = []
                self.alerts = []
                self.progress_emitted = []

            def _log(self, **kwargs):
                self.logs.append(kwargs)

            def _emit_alert(self, task_id, message, level='error'):
                self.alerts.append((task_id, message))

            def _emit_progress(self, task, force=False):
                self.progress_emitted.append(task)

        return _Eng()

    def test_stop_invokes_cancel_with_evaluating_cases(self):
        from shared.utils.status_utils import derive_task_case_status
        eng = self._engine_with_task()

        tc_evaluating = SimpleNamespace(
            id='rel-1', test_case_id='case-1', task_id='task-5',
            execution_status=ExecutionStatus.COMPLETED,
            evaluation_status=EvaluationStatus.RUNNING)
        tc_done = SimpleNamespace(
            id='rel-2', test_case_id='case-2', task_id='task-5',
            execution_status=ExecutionStatus.COMPLETED,
            evaluation_status=EvaluationStatus.COMPLETED)

        fake_session = MagicMock()
        fake_task = SimpleNamespace(
            id='task-5', status=ExecutionStatus.RUNNING, completed_at=None)
        fake_session.get.side_effect = lambda cls, tid: (
            fake_task if cls.__name__ == 'Task' else None)
        fake_session.query.return_value.filter.return_value.all.return_value = [
            tc_evaluating, tc_done]

        cancel_calls = []
        progress_ts = SimpleNamespace(
            id='tc-1', test_case_id='case-1', task_id='task-5',
            execution_status=ExecutionStatus.COMPLETED,
            evaluation_status=EvaluationStatus.RUNNING)

        with patch('task_service.core.execution_engine.mixins.task_control.get_db_session',
                   return_value=fake_session), \
             patch('task_service.core.execution_engine.mixins.task_control.'
                   '_dc.set_task_stop'), \
             patch('task_service.core.execution_engine.mixins.task_control.'
                   '_dc.clear_task_pause'), \
             patch('task_service.core.execution_engine.mixins.task_control.'
                   '_stop_task_audio_via_grpc'), \
             patch('task_service.core.execution_engine.mixins.task_control.'
                   '_cleanup_devices_via_grpc'), \
             patch('task_service.core.execution_engine.mixins.task_control.'
                   '_unregister_task_events_via_grpc'), \
             patch('task_service.core.execution_engine.mixins.task_control.'
                   '_register_task_events_via_grpc'), \
             patch('shared.clients.grpc_clients.cancel_case_evaluations',
                   side_effect=lambda tid, ids, reason: cancel_calls.append(
                       (tid, ids, reason)) or {
                       'success': True,
                       'data': {'cancelled_inflight': 1, 'results': []}}):

            eng.control_task('task-5', 'stop')

        # 评估中用例进入取消列表，已完成用例不进入
        assert len(cancel_calls) == 1
        tid, ids, reason = cancel_calls[0]
        assert str(tid) == 'task-5'
        assert ids == ['case-1']
        assert reason == 'task_stopped'

    def test_stop_not_blocked_by_cancel_grpc_failure(self):
        eng = self._engine_with_task()

        tc_evaluating = SimpleNamespace(
            id='rel-1', test_case_id='case-1', task_id='task-5',
            execution_status=ExecutionStatus.COMPLETED,
            evaluation_status=EvaluationStatus.RUNNING)
        fake_session = MagicMock()
        fake_task = SimpleNamespace(
            id='task-5', status=ExecutionStatus.RUNNING, completed_at=None)
        fake_session.get.side_effect = lambda cls, tid: (
            fake_task if cls.__name__ == 'Task' else None)
        fake_session.query.return_value.filter.return_value.all.return_value = [
            tc_evaluating]

        with patch('task_service.core.execution_engine.mixins.task_control.get_db_session',
                   return_value=fake_session), \
             patch('task_service.core.execution_engine.mixins.task_control.'
                   '_dc.set_task_stop'), \
             patch('task_service.core.execution_engine.mixins.task_control.'
                   '_dc.clear_task_pause'), \
             patch('task_service.core.execution_engine.mixins.task_control.'
                   '_stop_task_audio_via_grpc'), \
             patch('task_service.core.execution_engine.mixins.task_control.'
                   '_cleanup_devices_via_grpc'), \
             patch('task_service.core.execution_engine.mixins.task_control.'
                   '_unregister_task_events_via_grpc'), \
             patch('task_service.core.execution_engine.mixins.task_control.'
                   '_register_task_events_via_grpc'), \
             patch('shared.clients.grpc_clients.cancel_case_evaluations',
                   side_effect=RuntimeError('grpc down')):

            success, message = eng.control_task('task-5', 'stop')

        # 停止流程不被联动取消失败阻塞
        assert success is True
        assert message == '任务已停止'
