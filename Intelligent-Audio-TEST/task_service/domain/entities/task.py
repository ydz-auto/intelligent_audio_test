# -*- coding: utf-8 -*-
"""Task 聚合根 + 状态枚举（纯领域对象，不依赖 SQLAlchemy / db.Model）

DDD 分层原则：
- domain 层只含纯领域逻辑，不依赖基础设施（DB/HTTP/线程池）
- 领域实体 ≠ PO：PO 是持久化层概念（继承 db.Model），领域实体是领域层概念（纯业务对象）
- Repository 负责在 PO ↔ Entity 之间做转换
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from task_service.domain.entities.task_case import TaskCaseEntity


class TaskStatus(str, Enum):
    """任务状态枚举（与 PO Task.status 字段值保持一致）。"""
    PENDING = 'pending'
    QUEUED = 'queued'
    RUNNING = 'running'
    EVALUATING = 'evaluating'
    REEVALUATE_QUEUED = 'reevaluate_queued'
    REEVALUATING = 'reevaluating'
    COMPLETED = 'completed'
    FAILED = 'failed'
    STOPPED = 'stopped'
    PAUSED = 'paused'
    SKIPPED = 'skipped'

    @classmethod
    def is_terminal(cls, status: str) -> bool:
        """判断状态是否为终态。"""
        return status in (cls.COMPLETED.value, cls.FAILED.value,
                          cls.STOPPED.value, cls.SKIPPED.value)

    @classmethod
    def is_running(cls, status: str) -> bool:
        """判断状态是否为运行中。"""
        return status in (cls.RUNNING.value, cls.EVALUATING.value,
                          cls.REEVALUATING.value)


@dataclass
class TaskSnapshot:
    """Task 快照（值对象）

    从 Task PO 提取的不可变快照，含任务执行所需最小字段集。
    """
    id: int
    name: str
    type: str
    status: str = 'pending'
    config: Optional[Dict[str, Any]] = None
    algorithm_type: Optional[str] = None
    algorithm_params: Optional[Dict[str, Any]] = None
    total_cases: int = 0
    completed_cases: int = 0
    failed_cases: int = 0
    deleted: bool = False
    started_at: Optional[Any] = None
    completed_at: Optional[Any] = None
    actual_duration: Optional[int] = None


@dataclass
class TaskAggregate:
    """Task 聚合根（纯领域对象）

    任务的核心聚合根，包含任务元数据 + 关联用例集合。
    状态流转、进度计算等领域行为通过聚合根方法提供。

    注意：领域层不持有 PO 引用，通过 Repository 加载 PO 后转换为聚合根。
    """
    id: int
    name: str
    type: str
    status: str = TaskStatus.PENDING.value
    config: Optional[Dict[str, Any]] = None
    algorithm_type: Optional[str] = None
    algorithm_params: Optional[Dict[str, Any]] = None
    total_cases: int = 0
    completed_cases: int = 0
    failed_cases: int = 0
    deleted: bool = False
    started_at: Optional[Any] = None
    completed_at: Optional[Any] = None
    actual_duration: Optional[int] = None
    cases: List[TaskCaseEntity] = field(default_factory=list)

    # ---- 进度与状态查询 ----
    def progress_percent(self) -> float:
        """计算任务进度百分比。"""
        total = self.total_cases
        if total <= 0:
            return 0.0
        done = self.completed_cases + self.failed_cases
        return round(done / total * 100, 2)

    def is_running(self) -> bool:
        return TaskStatus.is_running(self.status)

    def is_terminal(self) -> bool:
        return TaskStatus.is_terminal(self.status)

    # ---- 状态流转 ----
    def can_start(self) -> bool:
        """是否允许启动（仅 pending/stopped/failed/skipped 可启动）。"""
        return self.status in (
            TaskStatus.PENDING.value,
            TaskStatus.STOPPED.value,
            TaskStatus.FAILED.value,
            TaskStatus.SKIPPED.value,
        )

    def can_pause(self) -> bool:
        return self.status in (TaskStatus.RUNNING.value, TaskStatus.QUEUED.value)

    def can_resume(self) -> bool:
        return self.status == TaskStatus.PAUSED.value

    def can_stop(self) -> bool:
        return self.status in (
            TaskStatus.RUNNING.value,
            TaskStatus.PAUSED.value,
            TaskStatus.QUEUED.value,
        )

    def mark_started(self, started_at) -> None:
        """标记任务为运行中。"""
        self.status = TaskStatus.RUNNING.value
        self.started_at = started_at

    def mark_completed(self, completed_at, actual_duration: Optional[int] = None) -> None:
        """标记任务为已完成。"""
        self.status = TaskStatus.COMPLETED.value
        self.completed_at = completed_at
        if actual_duration is not None:
            self.actual_duration = actual_duration

    def mark_failed(self, completed_at) -> None:
        """标记任务为失败。"""
        self.status = TaskStatus.FAILED.value
        self.completed_at = completed_at

    def mark_stopped(self, completed_at) -> None:
        """标记任务为已停止。"""
        self.status = TaskStatus.STOPPED.value
        self.completed_at = completed_at

    def mark_paused(self) -> None:
        if self.can_pause():
            self.status = TaskStatus.PAUSED.value

    def mark_resumed(self) -> None:
        if self.can_resume():
            self.status = TaskStatus.RUNNING.value

    def soft_delete(self) -> None:
        """软删除。"""
        self.deleted = True

    def __repr__(self) -> str:
        return (f"<TaskAggregate id={self.id} name={self.name!r} "
                f"status={self.status} progress={self.progress_percent()}%>")
