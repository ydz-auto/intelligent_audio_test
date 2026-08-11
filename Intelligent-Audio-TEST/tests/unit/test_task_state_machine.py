# -*- coding: utf-8 -*-
"""TaskStateMachine 测试。

测试 task_service.domain.services.task_state_machine.TaskStateMachine：
- can_transition() 合法/非法转换
- validate_action() 返回 (bool, str) 元组
- apply_action() 正确更新聚合根状态
"""
from datetime import datetime

import pytest

from task_service.domain.entities.task import TaskAggregate, TaskStatus
from task_service.domain.services.task_state_machine import TaskStateMachine


def make_aggregate(status='pending') -> TaskAggregate:
    return TaskAggregate(
        id=1,
        name='test-task',
        type='voice',
        status=status,
    )


class TestCanTransition:
    """can_transition() 对合法转换返回 True。"""

    @pytest.mark.parametrize("current,action", [
        # PENDING 可 start / skip
        (TaskStatus.PENDING.value, 'start'),
        (TaskStatus.PENDING.value, 'skip'),
        # QUEUED 可 start / pause / stop / skip
        (TaskStatus.QUEUED.value, 'start'),
        (TaskStatus.QUEUED.value, 'pause'),
        (TaskStatus.QUEUED.value, 'stop'),
        (TaskStatus.QUEUED.value, 'skip'),
        # RUNNING 可 pause / stop / complete / fail
        (TaskStatus.RUNNING.value, 'pause'),
        (TaskStatus.RUNNING.value, 'stop'),
        (TaskStatus.RUNNING.value, 'complete'),
        (TaskStatus.RUNNING.value, 'fail'),
        # PAUSED 可 resume / stop
        (TaskStatus.PAUSED.value, 'resume'),
        (TaskStatus.PAUSED.value, 'stop'),
        # STOPPED 可 start
        (TaskStatus.STOPPED.value, 'start'),
        # FAILED 可 start / reevaluate
        (TaskStatus.FAILED.value, 'start'),
        (TaskStatus.FAILED.value, 'reevaluate'),
        # COMPLETED 可 reevaluate
        (TaskStatus.COMPLETED.value, 'reevaluate'),
        # SKIPPED 可 start
        (TaskStatus.SKIPPED.value, 'start'),
        # EVALUATING 可 complete / fail / stop
        (TaskStatus.EVALUATING.value, 'complete'),
        (TaskStatus.EVALUATING.value, 'fail'),
        (TaskStatus.EVALUATING.value, 'stop'),
        # REEVALUATE_QUEUED 可 reevaluate_start / stop
        (TaskStatus.REEVALUATE_QUEUED.value, 'reevaluate_start'),
        (TaskStatus.REEVALUATE_QUEUED.value, 'stop'),
        # REEVALUATING 可 complete / fail / stop
        (TaskStatus.REEVALUATING.value, 'complete'),
        (TaskStatus.REEVALUATING.value, 'fail'),
        (TaskStatus.REEVALUATING.value, 'stop'),
    ])
    def test_legal_transition_returns_true(self, current, action):
        assert TaskStateMachine.can_transition(current, action) is True

    @pytest.mark.parametrize("current,action", [
        # PENDING 不能 pause / stop / complete
        (TaskStatus.PENDING.value, 'pause'),
        (TaskStatus.PENDING.value, 'stop'),
        (TaskStatus.PENDING.value, 'complete'),
        (TaskStatus.PENDING.value, 'fail'),
        # RUNNING 不能 start / resume / skip
        (TaskStatus.RUNNING.value, 'start'),
        (TaskStatus.RUNNING.value, 'resume'),
        (TaskStatus.RUNNING.value, 'skip'),
        # COMPLETED 不能 start / pause / stop
        (TaskStatus.COMPLETED.value, 'start'),
        (TaskStatus.COMPLETED.value, 'pause'),
        (TaskStatus.COMPLETED.value, 'stop'),
        # PAUSED 不能 start / complete / fail
        (TaskStatus.PAUSED.value, 'start'),
        (TaskStatus.PAUSED.value, 'complete'),
        (TaskStatus.PAUSED.value, 'fail'),
        # STOPPED 不能 pause / resume / complete
        (TaskStatus.STOPPED.value, 'pause'),
        (TaskStatus.STOPPED.value, 'resume'),
        (TaskStatus.STOPPED.value, 'complete'),
        # 未知状态
        ('unknown_state', 'start'),
    ])
    def test_illegal_transition_returns_false(self, current, action):
        assert TaskStateMachine.can_transition(current, action) is False


