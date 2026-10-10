# -*- coding: utf-8 -*-
"""TaskCase/Task 终态写库延迟重试队列（INT-116）

问题：评估终态（failed/completed）通过 gRPC 写 task_service，task_service 自身
连接池耗尽/过载时该写库失败且原先无重试，task_case_relations 永久停留在
evaluating/queued/running/calculating，task_service 执行引擎随之无限忙等
（INT-95 验收事故：忙等日志累计 24.5 万行）。

机制：
- 内联重试放在调用方（evaluation_mixin 的 *_with_retry 包装）；
- 内联重试仍失败时把终态请求入队，本模块后台线程按指数退避
  （5s→10s→…→60s 封顶）持续重试，直到落库成功或超过最大重试窗
  （默认 30 分钟）后放弃并记 ERROR（可观测，不再静默丢失）。
- 同一 (task_id, case_id) 的待重试请求只保留最新一条（新终态覆盖旧终态），
  避免旧请求落地后覆盖更新的状态。

仅 evaluation_service 侧使用；task_service 执行引擎侧的超时仲裁由 INT-116
的姊妹卡（开发工程师A）负责，两卡互为纵深防御。
"""
import logging
import threading
import time

from evaluation_service.infrastructure.acl import task_acl_repository

logger = logging.getLogger(__name__)

# 首次重试等待（秒）；此后指数退避
RETRY_BASE_INTERVAL_SECONDS = 5
# 单条重试间隔上限（秒）
RETRY_MAX_INTERVAL_SECONDS = 60
# 重试窗上限：超过即放弃并记 ERROR（秒）
MAX_RETRY_WINDOW_SECONDS = 30 * 60


class _PendingCaseStatus:
    __slots__ = ('task_id', 'case_id', 'status', 'evaluation_status',
                 'error_message', 'attempts', 'next_attempt_at', 'enqueued_at')

    def __init__(self, task_id, case_id, status, evaluation_status, error_message):
        self.task_id = task_id
        self.case_id = case_id
        self.status = status or ''
        self.evaluation_status = evaluation_status or ''
        self.error_message = error_message or ''
        self.attempts = 0
        self.next_attempt_at = 0.0
        self.enqueued_at = 0.0


class _PendingTaskStatus:
    __slots__ = ('task_id', 'status', 'attempts', 'next_attempt_at', 'enqueued_at')

    def __init__(self, task_id, status):
        self.task_id = task_id
        self.status = status or ''
        self.attempts = 0
        self.next_attempt_at = 0.0
        self.enqueued_at = 0.0


def _backoff_seconds(attempts):
    """attempts 从 1 计：5, 10, 20, 40, 60, 60, ..."""
    return min(RETRY_BASE_INTERVAL_SECONDS * (2 ** max(0, attempts - 1)),
               RETRY_MAX_INTERVAL_SECONDS)


class TaskStatusRetryQueue:
    """终态写库延迟重试队列（进程内单例，懒启动后台线程）"""

    def __init__(self):
        self._lock = threading.Lock()
        self._pending_case = {}  # (task_id, case_id) -> _PendingCaseStatus
        self._pending_task = {}  # task_id -> _PendingTaskStatus
        self._wake = threading.Event()
        self._thread = None

    # ---------- 对外入队 API ----------

    def enqueue_case_status(self, task_id, case_id, status,
                            evaluation_status='', error_message=''):
        """TaskCase 终态写库失败的延迟重试请求（同 case 只保留最新状态）"""
        item = _PendingCaseStatus(task_id, str(case_id), status,
                                  evaluation_status, error_message)
        with self._lock:
            self._pending_case[(item.task_id, item.case_id)] = item
            self._arm_locked(item)
            self._ensure_worker_locked()
        self._wake.set()

    def enqueue_task_status(self, task_id, status):
        """Task 终态写库失败的延迟重试请求（同 task 只保留最新状态）"""
        item = _PendingTaskStatus(task_id, status)
        with self._lock:
            self._pending_task[item.task_id] = item
            self._arm_locked(item)
            self._ensure_worker_locked()
        self._wake.set()

    # ---------- 内部 ----------

    def _arm_locked(self, item):
        now = time.monotonic()
        item.enqueued_at = now
        item.next_attempt_at = now + RETRY_BASE_INTERVAL_SECONDS

    def _ensure_worker_locked(self):
        if self._thread is None or not self._thread.is_alive():
            self._thread = threading.Thread(
                target=self._run, name='task-status-retry', daemon=True)
            self._thread.start()
            logger.info("终态写库延迟重试线程已启动")

    def _run(self):
        while True:
            self._process_due_cases()
            self._process_due_tasks()
            with self._lock:
                has_pending = bool(self._pending_case or self._pending_task)
                next_due = None
                if has_pending:
                    candidates = ([i.next_attempt_at for i in self._pending_case.values()]
                                  + [i.next_attempt_at for i in self._pending_task.values()])
                    next_due = min(candidates)
            if not has_pending:
                self._wake.wait()
            else:
                delay = max(0.5, min(next_due - time.monotonic(), RETRY_MAX_INTERVAL_SECONDS))
                self._wake.wait(timeout=delay)
            self._wake.clear()

    def _process_due_cases(self):
        now = time.monotonic()
        with self._lock:
            due = [item for item in self._pending_case.values()
                   if now >= item.next_attempt_at]
        for item in due:
            ok = False
            try:
                ok = task_acl_repository.update_task_case_status(
                    task_id=item.task_id,
                    case_id=item.case_id,
                    status=item.status,
                    evaluation_status=item.evaluation_status,
                    error_message=item.error_message,
                )
            except Exception as e:
                logger.warning('终态重试写库异常: task_id=%s case_id=%s: %s',
                               item.task_id, item.case_id, e)
            self._settle(item, ok, 'task_case_relations',
                         f"task_id={item.task_id} case_id={item.case_id} "
                         f"status={item.status} evaluation_status={item.evaluation_status}")

    def _process_due_tasks(self):
        now = time.monotonic()
        with self._lock:
            due = [item for item in self._pending_task.values()
                   if now >= item.next_attempt_at]
        for item in due:
            ok = False
            try:
                ok = task_acl_repository.update_task_status(
                    item.task_id, item.status)
            except Exception as e:
                logger.warning('任务终态重试写库异常: task_id=%s: %s',
                               item.task_id, e)
            self._settle(item, ok, 'test_tasks',
                         f"task_id={item.task_id} status={item.status}")

    def _settle(self, item, ok, table, desc):
        """按写库结果收敛条目：成功移除；失败退避重排或超窗放弃。"""
        with self._lock:
            if isinstance(item, _PendingCaseStatus):
                pending = self._pending_case
                key = (item.task_id, item.case_id)
            else:
                pending = self._pending_task
                key = item.task_id
            # 已被同 key 更新请求替换：本次结果不作用于新请求
            if pending.get(key) is not item:
                return
            if ok:
                pending.pop(key, None)
                logger.info("终态延迟重试成功: %s %s", table, desc)
                return
            item.attempts += 1
            if time.monotonic() - item.enqueued_at >= MAX_RETRY_WINDOW_SECONDS:
                pending.pop(key, None)
                logger.error(
                    "终态延迟重试超窗放弃（%s 超过 %ss 未落库，需人工核查）: %s",
                    table, MAX_RETRY_WINDOW_SECONDS, desc)
            else:
                item.next_attempt_at = time.monotonic() + _backoff_seconds(item.attempts)


# 模块级单例
task_status_retry_queue = TaskStatusRetryQueue()
