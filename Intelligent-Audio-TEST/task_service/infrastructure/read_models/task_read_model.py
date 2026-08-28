# -*- coding: utf-8 -*-
"""TaskReadModel - 任务读模型。

CQRS 读侧：直接查询 DB，支持过滤、分页、聚合统计。
读模型不返回领域聚合根，返回扁平 DTO 字典。
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional  # noqa: F401

from shared.models.database import get_db_session
from task_service.infrastructure.persistence.models import Task, TaskCase
from shared.utils.query_utils import now_cst
from shared.utils.status_constants import TaskStatus, ExecutionStatus, EvaluationStatus, TaskCaseStatus
from shared.models.common_enums import TestType
from sqlalchemy import and_, or_

logger = logging.getLogger(__name__)


class TaskReadModel:
    """任务读模型。

    提供面向查询优化的读取方法，避免加载完整 ORM 关系。
    所有方法返回 dict/list，不返回 ORM 对象。
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

    def find_by_id_with_relations(self, task_id: int) -> Optional[Dict[str, Any]]:
        """按 ID 查询单个任务，含关联用例/设备/API/标签详情。"""
        session = get_db_session()
        try:
            task = session.query(Task).filter(
                Task.id == task_id, Task.deleted == False  # noqa: E712
            ).first()
            if task is None:
                return None
            return self._to_detail_dto(task, session)
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

    def get_progress(self, task_id: int) -> Optional[Dict[str, Any]]:
        """查询任务进度（轻量级，仅进度字段）。"""
        session = get_db_session()
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

    def get_progress_detailed(self, task_id: int) -> Optional[Dict[str, Any]]:
        """网关 get_progress 使用的详细进度（含当前用例、用例列表、计数）。

        返回字段：
        - task_id / status / total_cases / completed_cases / failed_cases / progress
        - current_case: 当前正在执行的用例
        - test_cases: 全部用例列表（id/status/execution_status/evaluation_status/duration/error_message）
        - in_progress_count: 正在执行/排队中的用例数
        - actual_total_cases: TaskCase 表实际总数
        - actual_completed_cases: 执行和评估均完成的用例数
        - started_at / completed_at / updated_at: 任务时间戳
        - type: 任务类型（api/e2e）
        - api_resource_status: API 任务的资源状态
        """
        from task_service.infrastructure.persistence.models import TestCase

        session = get_db_session()
        try:
            task = session.get(Task, task_id)
            if task is None:
                return None

            current_case = session.query(TaskCase).filter_by(
                task_id=task_id, execution_status=ExecutionStatus.RUNNING
            ).first()
            current_case_data = None
            if current_case:
                case_info = session.get(TestCase, current_case.test_case_id)
                current_case_data = {
                    'case_id': str(current_case.test_case_id),
                    'name': case_info.name if case_info else "未知用例",
                    'step': "playing" if task.type == 'e2e' else "evaluating",
                    'started_at': current_case.started_at.isoformat() if current_case.started_at else None,
                }

            # 全部用例列表
            all_task_cases = session.query(TaskCase).filter_by(task_id=task_id).all()
            test_cases_data = []
            pending_count = 0
            running_count = 0
            completed_count = 0
            failed_count = 0
            from datetime import timezone, timedelta
            utc_plus_8 = timezone(timedelta(hours=8))
            for tc in all_task_cases:
                duration = 0
                if tc.started_at and tc.completed_at:
                    started_at = tc.started_at
                    completed_at = tc.completed_at
                    if started_at.tzinfo is None:
                        started_at = started_at.replace(tzinfo=utc_plus_8)
                    if completed_at.tzinfo is None:
                        completed_at = completed_at.replace(tzinfo=utc_plus_8)
                    duration = int((completed_at - started_at).total_seconds())

                test_cases_data.append({
                    'id': str(tc.test_case_id),
                    'status': tc.status,
                    'execution_status': tc.execution_status,
                    'evaluation_status': tc.evaluation_status,
                    'duration': duration,
                    'error_message': tc.error_message,
                })

                if tc.execution_status in [ExecutionStatus.PENDING, ExecutionStatus.QUEUED]:
                    pending_count += 1
                elif tc.execution_status == ExecutionStatus.RUNNING:
                    running_count += 1
                elif tc.execution_status == ExecutionStatus.COMPLETED:
                    completed_count += 1
                elif tc.execution_status == ExecutionStatus.FAILED:
                    failed_count += 1

            in_progress_count = session.query(TaskCase).filter(
                TaskCase.task_id == task_id,
                (TaskCase.execution_status.in_([ExecutionStatus.RUNNING, ExecutionStatus.QUEUED])) | (TaskCase.evaluation_status == EvaluationStatus.RUNNING) |
                (TaskCase.evaluation_status == EvaluationStatus.CALCULATING)
            ).count()

            actual_total_cases = len(all_task_cases)
            actual_completed_cases = session.query(TaskCase).filter(
                TaskCase.task_id == task_id,
                TaskCase.execution_status == ExecutionStatus.COMPLETED,
                TaskCase.status == TaskCaseStatus.COMPLETED,
            ).count()

            # API 资源状态
            api_resource_status = []
            if task.type == TestType.API.value:
                from task_service.infrastructure.persistence.models import TaskAPI
                task_api = session.query(TaskAPI).filter_by(task_id=task_id).first()
                if task_api:
                    from api_test_service.infrastructure.persistence.models import API
                    api = session.get(API, task_api.api_id)
                    if api:
                        pending_cases = session.query(TaskCase).filter(
                            TaskCase.task_id == task_id,
                            TaskCase.execution_status == ExecutionStatus.PENDING,
                        ).count()
                        completed_cases = session.query(TaskCase).filter(
                            TaskCase.task_id == task_id,
                            TaskCase.execution_status == ExecutionStatus.COMPLETED,
                        ).count()
                        avg_response_time = 0
                        if completed_cases > 0:
                            from task_service.infrastructure.persistence.models import TestResult
                            completed_results = session.query(TestResult).filter(
                                TestResult.task_id == task_id,
                                TestResult.execution_status == ExecutionStatus.COMPLETED,
                            ).all()
                            total_response_time = sum(
                                r.response_time for r in completed_results if r.response_time
                            )
                            if total_response_time > 0 and completed_results:
                                avg_response_time = round(total_response_time / len(completed_results))
                        api_resource_status.append({
                            'id': str(api.id),
                            'name': api.name,
                            'pending_cases': pending_cases,
                            'completed_cases': completed_cases,
                            'avg_response_time': avg_response_time,
                            'default_max_process': getattr(api, 'default_max_process', 5),
                        })

            total = task.total_cases or 0
            completed = task.completed_cases or 0

            # 如果实际总数与记录值不同，返回实际值
            if actual_total_cases != total:
                total = actual_total_cases

            return {
                'task_id': str(task.id),
                'status': task.status,
                'type': task.type,
                'total_cases': total,
                'completed_cases': completed,
                'failed_cases': task.failed_cases or 0,
                'progress': round(actual_completed_cases / total * 100, 2) if total > 0 else 0,
                'current_case': current_case_data,
                'test_cases': test_cases_data,
                'in_progress_count': in_progress_count,
                'actual_total_cases': actual_total_cases,
                'actual_completed_cases': actual_completed_cases,
                'execution_failed_count': sum(1 for tc in test_cases_data if tc['execution_status'] == ExecutionStatus.FAILED),
                'evaluation_failed_count': sum(1 for tc in test_cases_data if tc['evaluation_status'] == EvaluationStatus.FAILED),
                'api_resource_status': api_resource_status,
                'started_at': task.started_at.isoformat() if task.started_at else None,
                'completed_at': task.completed_at.isoformat() if task.completed_at else None,
                'updated_at': task.updated_at.isoformat() if task.updated_at else None,
                'updated_at_iso': now_cst().isoformat(),
            }
        finally:
            session.close()

    def get_case_stats(self, task_id: int) -> Dict[str, int]:
        """统计任务下各状态的用例数量。"""
        session = get_db_session()
        try:
            rows = (session.query(TaskCase.status)
                    .filter(TaskCase.task_id == task_id).all())
            stats: Dict[str, int] = {}
            for (s,) in rows:
                stats[s] = stats.get(s, 0) + 1
            return stats
        finally:
            session.close()

    def get_task_stats(self, task_id: int) -> Optional[Dict[str, Any]]:
        """网关 stats 使用的完整统计（含标签统计）。"""
        from task_service.infrastructure.persistence.models import Tag, TestCase

        session = get_db_session()
        try:
            task = session.query(Task).filter(
                Task.id == task_id, Task.deleted == False  # noqa: E712
            ).first()
            if task is None:
                return None

            total = task.total_cases or 0
            completed = task.completed_cases or 0
            failed = task.failed_cases or 0
            pending = session.query(TaskCase).filter_by(
                task_id=task_id, execution_status=ExecutionStatus.PENDING
            ).count()
            skipped = session.query(TaskCase).filter_by(
                task_id=task_id, status=TaskCaseStatus.SKIPPED
            ).count()

            # 按标签统计通过率和平均耗时
            tag_stats = {}
            results = session.query(Tag.name, TaskCase.status, TaskCase.duration)\
                .join(TestCase, TaskCase.test_case_id == TestCase.id)\
                .join(TestCase.tags)\
                .filter(TaskCase.task_id == task_id).all()

            for tag_name, status, duration in results:
                if tag_name not in tag_stats:
                    tag_stats[tag_name] = {"total": 0, "completed": 0, "durations": []}
                tag_stats[tag_name]["total"] += 1
                if status == TaskCaseStatus.COMPLETED:
                    tag_stats[tag_name]["completed"] += 1
                if duration:
                    tag_stats[tag_name]["durations"].append(duration)

            for tag_name in tag_stats:
                s = tag_stats[tag_name]
                s["pass_rate"] = round((s["completed"] / s["total"] * 100), 2) if s["total"] > 0 else 0
                s["avg_duration"] = round(sum(s["durations"]) / len(s["durations"]), 2) if s["durations"] else 0
                del s["durations"]

            return {
                "total": total,
                "completed": completed,
                "failed": failed,
                "pending": pending,
                "skipped": skipped,
                "pass_rate": round((completed / total * 100), 2) if total > 0 else 0,
                "tag_stats": tag_stats,
                "duration": task.actual_duration or 0,
            }
        finally:
            session.close()

    def list_cases(self, task_id: int, status: Optional[str] = None,
                   page: int = 1, page_size: int = 50) -> Dict[str, Any]:
        """分页查询任务下用例列表。"""
        session = get_db_session()
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

    def get_case_detail(self, task_id: int, case_id: str) -> Optional[Dict[str, Any]]:
        """网关 get_case_detail 使用的完整用例详情查询。

        P1.7 改造：TestResultDimension / Dimension 是 evaluation_service 自有 PO，
        改为通过 gRPC 调 evaluation_service.EvaluationDataService.GetDimensionResultsByResultIds。
        """
        from task_service.infrastructure.persistence.models import TestCase, TestResult
        from shared.utils.result_data_store import load_full_result_data

        session = get_db_session()
        try:
            tc = session.query(TaskCase).filter_by(
                task_id=task_id, test_case_id=case_id
            ).first()
            if tc is None:
                return None

            case_info = session.get(TestCase, case_id)
            task = session.get(Task, task_id)
            test_type = task.type if task else TestType.API.value

            results = session.query(TestResult).filter_by(
                task_id=task_id, test_case_id=case_id
            ).all()

            # P1.7: 一次性通过 gRPC 获取所有 result 的维度评估结果
            result_ids = [r.id for r in results]
            dim_map = self._fetch_dim_results_grouped(result_ids)

            # P3 改造：收集 device_id / api_id，通过 gRPC 批量查询名称，替代直连 PO
            device_name_map = self._fetch_device_names({r.device_id for r in results if r.device_id})
            api_name_map = self._fetch_api_names({r.api_id for r in results if r.api_id})

            processed_results = []
            for result in results:
                device_name = device_name_map.get(result.device_id) if result.device_id else None
                api_name = api_name_map.get(result.api_id) if result.api_id else None

                dim_data = dim_map.get(result.id, [])

                full_result_data = load_full_result_data(
                    result.result_data, getattr(result, 'result_data_path', None)
                )
                # 兼容历史双重序列化数据：algorithm_result 可能是 str
                algo_result = result.algorithm_result
                algo_result = deserialize_algorithm_result(algo_result)
                processed_results.append({
                    "id": result.id,
                    "device_id": result.device_id,
                    "device_name": device_name,
                    "api_id": result.api_id,
                    "api_name": api_name,
                    "execution_status": result.execution_status,
                    "response_time": result.response_time,
                    "algorithm_result": algo_result,
                    "asr_result": algo_result.get('asr_result'),
                    "translation_result": algo_result.get('translation_result'),
                    "result_data": full_result_data,
                    "error_message": result.error_message,
                    "dimensions": dim_data,
                    "created_at": result.created_at.isoformat()
                })

            return {
                "task_id": task_id,
                "case_id": case_id,
                "case_info": {
                    "id": case_info.id,
                    "name": case_info.name if case_info else "未知用例",
                    "algorithm_type": case_info.algorithm_type if case_info else '',
                    "config": case_info.config if case_info else {},
                } if case_info else None,
                "test_type": test_type,
                "tc": self._case_to_dto(tc),
                "results": processed_results,
            }
        finally:
            session.close()

    def get_case_results(self, task_id: int, case_id: str) -> Optional[Dict[str, Any]]:
        """网关 get_case_results 使用的查询。

        P1.7 改造：TestResultDimension / Dimension 改为 gRPC 调 evaluation_service。
        """
        from task_service.infrastructure.persistence.models import TestCase, TestResult
        from shared.utils.result_data_store import load_full_result_data

        session = get_db_session()
        try:
            tc = session.query(TaskCase).filter_by(
                task_id=task_id, test_case_id=case_id
            ).first()
            if tc is None:
                return None

            case_info = session.get(TestCase, case_id)
            results = session.query(TestResult).filter_by(
                task_id=task_id, test_case_id=case_id
            ).all()

            # P1.7: 一次性通过 gRPC 获取所有 result 的维度评估结果
            result_ids = [r.id for r in results]
            dim_map = self._fetch_dim_results_grouped(result_ids)

            # P3 改造：收集 device_id / api_id，通过 gRPC 批量查询名称，替代直连 PO
            device_name_map = self._fetch_device_names({r.device_id for r in results if r.device_id})
            api_name_map = self._fetch_api_names({r.api_id for r in results if r.api_id})

            processed_results = []
            for result in results:
                device_name = device_name_map.get(result.device_id) if result.device_id else None
                api_name = api_name_map.get(result.api_id) if result.api_id else None

                dim_data = dim_map.get(result.id, [])

                # 兼容历史双重序列化数据：algorithm_result 可能是 str
                algo_result = result.algorithm_result
                algo_result = deserialize_algorithm_result(algo_result)
                processed_results.append({
                    "id": result.id,
                    "device_id": result.device_id,
                    "device_name": device_name,
                    "api_id": result.api_id,
                    "api_name": api_name,
                    "execution_status": result.execution_status,
                    "response_time": result.response_time,
                    "algorithm_result": algo_result,
                    "asr_result": algo_result.get('asr_result'),
                    "translation_result": algo_result.get('translation_result'),
                    "result_data": load_full_result_data(result.result_data, getattr(result, 'result_data_path', None)),
                    "error_message": result.error_message,
                    "dimensions": dim_data,
                    "created_at": result.created_at.isoformat()
                })

            return {
                "task_id": task_id,
                "case_id": case_id,
                "case_name": case_info.name if case_info else "未知用例",
                "results": processed_results,
            }
        finally:
            session.close()

    @staticmethod
    def _fetch_device_list(device_ids):
        """通过 gRPC 批量获取设备列表（含 id/name/status），替代 task.devices 关系。

        P3 改造：Device 是 e2e_test_service 自有 PO，通过
        DeviceConfigService.GetDeviceStatuses 批量查询。
        注：GetDeviceStatuses 不返回 model 字段，列表视图可接受缺失。
        失败时返回空列表（仅日志告警）。
        """
        if not device_ids:
            return []

        from task_service.infrastructure.acl.device_acl_repository import device_acl_repository

        items = device_acl_repository.get_device_statuses(device_ids)
        return [
            {
                'id': item.get('id'),
                'name': item.get('name'),
                'status': item.get('status'),
                'model': None,  # GetDeviceStatuses 不返回 model
            }
            for item in items
        ]

    @staticmethod
    def _fetch_api_list(api_ids):
        """通过 gRPC 批量获取 API 列表（含 id/name/status），替代 task.apis 关系。

        P3 改造：API 是 api_test_service 自有 PO，通过
        APITestService.GetAPIConfig 逐个查询（无批量按 ids 查询接口）。
        失败时返回空列表（仅日志告警）。
        """
        if not api_ids:
            return []

        from task_service.infrastructure.acl.report_acl_repository import api_test_acl_repository

        return api_test_acl_repository.fetch_api_list(api_ids)

    @staticmethod
    def _fetch_device_names(device_ids):
        """通过 gRPC 批量获取设备名称，返回 {device_id: name} 映射。

        P3 改造：Device 是 e2e_test_service 自有 PO，通过
        DeviceConfigService.GetDeviceStatuses 批量查询，替代直连 DB。
        失败时返回空 dict（仅日志告警）。
        """
        if not device_ids:
            return {}

        from task_service.infrastructure.acl.device_acl_repository import device_acl_repository

        items = device_acl_repository.get_device_statuses(device_ids)
        return {item.get('id'): item.get('name') for item in items if item.get('id') is not None}

    @staticmethod
    def _fetch_api_names(api_ids):
        """通过 gRPC 批量获取 API 名称，返回 {api_id: name} 映射。

        P3 改造：API 是 api_test_service 自有 PO，通过
        APITestService.GetAPIConfig 逐个查询（无批量按 ids 查询接口），
        替代直连 DB。失败时返回空 dict（仅日志告警）。
        """
        if not api_ids:
            return {}

        from task_service.infrastructure.acl.report_acl_repository import api_test_acl_repository

        return api_test_acl_repository.fetch_api_names(api_ids)

    @staticmethod
    def _fetch_dim_results_grouped(result_ids):
        """通过 gRPC 批量获取维度评估结果，按 test_result_id 分组返回。

        P1.7: TestResultDimension / Dimension 是 evaluation_service 自有 PO，
        通过 evaluation_service.EvaluationDataService.GetDimensionResultsByResultIds 获取。
        失败时返回空 dict（不影响主流程，仅日志告警）。
        """
        if not result_ids:
            return {}

        from task_service.infrastructure.acl.evaluation_config_acl_repository import evaluation_config_acl_repository

        return evaluation_config_acl_repository.get_dimension_results_by_result_ids(result_ids)

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

    def _to_detail_dto(self, task: Task, session) -> Dict[str, Any]:
        """含关联的详情 DTO。"""
        from task_service.infrastructure.persistence.models import TestCase, TaskDevice, TaskAPI
        from task_service.infrastructure.persistence.models.testcase_models import TestCaseGroup

        cases = []
        task_cases = session.query(TaskCase).filter_by(task_id=task.id).all()
        # 预取分组名映射，避免逐条查询
        group_ids = {tc.test_case_id for tc in task_cases}
        case_infos = {c.id: c for c in session.query(TestCase).filter(TestCase.id.in_(list(group_ids))).all()} if group_ids else {}
        group_name_map = {}
        for ci in case_infos.values():
            if ci.group_id and ci.group_id not in group_name_map:
                g = session.get(TestCaseGroup, ci.group_id)
                group_name_map[ci.group_id] = g.name if g else None
        for tc in task_cases:
            case_info = case_infos.get(tc.test_case_id)
            cases.append({
                'case_id': tc.test_case_id,
                'name': case_info.name if case_info else "未知用例",
                'status': tc.status,
                'execution_status': tc.execution_status,
                'evaluation_status': tc.evaluation_status,
                'started_at': tc.started_at.isoformat() if tc.started_at else None,
                'completed_at': tc.completed_at.isoformat() if tc.completed_at else None,
                'duration': tc.duration,
                'error_message': tc.error_message,
                'group_name': group_name_map.get(case_info.group_id) if case_info else None,
                'tags': [t.name for t in case_info.tags] if case_info and case_info.tags else [],
            })

        # P3 改造：task.devices / task.apis 关系已移除，
        # 通过 TaskDevice/TaskAPI 关联表 + gRPC 查询设备/API 信息
        task_device_ids = [td.device_id for td in
                           session.query(TaskDevice).filter_by(task_id=task.id).all()]
        task_api_ids = [ta.api_id for ta in
                        session.query(TaskAPI).filter_by(task_id=task.id).all()]
        devices = self._fetch_device_list(task_device_ids)
        apis = self._fetch_api_list(task_api_ids)
        tag_names = [tag.name for tag in task.tags]

        return {
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
            'tags': tag_names,
            'cases': cases,
            'devices': devices,
            'apis': apis,
            'created_at': task.created_at.isoformat() if task.created_at else None,
            'updated_at': task.updated_at.isoformat() if task.updated_at else None,
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
