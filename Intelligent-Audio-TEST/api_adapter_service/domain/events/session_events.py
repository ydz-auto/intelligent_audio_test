# -*- coding: utf-8 -*-
"""API 适配领域事件

说明：与同包 ``__init__`` 内已有的事件（继承自 DomainEvent 基类、
带 occurred_at 时间戳）并存。本模块面向 HTTP 适配层，事件更简洁，
仅承载必要字段。
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SessionCreated:
    """会话创建事件"""
    session_id: str
    vendor: str


@dataclass
class MessageReceived:
    """消息接收事件"""
    session_id: str
    role: str
    content: str


@dataclass
class SessionClosed:
    """会话关闭事件"""
    session_id: str
    reason: Optional[str] = None
