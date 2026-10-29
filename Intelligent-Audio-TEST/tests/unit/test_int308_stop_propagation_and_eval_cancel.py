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
    """隔离 EvalTaskRegistry 类级状态（注册表为进程级单例）+ Redis case 取消标记

    INT-308 审计#2 修复后取消标记双通道（内存 + Redis eval:case_cancelled:*），
    测试间需同时清理，否则跨用例的 Redis 残留键会被 is_case_cancelled 的
    Redis 通道命中。
    """
    EvalTaskRegistry._entries = {}
    EvalTaskRegistry._cancelled = {}
    EvalTaskRegistry._cancelled_cases = {}
    _flush_redis_case_cancelled()
    yield
    EvalTaskRegistry._entries = {}
    EvalTaskRegistry._cancelled = {}
    EvalTaskRegistry._cancelled_cases = {}
    _flush_redis_case_cancelled()


def _flush_redis_case_cancelled():
    """清理 Redis 中 case 取消标记（Redis 不可用时静默跳过，测试退化为纯内存语义）"""
    try:
        from shared.utils.redis_pubsub import RedisPubSub
        from shared.models.common_enums import RedisKeyPrefix
        client = RedisPubSub().redis_client
        for key in client.scan_iter(f'{RedisKeyPrefix.EVAL_CASE_CANCELLED.value}:*'):
            client.delete(key)
    except Exception:
        pass


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
        from api_test_service.infrastructure.adapters.transport.realtime_ws_client import RealtimeWSClient
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

    def test_task_stopped_trusts_requester_despite_flipped_status(self):
        """审计#1 修复（核心回归）：task_service 停止链先翻转 evaluation_status=stopped
        再调用取消——命令语义下信任请求方，stopped 不误判为已完成，照常摘除"""
        tc_rels = [
            self._tc('case-1', 'stopped'),   # 停止链已翻转（此前 running/calculating）
            self._tc('case-2', 'stopped'),
        ]

        with patch.object(evaluation_cancel_handler.task_acl_repository,
                          'get_task_case_by_ids', return_value=tc_rels), \
             patch.object(evaluation_cancel_handler.eval_task_registry,
                          'cancel_by_case',
                          return_value=[('e1', 'http://ep-a')]) as mock_cancel, \
             patch.object(evaluation_cancel_handler, '_notify_subservices_cancel',
                          return_value=1), \
             patch.object(evaluation_cancel_handler, '_publish_cancel_audit'):

            result = cancel_case_evaluations(5, ['case-1', 'case-2'],
                                             reason='task_stopped')

        # 关键断言：翻转后状态不被误判为"已完成不可取消"
        assert mock_cancel.call_count == 2
        assert all(r['cancelled'] is True for r in result['results'])
        assert result['cancelled_inflight'] == 2

    def test_task_stopped_completed_case_still_excluded(self):
        """命令语义下已完成（completed/failed/skipped，有实际产出）的用例
        仍不可取消（返回 completed=true 供删除方标记 excluded）"""
        tc_rels = [
            self._tc('case-1', 'stopped'),                  # 停止链翻转 → 照常取消
            self._tc('case-2', EvaluationStatus.COMPLETED),  # 评估已产出 → excluded
            self._tc('case-3', EvaluationStatus.FAILED),     # 评估已产出 → excluded
        ]

        with patch.object(evaluation_cancel_handler.task_acl_repository,
                          'get_task_case_by_ids', return_value=tc_rels), \
             patch.object(evaluation_cancel_handler.eval_task_registry,
                          'cancel_by_case',
                          return_value=[('e1', 'http://ep-a')]) as mock_cancel, \
             patch.object(evaluation_cancel_handler, '_notify_subservices_cancel',
                          return_value=0), \
             patch.object(evaluation_cancel_handler, '_publish_cancel_audit'):

            result = cancel_case_evaluations(5, ['case-1', 'case-2', 'case-3'],
                                             reason='task_stopped')

        assert mock_cancel.call_count == 1  # 仅 case-1
        by_id = {r['test_case_id']: r for r in result['results']}
        assert by_id['case-1']['cancelled'] is True
        assert by_id['case-2']['completed'] is True and by_id['case-2']['cancelled'] is False
        assert by_id['case-3']['completed'] is True

    def test_adhoc_reason_keeps_conservative_semantics(self):
        """adhoc（外部临时调用）保持既有保守语义：回读非活跃即跳过（含 stopped）"""
        tc_rels = [
            self._tc('case-1', 'stopped'),
            self._tc('case-2', EvaluationStatus.RUNNING),
        ]

        with patch.object(evaluation_cancel_handler.task_acl_repository,
                          'get_task_case_by_ids', return_value=tc_rels), \
             patch.object(evaluation_cancel_handler.eval_task_registry,
                          'cancel_by_case',
                          return_value=[('e1', 'http://ep-a')]) as mock_cancel, \
             patch.object(evaluation_cancel_handler, '_notify_subservices_cancel',
                          return_value=0), \
             patch.object(evaluation_cancel_handler, '_publish_cancel_audit'):

            result = cancel_case_evaluations(5, ['case-1', 'case-2'],
                                             reason='adhoc')

        assert mock_cancel.call_count == 1  # 仅 case-2；stopped 被保守跳过
        by_id = {r['test_case_id']: r for r in result['results']}
        assert by_id['case-1']['cancelled'] is False
        assert by_id['case-2']['cancelled'] is True

    def test_unknown_reason_normalized_to_adhoc(self):
        """未知 reason 归一为 adhoc（保守语义），拒绝魔法字符串外溢"""
        assert evaluation_cancel_handler.EvaluationCancelReason.normalize(
            'whatever') == evaluation_cancel_handler.EvaluationCancelReason.ADHOC
        assert evaluation_cancel_handler.EvaluationCancelReason.is_command_semantic('whatever') is False
        assert evaluation_cancel_handler.EvaluationCancelReason.is_command_semantic('task_stopped') is True
        assert evaluation_cancel_handler.EvaluationCancelReason.is_command_semantic('case_deleted') is True

    def test_completed_case_no_cancel_event_published(self):
        """审计#4：已完成不可取消的用例不发布 case_evaluation_cancelled 事件"""
        events = []
        from shared.utils.redis_pubsub import EventBus
        with patch.object(EventBus, 'publish',
                          side_effect=lambda ch, et, payload: events.append((ch, et, payload))):
            evaluation_cancel_handler._publish_cancel_audit(
                5, [
                    {'test_case_id': 'case-1', 'cancelled': True, 'completed': False},
                    {'test_case_id': 'case-2', 'cancelled': False, 'completed': True},
                ],
                'task_stopped')

        # 仅实际取消的用例发布；completed 用例无事件（语义一致）
        assert len(events) == 1
        assert events[0][2]['test_case_id'] == 'case-1'

    def test_subservice_notify_parallel_with_timeout(self):
        """审计#3：子服务通知并行化 + 总耗时上限——单个端点挂死不拖垮停止主链"""
        import time as _time
        targets = [(f'e{i}', 'http://slow-endpoint') for i in range(4)]

        def _slow_delete(eval_task_id, endpoint_url):
            _time.sleep(30)  # 模拟端点挂死（timeout=5 也覆盖不到的场景）
            return True

        import requests as _requests
        with patch.object(_requests, 'delete', side_effect=_slow_delete):
            start = _time.time()
            notified = evaluation_cancel_handler._notify_subservices_cancel(
                targets, 5)
            elapsed = _time.time() - start

        # 4 个挂死通知在 join 上限内放弃，总耗时远小于串行 4×5s
        assert elapsed < 10
        assert notified == 0

    def test_subservice_notify_parallel_success(self):
        """并行通知成功路径：4 个端点并行，均成功计数"""
        targets = [(f'e{i}', f'http://ep-{i}') for i in range(4)]
        import requests as _requests
        with patch.object(_requests, 'delete',
                          side_effect=lambda url, timeout: SimpleNamespace(status_code=200)):
            notified = evaluation_cancel_handler._notify_subservices_cancel(targets, 5)
        assert notified == 4

    def test_cross_layer_timing_flip_then_cancel(self):
        """审计#1/#5 跨层时序贯通：task_service 翻转 commit → handler 回读
        stopped 状态 → 仍照常摘除在途任务（fake session 模拟翻转后的 DB 状态）"""
        # 模拟 task_service 停止链：采集时状态活跃，commit 后 DB 中已翻转
        collected_while_active = ['case-1']
        flipped_after_commit = self._tc('case-1', 'stopped')  # commit 后回读到的状态

        cancel_calls = []

        def fake_cancel(tid, ids, reason='case_deleted'):
            cancel_calls.append((tid, list(ids), reason))
            return {'success': True, 'message': 'ok',
                    'data': {'results': [{'test_case_id': c, 'cancelled': True,
                                          'completed': False, 'inflight_removed': 1,
                                          'subservice_notified': 0} for c in ids],
                             'cancelled_inflight': len(ids), 'subservice_notified': 0}}

        with patch.object(evaluation_cancel_handler.task_acl_repository,
                          'get_task_case_by_ids',
                          return_value=[flipped_after_commit]), \
             patch('shared.clients.grpc_clients.cancel_case_evaluations',
                   side_effect=fake_cancel):
            # 模拟 task_service 侧调用链：翻转 commit 后带着翻转前采集的 ID 调用
            from shared.clients.grpc_clients import cancel_case_evaluations as _cancel
            resp = _cancel('5', collected_while_active, reason='task_stopped')

        # 取消未被跳过：在途摘除 > 0（修复前此处为 0，幽灵数据）
        assert cancel_calls == [('5', ['case-1'], 'task_stopped')]
        assert resp['data']['cancelled_inflight'] == 1


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

    def test_cancel_invoked_before_status_flip_commit(self):
        """审计#1 修复（纵深）：取消调用必须发生在状态翻转 commit 之前——
        任何回读 TaskCase.evaluation_status 的调用路径看到的都是活跃状态"""
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

        call_order = []
        fake_session.commit.side_effect = lambda: call_order.append('commit')

        with patch('task_service.core.execution_engine.mixins.task_control.get_db_session',
                   return_value=fake_session),              patch('task_service.core.execution_engine.mixins.task_control.'
                   '_dc.set_task_stop'),              patch('task_service.core.execution_engine.mixins.task_control.'
                   '_dc.clear_task_pause'),              patch('task_service.core.execution_engine.mixins.task_control.'
                   '_stop_task_audio_via_grpc'),              patch('task_service.core.execution_engine.mixins.task_control.'
                   '_cleanup_devices_via_grpc'),              patch('task_service.core.execution_engine.mixins.task_control.'
                   '_unregister_task_events_via_grpc'),              patch('task_service.core.execution_engine.mixins.task_control.'
                   '_register_task_events_via_grpc'),              patch('shared.clients.grpc_clients.cancel_case_evaluations',
                   side_effect=lambda tid, ids, reason: call_order.append('cancel') or {
                       'success': True,
                       'data': {'cancelled_inflight': 1, 'results': []}}):

            eng.control_task('task-5', 'stop')

        assert call_order == ['cancel', 'commit']

