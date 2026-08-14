# -*- coding: utf-8 -*-
"""TaskCase 状态推导工具

status 字段由 execution_status + evaluation_status 推导，不手动赋值。
所有服务统一使用此函数，确保 status 始终一致。
"""
from shared.utils.status_constants import ExecutionStatus, EvaluationStatus, TaskCaseStatus


def derive_task_case_status(execution_status: str, evaluation_status: str) -> str:
    """根据 execution_status 和 evaluation_status 推导 status。

    推导规则：
    - execution_status=failed/stopped → failed
    - execution_status=completed AND evaluation_status=completed → completed
    - execution_status=completed AND evaluation_status=failed/stopped → failed
    - execution_status=completed AND evaluation_status IN (queued/running/calculating/pending) → evaluating
    - execution_status IN (queued/running) → running
    - 其余 → pending
    """
    if execution_status in (ExecutionStatus.FAILED, ExecutionStatus.STOPPED):
        return TaskCaseStatus.FAILED
    if execution_status == ExecutionStatus.COMPLETED:
        if evaluation_status == EvaluationStatus.COMPLETED:
            return TaskCaseStatus.COMPLETED
        if evaluation_status in (EvaluationStatus.FAILED, EvaluationStatus.STOPPED):
            return TaskCaseStatus.FAILED
        return TaskCaseStatus.EVALUATING
    if execution_status in (ExecutionStatus.QUEUED, ExecutionStatus.RUNNING):
        return TaskCaseStatus.RUNNING
    return TaskCaseStatus.PENDING
