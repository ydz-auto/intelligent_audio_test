# -*- coding: utf-8 -*-
"""AiReviewExecutor - AI 复核后台执行骨架（INT-822/INT-800）。

发起（status=running）后经本执行器异步执行：调用 evaluation_service LLM 复检
gRPC（INT-823 契约，本卡先留骨架），回写 verdict/confidence/reasoning 并置
status=completed；失败置 status=failed 不落判定（重试=force 再发）。

- 队列 + 后台 worker 线程（daemon），空闲超时退出、下次 submit 再拉起
- execute_now() 提供同步执行入口（单测/直调用，绕开线程时序）
- 执行不触任务统计/人工复核计数：AI 结论独立表，采纳才走人工复核语义
"""
from __future__ import annotations

import logging
import queue
import threading

from task_service.infrastructure.persistence.ai_review_repository import (
    ai_review_repository,
)
from task_service.infrastructure.acl.evaluation_config_acl_repository import (
    evaluation_config_acl_repository,
)

logger = logging.getLogger(__name__)

# AI 复核任务状态（与表契约一致）
_STATUS_RUNNING = 'running'
_STATUS_COMPLETED = 'completed'
_STATUS_FAILED = 'failed'


class AiReviewExecutor:
    """AI 复核后台执行骨架（队列 + worker 线程）。"""

    _instance = None
    _lock = threading.Lock()

    def __init__(self):
        self._queue = queue.Queue()
        self._worker = None
        self._worker_lock = threading.Lock()

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    # ==================== 提交 ====================

    def submit(self, review_id: int) -> None:
        """入队一条 AI 复核记录后台执行；worker 未在跑时拉起。"""
        try:
            review_id = int(review_id)
        except (TypeError, ValueError):
            logger.warning("AI 复核提交执行失败: review_id 非法 %r", review_id)
            return
        with self._worker_lock:
            if self._worker is None or not self._worker.is_alive():
                self._worker = threading.Thread(
                    target=self._worker_loop, daemon=True,
                    name='ai-review-executor')
                self._worker.start()
        self._queue.put(review_id)

    def _worker_loop(self) -> None:
        """后台 worker：逐条执行队列中的复核；空闲超时退出（下次 submit 再拉起）。"""
        while True:
            try:
                review_id = self._queue.get(timeout=1.0)
            except queue.Empty:
                with self._worker_lock:
                    # 若此期间有 submit 重建了 worker，本线程退出由新 worker 接管
                    if self._worker is not None and self._worker.ident == threading.get_ident():
                        self._worker = None
                return
            try:
                self.execute_now(review_id)
            except Exception as e:
                logger.error("AI 复核后台执行异常 review_id=%s: %s", review_id, e,
                             exc_info=True)
            finally:
                self._queue.task_done()

    # ==================== 执行 ====================

    def execute_now(self, review_id: int) -> bool:
        """同步执行一条 AI 复核记录（调用方所在线程）。

        - 记录缺失 / 非 running → 跳过（幂等）
        - evaluation_service LLM 复检成功且落 verdict → 置 completed
        - 失败 / 未就绪 / 无判定 → 置 failed 不落判定

        Returns:
            bool: 是否执行到终态（completed/failed 均算）。
        """
        try:
            review_id = int(review_id)
        except (TypeError, ValueError):
            return False
        rec = ai_review_repository.get(review_id)
        if rec is None or rec['status'] != _STATUS_RUNNING:
            return False

        try:
            resp = evaluation_config_acl_repository.run_ai_review_check(
                result_id=rec['result_id'],
                dimension_id=rec['dimension_id'],
                task_id=rec['task_id'],
                test_case_id=rec.get('test_case_id'),
            )
        except Exception as e:
            logger.warning("AI 复核调用 evaluation_service 异常 review_id=%s: %s",
                           review_id, e)
            ai_review_repository.update_status(review_id, _STATUS_FAILED)
            return True

        if not resp.get('success'):
            logger.warning("AI 复核执行未成功 review_id=%s: %s",
                           review_id, resp.get('message'))
            ai_review_repository.update_status(review_id, _STATUS_FAILED)
            return True

        data = resp.get('data') or {}
        verdict = data.get('verdict')
        if not verdict:
            logger.warning("AI 复核无判定结果 review_id=%s: %s",
                           review_id, resp.get('message'))
            ai_review_repository.update_status(review_id, _STATUS_FAILED)
            return True

        ai_review_repository.update_verdict(
            review_id,
            verdict,
            confidence=data.get('confidence'),
            reasoning=data.get('reasoning'),
        )
        ai_review_repository.update_status(review_id, _STATUS_COMPLETED)
        logger.info("AI 复核完成 review_id=%s verdict=%s", review_id, verdict)
        return True


# 模块级单例
ai_review_executor = AiReviewExecutor.get_instance()