class TestValidateAction:
    """validate_action() 返回 (bool, str) 元组。"""

    def test_validate_start_pending_ok(self):
        agg = make_aggregate(status=TaskStatus.PENDING.value)
        ok, msg = TaskStateMachine.validate_action(agg, 'start')
        assert ok is True
        assert isinstance(msg, str)

    def test_validate_start_running_rejected(self):
        agg = make_aggregate(status=TaskStatus.RUNNING.value)
        ok, msg = TaskStateMachine.validate_action(agg, 'start')
        assert ok is False
        assert isinstance(msg, str)
        assert 'running' in msg or '启动' in msg

    def test_validate_pause_running_ok(self):
        agg = make_aggregate(status=TaskStatus.RUNNING.value)
        ok, msg = TaskStateMachine.validate_action(agg, 'pause')
        assert ok is True

    def test_validate_pause_completed_rejected(self):
        agg = make_aggregate(status=TaskStatus.COMPLETED.value)
        ok, msg = TaskStateMachine.validate_action(agg, 'pause')
        assert ok is False
        assert '暂停' in msg

    def test_validate_resume_paused_ok(self):
        agg = make_aggregate(status=TaskStatus.PAUSED.value)
        ok, msg = TaskStateMachine.validate_action(agg, 'resume')
        assert ok is True

    def test_validate_resume_running_rejected(self):
        agg = make_aggregate(status=TaskStatus.RUNNING.value)
        ok, msg = TaskStateMachine.validate_action(agg, 'resume')
        assert ok is False
        assert '恢复' in msg

    def test_validate_stop_running_ok(self):
        agg = make_aggregate(status=TaskStatus.RUNNING.value)
        ok, msg = TaskStateMachine.validate_action(agg, 'stop')
        assert ok is True

    def test_validate_stop_pending_rejected(self):
        agg = make_aggregate(status=TaskStatus.PENDING.value)
        ok, msg = TaskStateMachine.validate_action(agg, 'stop')
        assert ok is False
        assert '停止' in msg

    def test_validate_complete_running_ok(self):
        agg = make_aggregate(status=TaskStatus.RUNNING.value)
        ok, msg = TaskStateMachine.validate_action(agg, 'complete')
        assert ok is True

    def test_validate_complete_pending_rejected(self):
        agg = make_aggregate(status=TaskStatus.PENDING.value)
        ok, msg = TaskStateMachine.validate_action(agg, 'complete')
        assert ok is False

    def test_validate_fail_running_ok(self):
        agg = make_aggregate(status=TaskStatus.RUNNING.value)
        ok, msg = TaskStateMachine.validate_action(agg, 'fail')
        assert ok is True

    def test_validate_skip_pending_ok(self):
        agg = make_aggregate(status=TaskStatus.PENDING.value)
        ok, msg = TaskStateMachine.validate_action(agg, 'skip')
        assert ok is True

    def test_validate_skip_running_rejected(self):
        agg = make_aggregate(status=TaskStatus.RUNNING.value)
        ok, msg = TaskStateMachine.validate_action(agg, 'skip')
        assert ok is False

    def test_validate_reevaluate_completed_ok(self):
        agg = make_aggregate(status=TaskStatus.COMPLETED.value)
        ok, msg = TaskStateMachine.validate_action(agg, 'reevaluate')
        assert ok is True

    def test_validate_reevaluate_running_rejected(self):
        agg = make_aggregate(status=TaskStatus.RUNNING.value)
        ok, msg = TaskStateMachine.validate_action(agg, 'reevaluate')
        assert ok is False

    def test_validate_unknown_action_rejected(self):
        agg = make_aggregate(status=TaskStatus.PENDING.value)
        ok, msg = TaskStateMachine.validate_action(agg, 'explode')
        assert ok is False
        assert '未知动作' in msg or 'explode' in msg

    def test_validate_returns_tuple_of_two(self):
        agg = make_aggregate(status=TaskStatus.PENDING.value)
        result = TaskStateMachine.validate_action(agg, 'start')
        assert isinstance(result, tuple)
        assert len(result) == 2


class TestApplyAction:
    """apply_action() 正确更新聚合根状态。"""

    def test_apply_start(self):
        agg = make_aggregate(status=TaskStatus.PENDING.value)
        TaskStateMachine.apply_action(agg, 'start')
        assert agg.status == TaskStatus.RUNNING.value
        assert agg.started_at is not None

    def test_apply_start_with_explicit_now(self):
        agg = make_aggregate(status=TaskStatus.PENDING.value)
        now = datetime(2026, 1, 1, 12, 0, 0)
        TaskStateMachine.apply_action(agg, 'start', now=now)
        assert agg.status == TaskStatus.RUNNING.value
        assert agg.started_at == now

    def test_apply_pause(self):
        agg = make_aggregate(status=TaskStatus.RUNNING.value)
        TaskStateMachine.apply_action(agg, 'pause')
        assert agg.status == TaskStatus.PAUSED.value

    def test_apply_resume(self):
        agg = make_aggregate(status=TaskStatus.PAUSED.value)
        TaskStateMachine.apply_action(agg, 'resume')
        assert agg.status == TaskStatus.RUNNING.value

    def test_apply_stop(self):
        agg = make_aggregate(status=TaskStatus.RUNNING.value)
        TaskStateMachine.apply_action(agg, 'stop')
        assert agg.status == TaskStatus.STOPPED.value
        assert agg.completed_at is not None

    def test_apply_complete(self):
        agg = make_aggregate(status=TaskStatus.RUNNING.value)
        TaskStateMachine.apply_action(agg, 'complete', actual_duration=120)
        assert agg.status == TaskStatus.COMPLETED.value
        assert agg.actual_duration == 120

    def test_apply_fail(self):
        agg = make_aggregate(status=TaskStatus.RUNNING.value)
        TaskStateMachine.apply_action(agg, 'fail')
        assert agg.status == TaskStatus.FAILED.value
        assert agg.completed_at is not None

    def test_apply_skip_sets_stopped(self):
        # skip 动作在 apply_action 中调用 mark_stopped
        agg = make_aggregate(status=TaskStatus.PENDING.value)
        TaskStateMachine.apply_action(agg, 'skip')
        assert agg.status == TaskStatus.STOPPED.value

    def test_apply_complete_without_duration(self):
        agg = make_aggregate(status=TaskStatus.RUNNING.value)
        agg.actual_duration = None
        TaskStateMachine.apply_action(agg, 'complete')
        assert agg.status == TaskStatus.COMPLETED.value
        assert agg.actual_duration is None

    def test_apply_reason_param_accepted(self):
        # reason 参数不影响状态转换，仅作为记录
        agg = make_aggregate(status=TaskStatus.RUNNING.value)
        TaskStateMachine.apply_action(agg, 'stop', reason='manual stop')
        assert agg.status == TaskStatus.STOPPED.value
