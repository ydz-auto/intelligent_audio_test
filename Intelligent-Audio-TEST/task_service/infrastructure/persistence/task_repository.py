# -*- coding: utf-8 -*-
"""TaskRepository - 任务聚合根仓储实现（写模型）。

仓储职责：
- 从 DB 加载 Task ORM 并包装为 TaskAggregate 聚合根
- 将聚合根的变更持久化回 DB
- 提供按条件查询聚合根的方法

仓储只处理写模型，读取走 read_models（查询处理器）。
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import List, Optional

from shared.models.database import db
from shared.models.models import Task, TaskCase, TaskAPI, TaskDevice

from task_service.domain.entities import TaskAggregate, TaskCaseEntity

_UTC_PLUS_8 = timezone(timedelta(hours=8))


class TaskRepository:
    """任务聚合根仓储。

    遵循 DDD 仓储模式：外部只看到聚合根，不感知 ORM。
    每个方法内部管理 DB session 生命周期。
    """

    def get_by_id(self, task_id: int) -> Optional[TaskAggregate]:
        """按 ID 加载任务聚合根。

        Returns:
            TaskAggregate 或 None（任务不存在）。
        """
        session = db.session()
        try:
            task = session.get(Task, task_id)
            if task is None:
                return None
            return TaskAggregate(task)
        finally:
            session.close()

    def save(self, aggregate: TaskAggregate) -> None:
        """持久化聚合根变更。

        聚合根内部持有 ORM 对象的引用，修改直接反映在 ORM 上。
        此方法负责 commit。
        """
        session = db.session()
        try:
            # 将聚合根的 ORM 对象加入当前 session
            orm = aggregate.orm
            if orm not in session:
                session.merge(orm)
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def add(self, aggregate: TaskAggregate) -> int:
        """新增任务聚合根。

        Returns:
            新任务 ID。
        """
        session = db.session()
        try:
            session.add(aggregate.orm)
            session.flush()
            task_id = aggregate.orm.id
            session.commit()
            return task_id
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def soft_delete(self, task_id: int) -> bool:
        """软删除任务。"""
        session = db.session()
        try:
            task = session.get(Task, task_id)
            if task is None:
                return False
            task.deleted = True
            session.commit()
            return True
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def get_cases(self, task_id: int,
                  status: Optional[str] = None) -> List[TaskCaseEntity]:
        """加载任务下的用例实体列表。"""
        session = db.session()
        try:
            q = session.query(TaskCase).filter(TaskCase.task_id == task_id)
            if status:
                q = q.filter(TaskCase.status == status)
            orms = q.all()
            return [TaskCaseEntity(orm) for orm in orms]
        finally:
            session.close()

    def save_case(self, case_entity: TaskCaseEntity) -> None:
        """持久化单个用例实体变更。"""
        session = db.session()
        try:
            orm = case_entity.orm
            if orm not in session:
                session.merge(orm)
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
        session = db.session()
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
        session = db.session()
        try:
            rows = session.query(TaskAPI).filter_by(task_id=task_id).all()
            return [r.api_id for r in rows]
        finally:
            session.close()

    def get_device_ids(self, task_id: int) -> List[int]:
        """获取任务关联的设备 ID 列表。"""
        session = db.session()
        try:
            rows = session.query(TaskDevice).filter_by(task_id=task_id).all()
            return [r.device_id for r in rows]
        finally:
            session.close()


# 模块级单例
task_repository = TaskRepository()
