# -*- coding: utf-8 -*-
"""INT-120 守卫：执行引擎忙等退避与评估挂起超时仲裁。

原缺陷（INT-95 主链实机验收复跑）：评估侧连接池耗尽（INT-116）导致
task_case_relations 永久停留 evaluating 时，执行引擎忙等循环暴露纵深防御
缺失——主循环 _handle_no_pending_case 每轮固定间隔刷「等待 N 个执行中/
评估中的用例完成」日志（同 logger 累计 24.5 万行）且无最大等待上限，
任务 493 永不收敛、需验收侧手工 UPDATE 解锁。

修复（EvaluationArbiterMixin，task_service 执行引擎侧纵深防御）：
- 忙等退避：等待间隔自 wait_initial_interval 倍增至 wait_max_interval，
  活跃集合变化（有进展）即重置；事件通知到达提前返回，正常路径无劣化；
- 等待日志跟随 wait_max_interval 节流：挂起场景同 logger 5 分钟 < 20 条；
- 评估挂起超时仲裁：无进展达 evaluation_hang_timeout（默认 600s，
  配置化）且执行侧已无活跃用例时，挂起用例按 INT-107 终态口径判
  failed（evaluation_status=FAILED、status 推导 failed、原因写
  error_message），逐用例发布 CASE_EVENTS/CASE_FAILED、任务级发布
  TASK_EVENTS/TASK_FAILED，主循环下一轮自然退出、任务收敛，无需人工干预；
- 执行等待上限：无进展达 test_case_wait_time 时执行中挂起用例一并判
  failed 收敛（评估未启动补写 COMPLETED，同 _finalize_dispatch_failure
  口径；已启动置 FAILED），忙等不再无限。

本文件覆盖（纯单测，不触真实 DB/Redis）：
- 退避语义：间隔倍增封顶、快照变化重置、事件等待收到当前间隔；
- 日志节流：模拟 5 分钟真实挂起，同 logger 等待日志 < 20 条（验收标准 1）；
- 仲裁触发条件矩阵：评估挂起达阈值触发；未达阈值不触发；执行侧仍有
  活跃用例时不提前触发；执行等待上限触发全量收敛；
- 终态口径矩阵（_finalize_hung_case）：评估挂起 / 执行挂起×评估
  未启动/已启动，全部落两个过程状态终态 + status 推导终态；
- 收敛事件：逐用例 CASE_FAILED + 任务级 TASK_FAILED，payload 字段
  对齐 evaluation_service 既有口径；
- 幂等与异常安全：无挂起用例返回 False 不发事件；写库失败回滚并
  返回 False（下一拍重试）。

真实 Postgres 链路（评估端点不可达 → 挂起 → 仲裁 → 收敛）由集成测试
覆盖，不在本文件范围。
"""
import os
import time as _time
from datetime import timezone, timedelta

# BaseConfig 在 import 时校验环境变量（本用例纯单测不触库，与仓库既有测试同款兜底）
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

import shared.utils.redis_pubsub as redis_pubsub_mod
from shared.utils.status_constants import (
    TaskStatus, TaskCaseStatus, ExecutionStatus, EvaluationStatus,
    ACTIVE_EXECUTION_STATUSES, ACTIVE_EVALUATION_STATUSES, FINISHED_CASE_STATUSES,
)
from shared.utils.status_utils import derive_task_case_status
from task_service.core.execution_engine.mixins import evaluation_arbiter as arbiter_mod
from task_service.core.execution_engine.mixins.evaluation_arbiter import (
    EvaluationArbiterMixin,
    ARBITRATION_REASON_EVALUATION_HANG,
    ARBITRATION_REASON_EXECUTION_HANG,
)
from task_service.core.execution_engine.mixins.task_finalize import TaskFinalizeMixin
from task_service.infrastructure.persistence.models import Task, TaskCase