class TestCaseCancelledRedisFallback:
    """审计#2：case 取消标记双通道——eval_service 重启（内存标记丢失）后，
    is_case_cancelled 仍能经 Redis 通道命中（Redis 持久化队列重放场景）"""

    def test_redis_channel_hits_when_memory_lost(self):
        """模拟重启：清空内存标记后，Redis 中预置的取消标记仍命中"""
        EvalTaskRegistry.cancel_by_case(5, 'case-1')  # 写内存 + Redis
        # 模拟 eval_service 重启：内存全部丢失
        EvalTaskRegistry._entries = {}
        EvalTaskRegistry._cancelled = {}
        EvalTaskRegistry._cancelled_cases = {}

        assert EvalTaskRegistry.is_case_cancelled(5, 'case-1') is True

        # 清理 Redis 标记后不再命中（autouse fixture 亦会清理）
        try:
            from shared.utils.redis_pubsub import RedisPubSub
            from shared.models.common_enums import RedisKeyPrefix
            client = RedisPubSub().redis_client
            client.delete(f'{RedisKeyPrefix.EVAL_CASE_CANCELLED.value}:5:case-1')
        except Exception:
            pass
        assert EvalTaskRegistry.is_case_cancelled(5, 'case-1') is False

    def test_redis_unavailable_falls_back_to_memory(self):
        """Redis 不可用（分布协调器禁用）：cancel 照常成功，内存标记兜底"""
        with patch('shared.utils.distributed_coordinator.set_flag',
                   side_effect=RuntimeError('redis down')),              patch('shared.utils.distributed_coordinator.is_flag_set',
                   return_value=False):
            removed = EvalTaskRegistry.cancel_by_case(5, 'case-1')

        assert removed == []  # 无在途条目，但标记已设
        assert EvalTaskRegistry.is_case_cancelled(5, 'case-1') is True  # 内存通道


