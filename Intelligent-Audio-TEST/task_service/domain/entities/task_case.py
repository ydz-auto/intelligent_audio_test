# -*- coding: utf-8 -*-
"""TaskCase 实体 + 快照 + 状态枚举（纯领域对象）"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional


class TaskCaseStatus(str, Enum):
    """用例最终结果状态（由 execution_status + evaluation_status 推导，不直接修改）。"""
    PENDING = 'pending'
    RUNNING = 'running'
    EVALUATING = 'evaluating'
    COMPLETED = 'completed'
    FAILED = 'failed'
    SKIPPED = 'skipped'


class ExecutionStatus(str, Enum):
    """用例执行过程状态。"""
    PENDING = 'pending'
    QUEUED = 'queued'
    RUNNING = 'running'
    COMPLETED = 'completed'
    STOPPED = 'stopped'
    FAILED = 'failed'


class EvaluationStatus(str, Enum):
    """用例评估过程状态。"""
    PENDING = 'pending'
    QUEUED = 'queued'
    RUNNING = 'running'
    CALCULATING = 'calculating'
    COMPLETED = 'completed'
    STOPPED = 'stopped'
    FAILED = 'failed'


def derive_task_case_status(execution_status: str, evaluation_status: str) -> str:
    """根据 execution_status 和 evaluation_status 推导 status。

    推导规则：
    - execution_status=failed/stopped → failed
    - execution_status=completed AND evaluation_status=completed → completed
    - execution_status=completed AND evaluation_status=failed/stopped → failed
    - execution_status=completed AND evaluation_status IN (queued/running/calculating) → evaluating
    - execution_status IN (queued/running) → running
    - 其余 → pending
    """
    if execution_status in (ExecutionStatus.FAILED.value, ExecutionStatus.STOPPED.value):
        return TaskCaseStatus.FAILED.value
    if execution_status == ExecutionStatus.COMPLETED.value:
        if evaluation_status == EvaluationStatus.COMPLETED.value:
            return TaskCaseStatus.COMPLETED.value
        if evaluation_status in (EvaluationStatus.FAILED.value, EvaluationStatus.STOPPED.value):
            return TaskCaseStatus.FAILED.value
        if evaluation_status in (EvaluationStatus.QUEUED.value, EvaluationStatus.RUNNING.value, EvaluationStatus.CALCULATING.value):
            return TaskCaseStatus.EVALUATING.value
        # evaluation_status=pending 等，执行完成但评估未开始
        return TaskCaseStatus.EVALUATING.value
    if execution_status in (ExecutionStatus.QUEUED.value, ExecutionStatus.RUNNING.value):
        return TaskCaseStatus.RUNNING.value
    return TaskCaseStatus.PENDING.value


@dataclass
class TaskCaseSnapshot:
    """TaskCase 快照（值对象）

    评估执行时从 TaskCase PO 提取的不可变快照，包含评估所需的最小字段集。
    使用快照而非 PO 引用，避免领域层依赖 ORM。
    """
    id: int
    task_id: int
    test_case_id: str
    status: str = TaskCaseStatus.PENDING.value
    execution_status: str = ExecutionStatus.PENDING.value
    evaluation_status: str = EvaluationStatus.PENDING.value
    started_at: Optional[Any] = None  # datetime
    completed_at: Optional[Any] = None
    duration: Optional[int] = None
    error_message: Optional[str] = None


@dataclass
class TaskCaseEntity:
    """TaskCase 实体（聚合内实体）

    归属 TaskAggregate 聚合，表示任务中某个用例的执行状态。
    对应 PO TaskCase，但不含持久化字段（id/created_at 等）。
    """
    id: int
    task_id: int
    test_case_id: str
    status: str = TaskCaseStatus.PENDING.value
    execution_status: str = ExecutionStatus.PENDING.value
    evaluation_status: str = EvaluationStatus.PENDING.value
    started_at: Optional[Any] = None
    completed_at: Optional[Any] = None
    duration: Optional[int] = None
    error_message: Optional[str] = None

    def is_completed(self) -> bool:
        return self.status == TaskCaseStatus.COMPLETED.value

    def is_failed(self) -> bool:
        return self.status == TaskCaseStatus.FAILED.value

    def is_skipped(self) -> bool:
        return self.status == TaskCaseStatus.SKIPPED.value

    def mark_execution_queued(self) -> None:
        """标记用例为排队中（原子占用）。"""
        self.execution_status = ExecutionStatus.QUEUED.value
        self.status = derive_task_case_status(self.execution_status, self.evaluation_status)

    def mark_execution_running(self) -> None:
        """标记用例为执行中。"""
        self.execution_status = ExecutionStatus.RUNNING.value
        self.status = derive_task_case_status(self.execution_status, self.evaluation_status)

    def mark_execution_completed(self) -> None:
        """标记用例执行完成。"""
        self.execution_status = ExecutionStatus.COMPLETED.value
        self.status = derive_task_case_status(self.execution_status, self.evaluation_status)

    def mark_execution_failed(self, error_message: str = '') -> None:
        """标记用例执行失败。"""
        self.execution_status = ExecutionStatus.FAILED.value
        self.status = derive_task_case_status(self.execution_status, self.evaluation_status)
        self.error_message = error_message

    def mark_evaluation_queued(self) -> None:
        """标记用例评估排队中。"""
        self.evaluation_status = EvaluationStatus.QUEUED.value
        self.status = derive_task_case_status(self.execution_status, self.evaluation_status)

    def mark_evaluation_running(self) -> None:
        """标记用例评估中。"""
        self.evaluation_status = EvaluationStatus.RUNNING.value
        self.status = derive_task_case_status(self.execution_status, self.evaluation_status)

    def mark_evaluation_calculating(self) -> None:
        """标记用例评估计算中。"""
        self.evaluation_status = EvaluationStatus.CALCULATING.value
        self.status = derive_task_case_status(self.execution_status, self.evaluation_status)

    def mark_evaluation_completed(self) -> None:
        """标记用例评估完成。"""
        self.evaluation_status = EvaluationStatus.COMPLETED.value
        self.status = derive_task_case_status(self.execution_status, self.evaluation_status)

    def mark_evaluation_failed(self, error_message: str = '') -> None:
        """标记用例评估失败。"""
        self.evaluation_status = EvaluationStatus.FAILED.value
        self.status = derive_task_case_status(self.execution_status, self.evaluation_status)
        self.error_message = error_message

    def mark_skipped(self, reason: str = '任务被手动停止', completed_at=None) -> None:
        """标记为跳过（任务停止时清理未完成用例）。"""
        self.execution_status = ExecutionStatus.STOPPED.value
        self.evaluation_status = EvaluationStatus.STOPPED.value
        self.status = derive_task_case_status(self.execution_status, self.evaluation_status)
        self.started_at = None
        self.completed_at = completed_at
        self.duration = None
        self.error_message = reason