class _Engine(EvaluationArbiterMixin):
    """与 ExecutionEngine 同构的最小组合（仅仲裁 Mixin，等待点打桩）。"""

    def __init__(self, evaluation_hang_timeout=600, test_case_wait_time=3000):
        self.utc_plus_8 = timezone(timedelta(hours=8))
        self.evaluation_hang_timeout = evaluation_hang_timeout
        self.test_case_wait_time = test_case_wait_time
        self.wait_initial_interval = 2
        self.wait_max_interval = 30
        self.task_wait_states = {}
        self.task_completion_events = {}
        self.logs = []
        self.alerts = []
        self.progress_emitted = []
        self.counts_refreshed = []
        self.wait_calls = []

    def _log(self, **kwargs):
        self.logs.append(kwargs)

    def _emit_alert(self, task_id, message, level='error'):
        self.alerts.append((task_id, message))

    def _emit_progress(self, task, force=False):
        self.progress_emitted.append(task)

    def refresh_task_counts_atomic(self, task_id):
        self.counts_refreshed.append(task_id)

    def _wait_completion_event(self, task_id, timeout=None):
        self.wait_calls.append((task_id, timeout))


class _RealWaitEngine(TaskFinalizeMixin):
    """仅承载 TaskFinalizeMixin._wait_completion_event 的最小引擎。"""

    def __init__(self):
        self.task_completion_events = {}

    def _log(self, **kwargs):
        pass


def _hung_eval_case(case_id='tc-rel-1', test_case_id='case-1',
                    evaluation_status=EvaluationStatus.RUNNING):
    """模拟执行已完成、评估挂起的 TaskCase 行（不入库，仅属性级）。"""
    tc = TaskCase()
    tc.id = case_id
    tc.task_id = 'task-1'
    tc.test_case_id = test_case_id
    tc.execution_status = ExecutionStatus.COMPLETED
    tc.evaluation_status = evaluation_status
    return tc


def _stuck_exec_case(case_id='tc-rel-2', test_case_id='case-2',
                     execution_status=ExecutionStatus.QUEUED,
                     evaluation_status=EvaluationStatus.PENDING):
    """模拟执行中挂起的 TaskCase 行（不入库，仅属性级）。"""
    tc = TaskCase()
    tc.id = case_id
    tc.task_id = 'task-1'
    tc.test_case_id = test_case_id
    tc.execution_status = execution_status
    tc.evaluation_status = evaluation_status
    return tc


def _task_row():
    task = Task()
    task.id = 'task-1'
    task.status = TaskStatus.RUNNING
    return task


def _advance_silent(eng, seconds, task_id='task-1'):
    """把无进展时钟回拨 seconds 秒（先拍注册快照，避免快照变化重置计时）。"""
    state = eng._get_wait_state(task_id)
    if state['snapshot'] is None:
        state['snapshot'] = eng._active_cases_snapshot(task_id)
    state['progress_at'] = _time.time() - seconds
    return state


class _FakeQuery:
    def __init__(self, items):
        self._items = list(items)

    def filter(self, *args, **kwargs):
        return self

    def all(self):
        return list(self._items)


class _FakeSession:
    """最小 DB session 打桩：query/get/commit/rollback/close。"""

    def __init__(self, cases=(), task=None, commit_error=None):
        self._cases = list(cases)
        self._task = task
        self._commit_error = commit_error
        self.committed = 0
        self.rolled_back = 0
        self.closed = 0

    def query(self, model):
        return _FakeQuery(self._cases)

    def get(self, model, obj_id):
        return self._task

    def commit(self):
        if self._commit_error is not None:
            raise self._commit_error
        self.committed += 1

    def rollback(self):
        self.rolled_back += 1

    def close(self):
        self.closed += 1


class _SpyEventBus:
    """EventBus 打桩：记录 publish 调用（替代真实 Redis）。"""

    def __init__(self, events):
        self._events = events

    def publish(self, channel, event_type, payload):
        self._events.append((channel, event_type, dict(payload)))


# ── 退避语义 ─────────────────────────────────────────────────────────────


