# -*- coding: utf-8 -*-
"""TTL 过期清理守护线程 — 中转暂存定时扫描，超时回收（设计文档 §4.5）。

清理范围（由 TransferCommandHandler.expire_packages 执行）：
- 未完成包（CREATED/TRANSFERRING/FAILED）超 TTL：分片文件与分片记录回收
- COMPLETED 且 ephemeral=true 的包：中转临时文件回收
- 流水记录保留（审计层），状态置 EXPIRED
"""
from __future__ import annotations

import logging
import threading

logger = logging.getLogger(__name__)


class ExpiryCleanupService:
    """传输过期清理守护线程（可 start/stop，测试可 run_once）。"""

    def __init__(self, command_handler, interval_seconds: int = 300, batch_limit: int = 100):
        self._handler = command_handler
        self._interval = max(1, int(interval_seconds))
        self._batch_limit = batch_limit
        self._thread: threading.Thread = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._loop, name='transfer-expiry-sweeper', daemon=True,
        )
        self._thread.start()
        logger.info('传输过期清理线程已启动（间隔 %ss）', self._interval)

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
            logger.info('传输过期清理线程已停止')

    def _loop(self) -> None:
        while not self._stop_event.wait(self._interval):
            try:
                self.run_once()
            except Exception:
                logger.exception('传输过期清理轮次失败（下轮重试）')

    def run_once(self) -> dict:
        """执行一轮清理，返回 {expired, transfer_ids}。"""
        from transfer_agent.application.commands.transfer_commands import (
            ExpirePackagesCommand,
        )
        result = self._handler.expire_packages(
            ExpirePackagesCommand(limit=self._batch_limit),
        )
        if result.get('expired'):
            logger.info('TTL 过期清理完成: %s 个传输包回收', result['expired'])
        return result
