# -*- coding: utf-8 -*-
"""领域事件。"""

import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class DomainEvent:
    """领域事件基类。"""
    occurred_at: float = field(default_factory=time.time)


@dataclass
class SessionCreated(DomainEvent):
    """会话已创建事件。"""
    session_id: str = ''
    task_id: str = ''


@dataclass
class RoundCompleted(DomainEvent):
    """一轮对话已完成事件。"""
    session_id: str = ''
    task_id: str = ''
    round: int = 0
    latency: float = 0.0


@dataclass
class SessionClosed(DomainEvent):
    """会话已关闭事件。"""
    session_id: str = ''
    reason: Optional[str] = None