class TestInt120WaitBackoff:
    """忙等退避：间隔倍增封顶、快照变化重置、事件等待收到当前间隔。"""

    def test_interval_doubles_and_caps_at_max(self):
        eng = _Engine()
        eng._active_cases_snapshot = lambda task_id: ((1, 'completed', 'running'),)

        for expected in (2, 4, 8, 16, 30, 30):
            eng._wait_active_cases_with_backoff('task-1')
            assert eng.wait_calls[-1] == ('task-1', expected)

    def test_snapshot_change_resets_interval(self):
        eng = _Engine()
        snapshots = iter([
            ((1, 'completed', 'running'),),
            ((1, 'completed', 'calculating'),),  # 评估推进 → 有进展
        ])
        eng._active_cases_snapshot = lambda task_id: next(snapshots)

        eng._wait_active_cases_with_backoff('task-1')  # 间隔 2 → 4
        eng._wait_active_cases_with_backoff('task-1')  # 快照变化 → 重置为 2
        assert eng.wait_calls[-1] == ('task-1', 2)

    def test_arbitration_tick_returns_without_wait(self, monkeypatch):
        """仲裁发生的那一拍立即返回（不进入事件等待），下一拍主循环自然退出。"""
        eng = _Engine(evaluation_hang_timeout=600)
        eng._active_cases_snapshot = lambda task_id: ((1, 'completed', 'running'),)
        monkeypatch.setattr(arbiter_mod, 'get_db_session',
                            lambda: _FakeSession(cases=[_hung_eval_case()], task=_task_row()))

        _advance_silent(eng, 601)
        eng._wait_active_cases_with_backoff('task-1')

        assert eng.wait_calls == []  # 仲裁拍不等待
        state = eng.task_wait_states['task-1']
        assert state['interval'] == eng.wait_initial_interval  # 仲裁后重置


class TestInt120LogThrottling:
    """日志节流：挂起场景同 logger 5 分钟 < 20 条（验收标准 1）。"""

    def test_hang_scenario_wait_log_under_20_per_5min(self, monkeypatch):
        eng = _Engine()
        # 挂起场景：活跃快照恒定，评估永不完成
        eng._active_cases_snapshot = lambda task_id: ((1, 'completed', 'running'),)

        # 假时钟推进 300 秒真实挂起：每拍后按当前退避间隔推进时钟
        clock = {'now': 1000.0}
        monkeypatch.setattr(arbiter_mod.time, 'time', lambda: clock['now'])
        while clock['now'] < 1000.0 + 300:
            eng._wait_active_cases_with_backoff('task-1')
            clock['now'] += eng.task_wait_states['task-1']['interval']

        wait_logs = [l for l in eng.logs if '等待' in str(l.get('content', ''))]
        assert len(wait_logs) < 20

    def test_first_tick_always_logs(self):
        eng = _Engine()
        eng._active_cases_snapshot = lambda task_id: ()
        eng._wait_active_cases_with_backoff('task-1')
        assert len(eng.logs) == 1


# ── 仲裁触发条件 ─────────────────────────────────────────────────────────


