import threading
import json
from task_service.infrastructure.persistence.models import Task
from shared.models.database import get_db_session
from shared.utils.config_manager import config_manager
from shared.utils.status_constants import TaskStatus
from shared.utils.redis_pubsub import RedisPubSub

import logging

logger = logging.getLogger(__name__)

# Redis 任务队列 key
TASK_QUEUE_KEY = 'task:queue'
# BRPOP 超时时间（秒），超时后回退到 DB 轮询兜底
BRPOP_TIMEOUT = 5


class SchedulerMixin:
    """调度器相关的逻辑：初始化、启动、停止、主循环、pending 任务调度

    事件驱动改造: 任务创建时 LPUSH 到 Redis 队列，调度器用 BRPOP 阻塞消费，
    实现零延迟调度。同时保留 DB 轮询作为兜底（防止 Redis 队列丢失或服务重启后遗漏）。
    """

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
        self._log(level='INFO', content="任务调度器已启动（Redis 队列 + DB 兜底）")

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

    def enqueue_task(self, task_id):
        """将任务推入 Redis 队列，供调度器 BRPOP 消费

        在任务创建时调用，实现零延迟调度。
        """
        try:
            client = RedisPubSub().redis_client
            client.lpush(TASK_QUEUE_KEY, str(task_id))
        except Exception as e:
            logger.warning(f"推入 Redis 任务队列失败 (task_id={task_id}): {e}，依赖 DB 兜底")

    def _scheduler_loop(self):
        """调度器主循环：优先用 BRPOP 消费 Redis 队列，超时后 DB 兜底"""
        if self.scheduler_stop_event is None:
            return

        db_check_interval = config_manager.get_value('execution_engine', 'scheduler_interval', 30)

        while not self.scheduler_stop_event.is_set():
            try:
                # 优先尝试从 Redis 队列消费（阻塞最多 BRPOP_TIMEOUT 秒）
                self._consume_redis_queue()
            except Exception as e:
                logger.warning(f"[Scheduler] Redis 队列消费异常: {e}")

            # DB 兜底：定期检查是否有遗漏的 pending 任务
            try:
                self._schedule_pending_tasks()
            except Exception as e:
                logger.error(f"[Scheduler] DB 兜底调度检查失败: {e}")
            finally:
                try:
                    from shared.models.database import remove_db_session
                    remove_db_session()
                except Exception:
                    logger.debug("调度器循环结束清理 DB session 失败", exc_info=True)

            # 等待下一轮（DB 兜底间隔较长，Redis 队列靠 BRPOP 阻塞实现低延迟）
            self.scheduler_event.wait(timeout=db_check_interval)
            self.scheduler_event.clear()

    def _consume_redis_queue(self):
        """从 Redis 队列 BRPOP 消费任务 ID，立即尝试启动"""
        if self.scheduler_stop_event is not None and self.scheduler_stop_event.is_set():
            return

        try:
            client = RedisPubSub().redis_client
            # BRPOP 阻塞等待，超时后返回 None
            result = client.brpop(TASK_QUEUE_KEY, timeout=BRPOP_TIMEOUT)
            if result is None:
                return

            # result = (key_bytes, value_bytes)
            _, task_id_bytes = result
            task_id_str = task_id_bytes.decode('utf-8') if isinstance(task_id_bytes, bytes) else task_id_bytes

            try:
                task_id = int(task_id_str)
            except ValueError:
                logger.warning(f"[Scheduler] Redis 队列收到无效 task_id: {task_id_str}")
                return

            # 检查任务是否已在运行或队列中
            if task_id in self.workers and self.workers[task_id].is_alive():
                return

            with self.queue_lock:
                if any(t['id'] == task_id for t in self.task_queue):
                    return

            # 尝试启动任务
            try:
                success, message = self.start_task(task_id)
                if success:
                    self._log(level='INFO', content=f"任务 {task_id} 从 Redis 队列消费并启动成功")
                else:
                    self._log(level='DEBUG', content=f"任务 {task_id} 从 Redis 队列消费但启动失败: {message}")
            except Exception as e:
                logger.error(f"[Scheduler] Redis 队列消费启动任务 {task_id} 失败: {e}")
        except Exception as e:
            logger.warning(f"[Scheduler] BRPOP 消费异常: {e}")

    def _schedule_pending_tasks(self):
        """DB 兜底：检查并自动启动 pending 状态的任务

        调度规则：
        - E2E 任务：同时只能运行一个
        - API 任务：可以并发运行，但不能使用相同的 API
        """
        local_db_session = get_db_session()
        try:
            pending_tasks = local_db_session.query(Task).filter_by(
                status=TaskStatus.PENDING,
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
                            self._log(level='INFO', content=f"任务 {task_id} ({task.type}) DB兜底调度启动成功")
                    except Exception as e:
                        logger.error(f"[Scheduler] DB兜底自动启动任务 {task_id} 失败: {e}")

        except Exception as e:
            logger.error(f"[Scheduler] DB兜底调度处理失败: {e}")
        finally:
            local_db_session.close()
