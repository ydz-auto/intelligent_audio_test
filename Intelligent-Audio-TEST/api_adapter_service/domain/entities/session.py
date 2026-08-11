# -*- coding: utf-8 -*-
"""API 适配会话聚合根

管理多轮对话会话的生命周期。

说明：本模块的 SessionAggregate 为对外可见的会话聚合根概念，
与同包 ``__init__`` 内已有的 ``AdapterSession``（被
``infrastructure/persistence/session_repository`` 使用的运行期聚合根）
并存，互不冲突。
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class SessionStatus(str, Enum):
    """会话状态"""
    ACTIVE = "active"
    CLOSED = "closed"
    EXPIRED = "expired"


@dataclass
class Message:
    """消息实体"""
    role: str  # user / assistant / system
    content: str
    timestamp: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class SessionSnapshot:
    """会话快照值对象"""
    session_id: str
    status: str
    vendor: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


@dataclass
class SessionAggregate:
    """会话聚合根"""
    id: str
    status: SessionStatus = SessionStatus.ACTIVE
    vendor: Optional[str] = None
    messages: List[Message] = field(default_factory=list)
    context: Optional[Dict[str, Any]] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    @classmethod
    def create(cls, session_id: str, vendor: str = "", **kwargs) -> "SessionAggregate":
        return cls(
            id=session_id,
            vendor=vendor or None,
            context=kwargs.get('context'),
        )

    def add_message(self, role: str, content: str, **kwargs) -> Message:
        """添加消息"""
        msg = Message(role=role, content=content, **kwargs)
        self.messages.append(msg)
        return msg

    def close(self) -> None:
        """关闭会话"""
        self.status = SessionStatus.CLOSED

    def to_snapshot(self) -> SessionSnapshot:
        """生成快照"""
        return SessionSnapshot(
            session_id=self.id,
            status=self.status.value,
            vendor=self.vendor,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )
