# -*- coding: utf-8 -*-
"""领域服务 (Domain Services)。

封装跨实体的领域逻辑，不持有状态。
- TaskStateMachine: 提取 ExecutionEngine 中的任务状态机逻辑
- TaskScheduler:    任务调度领域服务（委托给 ExecutionEngine 执行）
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional, Tuple

from task_service.domain.entities import TaskAggregate, TaskStatus


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
            from datetime import timezone, timedelta
            now = datetime.now(timezone(timedelta(hours=8)))

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


class TaskScheduler:
    """任务调度领域服务。

    领域层的调度逻辑仅定义调度规则和策略，
    实际执行委托给 ExecutionEngine（基础设施层）。
    本类不持有可变状态，仅提供无状态的决策方法。
    """

    @staticmethod
    def can_run_concurrently(task_type: str, running_e2e: bool,
                              running_apis: set, api_ids: list) -> bool:
        """判断任务是否可以并发执行。

        E2E 任务：同一时间只允许一个。
        API 任务：不能有相同 API 正在运行。
        """
        if task_type == 'e2e':
            return not running_e2e
        # API 任务
        overlapping = set(api_ids) & running_apis
        return len(overlapping) == 0

    @staticmethod
    def should_dequeue(task_type: str, running_e2e: bool,
                       running_apis: set, api_ids: list) -> bool:
        """判断排队任务是否应该出队执行。"""
        return TaskScheduler.can_run_concurrently(
            task_type, running_e2e, running_apis, api_ids
        )
