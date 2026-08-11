import threading
from task_service.infrastructure.persistence.models import Task
from shared.models.database import get_db_session
from shared.utils.config_manager import config_manager


class SchedulerMixin:
    """调度器相关的逻辑：初始化、启动、停止、主循环、pending 任务调度"""

    def _init_scheduler(self):
        """初始化并启动后台调度线程（在 _log 方法定义后调用）"""
        if self._scheduler_initialized:
            return

        self.scheduler_stop_event = threading.Event()
        self.scheduler_thread = threading.Thread(
            target=self._scheduler_loop,
            name="TaskScheduler",
            daemon=True
        )
        self.scheduler_thread.start()
        self._scheduler_initialized = True
        self._log(level='INFO', content="任务调度器已启动")

    def _start_scheduler(self):
        """启动后台调度线程，用于自动检查和启动 pending 状态的任务"""
        self._init_scheduler()

    def _stop_scheduler(self):
        """停止后台调度线程"""
        self.scheduler_stop_event.set()
        self.scheduler_event.set()  # 唤醒调度器以便快速退出
        if self.scheduler_thread is not None and self.scheduler_thread.is_alive():
            self.scheduler_thread.join(timeout=5)
        self._log(level='INFO', content="任务调度器已停止")

    def trigger_scheduler_check(self):
        """触发调度器立即检查，用于事件驱动"""
        self.scheduler_event.set()

    def _scheduler_loop(self):
        """调度器主循环，定期检查并启动 pending 任务，支持事件驱动"""
        if self.scheduler_stop_event is None:
            return

        check_interval = config_manager.get_value('execution_engine', 'scheduler_interval', 3)

        while not self.scheduler_stop_event.is_set():
            try:
                self._schedule_pending_tasks()
            except Exception as e:
                print(f"[Scheduler] 调度器检查任务时发生错误: {str(e)}")
            finally:
                # 每轮循环结束清理本线程 DB session，防止连接泄漏
                try:
                    from shared.models.database import remove_db_session
                    remove_db_session()
                except Exception:
                    pass

            self.scheduler_event.wait(timeout=check_interval)
            self.scheduler_event.clear()

    def _schedule_pending_tasks(self):
        """检查并自动启动 pending 状态的任务

        调度规则：
        - E2E 任务：同时只能运行一个
        - API 任务：可以并发运行，但不能使用相同的 API
        """
        local_db_session = get_db_session()
        try:
            pending_tasks = local_db_session.query(Task).filter_by(
                status='pending',
                deleted=False
            ).order_by(Task.created_at.asc()).all()

            if not pending_tasks:
                return

            for task in pending_tasks:
                if self.scheduler_stop_event.is_set():
                    break

                task_id = task.id

                if task_id in self.workers and self.workers[task_id].is_alive():
                    continue

                with self.queue_lock:
                    if any(t['id'] == task_id for t in self.task_queue):
                        continue

                from task_service.infrastructure.persistence.models import TaskAPI
                task_apis = local_db_session.query(TaskAPI).filter_by(task_id=task_id).all()
                api_ids = [task_api.api_id for task_api in task_apis]

                can_run = False

                if task.type == 'e2e':
                    if not self.running_e2e:
                        can_run = True
                else:
                    overlapping_apis = set(api_ids) & self.running_apis
                    if not overlapping_apis:
                        can_run = True

                if can_run:
                    try:
                        success, message = self.start_task(task_id)
                        if success:
                            print(f"[Scheduler] 任务 {task_id} ({task.type}) 自动启动成功")
                        else:
                            print(f"[Scheduler] 任务 {task_id} 自动启动失败: {message}")
                    except Exception as e:
                        print(f"[Scheduler] 自动启动任务 {task_id} 时发生错误: {str(e)}")

        except Exception as e:
            print(f"[Scheduler] 调度器处理任务时发生错误: {str(e)}")
        finally:
            local_db_session.close()
