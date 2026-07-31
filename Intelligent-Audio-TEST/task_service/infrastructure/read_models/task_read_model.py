# -*- coding: utf-8 -*-
"""TaskReadModel - 任务读模型。

CQRS 读侧：直接查询 DB，支持过滤、分页、聚合统计。
读模型不返回领域聚合根，返回扁平 DTO 字典。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional  # noqa: F401

from shared.models.database import db
from shared.models.models import Task, TaskCase


class TaskReadModel:
    """任务读模型。

    提供面向查询优化的读取方法，避免加载完整 ORM 关系。
    所有方法返回 dict/list，不返回 ORM 对象。
    """

    def find_by_id(self, task_id: int) -> Optional[Dict[str, Any]]:
        """按 ID 查询单个任务（扁平 DTO）。"""
        session = db.session()
        try:
            task = session.get(Task, task_id)
            if task is None:
                return None
            return self._to_dto(task)
        finally:
            session.close()

    def search(self,
               status: Optional[str] = None,
               task_type: Optional[str] = None,
               algorithm_type: Optional[str] = None,
               created_by: Optional[int] = None,
               include_deleted: bool = False,
               page: int = 1,
               page_size: int = 20) -> Dict[str, Any]:
        """多条件过滤分页查询。"""
        session = db.session()
        try:
            q = session.query(Task)
            if not include_deleted:
                q = q.filter(Task.deleted == False)  # noqa: E712
            if status:
                q = q.filter(Task.status == status)
            if task_type:
                q = q.filter(Task.type == task_type)
            if algorithm_type:
                q = q.filter(Task.algorithm_type == algorithm_type)
            if created_by is not None:
                q = q.filter(Task.created_by == created_by)

            total = q.count()
            offset = (page - 1) * page_size
            items = (q.order_by(Task.created_at.desc())
                     .offset(offset)
                     .limit(page_size)
                     .all())

            return {
                'items': [self._to_dto(t) for t in items],
                'total': total,
                'page': page,
                'page_size': page_size,
            }
        finally:
            session.close()

    def get_progress(self, task_id: int) -> Optional[Dict[str, Any]]:
        """查询任务进度（轻量级，仅进度字段）。"""
        session = db.session()
        try:
            result = (session.query(
                Task.id, Task.status, Task.total_cases,
                Task.completed_cases, Task.failed_cases,
                Task.started_at, Task.completed_at, Task.actual_duration
            ).filter(Task.id == task_id).first())

            if result is None:
                return None

            tid, status, total, completed, failed, started, completed_at, duration = result
            total = total or 0
            completed = completed or 0
            failed = failed or 0
            processed = completed + failed
            percent = round(processed / total * 100, 2) if total > 0 else 0.0

            return {
                'task_id': tid,
                'status': status,
                'total_cases': total,
                'completed_cases': completed,
                'failed_cases': failed,
                'processed_cases': processed,
                'progress_percent': percent,
                'started_at': started.isoformat() if started else None,
                'completed_at': completed_at.isoformat() if completed_at else None,
                'actual_duration': duration,
            }
        finally:
            session.close()

    def get_case_stats(self, task_id: int) -> Dict[str, int]:
        """统计任务下各状态的用例数量。"""
        session = db.session()
        try:
            rows = (session.query(TaskCase.status)
                    .filter(TaskCase.task_id == task_id).all())
            stats: Dict[str, int] = {}
            for (s,) in rows:
                stats[s] = stats.get(s, 0) + 1
            return stats
        finally:
            session.close()

    def list_cases(self, task_id: int, status: Optional[str] = None,
                   page: int = 1, page_size: int = 50) -> Dict[str, Any]:
        """分页查询任务下用例列表。"""
        session = db.session()
        try:
            q = session.query(TaskCase).filter(TaskCase.task_id == task_id)
            if status:
                q = q.filter(TaskCase.status == status)
            total = q.count()
            offset = (page - 1) * page_size
            items = (q.order_by(TaskCase.id)
                     .offset(offset)
                     .limit(page_size)
                     .all())

            return {
                'items': [self._case_to_dto(tc) for tc in items],
                'total': total,
                'page': page,
                'page_size': page_size,
            }
        finally:
            session.close()

    # ---- 内部序列化 ----

    @staticmethod
    def _to_dto(task: Task) -> Dict[str, Any]:
        total = task.total_cases or 0
        completed = task.completed_cases or 0
        failed = task.failed_cases or 0
        processed = completed + failed
        percent = round(processed / total * 100, 2) if total > 0 else 0.0
        return {
            'task_id': task.id,
            'name': task.name,
            'description': task.description,
            'type': task.type,
            'status': task.status,
            'config': task.config,
            'algorithm_type': task.algorithm_type,
            'algorithm_params': task.algorithm_params,
            'total_cases': total,
            'completed_cases': completed,
            'failed_cases': failed,
            'processed_cases': processed,
            'progress_percent': percent,
            'created_by': task.created_by,
            'created_at': task.created_at.isoformat() if task.created_at else None,
            'updated_at': task.updated_at.isoformat() if task.updated_at else None,
            'started_at': task.started_at.isoformat() if task.started_at else None,
            'completed_at': task.completed_at.isoformat() if task.completed_at else None,
            'estimated_time': task.estimated_time,
            'actual_duration': task.actual_duration,
            'deleted': task.deleted or False,
        }

    @staticmethod
    def _case_to_dto(tc: TaskCase) -> Dict[str, Any]:
        return {
            'id': tc.id,
            'task_id': tc.task_id,
            'test_case_id': tc.test_case_id,
            'status': tc.status,
            'execution_status': tc.execution_status,
            'evaluation_status': tc.evaluation_status,
            'started_at': tc.started_at.isoformat() if tc.started_at else None,
            'completed_at': tc.completed_at.isoformat() if tc.completed_at else None,
            'duration': tc.duration,
            'error_message': tc.error_message,
        }


# 模块级单例
task_read_model = TaskReadModel()
