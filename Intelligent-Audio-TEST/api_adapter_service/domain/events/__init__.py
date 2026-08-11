# -*- coding: utf-8 -*-
"""领域事件。

追加导出 session_events 模块的 MessageReceived。
session_events.SessionCreated / SessionClosed 与下方同名事件
（继承自 DomainEvent 基类、带 occurred_at 时间戳）字段结构不同，
故不在此顶层 re-export，需通过
``from api_adapter_service.domain.events.session_events import ...``
显式访问，避免遮蔽既有符号。
"""

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


# 追加 re-export：仅导入无冲突的新事件符号
from api_adapter_service.domain.events.session_events import MessageReceived  # noqa: E402,F401
