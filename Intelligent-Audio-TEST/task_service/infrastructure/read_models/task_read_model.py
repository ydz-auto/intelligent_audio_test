# -*- coding: utf-8 -*-
"""TaskReadModel - 任务读模型。

CQRS 读侧：直接查询 DB，支持过滤、分页、聚合统计。
读模型不返回领域聚合根，返回扁平 DTO 字典。

按职责拆分为 Mixin 组合（对外 API 不变，导入路径保持本模块）：
- task_read_model_detail.TaskDetailReadModelMixin: 任务详情 DTO 组装 + 设备/API 列表查询
- task_read_model_progress_stats.TaskProgressStatsMixin: 进度/统计查询（含标签统计）
- task_read_model_case_results.TaskCaseResultsMixin: 用例列表/详情/结果查询
- 本文件保留任务查询主流程（单查/分页搜索）与扁平 DTO 序列化。
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional  # noqa: F401

from shared.models.database import get_db_session
from task_service.infrastructure.persistence.models import Task, TaskCase
from shared.utils.query_utils import now_cst
from shared.utils.status_constants import (
    TaskStatus, ExecutionStatus, EvaluationStatus, TaskCaseStatus, ACTIVE_EXECUTION_STATUSES,
)
from shared.models.common_enums import TestType
from sqlalchemy import and_, or_, String  # String: search_tasks 中 Task.id.cast(String) 需要

from task_service.infrastructure.read_models.task_read_model_detail import TaskDetailReadModelMixin
from task_service.infrastructure.read_models.task_read_model_progress_stats import TaskProgressStatsMixin
from task_service.infrastructure.read_models.task_read_model_case_results import TaskCaseResultsMixin

logger = logging.getLogger(__name__)


class TaskReadModel(
    TaskDetailReadModelMixin,
    TaskProgressStatsMixin,
    TaskCaseResultsMixin,
):
    """任务读模型。

    提供面向查询优化的读取方法，避免加载完整 ORM 关系。
    所有方法返回 dict/list，不返回 ORM 对象。

    职责拆分为三个 Mixin 组合：
    - TaskDetailReadModelMixin: 任务详情 DTO 组装
    - TaskProgressStatsMixin: 进度/统计查询
    - TaskCaseResultsMixin: 用例列表/结果查询
    """

    def find_by_id(self, task_id: int) -> Optional[Dict[str, Any]]:
        """按 ID 查询单个任务（扁平 DTO）。"""
        session = get_db_session()
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
        session = get_db_session()
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

    def search_tasks(self, page: int = 1, per_page: int = 10,
                     status: Optional[str] = None,
                     task_type: Optional[str] = None,
                     algorithm_type: Optional[str] = None,
                     search: Optional[str] = None,
                     start_date: Optional[str] = None,
                     end_date: Optional[str] = None) -> Dict[str, Any]:
        """网关 get_all 使用的查询逻辑：含 Report 关联。"""
        from datetime import datetime

        session = get_db_session()
        try:
            query = session.query(Task).filter(Task.deleted == False)  # noqa: E712
            if status:
                query = query.filter(Task.status == status)
            if task_type:
                query = query.filter(Task.type == task_type)
            if algorithm_type:
                query = query.filter(Task.algorithm_type == algorithm_type)
            if search:
                query = query.filter(
                    or_(
                        Task.name.ilike(f'%{search}%'),
                        Task.id.cast(String).ilike(f'%{search}%')
                    )
                )
            if start_date:
                try:
                    dt_start = datetime.fromisoformat(start_date)
                    query = query.filter(Task.created_at >= dt_start)
                except ValueError:
                    logger.debug("start_date 非法 ISO 格式已忽略: %r", start_date)
            if end_date:
                try:
                    dt_end = datetime.fromisoformat(end_date)
                    query = query.filter(Task.created_at <= dt_end)
                except ValueError:
                    logger.debug("end_date 非法 ISO 格式已忽略: %r", end_date)

            query = query.order_by(Task.created_at.desc())
            pagination = query.paginate(page=page, per_page=per_page, error_out=False)
            tasks = pagination.items

            items = []
            from task_service.infrastructure.persistence.models import TaskDevice, TaskAPI
            for task in tasks:
                # 通过 gRPC 查询任务的报告（替代直连 report_service PO）
                reports = []
                try:
                    from task_service.infrastructure.acl.report_acl_repository import report_acl_repository

                    payload = report_acl_repository.list_reports(
                        task_id=task.id, page=1, per_page=100)
                    reports = payload.get('items', []) or [] if payload else []
                except Exception:
                    logger.debug("查询任务 %s 的报告列表失败", task.id, exc_info=True)
                    reports = []
                report_info = {
                    'count': len(reports),
                    'reports': [
                        {
                            'id': r.get('id'),
                            'name': r.get('name'),
                            'status': r.get('status'),
                            'type': r.get('type'),
                            'created_at': r.get('created_at'),
                        }
                        for r in reports
                    ],
                }
                # P3 改造：task.devices / task.apis 关系已移除，
                # 通过 TaskDevice/TaskAPI 关联表 + gRPC 查询设备/API 信息
                task_device_ids = [td.device_id for td in
                                   session.query(TaskDevice).filter_by(task_id=task.id).all()]
                task_api_ids = [ta.api_id for ta in
                                session.query(TaskAPI).filter_by(task_id=task.id).all()]
                devices = self._fetch_device_list(task_device_ids)
                apis = self._fetch_api_list(task_api_ids)
                items.append({
                    'id': task.id,
                    'name': task.name,
                    'description': task.description,
                    'status': task.status,
                    'type': task.type,
                    'config': task.config or {},
                    'algorithm_type': task.algorithm_type,
                    'algorithm_params': task.algorithm_params,
                    'started_at': task.started_at.isoformat() if task.started_at else None,
                    'completed_at': task.completed_at.isoformat() if task.completed_at else None,
                    'total_cases': task.total_cases,
                    'case_count': task.total_cases,
                    'device_count': len(devices),
                    'completed_cases': task.completed_cases,
                    'failed_cases': task.failed_cases,
                    'tags': [tag.name for tag in task.tags],
                    'created_at': task.created_at.isoformat() if task.created_at else None,
                    'updated_at': task.updated_at.isoformat() if task.updated_at else None,
                    'reports': report_info,
                    'devices': devices,
                    'apis': apis,
                })

            return {
                'items': items,
                'total': pagination.total,
                'page': pagination.page,
                'per_page': pagination.per_page,
                'pages': pagination.pages,
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
            'reevaluated_at': task.reevaluated_at.isoformat() if task.reevaluated_at else None,
            'reevaluation_count': task.reevaluation_count or 0,
        }


# 模块级单例
task_read_model = TaskReadModel()
