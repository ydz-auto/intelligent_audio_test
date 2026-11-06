# -*- coding: utf-8 -*-
"""TaskStatus 枚举测试。

测试 task_service.domain.entities.task.TaskStatus 的类方法：
- is_terminal(): 终态判断
- is_running():  运行态判断
"""
import pytest

from task_service.domain.entities.task import TaskStatus


class TestTaskStatusIsTerminal:
    """is_terminal() 对所有终态返回 True。"""

    @pytest.mark.parametrize("status", [
        TaskStatus.COMPLETED.value,
        TaskStatus.FAILED.value,
        TaskStatus.STOPPED.value,
        TaskStatus.SKIPPED.value,
    ])
    def test_terminal_states_return_true(self, status):
        assert TaskStatus.is_terminal(status) is True

    @pytest.mark.parametrize("status", [
        TaskStatus.PENDING.value,
        TaskStatus.QUEUED.value,
        TaskStatus.RUNNING.value,
        TaskStatus.EVALUATING.value,
        TaskStatus.REEVALUATE_QUEUED.value,
        TaskStatus.REEVALUATING.value,
        TaskStatus.PAUSED.value,
    ])
    def test_non_terminal_states_return_false(self, status):
        assert TaskStatus.is_terminal(status) is False


class TestTaskStatusIsRunning:
    """is_running() 对运行态返回 True。"""

    @pytest.mark.parametrize("status", [
        TaskStatus.RUNNING.value,
        TaskStatus.EVALUATING.value,
        TaskStatus.REEVALUATING.value,
    ])
    def test_running_states_return_true(self, status):
        assert TaskStatus.is_running(status) is True

    @pytest.mark.parametrize("status", [
        TaskStatus.PENDING.value,
        TaskStatus.QUEUED.value,
        TaskStatus.COMPLETED.value,
        TaskStatus.FAILED.value,
        TaskStatus.STOPPED.value,
        TaskStatus.PAUSED.value,
        TaskStatus.SKIPPED.value,
        TaskStatus.REEVALUATE_QUEUED.value,
    ])
    def test_non_running_states_return_false(self, status):
        assert TaskStatus.is_running(status) is False


class TestTaskStatusEnumMembers:
    """枚举成员值正确性。"""

    def test_enum_values_are_strings(self):
        for member in TaskStatus:
            assert isinstance(member.value, str)

    def test_pending_value(self):
        assert TaskStatus.PENDING.value == 'pending'

    def test_completed_value(self):
        assert TaskStatus.COMPLETED.value == 'completed'
