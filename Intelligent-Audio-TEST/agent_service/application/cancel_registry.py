# -*- coding: utf-8 -*-
"""进程内取消信号（§9.2 第 4 条）。

取消接口先置 ``agent_run.cancel_requested`` 与状态 CANCELLED，再 set 本事件；
Loop 在每个流式片段检查它，从而「当前模型调用中止」。DB 标志用于跨进程 /
恢复场景的兜底（Loop 轮次边界回读）。
"""
import threading
from typing import Dict


class CancelRegistry:
    def __init__(self):
        self._events: Dict[str, threading.Event] = {}
        self._guard = threading.Lock()

    def _event(self, run_id: str) -> threading.Event:
        with self._guard:
            event = self._events.get(run_id)
            if event is None:
                event = threading.Event()
                self._events[run_id] = event
            return event

    def cancel(self, run_id: str) -> None:
        self._event(run_id).set()

    def is_cancelled(self, run_id: str) -> bool:
        with self._guard:
            event = self._events.get(run_id)
            return bool(event and event.is_set())

    def clear(self, run_id: str) -> None:
        with self._guard:
            self._events.pop(run_id, None)
