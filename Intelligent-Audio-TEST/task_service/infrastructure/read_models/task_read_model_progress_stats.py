# -*- coding: utf-8 -*-
"""TaskProgressStatsMixin - 任务进度/统计读模型 Mixin。

从 task_read_model.py 按职责拆分，承担：
- 轻量进度查询（get_progress）
- 网关使用的详细进度（get_progress_detailed，含当前用例/API 资源状态）
- 用例状态计数（get_case_stats）与完整任务统计（get_task_stats，含标签统计）

由 TaskReadModel 组合复用，不单独实例化。
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from shared.models.database import get_db_session
from shared.utils.query_utils import now_cst
from task_service.infrastructure.persistence.models import Task, TaskCase
from shared.utils.status_constants import (
    ExecutionStatus, EvaluationStatus, TaskCaseStatus, ACTIVE_EXECUTION_STATUSES,
)
from shared.models.common_enums import TestType


class TaskProgressStatsMixin:
    """任务进度/统计读模型 Mixin：进度查询 + 状态/标签统计。"""

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
                (TaskCase.execution_status.in_(ACTIVE_EXECUTION_STATUSES)) | (TaskCase.evaluation_status == EvaluationStatus.RUNNING) |
                (TaskCase.evaluation_status == EvaluationStatus.CALCULATING)
            ).count()

            actual_total_cases = len(all_task_cases)
            actual_completed_cases = session.query(TaskCase).filter(
                TaskCase.task_id == task_id,
                TaskCase.execution_status == ExecutionStatus.COMPLETED,
                TaskCase.status == TaskCaseStatus.COMPLETED,
            ).count()

            # API 资源状态
            api_resource_status = self._collect_api_resource_status(session, task, task_id)

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

    def _collect_api_resource_status(self, session, task, task_id: int) -> list:
        """收集 API 任务的资源状态（待处理/已完成用例数、平均响应时间）。"""
        api_resource_status = []
        if task.type != TestType.API.value:
            return api_resource_status

        from task_service.infrastructure.persistence.models import TaskAPI, TestResult

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
        return api_resource_status

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
            tag_stats = self._collect_tag_stats(session, task_id)

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

    def _collect_tag_stats(self, session, task_id: int) -> dict:
        """按标签统计用例通过率和平均耗时。"""
        from task_service.infrastructure.persistence.models import Tag, TestCase

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
        return tag_stats
