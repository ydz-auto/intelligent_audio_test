# -*- coding: utf-8 -*-
"""SSE 事件流应用服务：先回放（DB）后跟随（唤醒 + 轮询兜底）。

游标语义：``sequence > cursor``；``Last-Event-ID`` 由接口层归一为 cursor。
yield ``None`` 表示心跳注释帧（接口层转 ``: keep-alive``）。
Run 进入终态后做一次最终回读再结束，避免「状态先变、终事件后落库」的窗口
导致客户端漏收 run_finished。
"""
import logging
import time
from typing import Iterator, Optional

from agent_service.domain.model.entities import AgentRunEvent
from agent_service.domain.ports.run_wakeup import RunWakeup
from agent_service.domain.repositories import EventRepository, RunRepository

logger = logging.getLogger(__name__)


class EventStreamService:
    def __init__(self, events: EventRepository, runs: RunRepository,
                 wakeup: RunWakeup, *, page_size: int = 200,
                 poll_interval_seconds: float = 0.5,
                 heartbeat_seconds: float = 15.0):
        self._events = events
        self._runs = runs
        self._wakeup = wakeup
        self._page_size = max(1, int(page_size))
        self._poll_interval = max(0.05, float(poll_interval_seconds))
        self._heartbeat = max(1.0, float(heartbeat_seconds))

    def iter_events(self, run_id: str,
                    last_sequence: int = 0) -> Iterator[Optional[AgentRunEvent]]:
        last = max(0, int(last_sequence or 0))
        last_heartbeat = time.monotonic()
        while True:
            batch = self._events.list_after(run_id, last, self._page_size)
            if batch:
                for event in batch:
                    last = event.sequence
                    yield event
                continue

            run = self._runs.get(run_id)
            if run is None:
                return
            if run.status.is_terminal:
                # 终态后可能有刚落库的事件：最后回读一次再结束
                if self._events.list_after(run_id, last, self._page_size):
                    continue
                return

            woke = self._wakeup.wait(run_id, self._poll_interval)
            now = time.monotonic()
            if not woke and now - last_heartbeat >= self._heartbeat:
                last_heartbeat = now
                yield None