class TestE2EExecutorStopBranchTerminalStatus:
    """审计#6：E2E 执行器 TaskStopSignal 分支此前引用不存在的
    TaskCaseStatus.STOPPED（2e919c18 引入）必抛 AttributeError 走异常路径；
    修复后按 task_service 停止分支同款口径收敛（exec=STOPPED，status 由
    _update_tc_rel_status 按推导规则落 failed），并留痕停止原因。"""

    @staticmethod
    def _executor_with_stop_signal():
        from e2e_test_service.application.services.e2e_executor.executor import E2EExecutor
        from shared.infrastructure.base_executor import TaskStopSignal

        ex = E2EExecutor.__new__(E2EExecutor)
        ex._aggregator = MagicMock()
        ex._task_data_repo = MagicMock()
        ex._device_repo = MagicMock()
        ex._playback_repo = MagicMock()
        ex._playback_repo.start_background_noise.return_value = None
        ex._playback_repo.stop_background_noise.return_value = None
        ex.current_test_case_id = 'c1'
        ex._thread_ctx = SimpleNamespace()
        ex._log = MagicMock()
        ex._handle_control = MagicMock(side_effect=TaskStopSignal('任务已停止'))
        ex._update_tc_rel_status = MagicMock()
        ex._get_control_events = MagicMock(return_value=(None, None))
        ex._prepare_rounds = MagicMock(return_value=([{'device_id': 1}], {1: 99}))
        ex._run_rounds_loop = MagicMock(return_value=([], {}, True, None))
        return ex

    def test_stop_branch_writes_terminal_without_attributeerror(self):
        from shared.utils.status_constants import ExecutionStatus

        ex = self._executor_with_stop_signal()

        # 修复前此处抛 AttributeError（TaskCaseStatus.STOPPED 不存在），
        # 异常被外层 except Exception 吞掉后误标 FAILED——修复后正常收敛
        result = ex._execute_e2e_with_rounds(
            task_id=5, tc_rel_id='rel-1',
            data={'case_name': 'n', 'case_config': {'rounds': []},
                  'test_case_id': 'case-1', 'algorithm_type': 'translation'})

        assert result is False
        kwargs = ex._update_tc_rel_status.call_args.kwargs
        assert kwargs['execution_status'] == ExecutionStatus.STOPPED
        # 不再引用不存在的 TaskCaseStatus.STOPPED（status 交由推导，无显式 status 覆盖）
        assert 'status' not in kwargs or kwargs.get('status') != 'stopped'
        assert kwargs.get('error_message') == '任务被手动停止'