class TestInt120ArbitrationTriggers:
    """评估挂起超时仲裁的触发条件矩阵。"""

    def test_evaluation_hang_at_timeout_triggers_arbitration(self, monkeypatch):
        eng = _Engine(evaluation_hang_timeout=600)
        cases = [_hung_eval_case()]
        session = _FakeSession(cases=cases, task=_task_row())
        monkeypatch.setattr(arbiter_mod, 'get_db_session', lambda: session)
        eng._active_cases_snapshot = lambda task_id: ((1, 'completed', 'running'),)

        _advance_silent(eng, 601)
        eng._wait_active_cases_with_backoff('task-1')

        assert session.committed == 1
        assert cases[0].evaluation_status == EvaluationStatus.FAILED
        assert eng.counts_refreshed == ['task-1']
        assert eng.alerts and eng.progress_emitted
        assert eng.wait_calls == []  # 仲裁拍不等待

    def test_no_arbitration_below_timeout(self, monkeypatch):
        eng = _Engine(evaluation_hang_timeout=600)
        session = _FakeSession(cases=[_hung_eval_case()], task=_task_row())
        monkeypatch.setattr(arbiter_mod, 'get_db_session', lambda: session)
        eng._active_cases_snapshot = lambda task_id: ((1, 'completed', 'running'),)

        eng._wait_active_cases_with_backoff('task-1')  # silent ≈ 0

        assert session.committed == 0
        assert eng.counts_refreshed == []
        assert eng.wait_calls  # 继续正常退避等待

    def test_no_arbitration_while_execution_active(self, monkeypatch):
        """执行侧仍有活跃用例时，评估挂起不提前仲裁（等执行等待上限兜底）。"""
        eng = _Engine(evaluation_hang_timeout=600, test_case_wait_time=3000)
        cases = [_hung_eval_case(), _stuck_exec_case()]
        session = _FakeSession(cases=cases, task=_task_row())
        monkeypatch.setattr(arbiter_mod, 'get_db_session', lambda: session)
        eng._active_cases_snapshot = lambda task_id: (
            (1, 'completed', 'running'), (2, 'queued', 'pending'))

        _advance_silent(eng, 601)  # 超评估阈值，未超执行阈值
        eng._wait_active_cases_with_backoff('task-1')

        assert session.committed == 0
        assert eng.counts_refreshed == []

    def test_execution_wait_limit_converges_all_stuck(self, monkeypatch):
        """无进展达执行等待上限（test_case_wait_time）：执行中挂起一并收敛。"""
        eng = _Engine(test_case_wait_time=3000)
        cases = [_stuck_exec_case(), _hung_eval_case()]
        session = _FakeSession(cases=cases, task=_task_row())
        monkeypatch.setattr(arbiter_mod, 'get_db_session', lambda: session)
        eng._active_cases_snapshot = lambda task_id: (
            (2, 'queued', 'pending'), (1, 'completed', 'running'))

        _advance_silent(eng, 3001)
        eng._wait_active_cases_with_backoff('task-1')

        assert session.committed == 1
        assert all(tc.status == TaskCaseStatus.FAILED for tc in cases)


# ── 终态口径（_finalize_hung_case） ──────────────────────────────────────


class TestInt120HungCaseFinalization:
    """挂起用例判 failed 的终态口径矩阵（INT-107 口径沿袭）。"""

    def test_evaluation_hang_marks_evaluation_failed(self):
        tc = _hung_eval_case()
        reason = _Engine()._finalize_hung_case(tc, silent_seconds=601.0)

        assert reason == ARBITRATION_REASON_EVALUATION_HANG
        assert tc.execution_status == ExecutionStatus.COMPLETED  # 执行侧不动
        assert tc.evaluation_status == EvaluationStatus.FAILED
        assert tc.status == TaskCaseStatus.FAILED
        assert '评估挂起超时' in tc.error_message
        assert '601' in tc.error_message

    def test_evaluation_hang_covers_calculating_status(self):
        tc = _hung_eval_case(evaluation_status=EvaluationStatus.CALCULATING)
        _Engine()._finalize_hung_case(tc, silent_seconds=601.0)

        assert tc.evaluation_status == EvaluationStatus.FAILED
        assert tc.status == TaskCaseStatus.FAILED

    def test_execution_hang_bumps_pending_evaluation_to_completed(self):
        """执行挂起且评估未启动：补写评估终态（_finalize_dispatch_failure 口径）。"""
        tc = _stuck_exec_case(execution_status=ExecutionStatus.QUEUED,
                              evaluation_status=EvaluationStatus.PENDING)
        reason = _Engine()._finalize_hung_case(tc, silent_seconds=3001.0)

        assert reason == ARBITRATION_REASON_EXECUTION_HANG
        assert tc.execution_status == ExecutionStatus.FAILED
        assert tc.evaluation_status == EvaluationStatus.COMPLETED
        assert tc.status == TaskCaseStatus.FAILED
        assert tc.completed_at is not None
        assert tc.duration == 0
        assert '执行挂起超时' in tc.error_message

    def test_execution_hang_marks_started_evaluation_failed(self):
        tc = _stuck_exec_case(execution_status=ExecutionStatus.RUNNING,
                              evaluation_status=EvaluationStatus.RUNNING)
        _Engine()._finalize_hung_case(tc, silent_seconds=3001.0)

        assert tc.execution_status == ExecutionStatus.FAILED
        assert tc.evaluation_status == EvaluationStatus.FAILED
        assert tc.status == TaskCaseStatus.FAILED

    def test_finalized_case_is_terminal_in_both_dimensions(self):
        """收敛不变量：仲裁后两个过程状态均终态，主循环可退出、任务可收敛。"""
        eng = _Engine()
        cases = [
            _hung_eval_case(),
            _hung_eval_case(evaluation_status=EvaluationStatus.CALCULATING),
            _stuck_exec_case(execution_status=ExecutionStatus.QUEUED,
                             evaluation_status=EvaluationStatus.PENDING),
            _stuck_exec_case(execution_status=ExecutionStatus.RUNNING,
                             evaluation_status=EvaluationStatus.RUNNING),
        ]
        for tc in cases:
            eng._finalize_hung_case(tc, silent_seconds=601.0)

            assert tc.execution_status not in ACTIVE_EXECUTION_STATUSES
            assert tc.evaluation_status not in ACTIVE_EVALUATION_STATUSES
            assert tc.status in FINISHED_CASE_STATUSES
            assert derive_task_case_status(tc.execution_status,
                                           tc.evaluation_status) == TaskCaseStatus.FAILED


