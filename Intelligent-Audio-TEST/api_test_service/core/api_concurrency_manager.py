"""API 并发控制：信号量、执行权获取/释放、任务锁"""
import time
from threading import Lock

from shared.utils.config_manager import config_manager
from shared.utils import distributed_coordinator as dc


# 分布式信号量 key 前缀
_API_SEM_KEY_PREFIX = 'api:sem:'


class APIConcurrencyManager:
    """API 并发管理器

    纯 Redis 分布式信号量：去掉进程内 threading.Semaphore，
    同一 API 的全局并发数由 DistributedSemaphore 统一限制，支持多实例部署。
    Redis 不可用时分布式信号量降级放行（见 DistributedSemaphore 实现）。
    """

    def __init__(self, executor):
        self._executor = executor
        self.api_waiting_counts = {}
        self.global_lock = Lock()
        self.task_locks = {}
        self.task_lock = Lock()
        self.completed_tasks = set()
        self.completed_tasks_lock = Lock()
        self.max_wait_time = config_manager.get_value('api_executor', 'max_wait_time', 300)

    @property
    def _log(self):
        return self._executor._log

    def get_task_lock(self, task_id):
        """获取任务级锁。

        单实例下返回进程内 threading.Lock；
        多实例下应使用分布式锁，此处仍提供进程内锁用于本进程内的线程同步。
        """
        task_id_str = str(task_id)
        with self.task_lock:
            if task_id_str not in self.task_locks:
                self.task_locks[task_id_str] = Lock()
        return self.task_locks[task_id_str]

    def cleanup_task_lock(self, task_id):
        task_id_str = str(task_id)
        with self.task_lock:
            if task_id_str in self.task_locks:
                del self.task_locks[task_id_str]

    def mark_task_completed(self, task_id):
        with self.completed_tasks_lock:
            self.completed_tasks.add(str(task_id))
        self.cleanup_task_lock(task_id)

    def cleanup_completed_tasks(self):
        with self.completed_tasks_lock:
            completed = list(self.completed_tasks)
            self.completed_tasks.clear()
        for task_id in completed:
            self.cleanup_task_lock(task_id)

    def _inc_waiting(self, api_id):
        with self.global_lock:
            self.api_waiting_counts[api_id] = self.api_waiting_counts.get(api_id, 0) + 1
            return self.api_waiting_counts[api_id]

    def _dec_waiting(self, api_id):
        with self.global_lock:
            current = self.api_waiting_counts.get(api_id, 0)
            if current <= 1:
                self.api_waiting_counts.pop(api_id, None)
                return 0
            self.api_waiting_counts[api_id] = current - 1
            return self.api_waiting_counts[api_id]

    def acquire(self, api_id, task_id, current_test_case_id, max_process=None, timeout=None):
        """获取 API 执行权（纯 Redis 分布式信号量）

        去掉进程内 threading.Semaphore，全局并发数由 DistributedSemaphore 统一限制。
        """
        # 并发参数配置化：max_process 缺省时从 config_manager 取默认值
        if max_process is None:
            max_process = config_manager.get_value('api_executor', 'default_max_process', 5)
        wait_timeout = timeout or self.max_wait_time
        self._log(
            level='DEBUG',
            content=f"API {api_id} 开始执行测试用例: {current_test_case_id}",
            task_id=task_id,
            api_id=api_id
        )

        # 纯分布式信号量：限制同一 API 的全局并发数
        dist_sem = dc.DistributedSemaphore(f'{_API_SEM_KEY_PREFIX}{api_id}', max_process)
        start_time = time.time()
        waiting_incremented = False

        try:
            # 非阻塞尝试：立即获取成功则无需进入等待队列
            if dist_sem.acquire(timeout=0):
                self._log(
                    level='INFO',
                    content=f"成功获取 API {api_id} 的执行权 (无需等待)",
                    task_id=task_id,
                    api_id=api_id
                )
                return True

            waiting_now = self._inc_waiting(api_id)
            waiting_incremented = True
            self._log(
                level='DEBUG',
                content=f"API {api_id} 并发已满，进入等待队列 (等待数: {waiting_now})",
                task_id=task_id,
                api_id=api_id
            )

            # 阻塞轮询获取，期间响应停止/暂停控制
            while True:
                self._executor._handle_control(task_id)

                elapsed_time = time.time() - start_time
                remaining_time = wait_timeout - elapsed_time
                if remaining_time <= 0:
                    self._dec_waiting(api_id)
                    waiting_incremented = False
                    self._log(
                        level='WARNING',
                        content=f"获取 API {api_id} 执行权超时，已等待 {elapsed_time:.1f}秒",
                        task_id=task_id,
                        api_id=api_id
                    )
                    return False

                try:
                    if dist_sem.acquire(timeout=min(0.5, remaining_time)):
                        elapsed_time = time.time() - start_time
                        self._log(
                            level='INFO',
                            content=f"成功获取 API {api_id} 的执行权 (等待: {elapsed_time:.1f}秒)",
                            task_id=task_id,
                            api_id=api_id
                        )
                        waiting_incremented = False
                        return True
                except Exception as e:
                    self._dec_waiting(api_id)
                    waiting_incremented = False
                    self._log(
                        level='ERROR',
                        content=f"获取 API {api_id} 执行权时发生异常: {str(e)}",
                        task_id=task_id,
                        api_id=api_id
                    )
                    return False

        except Exception as outer_e:
            if waiting_incremented:
                self._dec_waiting(api_id)
            self._log(
                level='ERROR',
                content=f"获取 API {api_id} 执行权时发生外部异常: {str(outer_e)}",
                task_id=task_id,
                api_id=api_id
            )
            return False

    def release(self, api_id, task_id):
        """释放 API 执行权（纯 Redis 分布式信号量）"""
        # 释放分布式信号量（max_process=0 的占位实例仅用于 release）
        dc.DistributedSemaphore(f'{_API_SEM_KEY_PREFIX}{api_id}', 0).release()
        self._dec_waiting(api_id)
        self._log(
            level='DEBUG',
            content=f"释放 API {api_id} 的执行权",
            task_id=task_id,
            api_id=api_id
        )

