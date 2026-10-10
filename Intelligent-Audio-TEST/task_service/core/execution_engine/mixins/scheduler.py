import threading
import time
import json
from sqlalchemy import or_
from task_service.infrastructure.persistence.models import Task
from shared.models.database import get_db_session
from shared.utils.config_manager import config_manager
from shared.utils.service_registry import RedisServiceRegistry
from shared.utils.status_constants import TaskStatus, FINISHED_TASK_STATUSES
from shared.utils.redis_pubsub import RedisPubSub, create_blocking_redis_client

import logging

logger = logging.getLogger(__name__)

# Redis 任务队列 key
TASK_QUEUE_KEY = 'task:queue'
# BRPOP 阻塞等待默认超时（秒），可经 execution_engine.brpop_timeout 配置覆盖，超时后回退 DB 兜底
DEFAULT_BRPOP_TIMEOUT = 5


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
        # BRPOP 阻塞消费专用连接（socket_timeout=None，避免客户端读超时先于阻塞超时触发）
        self.redis_blocking_client = create_blocking_redis_client()
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
        brpop_timeout = config_manager.get_value('execution_engine', 'brpop_timeout', DEFAULT_BRPOP_TIMEOUT)

        while not self.scheduler_stop_event.is_set():
            try:
                # 优先尝试从 Redis 队列消费（阻塞最多 brpop_timeout 秒）
                self._consume_redis_queue(brpop_timeout)
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

    def _consume_redis_queue(self, brpop_timeout):
        """从 Redis 队列 BRPOP 消费任务 ID，立即尝试启动"""
        if self.scheduler_stop_event is not None and self.scheduler_stop_event.is_set():
            return

        try:
            # BRPOP 阻塞等待，超时后返回 None（专用连接 socket_timeout=None，见 _init_scheduler）
            result = self.redis_blocking_client.brpop(TASK_QUEUE_KEY, timeout=brpop_timeout)
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

            # 归属校验：多实例下只执行归属本实例（或未归属）的任务
            my_instance_id = getattr(self, 'instance_id', None)
            owner = None
            try:
                db_session = get_db_session()
                try:
                    owned_row = db_session.query(Task.worker_instance_id).filter(Task.id == task_id).first()
                    owner = owned_row[0] if owned_row else None
                finally:
                    db_session.close()
            except Exception as e:
                logger.warning(f"[Scheduler] 查询任务 {task_id} 归属失败: {e}")

            if owner and owner != my_instance_id:
                # 归属其他实例：对方存活则放回队列等其消费；对方已下线则收养（置 NULL）后放回
                if owner not in self._get_alive_instance_ids():
                    try:
                        adopt_session = get_db_session()
                        try:
                            adopt_session.query(Task).filter(
                                Task.id == task_id,
                                Task.worker_instance_id == owner,
                            ).update({Task.worker_instance_id: None}, synchronize_session=False)
                            adopt_session.commit()
                            logger.info(f"[Scheduler] 收养孤儿任务 {task_id}（归属实例 {owner} 已下线）")
                        finally:
                            adopt_session.close()
                    except Exception as e:
                        logger.warning(f"[Scheduler] 收养任务 {task_id} 失败: {e}")
                # 放回队列，待归属方（或收养后的任一实例）消费；sleep 防空转
                self.redis_blocking_client.lpush(TASK_QUEUE_KEY, task_id_str)
                time.sleep(0.2)
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

        调度规则（差异#2 收尾：互斥依据由 task.type 迁至执行画像 ——
        含物理用例的任务占 e2e 单飞槽位，API 用例按 api_ids 并发互斥）：
        - 物理任务：同时只能运行一个
        - API 任务：可以并发运行，但不能使用相同的 API
        """
        local_db_session = get_db_session()
        try:
            # 孤儿收养：归属实例已下线的任务解除归属（中间态回退 PENDING），
            # 保证死实例名下的任务可被任一存活实例重新拉起
            self._adopt_orphan_tasks(local_db_session)

            # 归属过滤：只拉起归属本实例（或未归属）的 PENDING 任务
            my_instance_id = getattr(self, 'instance_id', None)
            pending_tasks = local_db_session.query(Task).filter(
                Task.status == TaskStatus.PENDING,
                Task.deleted == False,  # noqa: E712
                or_(
                    Task.worker_instance_id.is_(None),
                    Task.worker_instance_id == my_instance_id,
                ),
            ).order_by(Task.created_at.asc()).all()

            if not pending_tasks:
                return

            # INT-40：start_task 内部会 close 线程共享的 scoped session，
            # 循环若跨该调用持有 ORM 对象，对象被 expunge（且已被本方法/
            # start_task 的 commit 过期）后访问属性即抛 DetachedInstanceError，
            # 整轮兜底调度中止。先抽取纯数据，循环内不持有 ORM 对象。
            from task_service.infrastructure.persistence.task_repository import task_repository
            profiles = task_repository.get_execution_profiles([t.id for t in pending_tasks])
            candidates = [(t.id, profiles.get(t.id, {'has_physical': False, 'api_ids': []}))
                          for t in pending_tasks]

            for task_id, profile in candidates:
                if self.scheduler_stop_event.is_set():
                    break

                if task_id in self.workers and self.workers[task_id].is_alive():
                    continue

                with self.queue_lock:
                    if any(t['id'] == task_id for t in self.task_queue):
                        continue

                has_physical = profile['has_physical']
                api_ids = profile['api_ids']

                can_run = False

                if has_physical and self.running_e2e:
                    can_run = False
                elif set(api_ids) & self.running_apis:
                    can_run = False
                else:
                    can_run = True

                if can_run:
                    try:
                        success, message = self.start_task(task_id)
                        if success:
                            self._log(level='INFO', content=f"任务 {task_id} DB兜底调度启动成功")
                    except Exception as e:
                        logger.error(f"[Scheduler] DB兜底自动启动任务 {task_id} 失败: {e}")

        except Exception as e:
            logger.error(f"[Scheduler] DB兜底调度处理失败: {e}")
        finally:
            local_db_session.close()

    def _get_alive_instance_ids(self):
        """存活实例 ID 集合（含本实例）。Redis 不可用时返回仅含本实例的集合。"""
        try:
            alive = RedisServiceRegistry().get_alive_ids('task_service')
        except Exception as e:
            logger.warning(f"[Scheduler] 获取存活实例列表失败: {e}")
            alive = set()
        my_instance_id = getattr(self, 'instance_id', None)
        if my_instance_id:
            alive.add(my_instance_id)
        return alive

    def _adopt_orphan_tasks(self, local_db_session):
        """收养归属已下线实例的任务。

        归属实例心跳过期（已下线，不再可被 get_alive_ids 发现）的任务，
        对任何存活实例都不再可靠推进：
        - worker_instance_id 置 NULL（解除归属）；
        - 中间态（queued/running/...）回退 PENDING，交 DB 兜底调度重新拉起；
        - 终态任务保持不动（仅解除归属，不需重跑）。
        """
        alive_ids = self._get_alive_instance_ids()
        orphan_rows = local_db_session.query(Task.id).filter(
            Task.deleted == False,  # noqa: E712
            Task.worker_instance_id.isnot(None),
            Task.worker_instance_id.notin_(alive_ids),
        ).all()
        if not orphan_rows:
            return
        ids = [row[0] for row in orphan_rows]
        try:
            local_db_session.query(Task).filter(Task.id.in_(ids)).update(
                {Task.worker_instance_id: None}, synchronize_session=False)
            local_db_session.query(Task).filter(
                Task.id.in_(ids),
                Task.status.notin_(FINISHED_TASK_STATUSES),
            ).update({
                Task.status: TaskStatus.PENDING,
                Task.completed_at: None,
            }, synchronize_session=False)
            local_db_session.commit()
            logger.info(f"[Scheduler] 孤儿收养完成，重置 {len(ids)} 个任务（归属实例已下线）")
        except Exception as e:
            local_db_session.rollback()
            logger.error(f"[Scheduler] 孤儿收养失败: {e}")
