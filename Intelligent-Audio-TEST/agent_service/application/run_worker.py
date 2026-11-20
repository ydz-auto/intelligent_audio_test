# -*- coding: utf-8 -*-
"""Run 执行器：把 run_id 投递到线程池，由唯一 Loop 执行。

单进程 M0：进程内线程池即 worker；重启后由 RecoveryService 重新投递，
执行语义与进程内一致（上下文从 DB 重建）。
"""
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Set

from agent_service.application.run_orchestrator import RunOrchestrator

logger = logging.getLogger(__name__)


class RunExecutor:
    def submit(self, run_id: str) -> None:  # pragma: no cover - 接口
        raise NotImplementedError

    def shutdown(self) -> None:  # pragma: no cover - 接口
        pass


class ThreadPoolRunExecutor(RunExecutor):
    def __init__(self, orchestrator: RunOrchestrator, max_workers: int = 4):
        self._orchestrator = orchestrator
        self._pool = ThreadPoolExecutor(
            max_workers=max(1, int(max_workers)),
            thread_name_prefix='agent-run')
        self._active: Set[str] = set()
        self._guard = threading.Lock()

    def submit(self, run_id: str) -> None:
        with self._guard:
            if run_id in self._active:
                return
            self._active.add(run_id)
        self._pool.submit(self._run, run_id)

    def _run(self, run_id: str) -> None:
        try:
            self._orchestrator.execute(run_id)
        except Exception as exc:  # noqa: BLE001 - 兜底，绝不让 run 卡在 RUNNING
            logger.exception('Run worker 异常 run=%s', run_id)
            try:
                self._orchestrator.fail_run(run_id, f'WORKER_CRASH: {exc}')
            except Exception:  # noqa: BLE001
                logger.exception('Run 失败收口异常 run=%s', run_id)
        finally:
            with self._guard:
                self._active.discard(run_id)

    def shutdown(self) -> None:
        self._pool.shutdown(wait=True, cancel_futures=False)


class InlineRunExecutor(RunExecutor):
    """同步执行（测试 / 单请求内联场景）。"""

    def __init__(self, orchestrator: RunOrchestrator):
        self._orchestrator = orchestrator

    def submit(self, run_id: str) -> None:
        self._orchestrator.execute(run_id)
