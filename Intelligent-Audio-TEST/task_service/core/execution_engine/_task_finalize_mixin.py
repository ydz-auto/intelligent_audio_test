# -*- coding: utf-8 -*-
"""任务状态收尾 Mixin（从 _task_runner_mixin.py 拆分，P4-4）。

包含主循环结束后的状态收敛、等待、异常与资源清理：
- _update_post_loop_status：提前收敛任务状态
- _wait_for_cases_completion：等待用例完成（事件驱动 + 兜底轮询）
- _finalize_task_status / _handle_task_exception：最终状态与异常处理
- _cleanup_task_resources：资源清理
"""
import time
import traceback
from datetime import datetime

from task_service.infrastructure.persistence.models import Task, TaskCase
from shared.models.database import get_db_session
from shared.utils.status_utils import derive_task_case_status
from shared.utils.status_constants import (
    TaskStatus, TaskCaseStatus, ExecutionStatus, EvaluationStatus,
    FINISHED_CASE_STATUSES, ACTIVE_EXECUTION_STATUSES, ACTIVE_EVALUATION_STATUSES,
)

import logging

logger = logging.getLogger(__name__)


class TaskFinalizeMixin:
    """任务状态收尾：等待 / 收敛 / 异常 / 清理"""

    def _update_post_loop_status(self, task_id):
        """检查是否所有测试用例都已执行完成，提前更新任务状态

        Returns:
            task 对象（可能为 None）
        """
        local_db_session = get_db_session()
        try:
            task = local_db_session.get(Task, task_id)
            if task:
                # 获取所有测试用例
                all_cases = local_db_session.query(TaskCase).filter_by(task_id=task_id).count()
                # 获取已处理的测试用例（状态为completed/failed/skipped）
                all_processed_cases = local_db_session.query(TaskCase).filter(
                    TaskCase.task_id == task_id,
                    TaskCase.status.in_(FINISHED_CASE_STATUSES)
                ).count()
                # 获取运行中的测试用例 (只包括执行中、排队中，不包括评估中/待评估)
                running_cases = local_db_session.query(TaskCase).filter(
                    TaskCase.task_id == task_id,
                    TaskCase.execution_status.in_(ACTIVE_EXECUTION_STATUSES)
                ).count()
                failed_cases = local_db_session.query(TaskCase).filter_by(task_id=task_id, status=TaskCaseStatus.FAILED).count()
                completed_cases = local_db_session.query(TaskCase).filter_by(task_id=task_id, status=TaskCaseStatus.COMPLETED).count()

                # 如果所有测试用例都已处理完成，提前更新任务状态
                if all_processed_cases == all_cases and running_cases == 0:
                    # 检查是否还有用例在评估中
                    evaluating_cases = local_db_session.query(TaskCase).filter(
                        TaskCase.task_id == task_id,
                        TaskCase.evaluation_status.in_(ACTIVE_EVALUATION_STATUSES)
                    ).count()

                    if evaluating_cases > 0:
                        # 还有用例在评估中，设为 evaluating 过渡态
                        task.status = TaskStatus.EVALUATING
                    elif all_cases > 0:
                        if failed_cases > 0:
                            task.status = TaskStatus.FAILED
                        else:
                            task.status = TaskStatus.COMPLETED
                    else:
                        task.status = TaskStatus.COMPLETED

                    # 提前更新任务状态和统计信息，后续等待循环会继续监控评估完成
                    # 最终状态由评估服务的 _post_evaluate_updates 统一确认

                    if task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED]:
                        # 更新任务完成时间和实际执行时长
                        task.completed_at = datetime.now(self.utc_plus_8)
                        if task.started_at:
                            # 确保 started_at 是带时区的 datetime 对象
                            if task.started_at.tzinfo is None:
                                task.started_at = task.started_at.replace(tzinfo=self.utc_plus_8)
                            # 计算实际执行时长（秒）
                            task.actual_duration = int((task.completed_at - task.started_at).total_seconds())
                    # 更新任务的已完成用例数和失败用例数
                    task.completed_cases = completed_cases
                    task.failed_cases = failed_cases
                    local_db_session.commit()
                    # 发送最终进度更新
                    self._emit_progress(task)
        finally:
            local_db_session.close()

        return task

    def _wait_for_cases_completion(self, task_id, task, stop_event):
        """等待所有测试用例执行完成 — 编排入口"""
        if task.type not in ('api', 'e2e'):
            return

        max_wait_time = self.test_case_wait_time
        wait_start_time = time.time()
        last_log_time = 0
        last_counts = None

        all_cases = self._get_total_case_count(task_id)

        while True:
            local_db_session = get_db_session()
            try:
                local_db_session.expire_all()
                task_status = self._get_task_status(local_db_session, task_id)
                status_counts = self._query_status_counts(local_db_session, task_id)
                counts = self._aggregate_status_counts(status_counts)

                self._log_wait_debug(task_id, all_cases, counts, task_status)

                # 任务已停止
                if task_status == TaskStatus.STOPPED:
                    self._mark_uncompleted_cases_failed(task_id, local_db_session)
                    break

                # 所有用例已处理完成
                if counts['running'] == 0 and counts['processed'] == all_cases:
                    if self._has_evaluating_cases(task_id, local_db_session):
                        self._log_evaluating_wait(task_id, all_cases, counts, task_status)
                        local_db_session.close()
                        self._wait_completion_event(task_id)
                        continue
                    self._update_final_case_counts(local_db_session, task_id, counts)
                    self._log_wait_summary(task_id, all_cases, counts, task_status)
                    break

                # running=0 但有用例状态未更新
                if counts['running'] == 0:
                    self._fix_stale_case_statuses(task_id, local_db_session)

                # 周期性日志
                self._maybe_log_wait_status(task_id, all_cases, counts, task_status,
                                            last_counts, last_log_time)
                last_log_time, last_counts = self._update_log_tracking(last_log_time, last_counts, counts)

                # 超时检查
                if time.time() - wait_start_time > max_wait_time:
                    self._log_wait_timeout(task_id, counts['running'])
                    break

                # 事件驱动等待
                local_db_session.close()
                self._wait_completion_event(task_id)
            finally:
                try:
                    local_db_session.close()
                except Exception:
                    logger.debug("等待用例完成时关闭 DB session 失败 task_id=%s", task_id, exc_info=True)

    def _get_total_case_count(self, task_id):
        """获取任务用例总数"""
        session = get_db_session()
        try:
            return session.query(TaskCase).filter_by(task_id=task_id).count()
        finally:
            session.close()

    def _get_task_status(self, session, task_id):
        """获取任务当前状态"""
        task_obj = session.query(Task).filter_by(id=task_id).first()
        return task_obj.status if task_obj else 'unknown'

    def _query_status_counts(self, session, task_id):
        """按 execution/evaluation/final status 分组统计"""
        from sqlalchemy import func
        return session.query(
            TaskCase.execution_status, TaskCase.evaluation_status, TaskCase.status, func.count(TaskCase.id)
        ).filter(TaskCase.task_id == task_id).group_by(
            TaskCase.execution_status, TaskCase.evaluation_status, TaskCase.status
        ).all()

    def _aggregate_status_counts(self, status_counts):
        """将分组查询结果汇总为计数字典"""
        running = queued = exec_running = eval_running = 0
        exec_success = eval_success = failed = exec_failed = eval_failed = 0
        processed = passed = 0

        for exec_st, eval_st, final_st, count in status_counts:
            if exec_st in ACTIVE_EXECUTION_STATUSES:
                running += count
            if exec_st == ExecutionStatus.QUEUED:
                queued += count
            if exec_st == ExecutionStatus.RUNNING:
                exec_running += count
            if exec_st == ExecutionStatus.COMPLETED:
                exec_success += count
            if exec_st == ExecutionStatus.FAILED:
                exec_failed += count
            if eval_st in [EvaluationStatus.RUNNING, EvaluationStatus.QUEUED]:
                eval_running += count
            if eval_st == EvaluationStatus.COMPLETED:
                eval_success += count
            if eval_st == EvaluationStatus.FAILED:
                eval_failed += count
            if final_st in FINISHED_CASE_STATUSES:
                processed += count
            if final_st == TaskCaseStatus.COMPLETED:
                passed += count
            if final_st == TaskCaseStatus.FAILED:
                failed += count

        return {
            'running': running, 'queued': queued, 'exec_running': exec_running,
            'eval_running': eval_running, 'exec_success': exec_success, 'eval_success': eval_success,
            'failed': failed, 'exec_failed': exec_failed, 'eval_failed': eval_failed,
            'processed': processed, 'passed': passed,
        }

    def _log_wait_debug(self, task_id, all_cases, counts, task_status):
        """记录等待循环的调试日志"""
        self._log(level='DEBUG', content=(
            f"任务 {task_id} 统计结果: all_cases={all_cases}, running={counts['running']}, "
            f"all_processed={counts['processed']}, eval_success={counts['eval_success']}, "
            f"eval_failed={counts['eval_failed']}"), task_id=task_id)

    def _mark_uncompleted_cases_failed(self, task_id, session):
        """任务停止时，将所有未完成用例标记为失败"""
        uncompleted = session.query(TaskCase).filter(
            TaskCase.task_id == task_id,
            TaskCase.execution_status.in_(ACTIVE_EXECUTION_STATUSES)
        ).all()
        for tc in uncompleted:
            tc.execution_status = ExecutionStatus.FAILED
            tc.status = derive_task_case_status(tc.execution_status, tc.evaluation_status or EvaluationStatus.PENDING)
            tc.completed_at = datetime.now(self.utc_plus_8)
            tc.duration = 0
            tc.error_message = '任务被停止，用例执行中断'
        session.commit()
        self._log(level='INFO', content=f"任务已停止，标记 {len(uncompleted)} 个未完成用例为失败", task_id=task_id)

    def _has_evaluating_cases(self, task_id, session):
        """检查是否还有用例在评估中"""
        return session.query(TaskCase).filter(
            TaskCase.task_id == task_id,
            TaskCase.evaluation_status.in_([EvaluationStatus.RUNNING, EvaluationStatus.CALCULATING,
                                             EvaluationStatus.QUEUED, EvaluationStatus.PENDING])
        ).count() > 0

    def _update_final_case_counts(self, session, task_id, counts):
        """更新任务用例统计"""
        task_obj = session.query(Task).filter_by(id=task_id).first()
        if task_obj:
            task_obj.completed_cases = counts['passed']
            task_obj.failed_cases = counts['failed']
            session.commit()

    def _fix_stale_case_statuses(self, task_id, session):
        """修复状态未更新的用例"""
        all_task_cases = session.query(TaskCase).filter_by(task_id=task_id).all()
        updated = False
        for tc in all_task_cases:
            if tc.status in FINISHED_CASE_STATUSES:
                continue
            new_status = derive_task_case_status(
                tc.execution_status or ExecutionStatus.PENDING, tc.evaluation_status or EvaluationStatus.PENDING)
            tc.status = new_status
            if new_status in (TaskCaseStatus.COMPLETED, TaskCaseStatus.FAILED):
                tc.completed_at = datetime.now(self.utc_plus_8)
                updated = True
        if updated:
            session.commit()

    def _maybe_log_wait_status(self, task_id, all_cases, counts, task_status, last_counts, last_log_time):
        """状态变化或超过10秒时记录日志"""
        current_counts = self._build_counts_tuple(counts, task_status)
        current_time = time.time()
        if current_counts != last_counts or current_time - last_log_time >= 10:
            self._log_wait_summary(task_id, all_cases, counts, task_status)
            return current_time, current_counts
        return last_log_time, last_counts

    def _update_log_tracking(self, last_log_time, last_counts, counts):
        """更新日志追踪状态"""
        current_time = time.time()
        current_counts = self._build_counts_tuple(counts, None)
        return current_time, current_counts

    def _build_counts_tuple(self, counts, task_status):
        """构建计数元组用于比较"""
        return (
            counts['running'], counts['queued'], counts['exec_running'], counts['eval_running'],
            counts['exec_success'], counts['eval_success'], counts['failed'],
            counts['exec_failed'], counts['eval_failed'], counts['processed'], task_status
        )

    def _log_wait_summary(self, task_id, all_cases, counts, task_status):
        """记录等待循环的摘要日志"""
        c = counts
        self._log(level='INFO', content=(
            f"等待测试用例执行完成 |任务状态：{task_status} 总用例数: {all_cases}, "
            f"运行中: {c['running']} (排队中: {c['queued']}, 执行中: {c['exec_running']}, "
            f"评估中: {c['eval_running']}, 执行成功: {c['exec_success']}), "
            f"已完成：{all_cases - c['running']}(评估成功: {c['eval_success']}, "
            f"失败: {c['failed']} (执行失败: {c['exec_failed']}, 评估失败: {c['eval_failed']}))"), task_id=task_id)

    def _log_evaluating_wait(self, task_id, all_cases, counts, task_status):
        """记录评估中等待日志"""
        self._log_wait_summary(task_id, all_cases, counts, task_status)

    def _log_wait_timeout(self, task_id, running_count):
        """记录超时日志"""
        self._log(level='WARNING', content=f"等待测试用例执行完成超时，还有 {running_count} 个用例状态为running或queued", task_id=task_id)

    def _wait_completion_event(self, task_id):
        """事件驱动等待用例完成通知"""
        completion_event = self.task_completion_events.get(task_id)
        if completion_event:
            completion_event.wait(timeout=5)
        else:
            time.sleep(2)

    def _finalize_task_status(self, task_id, task, stop_event):
        """最终状态更新"""
        # 检查任务状态，如果是暂停状态则保持暂停，不改变状态
        if task.status != TaskStatus.PAUSED:
            # 使用本地会话确保独立可靠的会话
            local_db_session = get_db_session()
            try:
                # 重新获取任务对象，确保它在有效会话中
                task = local_db_session.get(Task, task_id)
                if not task:
                    # 任务不存在，直接返回，不继续处理
                    return

                # 根据停止事件和执行结果更新任务状态
                if stop_event.is_set():
                    task.status = TaskStatus.STOPPED
                else:
                    # 检查是否所有测试用例都失败
                    all_cases = local_db_session.query(TaskCase).filter_by(task_id=task.id).count()
                    failed_cases = local_db_session.query(TaskCase).filter_by(task_id=task.id, status=TaskCaseStatus.FAILED).count()
                    all_processed_cases = local_db_session.query(TaskCase).filter(
                        TaskCase.task_id == task.id,
                        TaskCase.status.in_(FINISHED_CASE_STATUSES)
                    ).count()

                    # 动态更新任务的total_cases字段，确保进度计算准确
                    task.total_cases = all_cases

                    # 确保所有测试用例都已处理完成
                    if all_processed_cases == all_cases:
                        if failed_cases > 0:
                            task.status = TaskStatus.FAILED
                        else:
                            task.status = TaskStatus.COMPLETED
                    else:
                        # 如果还有测试用例未完成，标记为失败
                        task.status = TaskStatus.FAILED
                        # 将所有未处理的测试用例标记为失败，避免任务被重新执行
                        unprocessed_cases = local_db_session.query(TaskCase).filter(
                            TaskCase.task_id == task.id,
                            TaskCase.status.notin_(FINISHED_CASE_STATUSES)
                        ).all()
                        for tc in unprocessed_cases:
                            tc.execution_status = ExecutionStatus.FAILED
                            tc.status = derive_task_case_status(tc.execution_status, tc.evaluation_status or EvaluationStatus.PENDING)
                            tc.completed_at = datetime.now(self.utc_plus_8)
                            tc.duration = 0
                            tc.error_message = "任务执行失败，未处理的用例被标记为失败"

                # 记录任务完成时间和实际执行时长
                task.completed_at = datetime.now(self.utc_plus_8)
                if task.started_at:
                    # 确保 started_at 是带时区的 datetime 对象
                    if task.started_at.tzinfo is None:
                        task.started_at = task.started_at.replace(tzinfo=self.utc_plus_8)
                    # 计算实际执行时长（秒）
                    task.actual_duration = int((task.completed_at - task.started_at).total_seconds())

                # 更新任务的已完成用例数和失败用例数
                success_count = local_db_session.query(TaskCase).filter(
                    TaskCase.task_id == task_id,
                    TaskCase.status == TaskCaseStatus.COMPLETED
                ).count()
                task.completed_cases = success_count
                task.failed_cases = local_db_session.query(TaskCase).filter_by(task_id=task_id, status=TaskCaseStatus.FAILED).count()

                local_db_session.commit()
                # 在关闭会话前发送任务完成进度更新
                self._emit_progress(task)
            finally:
                local_db_session.close()

    def _handle_task_exception(self, task_id, e):
        """异常处理"""
        error_trace = traceback.format_exc()

        # 使用本地会话确保独立可靠的会话
        local_db_session = get_db_session()
        try:
            # 重新获取任务对象，确保它在有效会话中
            task = local_db_session.get(Task, task_id)
            if not task:
                self._log(
                    level='ERROR',
                    content=f"任务 {task_id} 不存在，无法更新状态",
                    task_id=task_id
                )
                # 任务不存在，直接返回，不继续处理
                return

            # 更新所有正在执行的测试用例状态为 failed
            running_cases = local_db_session.query(TaskCase).filter_by(task_id=task_id, execution_status=ExecutionStatus.RUNNING).all()
            for tc_rel in running_cases:
                tc_rel.execution_status = ExecutionStatus.FAILED
                tc_rel.status = derive_task_case_status(tc_rel.execution_status, tc_rel.evaluation_status or EvaluationStatus.PENDING)
                tc_rel.completed_at = datetime.now(self.utc_plus_8)
                if tc_rel.started_at:
                    # 确保两个datetime对象都具有相同的时区信息
                    try:
                        if tc_rel.started_at.tzinfo is None:
                            # 如果started_at不带时区，将其转换为带时区的datetime对象
                            started_at_with_tz = tc_rel.started_at.replace(tzinfo=self.utc_plus_8)
                            completed_at_with_tz = datetime.now(self.utc_plus_8)
                        else:
                            started_at_with_tz = tc_rel.started_at
                            completed_at_with_tz = datetime.now(self.utc_plus_8)
                        # 计算执行时长
                        tc_rel.duration = int((completed_at_with_tz - started_at_with_tz).total_seconds())
                    except Exception as duration_error:
                        # 如果计算失败，设置时长为0
                        tc_rel.duration = 0
                tc_rel.error_message = f"任务执行异常: {str(e)}"

            # 更新任务状态为失败
            task.status = TaskStatus.FAILED
            task.completed_at = datetime.now(self.utc_plus_8)
            if task.started_at:
                # 确保两个datetime对象都具有相同的时区信息
                if task.started_at.tzinfo is None:
                    started_at_with_tz = task.started_at.replace(tzinfo=self.utc_plus_8)
                    completed_at_with_tz = task.completed_at
                elif task.completed_at.tzinfo is None:
                    started_at_with_tz = task.started_at
                    completed_at_with_tz = task.completed_at.replace(tzinfo=self.utc_plus_8)
                else:
                    started_at_with_tz = task.started_at
                    completed_at_with_tz = task.completed_at
                # 计算实际执行时长
                task.actual_duration = int((completed_at_with_tz - started_at_with_tz).total_seconds())

            # 更新任务统计信息
            task.completed_cases = local_db_session.query(TaskCase).filter(
                TaskCase.task_id == task_id,
                TaskCase.status == TaskCaseStatus.COMPLETED
            ).count()
            task.failed_cases = local_db_session.query(TaskCase).filter_by(task_id=task_id, status=TaskCaseStatus.FAILED).count()

            local_db_session.commit()

            # 记录详细错误日志
            self._log(
                level='ERROR',
                content=f"任务 {task_id} 执行失败: {str(e)}\n{error_trace}",
                task_id=task_id
            )

            # 发送告警和进度更新
            self._emit_alert(task_id, f"任务执行异常: {str(e)}")
            self._emit_progress(task)

            # 记录错误日志
            self._log(
                level='ERROR',
                content=f"执行任务 {task_id} 时发生错误: {str(e)}",
                task_id=task_id
            )
            self._log(
                level='DEBUG',
                content=f"错误详情: {error_trace}",
                task_id=task_id
            )
        except Exception as ex:
            # 记录会话操作异常
            self._log(
                level='ERROR',
                category='database',
                content=f"处理任务异常时发生数据库会话错误: {str(ex)}\n{traceback.format_exc()}",
                task_id=task_id
            )
        finally:
            local_db_session.close()

    def _cleanup_task_resources(self, task_id, stop_event):
        """清理任务资源"""
        # 重新检查任务状态，决定是否清理资源
        should_cleanup = True
        local_db_session = get_db_session()
        try:
            task = local_db_session.get(Task, task_id)
            # 只有当任务明确处于 'paused' 状态时，才保留资源（以便恢复）
            # 如果任务被停止 ('stopped')、完成 ('completed') 或失败 ('failed')，必须清理
            if task and task.status == TaskStatus.PAUSED and not stop_event.is_set():
                should_cleanup = False
        except Exception as e:
            self._log(level='WARNING', content=f"获取任务状态失败，默认清理资源: {str(e)}", task_id=task_id)
        finally:
            local_db_session.close()

        if should_cleanup:
            # 清理运行状态
            with self.queue_lock:
                if task_id in self.running_tasks:
                    task_type = self.running_tasks[task_id]
                    del self.running_tasks[task_id]

                    if task_type == 'e2e':
                        self.running_e2e = False
                    else:
                        # 释放占用的 API ID
                        local_db_session = get_db_session()
                        try:
                            from task_service.infrastructure.persistence.models import TaskAPI
                            task_apis = local_db_session.query(TaskAPI).filter_by(task_id=task_id).all()
                            for api_rel in task_apis:
                                if api_rel.api_id in self.running_apis:
                                    self.running_apis.remove(api_rel.api_id)
                        finally:
                            local_db_session.close()

            # 清理线程和标志位
            self.workers.pop(task_id, None)
            self.stop_flags.pop(task_id, None)
            self.pause_flags.pop(task_id, None)
            self.task_completion_events.pop(task_id, None)
            # 清理进度缓存，避免内存泄漏
            self.task_progress_cache.pop(task_id, None)
            self.last_progress_update.pop(task_id, None)
            # 清理多轮进度缓存（key 为 tc_rel_id，需查询当前任务的用例 ID）
            try:
                cleanup_session = get_db_session()
                try:
                    tc_rel_ids = [
                        tc_id for (tc_id,) in
                        cleanup_session.query(TaskCase.id).filter_by(task_id=task_id).all()
                    ]
                    for tc_rel_id in tc_rel_ids:
                        self.round_progress_cache.pop(tc_rel_id, None)
                finally:
                    cleanup_session.close()
            except Exception:
                logger.debug("清理多轮进度缓存失败 task_id=%s", task_id, exc_info=True)

            # 检查队列并启动下一个任务
            self._check_queue()
