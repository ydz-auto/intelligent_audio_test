# -*- coding: utf-8 -*-
"""SSE 唤醒端口：Redis pubsub 只作唤醒，不复用现有 /api/v1/sse 广播通道。

事件正文永远以 agent_run_event 表为唯一事实源；唤醒消息只携带 run_id，
订阅端收到后回表读增量。Redis 不可用时退化为轮询（实现见
infrastructure/wakeup.py）。
"""
from abc import ABC, abstractmethod


class RunWakeup(ABC):
    """同一进程内的 run 事件唤醒。"""

    @abstractmethod
    def notify(self, run_id: str) -> None:
        """有新的 run 事件落库（或 run 进入终态）。"""

    @abstractmethod
    def wait(self, run_id: str, timeout: float) -> bool:
        """等待该 run 的下一次唤醒；超时返回 False。"""

    def close(self) -> None:
        """释放订阅资源（可选）。"""
