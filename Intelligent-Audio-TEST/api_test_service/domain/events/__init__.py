# -*- coding: utf-8 -*-
"""领域事件 — 描述测试生命周期中发生的业务事件，纯数据载体。"""
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class APITestStarted:
    """API 测试会话启动事件"""

    session_id: str
    task_id: int
    api_ids: tuple
    occurred_at: float = field(default_factory=time.time)


@dataclass(frozen=True)
class APITestCompleted:
    """API 测试会话完成事件"""

    session_id: str
    task_id: int
    total_rounds: int
    success_count: int
    failed_count: int
    status: str
    occurred_at: float = field(default_factory=time.time)


@dataclass(frozen=True)
class ConcurrencyReached:
    """API 并发达到上限事件

    当某个 API 的执行权获取进入等待队列时发布。
    """

    api_id: int
    task_id: int
    waiting_count: int
    max_process: int
    occurred_at: float = field(default_factory=time.time)


# === API 领域事件 re-export ===
from api_test_service.domain.events.api_events import (
    APICreated,
    APIDeleted,
    APIEvent,
    APIUpdated,
)

__all__ = [
    "APITestStarted",
    "APITestCompleted",
    "ConcurrencyReached",
    "APIEvent",
    "APICreated",
    "APIUpdated",
    "APIDeleted",
]