# ── 收敛事件 ─────────────────────────────────────────────────────────────


class TestInt120ArbitrationEvents:
    """仲裁收敛事件：逐用例 CASE_FAILED + 任务级 TASK_FAILED（验收标准 3）。"""

    def test_events_published_for_evaluation_hang(self, monkeypatch):
        events = []
        monkeypatch.setattr(redis_pubsub_mod, 'EventBus', lambda: _SpyEventBus(events))
        eng = _Engine(evaluation_hang_timeout=600)
        cases = [_hung_eval_case(),
                 _hung_eval_case('tc-rel-3', 'case-3', EvaluationStatus.CALCULATING)]
        session = _FakeSession(cases=cases, task=_task_row())
        monkeypatch.setattr(arbiter_mod, 'get_db_session', lambda: session)

        assert eng._arbitrate_hung_cases('task-1', include_execution_stuck=False,
                                         silent_seconds=601.0) is True

        case_events = [e for e in events if e[1] == 'case_failed']
        task_events = [e for e in events if e[1] == 'task_failed']
        assert len(case_events) == 2
        assert len(task_events) == 1

        channel, _, payload = case_events[0]
        assert channel == 'case_events'
        assert payload['task_id'] == 'task-1'
        assert payload['evaluation_status'] == EvaluationStatus.FAILED
        assert payload['case_status'] == TaskCaseStatus.FAILED
        assert payload['success'] is False
        assert payload['reason'] == ARBITRATION_REASON_EVALUATION_HANG

        _, _, task_payload = task_events[0]
        assert task_payload['task_id'] == 'task-1'
        assert task_payload['status'] == TaskStatus.FAILED

    def test_task_event_reason_reflects_execution_hang(self, monkeypatch):
        events = []
        monkeypatch.setattr(redis_pubsub_mod, 'EventBus', lambda: _SpyEventBus(events))
        eng = _Engine(test_case_wait_time=3000)
        session = _FakeSession(cases=[_stuck_exec_case()], task=_task_row())
        monkeypatch.setattr(arbiter_mod, 'get_db_session', lambda: session)

        eng._arbitrate_hung_cases('task-1', include_execution_stuck=True,
                                  silent_seconds=3001.0)

        task_events = [e for e in events if e[1] == 'task_failed']
        assert task_events[0][2]['reason'] == ARBITRATION_REASON_EXECUTION_HANG


