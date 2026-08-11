# -*- coding: utf-8 -*-
"""TaskAggregate 聚合根测试。

测试 task_service.domain.entities.task.TaskAggregate 的：
- progress_percent() 进度计算
- can_start/can_pause/can_resume/can_stop 状态校验
- mark_started/mark_completed/mark_failed/mark_stopped/mark_paused/mark_resumed 状态转换
- soft_delete()
"""
from datetime import datetime

import pytest

from task_service.domain.entities.task import TaskAggregate, TaskStatus


def make_aggregate(status='pending', total=0, completed=0, failed=0,
                   deleted=False) -> TaskAggregate:
    """构造测试用 TaskAggregate。"""
    return TaskAggregate(
        id=1,
        name='test-task',
        type='voice',
        status=status,
        total_cases=total,
        completed_cases=completed,
        failed_cases=failed,
        deleted=deleted,
    )


class TestProgressPercent:
    """progress_percent() 计算。"""

    def test_zero_cases_returns_zero(self):
        agg = make_aggregate(total=0)
        assert agg.progress_percent() == 0.0

    def test_zero_total_returns_zero(self):
        agg = make_aggregate(total=0, completed=0)
        assert agg.progress_percent() == 0.0

    def test_negative_total_returns_zero(self):
        agg = make_aggregate(total=-5)
        assert agg.progress_percent() == 0.0

    def test_half_complete_returns_50(self):
        agg = make_aggregate(total=10, completed=5)
        assert agg.progress_percent() == 50.0

    def test_all_complete_returns_100(self):
        agg = make_aggregate(total=10, completed=10)
        assert agg.progress_percent() == 100.0

    def test_failed_counts_as_done(self):
        # failed_cases 也计入完成数
        agg = make_aggregate(total=10, completed=3, failed=2)
        assert agg.progress_percent() == 50.0

    def test_full_done_with_failures(self):
        agg = make_aggregate(total=4, completed=3, failed=1)
        assert agg.progress_percent() == 100.0


class TestCanStart:
    """can_start() 状态校验。"""

    @pytest.mark.parametrize("status", [
        TaskStatus.PENDING.value,
        TaskStatus.STOPPED.value,
        TaskStatus.FAILED.value,
        TaskStatus.SKIPPED.value,
    ])
    def test_can_start_returns_true(self, status):
        agg = make_aggregate(status=status)
        assert agg.can_start() is True

    @pytest.mark.parametrize("status", [
        TaskStatus.RUNNING.value,
        TaskStatus.QUEUED.value,
        TaskStatus.COMPLETED.value,
        TaskStatus.PAUSED.value,
        TaskStatus.EVALUATING.value,
    ])
    def test_cannot_start_returns_false(self, status):
        agg = make_aggregate(status=status)
        assert agg.can_start() is False


class TestCanPause:
    """can_pause() 状态校验。"""

    @pytest.mark.parametrize("status", [
        TaskStatus.RUNNING.value,
        TaskStatus.QUEUED.value,
    ])
    def test_can_pause_returns_true(self, status):
        agg = make_aggregate(status=status)
        assert agg.can_pause() is True

    @pytest.mark.parametrize("status", [
        TaskStatus.COMPLETED.value,
        TaskStatus.PENDING.value,
        TaskStatus.PAUSED.value,
        TaskStatus.STOPPED.value,
    ])
    def test_cannot_pause_returns_false(self, status):
        agg = make_aggregate(status=status)
        assert agg.can_pause() is False


class TestCanResume:
    """can_resume() 状态校验。"""

    def test_can_resume_paused(self):
        agg = make_aggregate(status=TaskStatus.PAUSED.value)
        assert agg.can_resume() is True

    @pytest.mark.parametrize("status", [
        TaskStatus.RUNNING.value,
        TaskStatus.PENDING.value,
        TaskStatus.COMPLETED.value,
        TaskStatus.STOPPED.value,
    ])
    def test_cannot_resume_non_paused(self, status):
        agg = make_aggregate(status=status)
        assert agg.can_resume() is False


class TestCanStop:
    """can_stop() 状态校验。"""

    @pytest.mark.parametrize("status", [
        TaskStatus.RUNNING.value,
        TaskStatus.PAUSED.value,
        TaskStatus.QUEUED.value,
    ])
    def test_can_stop_returns_true(self, status):
        agg = make_aggregate(status=status)
        assert agg.can_stop() is True

    @pytest.mark.parametrize("status", [
        TaskStatus.COMPLETED.value,
        TaskStatus.PENDING.value,
        TaskStatus.FAILED.value,
        TaskStatus.STOPPED.value,
    ])
    def test_cannot_stop_returns_false(self, status):
        agg = make_aggregate(status=status)
        assert agg.can_stop() is False


