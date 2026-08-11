# -*- coding: utf-8 -*-
"""领域事件包 — 认证相关事件。

re-export AuthEvent 基类及 UserLoggedIn / UserLoggedOut / UserRegistered。
"""
from .auth_events import (
    AuthEvent,
    UserLoggedIn,
    UserLoggedOut,
    UserRegistered,
)

__all__ = [
    'AuthEvent',
    'UserLoggedIn',
    'UserLoggedOut',
    'UserRegistered',
]