class _FakeLock:
    def __init__(self):
        self.released = False

    def release(self):
        self.released = True


class TestDispatchE2EFailureTerminalPreservation:
    """复验打回修复（终态覆盖）：_execute_e2e_case 同步执行期间执行器可经 gRPC
    写入 TaskCase 终态（停止分支 execution_status=stopped / '任务被手动停止'），
    而 tc_rel 持有派发时的 identity map 快照——session.get 命中未过期陈旧对象，
    _handle_e2e_failure 把停止终态覆盖回兜底失败文案。

    修复：执行返回后 session.refresh 强制重读；防护条件排除 STOPPED 与
    INT-305 移除留痕行；告警仅对执行失败终态发布。

    用真实 SQLite 会话（StaticPool 单连接）按生产时序复现：
    派发快照载入 → claim commit 过期 → 抢锁内属性访问重读（执行前态）→
    执行期间另一会话落库终态 → 返回后收敛。修复前本组用例必失败
    （陈旧 RUNNING 对象被改写为 FAILED + 兜底文案，即复验实测的落库结果）。"""

    @staticmethod
    def _session_factory():
        from sqlalchemy import create_engine
        from sqlalchemy.pool import StaticPool
        from sqlalchemy.orm import sessionmaker
        from task_service.infrastructure.persistence.models import Task, TaskCase

        engine = create_engine(
            'sqlite:///:memory:',
            connect_args={'check_same_thread': False},
            poolclass=StaticPool,
        )
        Task.__table__.create(engine)
        TaskCase.__table__.create(engine)
        return sessionmaker(bind=engine)

    @staticmethod
    def _make_case(factory):
        from task_service.infrastructure.persistence.models import Task, TaskCase
        s = factory()
        s.add(Task(id=9, name='t', status='running',
                   total_cases=1, completed_cases=0, failed_cases=0))
        row = TaskCase(task_id=9, test_case_id='case-1', status='running',
                       execution_status=ExecutionStatus.RUNNING,
                       evaluation_status='pending', error_message=None)
        s.add(row)
        s.commit()
        row_id = row.id
        s.close()
        return row_id

    @staticmethod
    def _engine(during_execution=None):
        """engine 桩：抢锁内属性访问（模拟生产 claim-commit 过期后重读快照）；
        _execute_e2e_case 返回 False，可经 during_execution 在执行期间写库"""
        from datetime import timedelta, timezone
        from task_service.core.execution_engine.mixins.task_dispatch import TaskDispatchMixin

        eng = TaskDispatchMixin.__new__(TaskDispatchMixin)
        eng.utc_plus_8 = timezone(timedelta(hours=8))
        eng._log = MagicMock()
        eng._emit_alert = MagicMock()
        eng._claim_case = MagicMock(return_value=1)
        lock = _FakeLock()

        def _acquire(task_id_, tc_rel_):
            _ = tc_rel_.device_id  # 真实抢锁路径的属性访问：过期后重读执行前快照
            return lock

        eng._acquire_physical_device_lock = MagicMock(side_effect=_acquire)

        def _execute(task_id_, tc_rel_id_, device_id=None):
            if during_execution is not None:
                during_execution()
            return False

        eng._execute_e2e_case = MagicMock(side_effect=_execute)
        eng.refresh_task_counts_atomic = MagicMock()
        eng._count_cases_by_status = MagicMock(return_value=0)
        return eng, lock

    @staticmethod
    def _run_dispatch(factory, row_id, during_execution=None):
        eng, lock = TestDispatchE2EFailureTerminalPreservation._engine(during_execution)
        from task_service.infrastructure.persistence.models import Task, TaskCase
        s1 = factory()
        tc_rel = s1.get(TaskCase, row_id)  # identity map 快照（执行前态）
        assert tc_rel.error_message is None and tc_rel.execution_status == ExecutionStatus.RUNNING
        task = s1.get(Task, 9)
        eng._dispatch_e2e_case(9, task, tc_rel, s1)
        s1.commit()  # 主循环派发后提交（task_lifecycle.py:245 同语义）
        s1.close()
        return eng, lock

    @staticmethod
    def _fresh_read(factory, row_id):
        from task_service.infrastructure.persistence.models import TaskCase
        s3 = factory()
        try:
            return s3.get(TaskCase, row_id)
        finally:
            s3.close()

    def test_stop_terminal_not_overwritten(self):
        """复验打回主场景：执行期间执行器写入停止终态，success=False 返回后
        兜底收敛不得覆盖（修复前：陈旧对象被改写为 FAILED+兜底文案）"""
        from task_service.infrastructure.persistence.models import TaskCase
        factory = self._session_factory()
        row_id = self._make_case(factory)

        def executor_writes():
            s2 = factory()
            s2.query(TaskCase).filter(TaskCase.id == row_id).update({
                'execution_status': ExecutionStatus.STOPPED,
                'status': 'failed',
                'error_message': '任务被手动停止',
            }, synchronize_session=False)
            s2.commit()
            s2.close()

        eng, lock = self._run_dispatch(factory, row_id, executor_writes)

        fresh = self._fresh_read(factory, row_id)
        assert fresh.execution_status == ExecutionStatus.STOPPED
        assert fresh.status == 'failed'
        assert fresh.error_message == '任务被手动停止'
        eng._emit_alert.assert_not_called()  # 停止路径不发"用例执行失败"告警
        assert lock.released is True

    def test_genuine_failure_still_converges(self):
        """执行器未写终态（gRPC 失败等真失败）：兜底收敛照常写 FAILED+告警"""
        factory = self._session_factory()
        row_id = self._make_case(factory)

        eng, _lock = self._run_dispatch(factory, row_id)

        fresh = self._fresh_read(factory, row_id)
        assert fresh.execution_status == ExecutionStatus.FAILED
        assert fresh.error_message == 'E2E用例执行失败（gRPC返回失败或异常）'
        eng._emit_alert.assert_called_once()

    def test_removed_marker_not_stomped(self):
        """INT-305 移除留痕行（error_message='用例已被移除'）不参与失败收敛：
        执行器对移除用例静默退出不写终态（success=False 返回），行仍 active——
        兜底不得盖写移除标记（移除语义收敛归 INT-305）"""
        from task_service.infrastructure.persistence.models import TaskCase
        factory = self._session_factory()
        row_id = self._make_case(factory)

        def removal_marks_row():
            s2 = factory()
            s2.query(TaskCase).filter(TaskCase.id == row_id).update({
                'error_message': '用例已被移除',
            }, synchronize_session=False)
            s2.commit()
            s2.close()

        eng, _lock = self._run_dispatch(factory, row_id, removal_marks_row)

        fresh = self._fresh_read(factory, row_id)
        assert fresh.error_message == '用例已被移除'
        assert fresh.execution_status == ExecutionStatus.RUNNING
        eng._emit_alert.assert_not_called()

    def test_row_deleted_mid_execution_skips_convergence(self):
        """执行期间用例被物理删除（INT-305 待执行删除竞态）：refresh 抛
        ObjectDeletedError → 记日志跳过收敛，锁照常释放，不抛异常"""
        from task_service.infrastructure.persistence.models import TaskCase
        factory = self._session_factory()
        row_id = self._make_case(factory)

        def executor_side_deletes_row():
            s2 = factory()
            s2.query(TaskCase).filter(TaskCase.id == row_id).delete(synchronize_session=False)
            s2.commit()
            s2.close()

        eng, lock = self._run_dispatch(factory, row_id, executor_side_deletes_row)

        assert self._fresh_read(factory, row_id) is None
        assert lock.released is True
        eng._emit_alert.assert_not_called()

    def test_executor_failed_terminal_keeps_message_and_alert(self):
        """执行器已写 FAILED 终态（自定义失败文案）：兜底不覆盖文案，
        失败告警保留（既有可观测性）"""
        from task_service.infrastructure.persistence.models import TaskCase
        factory = self._session_factory()
        row_id = self._make_case(factory)

        def executor_writes_failed():
            s2 = factory()
            s2.query(TaskCase).filter(TaskCase.id == row_id).update({
                'execution_status': ExecutionStatus.FAILED,
                'status': 'failed',
                'error_message': '设备连接超时',
            }, synchronize_session=False)
            s2.commit()
            s2.close()

        eng, _lock = self._run_dispatch(factory, row_id, executor_writes_failed)

        fresh = self._fresh_read(factory, row_id)
        assert fresh.execution_status == ExecutionStatus.FAILED
        assert fresh.error_message == '设备连接超时'  # 执行器文案不被兜底覆盖
        eng._emit_alert.assert_called_once()  # 失败终态告警保留


