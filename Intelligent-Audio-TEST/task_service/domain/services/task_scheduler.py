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

    差异#2 收尾：调度互斥依据为任务执行画像
    （has_physical：含物理用例占 e2e 单飞槽位；api_ids：API 并发互斥），
    task.type 语义已废弃。
    """

    @staticmethod
    def can_run_concurrently(has_physical: bool, running_e2e: bool,
                             running_apis: set, api_ids: list) -> bool:
        """判断任务是否可以并发执行。

        物理任务：同一时间只允许一个。
        API 任务：不能有相同 API 正在运行。
        """
        if has_physical and running_e2e:
            return False
        overlapping = set(api_ids) & running_apis
        return len(overlapping) == 0

    @staticmethod
    def should_dequeue(has_physical: bool, running_e2e: bool,
                       running_apis: set, api_ids: list) -> bool:
        """判断排队任务是否应该出队执行。"""
        return TaskScheduler.can_run_concurrently(
            has_physical, running_e2e, running_apis, api_ids
        )
