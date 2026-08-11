# -*- coding: utf-8 -*-
"""任务状态机（纯领域逻辑，不依赖基础设施）

封装合法的状态转换规则，提取自 ExecutionEngine.control_task 中的状态校验逻辑。
所有状态流转必须经过此状态机校验，确保业务一致性。
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple

from task_service.domain.entities import TaskAggregate, TaskStatus

_UTC_PLUS_8 = timezone(timedelta(hours=8))


class TaskStateMachine:
    """任务状态机。

    封装合法的状态转换规则，提取自 ExecutionEngine.control_task 中的状态校验逻辑。
    所有状态流转必须经过此状态机校验，确保业务一致性。
    """

    # 合法状态转换表: {当前状态: {允许的目标状态/动作}}
    _TRANSITIONS = {
        TaskStatus.PENDING.value: {'start', 'skip'},
        TaskStatus.QUEUED.value: {'start', 'pause', 'stop', 'skip'},
        TaskStatus.RUNNING.value: {'pause', 'stop', 'complete', 'fail'},
        TaskStatus.PAUSED.value: {'resume', 'stop'},
        TaskStatus.STOPPED.value: {'start'},
        TaskStatus.FAILED.value: {'start', 'reevaluate'},
        TaskStatus.COMPLETED.value: {'reevaluate'},
        TaskStatus.SKIPPED.value: {'start'},
        TaskStatus.EVALUATING.value: {'complete', 'fail', 'stop'},
        TaskStatus.REEVALUATE_QUEUED.value: {'reevaluate_start', 'stop'},
        TaskStatus.REEVALUATING.value: {'complete', 'fail', 'stop'},
    }

    @classmethod
    def can_transition(cls, current_status: str, action: str) -> bool:
        """校验当前状态是否允许执行指定动作。"""
        allowed = cls._TRANSITIONS.get(current_status, set())
        return action in allowed

    @classmethod
    def validate_action(cls, aggregate: TaskAggregate, action: str) -> Tuple[bool, str]:
        """校验动作合法性，返回 (是否允许, 消息)。

        Args:
            aggregate: Task 聚合根
            action: 动作类型 (start/pause/resume/stop/complete/fail/skip)
        """
        current = aggregate.status

        # 委托聚合根的业务校验
        if action == 'start':
            if not aggregate.can_start():
                return False, f"当前状态 {current} 不允许启动"
        elif action == 'pause':
            if not aggregate.can_pause():
                return False, "只有执行中或排队中的任务才能暂停"
        elif action == 'resume':
            if not aggregate.can_resume():
                return False, "只有已暂停的任务才能恢复"
        elif action == 'stop':
            if not aggregate.can_stop():
                return False, "只有执行中、已暂停或排队中的任务才能停止"
        elif action in ('complete', 'fail', 'skip', 'reevaluate',
                         'reevaluate_start'):
            if not cls.can_transition(current, action):
                return False, f"当前状态 {current} 不允许执行 {action}"
        else:
            return False, f"未知动作: {action}"

        return True, "ok"

    @classmethod
    def apply_action(cls, aggregate: TaskAggregate, action: str,
                     now: Optional[datetime] = None,
                     actual_duration: Optional[int] = None,
                     reason: str = '') -> None:
        """在聚合根上应用状态转换动作。

        调用前应先 validate_action 校验。
        """
        if now is None:
            now = datetime.now(_UTC_PLUS_8)

        if action == 'start':
            aggregate.mark_started(now)
        elif action == 'pause':
            aggregate.mark_paused()
        elif action == 'resume':
            aggregate.mark_resumed()
        elif action == 'stop':
            aggregate.mark_stopped(now)
        elif action == 'complete':
            aggregate.mark_completed(now, actual_duration)
        elif action == 'fail':
            aggregate.mark_failed(now)
        elif action == 'skip':
            aggregate.mark_stopped(now)
