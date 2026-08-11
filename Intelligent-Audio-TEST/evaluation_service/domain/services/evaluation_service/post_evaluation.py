"""评估后状态更新混入：更新 TaskCase 状态、任务统计并通知执行引擎

P0 DDD 改造：移除模块级 infrastructure/acl import，改用方法内延迟导入。
"""
from datetime import datetime, timezone, timedelta


class PostEvaluationMixin:
    """评估完成后的状态更新与执行引擎通知"""

    def _post_evaluate_updates(self, task_id, test_case_id=None):
        """
        评估后的状态更新

        更新用例的status字段和统计信息，任务状态由执行引擎统一更新

        P1.4 改造：所有 TaskCase/Task 读写通过 gRPC 调 task_service。
        注意：跨服务调用无原子事务，失败时通过日志告警。
        """
        try:
            task = self._update_task_case_and_progress(task_id, test_case_id)
            if task is not None:
                self._notify_engine_completion(task_id, test_case_id, task)
        except Exception as e:
            self._log(level='ERROR', content=f"评估后更新任务状态失败: {str(e)}", task_id=task_id, test_case_id=test_case_id)

    def _update_task_case_and_progress(self, task_id, test_case_id=None):
        """更新 TaskCase 的 evaluation_status 和 status，并更新任务统计信息

        Returns:
            dict: 已更新的任务信息（来自 task_service）；无对应 task 则返回 None
        """
        # P0-1: 通过依赖注入的 ABC 访问 ACL，domain 层不 import infrastructure
        # 1. 读取该任务的所有 TaskCase（P1.4: 通过 gRPC）
        tc_rels = self._task_acl_repo.get_task_case_by_ids(task_id=task_id)
        if not tc_rels:
            return None

        # 2. 更新 queued/pending 状态的 TaskCase 为 completed
        any_updated = False
        for tc in tc_rels:
            if (tc.evaluation_status in ['queued', 'pending']
                    and tc.execution_status in ['completed', 'failed']):
                new_status = tc.execution_status if tc.status == 'pending' else tc.status
                ok = self._task_acl_repo.update_task_case_status(
                    task_id=task_id,
                    case_id=str(tc.test_case_id),
                    status=new_status or tc.status or 'completed',
                    evaluation_status='completed',
                )
                if ok:
                    tc.status = new_status or tc.status or 'completed'
                    tc.evaluation_status = 'completed'
                    any_updated = True

        # 3. 统计已处理/失败/完成的用例数
        total_cases = len(tc_rels)
        processed_cases = sum(1 for tc in tc_rels if tc.status in ['completed', 'failed'])
        failed_cases = sum(1 for tc in tc_rels if tc.status == 'failed')
        completed_cases = sum(1 for tc in tc_rels if tc.status == 'completed')

        # 4. 读取 Task（P1.4: 通过 gRPC）
        task = self._task_acl_repo.get_task_by_id(task_id)
        if not task:
            return None

        # 5. 当任务处于评估过渡态时，检查是否所有用例都已完成评估
        if task.status == 'evaluating':
            pending_eval_count = sum(
                1 for tc in tc_rels
                if tc.evaluation_status in ['running', 'calculating', 'queued', 'pending']
            )
            if pending_eval_count == 0:
                # 所有用例评估完成，通过 gRPC 更新任务最终状态
                new_task_status = 'failed' if failed_cases > 0 else 'completed'
                ok = self._task_acl_repo.update_task_status(task_id, new_task_status)
                self._log(
                    level='INFO' if ok else 'ERROR',
                    content=f"任务 {task_id} 所有用例评估完成，更新状态为 {new_task_status}: {'成功' if ok else '失败'} (completed={completed_cases}, failed={failed_cases})",
                    task_id=task_id,
                    test_case_id=test_case_id,
                )
                task.status = new_task_status

        self._log(
            level='DEBUG',
            content=f"评估后更新任务 {task_id} 统计信息: completed={completed_cases}, failed={failed_cases}, total={total_cases}",
            task_id=task_id,
            test_case_id=test_case_id
        )

        return task

    def _notify_engine_completion(self, task_id, test_case_id, task):
        """发送进度更新并通知执行引擎某个用例的评估已完成"""
        # P0-1: 通过依赖注入的 ABC 通知，domain 层不 import shared.clients.grpc_clients
        self._task_acl_repo.notify_task_progress(task_id, force=True)

        # 通过 gRPC 通知 task_service 唤醒等待线程
        self._task_acl_repo.notify_case_completed(task_id)
