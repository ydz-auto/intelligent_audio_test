# -*- coding: utf-8 -*-
"""auth_service 应用层 —— 命令（写操作）。

CQRS Command 侧：描述对用户与权限的写操作意图。
所有命令为 frozen dataclass，不可变，便于序列化与审计。

归属：auth_service（用户与权限上下文）
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class RegisterUserCommand:
    """注册本地账号用户（用户名 + 密码）。

    password 为明文密码，由应用层下游（repository/infrastructure）
    负责哈希持久化；命令本身只承载意图，不处理哈希。
    """
    username: str
    email: str
    password: str
    role_id: Optional[int] = None


@dataclass(frozen=True)
class UpdateUserStatusCommand:
    """更新用户状态（active/inactive/locked/deleted）。"""
    user_id: int
    status: str


@dataclass(frozen=True)
class GrantPermissionCommand:
    """向用户授予附加权限码。"""
    user_id: int
    permission: str


@dataclass(frozen=True)
class RevokePermissionCommand:
    """撤销用户附加权限码。"""
    user_id: int
    permission: str


@dataclass(frozen=True)
class CreateUserCommand:
    """创建用户（OAuth 登录场景，无密码）。"""
    username: str
    email: Optional[str]
    oauth_provider: str
    oauth_subject: str
    role_id: Optional[int] = None


@dataclass(frozen=True)
class DeleteUserCommand:
    """删除用户（软删除，置 status='deleted'）。"""
    user_id: int
