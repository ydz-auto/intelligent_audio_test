# -*- coding: utf-8 -*-
"""SSE 事件流应用服务：先回放（DB）后跟随（唤醒 + 轮询兜底）。

游标语义：``sequence > cursor``；``Last-Event-ID`` 由接口层归一为 cursor。
yield ``None`` 表示心跳注释帧（接口层转 ``: keep-alive``）。

结束条件以「run_finished 事件已落库」为准，而不是只看 run 状态：状态机是
先改状态、后落终事件，若只看状态，正好卡在这个窗口连上的客户端会拿到终态
却收不到 run_finished。终态但终事件尚未落库时，最多再宽限
``terminal_grace_seconds`` 秒等它落库（有界，不会挂死）。
"""
import logging
import time
from typing import Iterator, Optional

from agent_service.domain.enums import EventType
from agent_service.domain.model.entities import AgentRunEvent
from agent_service.domain.ports.run_wakeup import RunWakeup
from agent_service.domain.repositories import EventRepository, RunRepository

logger = logging.getLogger(__name__)


class EventStreamService:
    def __init__(self, events: EventRepository, runs: RunRepository,
                 wakeup: RunWakeup, *, page_size: int = 200,
                 poll_interval_seconds: float = 0.5,
                 heartbeat_seconds: float = 15.0,
                 terminal_grace_seconds: float = 5.0):
        self._events = events
        self._runs = runs
        self._wakeup = wakeup
        self._page_size = max(1, int(page_size))
        self._poll_interval = max(0.05, float(poll_interval_seconds))
        self._heartbeat = max(1.0, float(heartbeat_seconds))
        self._terminal_grace = max(0.0, float(terminal_grace_seconds))

    def iter_events(self, run_id: str,
                    last_sequence: int = 0) -> Iterator[Optional[AgentRunEvent]]:
        last = max(0, int(last_sequence or 0))
        last_heartbeat = time.monotonic()
        terminal_deadline: Optional[float] = None
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
                if terminal_deadline is None:
                    terminal_deadline = time.monotonic() + self._terminal_grace
                if self._events.has_type(run_id, EventType.RUN_FINISHED):
                    return
                now = time.monotonic()
                if now >= terminal_deadline:
                    return
                # 终态先落、run_finished 后落的窗口：宽限期内继续等它
                self._wakeup.wait(run_id, min(self._poll_interval,
                                              max(0.0, terminal_deadline - now)))
                continue

            woke = self._wakeup.wait(run_id, self._poll_interval)
            now = time.monotonic()
            if not woke and now - last_heartbeat >= self._heartbeat:
                last_heartbeat = now
                yield None