class TestMarkStarted:
    def test_mark_started_sets_status_and_time(self):
        agg = make_aggregate(status=TaskStatus.PENDING.value)
        now = datetime(2026, 1, 1, 12, 0, 0)
        agg.mark_started(now)
        assert agg.status == TaskStatus.RUNNING.value
        assert agg.started_at == now


class TestMarkCompleted:
    def test_mark_completed_sets_status_and_time(self):
        agg = make_aggregate(status=TaskStatus.RUNNING.value)
        now = datetime(2026, 1, 1, 12, 0, 0)
        agg.mark_completed(now)
        assert agg.status == TaskStatus.COMPLETED.value
        assert agg.completed_at == now

    def test_mark_completed_with_duration(self):
        agg = make_aggregate(status=TaskStatus.RUNNING.value)
        now = datetime(2026, 1, 1, 12, 0, 0)
        agg.mark_completed(now, actual_duration=3600)
        assert agg.status == TaskStatus.COMPLETED.value
        assert agg.completed_at == now
        assert agg.actual_duration == 3600

    def test_mark_completed_without_duration_keeps_none(self):
        agg = make_aggregate(status=TaskStatus.RUNNING.value)
        agg.actual_duration = None
        now = datetime(2026, 1, 1, 12, 0, 0)
        agg.mark_completed(now)
        assert agg.actual_duration is None


class TestMarkFailed:
    def test_mark_failed_sets_status_and_time(self):
        agg = make_aggregate(status=TaskStatus.RUNNING.value)
        now = datetime(2026, 1, 1, 12, 0, 0)
        agg.mark_failed(now)
        assert agg.status == TaskStatus.FAILED.value
        assert agg.completed_at == now


class TestMarkStopped:
    def test_mark_stopped_sets_status_and_time(self):
        agg = make_aggregate(status=TaskStatus.RUNNING.value)
        now = datetime(2026, 1, 1, 12, 0, 0)
        agg.mark_stopped(now)
        assert agg.status == TaskStatus.STOPPED.value
        assert agg.completed_at == now


class TestMarkPaused:
    def test_mark_paused_from_running(self):
        agg = make_aggregate(status=TaskStatus.RUNNING.value)
        agg.mark_paused()
        assert agg.status == TaskStatus.PAUSED.value

    def test_mark_paused_from_queued(self):
        agg = make_aggregate(status=TaskStatus.QUEUED.value)
        agg.mark_paused()
        assert agg.status == TaskStatus.PAUSED.value

    def test_mark_paused_from_completed_no_change(self):
        # can_pause() 对 completed 返回 False，状态不变
        agg = make_aggregate(status=TaskStatus.COMPLETED.value)
        agg.mark_paused()
        assert agg.status == TaskStatus.COMPLETED.value


class TestMarkResumed:
    def test_mark_resumed_from_paused(self):
        agg = make_aggregate(status=TaskStatus.PAUSED.value)
        agg.mark_resumed()
        assert agg.status == TaskStatus.RUNNING.value

    def test_mark_resumed_from_running_no_change(self):
        agg = make_aggregate(status=TaskStatus.RUNNING.value)
        agg.mark_resumed()
        assert agg.status == TaskStatus.RUNNING.value


class TestSoftDelete:
    def test_soft_delete_sets_deleted_true(self):
        agg = make_aggregate(deleted=False)
        assert agg.deleted is False
        agg.soft_delete()
        assert agg.deleted is True

    def test_soft_delete_idempotent(self):
        agg = make_aggregate(deleted=True)
        agg.soft_delete()
        assert agg.deleted is True


class TestIsRunningIsTerminal:
    def test_is_running_true(self):
        agg = make_aggregate(status=TaskStatus.RUNNING.value)
        assert agg.is_running() is True

    def test_is_running_false(self):
        agg = make_aggregate(status=TaskStatus.PENDING.value)
        assert agg.is_running() is False

    def test_is_terminal_true(self):
        agg = make_aggregate(status=TaskStatus.COMPLETED.value)
        assert agg.is_terminal() is True

    def test_is_terminal_false(self):
        agg = make_aggregate(status=TaskStatus.RUNNING.value)
        assert agg.is_terminal() is False


class TestRepr:
    def test_repr_contains_id_and_status(self):
        agg = make_aggregate(status=TaskStatus.RUNNING.value, total=10,
                             completed=5)
        r = repr(agg)
        assert 'TaskAggregate' in r
        assert 'id=1' in r
        assert 'running' in r
