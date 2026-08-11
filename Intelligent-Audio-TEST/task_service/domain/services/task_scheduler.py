# -*- coding: utf-8 -*-
"""任务调度领域服务（纯逻辑，不持有状态）

领域层的调度逻辑仅定义调度规则和策略，
实际执行委托给 ExecutionEngine（基础设施层）。
本类不持有可变状态，仅提供无状态的决策方法。
"""
from __future__ import annotations


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
