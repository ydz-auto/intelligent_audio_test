# -*- coding: utf-8 -*-
"""查询处理器 (Query Handlers) - CQRS 读模型处理器。

重要原则：直接查 DB，不走 ExecutionEngine。
读模型关注查询效率和返回 DTO，不返回领域聚合根。
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from shared.models.database import db
from shared.models.models import Task, TaskCase, TaskAPI, TaskDevice

from task_service.application.queries.task_queries import (
    GetTaskQuery,
    ListTasksQuery,
    GetTaskProgressQuery,
    GetTaskCasesQuery,
)


def _serialize_task(task: Task, include_cases: bool = False) -> Dict[str, Any]:
    """将 Task ORM 序列化为 DTO 字典。"""
    total = task.total_cases or 0
    completed = task.completed_cases or 0
    failed = task.failed_cases or 0
    processed = completed + failed
    percent = round(processed / total * 100, 2) if total > 0 else 0.0

    data = {
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
    return data


def _serialize_task_case(tc: TaskCase) -> Dict[str, Any]:
    """将 TaskCase ORM 序列化为 DTO 字典。"""
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


class TaskQueryHandler:
    """任务查询处理器。

    所有读操作通过此类入口，直接查询 DB。
    查询处理器无状态，可安全并发调用。
    """

    def handle_get_task(self, query: GetTaskQuery) -> Optional[Dict[str, Any]]:
        """处理获取单个任务详情查询。

        Returns:
            任务 DTO 字典，任务不存在返回 None。
        """
        session = db.session()
        try:
            task = session.get(Task, query.task_id)
            if task is None:
                return None
            data = _serialize_task(task, query.include_cases)

            if query.include_cases:
                cases = (session.query(TaskCase)
                         .filter(TaskCase.task_id == query.task_id)
                         .all())
                data['cases'] = [_serialize_task_case(tc) for tc in cases]

            # 关联的 API 和设备 ID
            api_ids = [r.api_id for r in
                       session.query(TaskAPI).filter_by(task_id=query.task_id).all()]
            device_ids = [r.device_id for r in
                          session.query(TaskDevice).filter_by(task_id=query.task_id).all()]
            data['api_ids'] = api_ids
            data['device_ids'] = device_ids

            return data
        finally:
            session.close()

    def handle_list_tasks(self, query: ListTasksQuery) -> Dict[str, Any]:
        """处理任务列表查询（带过滤和分页）。

        Returns:
            {'items': [...], 'total': N, 'page': P, 'page_size': S}
        """
        session = db.session()
        try:
            q = session.query(Task)

            # 过滤
            if not query.include_deleted:
                q = q.filter(Task.deleted == False)  # noqa: E712

            if query.status:
                q = q.filter(Task.status == query.status)
            if query.task_type:
                q = q.filter(Task.type == query.task_type)
            if query.algorithm_type:
                q = q.filter(Task.algorithm_type == query.algorithm_type)
            if query.created_by is not None:
                q = q.filter(Task.created_by == query.created_by)

            total = q.count()

            # 分页（按创建时间倒序）
            offset = (query.page - 1) * query.page_size
            items = (q.order_by(Task.created_at.desc())
                     .offset(offset)
                     .limit(query.page_size)
                     .all())

            return {
                'items': [_serialize_task(t) for t in items],
                'total': total,
                'page': query.page,
                'page_size': query.page_size,
            }
        finally:
            session.close()

    def handle_get_task_progress(self, query: GetTaskProgressQuery) -> Optional[Dict[str, Any]]:
        """处理获取任务进度查询（轻量级）。

        仅查询进度相关字段，避免加载完整任务对象。
        """
        session = db.session()
        try:
            task = session.get(Task, query.task_id)
            if task is None:
                return None

            total = task.total_cases or 0
            completed = task.completed_cases or 0
            failed = task.failed_cases or 0
            processed = completed + failed
            percent = round(processed / total * 100, 2) if total > 0 else 0.0

            return {
                'task_id': task.id,
                'status': task.status,
                'total_cases': total,
                'completed_cases': completed,
                'failed_cases': failed,
                'processed_cases': processed,
                'progress_percent': percent,
                'started_at': task.started_at.isoformat() if task.started_at else None,
                'completed_at': task.completed_at.isoformat() if task.completed_at else None,
                'actual_duration': task.actual_duration,
            }
        finally:
            session.close()

    def handle_get_task_cases(self, query: GetTaskCasesQuery) -> Dict[str, Any]:
        """处理获取任务下用例执行状态查询。"""
        session = db.session()
        try:
            q = session.query(TaskCase).filter(TaskCase.task_id == query.task_id)

            if query.status:
                q = q.filter(TaskCase.status == query.status)

            total = q.count()
            offset = (query.page - 1) * query.page_size
            items = (q.order_by(TaskCase.id)
                     .offset(offset)
                     .limit(query.page_size)
                     .all())

            return {
                'items': [_serialize_task_case(tc) for tc in items],
                'total': total,
                'page': query.page,
                'page_size': query.page_size,
            }
        finally:
            session.close()


# 模块级单例
task_query_handler = TaskQueryHandler()