# ── 幂等与异常安全 ───────────────────────────────────────────────────────


class TestInt120ArbitrationSafety:
    """无挂起用例不动作；写库失败回滚并返回 False（下一拍重试）。"""

    def test_no_hung_cases_returns_false_without_events(self, monkeypatch):
        events = []
        monkeypatch.setattr(redis_pubsub_mod, 'EventBus', lambda: _SpyEventBus(events))
        eng = _Engine()
        session = _FakeSession(cases=[], task=_task_row())
        monkeypatch.setattr(arbiter_mod, 'get_db_session', lambda: session)

        assert eng._arbitrate_hung_cases('task-1', include_execution_stuck=False,
                                         silent_seconds=700.0) is False
        assert session.committed == 0
        assert events == []
        assert eng.counts_refreshed == []

    def test_commit_failure_rolls_back_and_returns_false(self, monkeypatch):
        events = []
        monkeypatch.setattr(redis_pubsub_mod, 'EventBus', lambda: _SpyEventBus(events))
        eng = _Engine()
        session = _FakeSession(cases=[_hung_eval_case()], task=_task_row(),
                               commit_error=RuntimeError('db down'))
        monkeypatch.setattr(arbiter_mod, 'get_db_session', lambda: session)

        assert eng._arbitrate_hung_cases('task-1', include_execution_stuck=False,
                                         silent_seconds=700.0) is False
        assert session.rolled_back == 1
        assert session.committed == 0
        assert events == []  # 事件只在写库成功后发布

    def test_session_always_closed(self, monkeypatch):
        eng = _Engine()
        session = _FakeSession(cases=[], task=_task_row())
        monkeypatch.setattr(arbiter_mod, 'get_db_session', lambda: session)

        eng._arbitrate_hung_cases('task-1', include_execution_stuck=False,
                                  silent_seconds=700.0)
        assert session.closed == 1


# ── 等待状态生命周期与事件等待参数 ────────────────────────────────────────


class TestInt120WaitStateLifecycle:
    def test_reset_wait_state_pops_entry(self):
        eng = _Engine()
        eng._get_wait_state('task-1')
        assert 'task-1' in eng.task_wait_states

        eng._reset_wait_state('task-1')
        assert 'task-1' not in eng.task_wait_states

    def test_wait_completion_event_passes_timeout_to_event(self):
        class _WaitEvent:
            def __init__(self):
                self.timeouts = []

            def wait(self, timeout=None):
                self.timeouts.append(timeout)

        eng = _RealWaitEngine()
        event = _WaitEvent()
        eng.task_completion_events['task-1'] = event

        eng._wait_completion_event('task-1', timeout=17)
        assert event.timeouts == [17]

    def test_wait_completion_event_default_sleeps_5s(self, monkeypatch):
        import task_service.core.execution_engine.mixins.task_finalize as finalize_mod
        eng = _RealWaitEngine()
        sleeps = []
        monkeypatch.setattr(finalize_mod.time, 'sleep', lambda s: sleeps.append(s))

        eng._wait_completion_event('task-1')  # 无事件 → sleep 兜底
        assert sleeps == [5]

        eng._wait_completion_event('task-1', timeout=30)
        assert sleeps == [5, 30]


# ── 配置化（禁魔法数字） ─────────────────────────────────────────────────


class TestInt120ConfigWiring:
    def test_concurrency_config_contains_arbiter_keys(self):
        from shared.utils.config_manager import config_manager

        assert config_manager.get_value('execution_engine', 'evaluation_hang_timeout') == 600
        assert config_manager.get_value('execution_engine', 'wait_initial_interval') == 2
        assert config_manager.get_value('execution_engine', 'wait_max_interval') == 30

    def test_engine_instance_loads_arbiter_config(self):
        from task_service.core.execution_engine import execution_engine

        assert execution_engine.evaluation_hang_timeout == 600
        assert execution_engine.wait_initial_interval == 2
        assert execution_engine.wait_max_interval == 30
        assert execution_engine.task_wait_states == {}
