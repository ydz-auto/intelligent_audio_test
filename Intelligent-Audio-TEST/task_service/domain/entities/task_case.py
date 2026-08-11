# -*- coding: utf-8 -*-
"""TaskCase 实体 + 快照 + 状态枚举（纯领域对象）"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional


class TaskCaseStatus(str, Enum):
    """任务-用例状态枚举。"""
    PENDING = 'pending'
    COMPLETED = 'completed'
    FAILED = 'failed'
    SKIPPED = 'skipped'


@dataclass
class TaskCaseSnapshot:
    """TaskCase 快照（值对象）

    评估执行时从 TaskCase PO 提取的不可变快照，包含评估所需的最小字段集。
    使用快照而非 PO 引用，避免领域层依赖 ORM。
    """
    id: int
    task_id: int
    test_case_id: str
    status: str = 'pending'
    execution_status: str = 'pending'
    evaluation_status: str = 'pending'
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
    status: str = 'pending'
    execution_status: str = 'pending'
    evaluation_status: str = 'pending'
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

    def mark_skipped(self, reason: str = '任务被手动停止', completed_at=None) -> None:
        """标记为跳过（任务停止时清理未完成用例）。"""
        self.status = TaskCaseStatus.SKIPPED.value
        self.execution_status = 'stopped'
        self.evaluation_status = 'stopped'
        self.started_at = None
        self.completed_at = completed_at
        self.duration = None
        self.error_message = reason
