# -*- coding: utf-8 -*-
"""领域实体与聚合根。

包装 shared.models.models 中的 ORM 模型为 DDD 聚合根，
暴露领域行为（状态流转、进度计算等），隔离基础设施细节。
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, Optional

from shared.models.models import Task, TaskCase, TaskMergeRelation


class TaskStatus(str, Enum):
    """任务状态枚举（与 ORM Task.status 字段值保持一致）。"""
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


class TaskCaseStatus(str, Enum):
    """任务-用例状态枚举。"""
    PENDING = 'pending'
    COMPLETED = 'completed'
    FAILED = 'failed'
    SKIPPED = 'skipped'


class TaskAggregate:
    """Task 聚合根。

    包装 ORM Task 模型，提供领域方法：
    - 状态流转校验
    - 进度计算
    - 用例集合管理

    聚合根是事务边界，对 Task 及其关联 TaskCase 的修改都通过聚合根进行。
    """

    def __init__(self, task_orm: Task):
        self._task = task_orm

    # ---- 属性代理 ----
    @property
    def id(self) -> int:
        return self._task.id

    @property
    def name(self) -> str:
        return self._task.name

    @property
    def status(self) -> str:
        return self._task.status

    @property
    def task_type(self) -> str:
        return self._task.type

    @property
    def config(self) -> Optional[Dict[str, Any]]:
        return self._task.config

    @property
    def total_cases(self) -> int:
        return self._task.total_cases or 0

    @property
    def completed_cases(self) -> int:
        return self._task.completed_cases or 0

    @property
    def failed_cases(self) -> int:
        return self._task.failed_cases or 0

    @property
    def deleted(self) -> bool:
        return self._task.deleted or False

    @property
    def orm(self) -> Task:
        """返回底层 ORM 对象（供基础设施层持久化使用）。"""
        return self._task

    # ---- 领域方法 ----
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
        self._task.status = TaskStatus.RUNNING.value
        self._task.started_at = started_at

    def mark_completed(self, completed_at, actual_duration: Optional[int] = None) -> None:
        """标记任务为已完成。"""
        self._task.status = TaskStatus.COMPLETED.value
        self._task.completed_at = completed_at
        if actual_duration is not None:
            self._task.actual_duration = actual_duration

    def mark_failed(self, completed_at) -> None:
        """标记任务为失败。"""
        self._task.status = TaskStatus.FAILED.value
        self._task.completed_at = completed_at

    def mark_stopped(self, completed_at) -> None:
        """标记任务为已停止。"""
        self._task.status = TaskStatus.STOPPED.value
        self._task.completed_at = completed_at

    def mark_paused(self) -> None:
        if self.can_pause():
            self._task.status = TaskStatus.PAUSED.value

    def mark_resumed(self) -> None:
        if self.can_resume():
            self._task.status = TaskStatus.RUNNING.value

    def soft_delete(self) -> None:
        """软删除。"""
        self._task.deleted = True

    def __repr__(self) -> str:
        return (f"<TaskAggregate id={self.id} name={self.name!r} "
                f"status={self.status} progress={self.progress_percent()}%>")


class TaskCaseEntity:
    """TaskCase 实体（聚合内实体）。"""

    def __init__(self, task_case_orm: TaskCase):
        self._tc = task_case_orm

    @property
    def id(self) -> int:
        return self._tc.id

    @property
    def task_id(self) -> int:
        return self._tc.task_id

    @property
    def test_case_id(self) -> str:
        return self._tc.test_case_id

    @property
    def status(self) -> str:
        return self._tc.status

    @property
    def execution_status(self) -> str:
        return self._tc.execution_status

    @property
    def evaluation_status(self) -> str:
        return self._tc.evaluation_status

    @property
    def duration(self) -> Optional[int]:
        return self._tc.duration

    @property
    def orm(self) -> TaskCase:
        return self._tc

    def is_completed(self) -> bool:
        return self.status == TaskCaseStatus.COMPLETED.value

    def is_failed(self) -> bool:
        return self.status == TaskCaseStatus.FAILED.value

    def is_skipped(self) -> bool:
        return self.status == TaskCaseStatus.SKIPPED.value

    def mark_skipped(self, reason: str = '任务被手动停止', completed_at=None) -> None:
        """标记为跳过（任务停止时清理未完成用例）。"""
        self._tc.status = TaskCaseStatus.SKIPPED.value
        self._tc.execution_status = 'stopped'
        self._tc.evaluation_status = 'stopped'
        self._tc.started_at = None
        self._tc.completed_at = completed_at
        self._tc.duration = None
        self._tc.error_message = reason

    def __repr__(self) -> str:
        return (f"<TaskCaseEntity id={self.id} task_id={self.task_id} "
                f"status={self.status} exec={self.execution_status}>")


class TaskMergeRelationEntity:
    """任务合并关系实体。"""

    def __init__(self, orm: TaskMergeRelation):
        self._orm = orm

    @property
    def merged_task_id(self) -> int:
        return self._orm.merged_task_id

    @property
    def source_task_id(self) -> int:
        return self._orm.source_task_id

    @property
    def source_result_count(self) -> int:
        return self._orm.source_result_count or 0

    @property
    def orm(self) -> TaskMergeRelation:
        return self._orm
