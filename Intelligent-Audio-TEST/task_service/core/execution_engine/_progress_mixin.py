import time
from shared.utils.log_handler import log_and_emit
from shared.utils.status_constants import TaskStatus


class ProgressMixin:
    """进度、告警、日志相关的方法"""

    def _emit_progress(self, task, force=False):
        """发送任务进度更新

        Args:
            task: 任务对象，包含当前任务状态信息
            force: 是否强制更新，跳过节流逻辑
        """
        # 获取任务ID
        task_id = None
        task_status = None
        if isinstance(task, (str, int)):
            task_id = str(task)
        elif hasattr(task, 'id'):
            task_id = str(task.id)
            task_status = getattr(task, 'status', None)

        if task_id and not force:
            if task_status in [TaskStatus.RUNNING, TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.STOPPED, TaskStatus.PAUSED]:
                force = True
            else:
                current_time = time.time()
                last_update = self.last_progress_update.get(task_id, 0)
                if current_time - last_update < 0.5:
                    return
                self.last_progress_update[task_id] = current_time

        self.event_manager.emit_progress(task, force=force)

    @staticmethod
    def refresh_task_counts_atomic(task_id):
        """原子刷新任务的 completed/failed/total_cases 计数（多实例安全）

        用 SQL 子查询一次性 UPDATE，避免读-改-写的丢失更新问题。
        所有需要更新任务统计的地方都应调用此方法，而非直接赋值。
        """
        from sqlalchemy import text
        from shared.models.database import get_engine
        sql = text("""
            UPDATE test_tasks SET
                completed_cases = (
                    SELECT COUNT(*) FROM task_case_relations
                    WHERE task_id = :task_id AND status = 'completed'
                ),
                failed_cases = (
                    SELECT COUNT(*) FROM task_case_relations
                    WHERE task_id = :task_id AND status = 'failed'
                )
            WHERE id = :task_id
        """)
        try:
            with get_engine().connect() as conn:
                conn.execute(sql, {'task_id': task_id})
                conn.commit()
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"原子刷新任务 {task_id} 计数失败: {e}")

    def update_case_round_progress(self, task_id, tc_rel_id, current_round, total_rounds):
        """
        Update round progress for a multi-round test case (in-memory cache).
        
        The round progress is stored in memory and read by event_manager
        during progress emission. This avoids needing a DB migration for
        an extra_data column on TaskCase.
        
        Args:
            task_id: Task ID
            tc_rel_id: TaskCase relation ID
            current_round: Current round number (0-indexed)
            total_rounds: Total number of rounds
        """
        self.round_progress_cache[tc_rel_id] = {
            'current': current_round + 1,
            'total': total_rounds,
        }
        # Force progress push on round change
        self._emit_progress(task_id, force=True)

    def _emit_alert(self, task_id, message, level='error'):
        """发送任务告警信息
        
        Args:
            task_id: 任务ID
            message: 告警消息内容
            level: 告警级别，默认为'error'
        """
        self.event_manager.emit_alert(task_id, message, level)

    def notify_case_completed(self, task_id):
        """通知等待线程：某个用例的执行或评估已完成
        
        唤醒 _run_task 中的 event.wait()，替代 time.sleep 忙等待。
        由 evaluation_service._post_evaluate_updates 和 api_executor 调用。
        """
        event = self.task_completion_events.get(task_id)
        if event:
            event.set()
            event.clear()

    def _log(self, level, content, task_id=None, test_case_id=None, api_id=None, **kwargs):
        """统一日志记录方法"""
        log_and_emit(
            level=level,
            module='Engine',
            content=content,
            category=kwargs.pop('category', 'execution'),
            source='backend',
            task_id=task_id,
            api_id=api_id,
            test_case_id=test_case_id,
            **kwargs
        )
