# -*- coding: utf-8 -*-
"""Run 状态机（落地方案 §9.1）。

    QUEUED → RUNNING → WAITING_APPROVAL → RUNNING → SUCCEEDED
                     ↘ FAILED / CANCELLED / BUDGET_EXCEEDED

非法迁移一律抛 InvalidRunTransition —— 状态推进只能经此，禁止各处直接写库。
"""
from typing import Dict, FrozenSet

from agent_service.domain.enums import RunStatus
from agent_service.domain.exceptions import InvalidRunTransition


_ALLOWED_TRANSITIONS: Dict[RunStatus, FrozenSet[RunStatus]] = {
    RunStatus.QUEUED: frozenset({
        RunStatus.RUNNING,
        RunStatus.FAILED,
        RunStatus.CANCELLED,
        RunStatus.BUDGET_EXCEEDED,
    }),
    RunStatus.RUNNING: frozenset({
        RunStatus.WAITING_APPROVAL,
        RunStatus.SUCCEEDED,
        RunStatus.FAILED,
        RunStatus.CANCELLED,
        RunStatus.BUDGET_EXCEEDED,
    }),
    RunStatus.WAITING_APPROVAL: frozenset({
        RunStatus.RUNNING,
        RunStatus.FAILED,
        RunStatus.CANCELLED,
        RunStatus.BUDGET_EXCEEDED,
    }),
    RunStatus.SUCCEEDED: frozenset(),
    RunStatus.FAILED: frozenset(),
    RunStatus.CANCELLED: frozenset(),
    RunStatus.BUDGET_EXCEEDED: frozenset(),
}


class RunStateMachine:
    """纯函数状态机：校验 → 返回目标状态。"""

    @staticmethod
    def allowed_targets(current: RunStatus) -> FrozenSet[RunStatus]:
        return _ALLOWED_TRANSITIONS[current]

    @staticmethod
    def can_transition(current: RunStatus, target: RunStatus) -> bool:
        return target in _ALLOWED_TRANSITIONS[current]

    @classmethod
    def assert_transition(cls, current: RunStatus, target: RunStatus) -> RunStatus:
        if not cls.can_transition(current, target):
            raise InvalidRunTransition(current.value, target.value)
        return target

    @staticmethod
    def is_terminal(status: RunStatus) -> bool:
        return status.is_terminal
