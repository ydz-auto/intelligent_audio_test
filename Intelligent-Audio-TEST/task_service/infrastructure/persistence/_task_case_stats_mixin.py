# -*- coding: utf-8 -*-
"""任务仓储 — TaskCase 状态 / dict 序列化 / 统计 Mixin（从 task_repository.py 拆分，P4-5）。

供 gRPC servicer 使用的 dict 序列化读取、TaskCase 状态更新、聚合统计、
TaskCaseRepositoryABC 接口适配。
"""
from typing import Any, Dict, List, Optional

from shared.models.database import get_db_session, utc8now
from shared.utils.status_utils import derive_task_case_status
from shared.utils.status_constants import (
    ExecutionStatus,
    TaskStatus as SharedTaskStatus,
)
from task_service.infrastructure.persistence.models import Task, TaskCase, TaskAPI, TaskDevice


class TaskCaseStatsMixin:
    """TaskCase 状态维护与 dict 序列化（供 TaskRepository 组合）"""

    # ========== TaskDataService servicer 用 — dict 序列化方法 ==========

    def get_task_dict_by_id(self, task_id: int) -> Optional[dict]:
        """按 ID 读取 Task 详情（返回 dict 序列化格式，供 gRPC servicer 用）。"""
        session = get_db_session()
        try:
            task = session.get(Task, task_id)
            if task is None:
                return None
            return {
                'id': task.id,
                'name': task.name,
                'description': task.description,
                'type': task.type,
                'status': task.status,
                'config': task.config,
                'algorithm_type': task.algorithm_type,
                'algorithm_params': task.algorithm_params,
                'total_cases': task.total_cases,
                'completed_cases': task.completed_cases,
                'failed_cases': task.failed_cases,
                'created_by_user_id': task.created_by_user_id,
                'created_at': task.created_at.isoformat() if task.created_at else None,
                'updated_at': task.updated_at.isoformat() if task.updated_at else None,
                'started_at': task.started_at.isoformat() if task.started_at else None,
                'completed_at': task.completed_at.isoformat() if task.completed_at else None,
                'estimated_time': task.estimated_time,
                'actual_duration': task.actual_duration,
            }
        finally:
            session.close()

    def update_status(self, task_id: int, status: str) -> Optional[dict]:
        """更新 Task 的 status，返回 {task_id, old_status, new_status} 或 None。"""
        session = get_db_session()
        try:
            task = session.get(Task, task_id)
            if task is None:
                return None
            old_status = task.status
            task.status = status
            # 重新评估完成时自动更新计数和时间戳
            if old_status == SharedTaskStatus.REEVALUATING and status in (SharedTaskStatus.COMPLETED, SharedTaskStatus.FAILED):
                task.reevaluation_count = (task.reevaluation_count or 0) + 1
                task.reevaluated_at = utc8now()
            session.flush()
            return {
                'task_id': task.id,
                'old_status': old_status,
                'new_status': task.status,
            }
        finally:
            session.close()

    def get_task_device_dicts(self, task_id: int) -> List[dict]:
        """获取任务关联设备列表（返回 dict 列表）。"""
        session = get_db_session()
        try:
            rows = session.query(TaskDevice).filter(
                TaskDevice.task_id == task_id
            ).all()
            return [{'id': td.id, 'task_id': td.task_id, 'device_id': td.device_id} for td in rows]
        finally:
            session.close()

    def get_task_api_dicts(self, task_id: int) -> List[dict]:
        """获取任务关联 API 列表（返回 dict 列表）。"""
        session = get_db_session()
        try:
            rows = session.query(TaskAPI).filter(
                TaskAPI.task_id == task_id
            ).all()
            return [{'id': ta.id, 'task_id': ta.task_id, 'api_id': ta.api_id} for ta in rows]
        finally:
            session.close()

    def get_task_case_dicts(self, task_id: int, case_ids: List[str] = None) -> List[dict]:
        """按 task_id + case_ids 批量读取 TaskCase（返回 dict 列表）。

        case_ids 为空时返回该 task 下所有 TaskCase。
        """
        session = get_db_session()
        try:
            q = session.query(TaskCase).filter(TaskCase.task_id == task_id)
            if case_ids:
                q = q.filter(TaskCase.test_case_id.in_(list(case_ids)))
            tcs = q.all()
            return [{
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
            } for tc in tcs]
        finally:
            session.close()

    def update_task_case_status(self, task_id: int, case_id: str,
                                status: str = '', execution_status: str = '',
                                evaluation_status: str = '',
                                error_message: str = '') -> bool:
        """更新 TaskCase 状态，返回是否有更新。"""
        session = get_db_session()
        try:
            status = self._derive_case_status(
                session, task_id, case_id, status, execution_status, evaluation_status)

            update_fields = {}
            if status:
                update_fields['status'] = status
            if execution_status:
                update_fields['execution_status'] = execution_status
            if evaluation_status:
                update_fields['evaluation_status'] = evaluation_status
            if error_message:
                update_fields['error_message'] = error_message

            if update_fields:
                session.query(TaskCase).filter(
                    TaskCase.task_id == task_id,
                    TaskCase.test_case_id == case_id,
                ).update(update_fields, synchronize_session=False)
                session.commit()
            return bool(update_fields)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    @staticmethod
    def _derive_case_status(session, task_id: int, case_id: str, status: str,
                            execution_status: str, evaluation_status: str) -> str:
        """未显式传 status 时，由 execution/evaluation 状态推导复合状态。"""
        if status or not (execution_status or evaluation_status):
            return status
        tc = session.query(TaskCase).filter(
            TaskCase.task_id == task_id,
            TaskCase.test_case_id == case_id,
        ).first()
        if not tc:
            return status
        cur_exec = execution_status or tc.execution_status or 'pending'
        cur_eval = evaluation_status or tc.evaluation_status or 'pending'
        return derive_task_case_status(cur_exec, cur_eval)

    def get_task_stats(self, status: str = '', algorithm_type: str = '',
                       group_by: str = '') -> dict:
        """聚合统计 Task — count / group_by。"""
        from sqlalchemy import func as _func
        session = get_db_session()
        try:
            query = session.query(Task).filter(Task.deleted == False)  # noqa: E712
            if status:
                query = query.filter(Task.status == status)
            if algorithm_type:
                query = query.filter(Task.algorithm_type == algorithm_type)

            if group_by:
                return self._get_task_stats_grouped(
                    session, _func, status, algorithm_type, group_by)

            total = query.count()
            return {'total': int(total)}
        finally:
            session.close()

    @staticmethod
    def _get_task_stats_grouped(session, _func, status: str,
                                algorithm_type: str, group_by: str) -> dict:
        """按字段分组统计分支。"""
        allowed = {'status': Task.status, 'algorithm_type': Task.algorithm_type,
                   'type': Task.type}
        col = allowed.get(group_by)
        if col is None:
            return {'error': f'unsupported group_by field: {group_by}'}
        rows = session.query(col, _func.count(Task.id)).filter(
            Task.deleted == False  # noqa: E712
        )
        if status:
            rows = rows.filter(Task.status == status)
        if algorithm_type:
            rows = rows.filter(Task.algorithm_type == algorithm_type)
        rows = rows.group_by(col).all()
        items = [{'key': str(k) if k is not None else '', 'count': int(c)} for k, c in rows]
        return {'items': items}

    # ========== ABC 接口适配（TaskCaseRepositoryABC） ==========

    def get_task_device_ids(self, task_id: int) -> List[dict]:
        """ABC 接口 — 委托到 get_task_device_dicts。"""
        return self.get_task_device_dicts(task_id)

    def get_task_api_ids(self, task_id: int) -> List[dict]:
        """ABC 接口 — 委托到 get_task_api_dicts。"""
        return self.get_task_api_dicts(task_id)

    def get_by_task_and_case_ids(self, task_id: int,
                                 case_ids: List[str] = None) -> List[dict]:
        """ABC 接口 — 委托到 get_task_case_dicts。"""
        return self.get_task_case_dicts(task_id, case_ids)

    def get_stats(self, algorithm_type: str = '', group_id: str = '',
                  group_by: str = '') -> dict:
        """ABC 接口 — TestCase 维度聚合统计。

        签名与 TaskCaseRepositoryABC.get_stats 对齐（group_id 用于按分组过滤）。
        """
        from sqlalchemy import func as _func
        session = get_db_session()
        try:
            query = session.query(TaskCase).join(
                Task, TaskCase.task_id == Task.id
            ).filter(Task.deleted == False)  # noqa: E712
            if algorithm_type:
                query = query.filter(Task.algorithm_type == algorithm_type)
            if group_id:
                query = query.filter(Task.group_id == group_id)
            total = query.count()
            return {'total': int(total)}
        finally:
            session.close()
