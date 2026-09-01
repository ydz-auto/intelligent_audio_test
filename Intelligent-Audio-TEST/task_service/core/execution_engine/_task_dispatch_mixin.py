# -*- coding: utf-8 -*-
"""用例分发 Mixin（从 _task_runner_mixin.py 拆分，P4-4）。

包含主循环中的用例领取、分发与失败处理：
- _get_next_pending_case / _handle_no_pending_case：用例选取与空转处理
- _dispatch_case_by_type / _dispatch_api_case / _dispatch_e2e_case：按任务类型分发
- _claim_case：原子占用用例
- _handle_e2e_failure / _handle_device_check_failed：失败处理
"""
from datetime import datetime

from task_service.infrastructure.persistence.models import TaskCase
from shared.utils.status_utils import derive_task_case_status
from shared.utils.status_constants import (
    TaskCaseStatus, ExecutionStatus, EvaluationStatus,
    ACTIVE_EXECUTION_STATUSES, ACTIVE_EVALUATION_STATUSES,
)

import logging

logger = logging.getLogger(__name__)


class TaskDispatchMixin:
    """用例分发：领取 / 原子占用 / 按类型分发 / 失败处理"""

    def _get_next_pending_case(self, task_id, session):
        """获取下一个待执行的测试用例"""
        return session.query(TaskCase).filter_by(
            task_id=task_id, execution_status=ExecutionStatus.PENDING
        ).order_by(TaskCase.created_at.asc()).first()

    def _handle_no_pending_case(self, task_id, task, session):
        """没有待执行用例时的处理，返回 True 表示需要继续循环"""
        if task.type != 'api':
            self._log(level='INFO', content=f"任务 {task_id} 所有用例执行完成，退出主循环", task_id=task_id)
            return False

        # API 任务：检查是否有执行中/评估中的用例
        in_progress = self._count_in_progress_cases(task_id, session)
        evaluating = self._count_evaluating_cases(task_id, session)
        if in_progress > 0 or evaluating > 0:
            total = in_progress + evaluating
            self._log(level='DEBUG', content=f"等待 {total} 个执行中/评估中的用例完成 (执行中: {in_progress}, 评估中: {evaluating})...", task_id=task_id)
            session.close()
            self._wait_completion_event(task_id)
            return True

        self._log(level='INFO', content=f"任务 {task_id} 所有用例执行完成，退出主循环", task_id=task_id)
        return False

    def _count_in_progress_cases(self, task_id, session):
        """统计执行中/排队中的用例数"""
        return session.query(TaskCase).filter(
            TaskCase.task_id == task_id,
            TaskCase.execution_status.in_(ACTIVE_EXECUTION_STATUSES)
        ).count()

    def _count_evaluating_cases(self, task_id, session):
        """统计评估中的用例数"""
        return session.query(TaskCase).filter(
            TaskCase.task_id == task_id,
            TaskCase.evaluation_status.in_(ACTIVE_EVALUATION_STATUSES)
        ).count()

    def _handle_device_check_failed(self, task_id, task, tc_rel, error_msg, session):
        """设备检查失败时的用例标记和统计更新"""
        tc_rel.execution_status = ExecutionStatus.FAILED
        tc_rel.status = derive_task_case_status(tc_rel.execution_status, tc_rel.evaluation_status or EvaluationStatus.PENDING)
        tc_rel.completed_at = datetime.now(self.utc_plus_8)
        tc_rel.duration = 0
        tc_rel.error_message = error_msg
        session.commit()

        task.completed_cases = self._count_cases_by_status(task_id, session, TaskCaseStatus.COMPLETED)
        task.failed_cases = self._count_cases_by_status(task_id, session, TaskCaseStatus.FAILED, use_filter_by=True)
        session.commit()
        self._emit_alert(task_id, error_msg)
        self._emit_progress(task)

    def _count_cases_by_status(self, task_id, session, status, use_filter_by=False):
        """按状态统计用例数"""
        if use_filter_by:
            return session.query(TaskCase).filter_by(task_id=task_id, status=status).count()
        return session.query(TaskCase).filter(
            TaskCase.task_id == task_id, TaskCase.status == status
        ).count()

    def _dispatch_case_by_type(self, task_id, task, tc_rel, session):
        """根据任务类型分发用例执行"""
        if task.type == 'api':
            self._dispatch_api_case(task_id, tc_rel, session)
        else:
            self._dispatch_e2e_case(task_id, task, tc_rel, session)

    def _dispatch_api_case(self, task_id, tc_rel, session):
        """API 任务用例执行"""
        try:
            claimed = self._claim_case(task_id, tc_rel.id, session)
            if claimed != 1:
                session.rollback()
                return
            session.commit()
            self._execute_api_case(task_id, tc_rel.id)
        except Exception as e:
            self._log(level='ERROR', content=f"API任务执行异常: {str(e)}", task_id=task_id)
            tc_rel.execution_status = ExecutionStatus.FAILED
            tc_rel.status = derive_task_case_status(tc_rel.execution_status, tc_rel.evaluation_status or EvaluationStatus.PENDING)
            tc_rel.error_message = f"API任务执行异常: {str(e)}"
            session.commit()

    def _dispatch_e2e_case(self, task_id, task, tc_rel, session):
        """E2E 任务用例执行"""
        claimed = self._claim_case(task_id, tc_rel.id, session)
        if claimed != 1:
            session.rollback()
            return
        session.commit()

        success = self._execute_e2e_case(task_id, tc_rel.id)
        tc_rel = session.get(TaskCase, tc_rel.id)

        task.completed_cases = self._count_cases_by_status(task_id, session, TaskCaseStatus.COMPLETED)
        task.failed_cases = self._count_cases_by_status(task_id, session, TaskCaseStatus.FAILED, use_filter_by=True)

        if not success:
            self._handle_e2e_failure(task_id, tc_rel)

    def _claim_case(self, task_id, tc_rel_id, session):
        """原子占用用例，避免重复提交"""
        return session.query(TaskCase).filter(
            TaskCase.id == tc_rel_id,
            TaskCase.task_id == task_id,
            TaskCase.execution_status == ExecutionStatus.PENDING
        ).update({
            TaskCase.execution_status: ExecutionStatus.QUEUED,
            TaskCase.status: derive_task_case_status(ExecutionStatus.QUEUED, EvaluationStatus.PENDING)
        }, synchronize_session=False)

    def _handle_e2e_failure(self, task_id, tc_rel):
        """E2E 执行失败处理"""
        if tc_rel.execution_status not in (ExecutionStatus.COMPLETED, ExecutionStatus.FAILED):
            tc_rel.execution_status = ExecutionStatus.FAILED
            tc_rel.evaluation_status = EvaluationStatus.COMPLETED
            tc_rel.status = derive_task_case_status(tc_rel.execution_status, tc_rel.evaluation_status)
            tc_rel.completed_at = datetime.now(self.utc_plus_8)
            tc_rel.error_message = tc_rel.error_message or 'E2E用例执行失败（gRPC返回失败或异常）'
        self._emit_alert(task_id, f"用例执行失败: {tc_rel.test_case_id}")
