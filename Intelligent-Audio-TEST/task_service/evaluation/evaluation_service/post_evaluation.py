"""评估后状态更新混入：更新 TaskCase 状态、任务统计并通知执行引擎"""
from datetime import datetime, timezone, timedelta

from shared.models.models import TaskCase, Task
from shared.models.database import db


class PostEvaluationMixin:
    """评估完成后的状态更新与执行引擎通知"""

    def _post_evaluate_updates(self, task_id, test_case_id=None):
        """
        评估后的状态更新

        更新用例的status字段和统计信息，任务状态由执行引擎统一更新
        """
        local_db_session = db.session()
        try:
            from task_service.core.execution_engine import execution_engine

            # 更新 TaskCase 的 evaluation_status 和 status，并更新任务统计
            task = self._update_task_case_and_progress(
                task_id, test_case_id, local_db_session
            )

            if task is not None:
                self._notify_engine_completion(task_id, test_case_id, task,
                                                local_db_session, execution_engine)

            # 注意：任务状态（task.status）由执行引擎在评估完成后统一更新
            # 评估服务只更新统计信息，不更新任务状态
        except Exception as e:
            self._log(level='ERROR', content=f"评估后更新任务状态失败: {str(e)}", task_id=task_id, test_case_id=test_case_id)
        finally:
            local_db_session.close()

    def _update_task_case_and_progress(self, task_id, test_case_id, local_db_session):
        """更新 TaskCase 的 evaluation_status 和 status，并更新任务统计信息

        Returns:
            Task: 已更新的任务对象（统计信息已 commit）；无对应 task 则返回 None
        """
        # 更新 TaskCase 的 evaluation_status 和 status
        # 当没有评估维度时，评估流程不会真正执行，需要在这里更新状态
        task_cases_query = local_db_session.query(TaskCase).filter_by(task_id=task_id)
        if test_case_id:
            task_cases_query = task_cases_query.filter_by(test_case_id=test_case_id)

        task_cases = task_cases_query.all()
        for tc in task_cases:
            if tc.evaluation_status in ['queued', 'pending'] and tc.execution_status in ['completed', 'failed']:
                tc.evaluation_status = 'completed'
                if tc.status == 'pending':
                    tc.status = tc.execution_status

        local_db_session.commit()

        # 检查任务的所有用例是否都已处理完成
        total_cases = local_db_session.query(TaskCase).filter_by(task_id=task_id).count()

        # 统计已处理完成的用例数（status为completed或failed）
        processed_cases = local_db_session.query(TaskCase).filter(
            TaskCase.task_id == task_id,
            TaskCase.status.in_(['completed', 'failed'])
        ).count()

        # 统计失败的用例数
        failed_cases = local_db_session.query(TaskCase).filter(
            TaskCase.task_id == task_id,
            TaskCase.status == 'failed'
        ).count()

        # 统计已完成的用例数
        completed_cases = local_db_session.query(TaskCase).filter(
            TaskCase.task_id == task_id,
            TaskCase.status == 'completed'
        ).count()

        # 更新任务的统计信息
        task = local_db_session.get(Task, task_id)
        if task:
            task.completed_cases = completed_cases
            task.failed_cases = failed_cases

            # 当任务处于评估过渡态时，检查是否所有用例都已完成评估
            if task.status == 'evaluating':
                # 检查是否还有未完成评估的用例
                pending_eval_count = local_db_session.query(TaskCase).filter(
                    TaskCase.task_id == task_id,
                    TaskCase.evaluation_status.in_(['running', 'calculating', 'queued', 'pending'])
                ).count()
                if pending_eval_count == 0:
                    # 所有用例评估完成，更新任务最终状态
                    task.status = 'failed' if failed_cases > 0 else 'completed'
                    if task.status in ['completed', 'failed']:
                        task.completed_at = datetime.now(timezone(timedelta(hours=8)))

            local_db_session.commit()

            self._log(
                level='DEBUG',
                content=f"评估后更新任务 {task_id} 统计信息: completed={completed_cases}, failed={failed_cases}, total={total_cases}",
                task_id=task_id,
                test_case_id=test_case_id
            )

        return task

    def _notify_engine_completion(self, task_id, test_case_id, task, local_db_session,
                                    execution_engine):
        """发送进度更新并通知执行引擎某个用例的评估已完成"""
        # 发送进度更新
        execution_engine._emit_progress(task, force=True)

        # 唤醒等待线程：通知执行引擎某个用例的评估已完成
        execution_engine.notify_case_completed(task_id)