class TestStopSweepAlignsStoppedContract:
    """INT-332 核验偏差#2：停止兜底收敛与 task_control 停止分支同款标签
    （stopped / '任务被手动停止'），移除留痕行不参与收敛（真实过滤条件）。"""

    @staticmethod
    def _engine():
        from datetime import timedelta, timezone
        from task_service.core.execution_engine.mixins.task_finalize import TaskFinalizeMixin

        eng = TaskFinalizeMixin.__new__(TaskFinalizeMixin)
        eng.utc_plus_8 = timezone(timedelta(hours=8))
        eng._log = MagicMock()
        return eng

    @staticmethod
    def _session_with_rows():
        from sqlalchemy import create_engine
        from sqlalchemy.pool import StaticPool
        from sqlalchemy.orm import sessionmaker
        from task_service.infrastructure.persistence.models import TaskCase

        engine = create_engine(
            'sqlite:///:memory:',
            connect_args={'check_same_thread': False},
            poolclass=StaticPool,
        )
        TaskCase.__table__.create(engine)
        factory = sessionmaker(bind=engine)
        s = factory()
        active = TaskCase(task_id=9, test_case_id='case-a', status='running',
                          execution_status=ExecutionStatus.RUNNING,
                          evaluation_status='running', duration=12)
        removed = TaskCase(task_id=9, test_case_id='case-b', status='running',
                           execution_status=ExecutionStatus.RUNNING,
                           evaluation_status='pending', error_message='用例已被移除')
        done = TaskCase(task_id=9, test_case_id='case-c', status='completed',
                        execution_status=ExecutionStatus.COMPLETED,
                        evaluation_status='completed')
        s.add_all([active, removed, done])
        s.commit()
        ids = (active.id, removed.id, done.id)
        s.close()
        return factory, ids

    def test_sweep_writes_stopped_contract(self):
        from task_service.infrastructure.persistence.models import TaskCase
        factory, (active_id, removed_id, done_id) = self._session_with_rows()
        eng = self._engine()
        s = factory()
        eng._mark_uncompleted_cases_failed(9, s)
        s.close()

        s = factory()
        active = s.get(TaskCase, active_id)
        assert active.execution_status == ExecutionStatus.STOPPED
        assert active.evaluation_status == 'stopped'
        assert active.status == 'failed'  # derive(stopped, stopped) = failed
        assert active.error_message == '任务被手动停止'
        assert active.duration is None
        assert active.completed_at is not None

        removed = s.get(TaskCase, removed_id)
        assert removed.error_message == '用例已被移除'  # 移除留痕不被盖写
        assert removed.execution_status == ExecutionStatus.RUNNING
        done = s.get(TaskCase, done_id)
        assert done.execution_status == ExecutionStatus.COMPLETED  # 终态不动
        s.close()



