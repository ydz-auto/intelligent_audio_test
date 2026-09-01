# -*- coding: utf-8 -*-
"""Task PO ↔ Entity 转换器（从 task_repository.py 拆分，P4-5）。

TaskAggregate / TaskCaseEntity 的双向显式映射（DDD PO ↔ Entity）。
"""
from datetime import timezone, timedelta

from shared.utils.status_constants import ExecutionStatus, EvaluationStatus, TaskCaseStatus
from task_service.infrastructure.persistence.models import Task, TaskCase
from task_service.domain.entities import TaskAggregate, TaskCaseEntity

# 中国标准时区（UTC+8），与 shared.models.database.utc8now 语义一致
_UTC_PLUS_8 = timezone(timedelta(hours=8))


def _task_po_to_entity(po: Task) -> TaskAggregate:
    """Task PO → TaskAggregate 聚合根"""
    return TaskAggregate(
        id=po.id,
        name=po.name,
        type=po.type,
        status=po.status,
        config=po.config,
        algorithm_type=po.algorithm_type,
        algorithm_params=po.algorithm_params,
        total_cases=po.total_cases or 0,
        completed_cases=po.completed_cases or 0,
        failed_cases=po.failed_cases or 0,
        deleted=po.deleted or False,
        started_at=po.started_at,
        completed_at=po.completed_at,
        actual_duration=po.actual_duration,
        cases=[],  # 用例集合按需加载
    )


def _apply_aggregate_to_po(aggregate: TaskAggregate, po: Task) -> None:
    """将聚合根的可写字段映射回 PO（不含 id/deleted_at/created_at 等元数据）"""
    # 只更新可变字段，避免覆盖不可变字段
    po.status = aggregate.status
    po.config = aggregate.config
    po.algorithm_type = aggregate.algorithm_type
    po.algorithm_params = aggregate.algorithm_params
    po.total_cases = aggregate.total_cases
    po.completed_cases = aggregate.completed_cases
    po.failed_cases = aggregate.failed_cases
    po.deleted = aggregate.deleted
    po.started_at = aggregate.started_at
    po.completed_at = aggregate.completed_at
    po.actual_duration = aggregate.actual_duration


def _task_case_po_to_entity(po: TaskCase) -> TaskCaseEntity:
    """TaskCase PO → TaskCaseEntity 实体"""
    return TaskCaseEntity(
        id=po.id,
        task_id=po.task_id,
        test_case_id=po.test_case_id,
        status=po.status or TaskCaseStatus.PENDING,
        execution_status=po.execution_status or ExecutionStatus.PENDING,
        evaluation_status=po.evaluation_status or EvaluationStatus.PENDING,
        started_at=po.started_at,
        completed_at=po.completed_at,
        duration=po.duration,
        error_message=po.error_message,
    )


def _apply_case_entity_to_po(entity: TaskCaseEntity, po: TaskCase) -> None:
    """将 TaskCaseEntity 可写字段映射回 PO"""
    po.status = entity.status
    po.execution_status = entity.execution_status
    po.evaluation_status = entity.evaluation_status
    po.started_at = entity.started_at
    po.completed_at = entity.completed_at
    po.duration = entity.duration
    po.error_message = entity.error_message
