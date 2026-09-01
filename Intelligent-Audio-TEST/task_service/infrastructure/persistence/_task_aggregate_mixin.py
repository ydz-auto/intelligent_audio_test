# -*- coding: utf-8 -*-
"""任务仓储 — 聚合根 CRUD Mixin（从 task_repository.py 拆分，P4-5）。

TaskAggregate / TaskCaseEntity 的加载、持久化与计数更新（DDD 写模型）。
"""
from datetime import datetime
from typing import List, Optional

from shared.models.database import get_db_session
from shared.utils.db_session import with_session

# 中国标准时区（UTC+8），与 _task_converters 保持一致
from task_service.infrastructure.persistence._task_converters import (
    _UTC_PLUS_8,
    _task_po_to_entity,
    _apply_aggregate_to_po,
    _task_case_po_to_entity,
    _apply_case_entity_to_po,
)
from task_service.infrastructure.persistence.models import Task, TaskCase, TaskAPI, TaskDevice
from task_service.domain.entities import TaskAggregate, TaskCaseEntity


class TaskAggregateMixin:
    """聚合根 CRUD（供 TaskRepository 组合）"""

    PO_CLASS = Task

    @with_session
    def get_by_id(self, task_id: int) -> Optional[TaskAggregate]:
        """按 ID 加载任务聚合根。

        Returns:
            TaskAggregate 或 None（任务不存在）。
        """
        po = get_db_session().get(Task, task_id)
        if po is None:
            return None
        return _task_po_to_entity(po)

    @with_session(auto_commit=True)
    def save(self, aggregate: TaskAggregate) -> None:
        """持久化聚合根变更。

        P5+DOMAIN: 通过 PO ↔ Entity 转换，将聚合根字段写回 PO，
        不再依赖 aggregate.orm 属性。
        """
        session = get_db_session()
        po = session.get(Task, aggregate.id)
        if po is None:
            # 不应发生（save 只更新已存在的聚合），但容错处理
            raise ValueError(f"Task id={aggregate.id} 不存在，无法 save")
        _apply_aggregate_to_po(aggregate, po)

    @with_session(auto_commit=True)
    def add(self, aggregate: TaskAggregate) -> int:
        """新增任务聚合根。

        Returns:
            新任务 ID。

        P5+DOMAIN: 从聚合根字段构造新 PO，不再依赖 aggregate.orm。
        """
        session = get_db_session()
        po = Task(
            name=aggregate.name,
            type=aggregate.type,
            status=aggregate.status,
            config=aggregate.config,
            algorithm_type=aggregate.algorithm_type,
            algorithm_params=aggregate.algorithm_params,
            total_cases=aggregate.total_cases,
            completed_cases=aggregate.completed_cases,
            failed_cases=aggregate.failed_cases,
            deleted=aggregate.deleted,
            started_at=aggregate.started_at,
            completed_at=aggregate.completed_at,
            actual_duration=aggregate.actual_duration,
        )
        session.add(po)
        session.flush()
        new_id = po.id
        # 将生成的 ID 回写聚合根
        aggregate.id = new_id
        return new_id

    def get_cases(self, task_id: int,
                  status: Optional[str] = None) -> List[TaskCaseEntity]:
        """加载任务下的用例实体列表。"""
        session = get_db_session()
        try:
            q = session.query(TaskCase).filter(TaskCase.task_id == task_id)
            if status:
                q = q.filter(TaskCase.status == status)
            orms = q.all()
            return [_task_case_po_to_entity(po) for po in orms]
        finally:
            session.close()

    def save_case(self, case_entity: TaskCaseEntity) -> None:
        """持久化单个用例实体变更。

        P5+DOMAIN: 通过 PO ↔ Entity 转换，不再依赖 case_entity.orm。
        """
        session = get_db_session()
        try:
            po = session.get(TaskCase, case_entity.id)
            if po is None:
                raise ValueError(f"TaskCase id={case_entity.id} 不存在，无法 save")
            _apply_case_entity_to_po(case_entity, po)
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def update_counts(self, task_id: int, completed_delta: int = 0,
                      failed_delta: int = 0) -> None:
        """原子更新任务的完成/失败计数。

        用于用例执行完成时的进度累加。
        """
        session = get_db_session()
        try:
            task = session.get(Task, task_id)
            if task is None:
                return
            if completed_delta:
                task.completed_cases = (task.completed_cases or 0) + completed_delta
            if failed_delta:
                task.failed_cases = (task.failed_cases or 0) + failed_delta
            task.updated_at = datetime.now(_UTC_PLUS_8)
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def get_api_ids(self, task_id: int) -> List[int]:
        """获取任务关联的 API ID 列表。"""
        session = get_db_session()
        try:
            rows = session.query(TaskAPI).filter_by(task_id=task_id).all()
            return [r.api_id for r in rows]
        finally:
            session.close()

    def get_device_ids(self, task_id: int) -> List[int]:
        """获取任务关联的设备 ID 列表。"""
        session = get_db_session()
        try:
            rows = session.query(TaskDevice).filter_by(task_id=task_id).all()
            return [r.device_id for r in rows]
        finally:
            session.close()
