"""API 并发控制：信号量、执行权获取/释放、任务锁"""
import time
import threading
from threading import Lock

from backend.utils.common.config_manager import config_manager


class APIConcurrencyManager:
    """API 并发管理器"""

    def __init__(self, executor):
        self._executor = executor
        self.api_semaphores = {}
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

    def _get_or_create_semaphore(self, api_id, max_process):
        """获取或创建 API 的信号量"""
        with self.global_lock:
            if api_id not in self.api_semaphores:
                self.api_semaphores[api_id] = threading.Semaphore(max_process)
                self._log(
                    level='DEBUG',
                    content=f"为 API {api_id} 创建信号量，最大并发数: {max_process}",
                    api_id=api_id
                )
            return self.api_semaphores[api_id]

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

    def acquire(self, api_id, task_id, current_test_case_id, max_process=5, timeout=None):
        """获取 API 执行权"""
        wait_timeout = timeout or self.max_wait_time
        self._log(
            level='DEBUG',
            content=f"API {api_id} 开始执行测试用例: {current_test_case_id}",
            task_id=task_id,
            api_id=api_id
        )

        semaphore = self._get_or_create_semaphore(api_id, max_process)
        start_time = time.time()
        waiting_incremented = False

        try:
            acquired = semaphore.acquire(blocking=False)
            if acquired:
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
                    acquired = semaphore.acquire(blocking=True, timeout=min(0.5, remaining_time))
                    if acquired:
                        elapsed_time = time.time() - start_time
                        self._log(
                            level='INFO',
                            content=f"成功获取 API {api_id} 的执行权 (等待: {elapsed_time:.1f}秒)",
                            task_id=task_id,
                            api_id=api_id
                        )
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
        """释放 API 执行权"""
        if api_id in self.api_semaphores:
            try:
                self.api_semaphores[api_id].release()
                self._dec_waiting(api_id)
                self._log(
                    level='DEBUG',
                    content=f"释放 API {api_id} 的执行权",
                    task_id=task_id,
                    api_id=api_id
                )
            except ValueError:
                self._log(
                    level='WARNING',
                    content=f"尝试释放 API {api_id} 的执行权，但信号量已达到最大值",
                    task_id=task_id,
                    api_id=api_id
                )
