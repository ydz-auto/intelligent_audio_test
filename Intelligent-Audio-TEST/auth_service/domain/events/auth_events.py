# -*- coding: utf-8 -*-
"""认证领域事件。

归属：auth_service（用户与权限上下文）
领域事件：描述领域中已发生的事实，由聚合根/领域服务产生，
消费方据此解耦触发后续动作（审计、通知等）。
本文件为纯领域对象，不依赖 SQLAlchemy / db.Model。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class AuthEvent:
    """认证事件基类。

    occurred_at 缺省取当前 UTC+8 时间，避免外部依赖时间源。
    """
    user_id: int
    occurred_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class UserLoggedIn(AuthEvent):
    """用户登录成功事件。"""
    username: str = ''
    ip: Optional[str] = None


@dataclass
class UserLoggedOut(AuthEvent):
    """用户登出事件。"""
    username: str = ''


@dataclass
class UserRegistered(AuthEvent):
    """用户注册成功事件。"""
    username: str = ''
    email: Optional[str] = None
