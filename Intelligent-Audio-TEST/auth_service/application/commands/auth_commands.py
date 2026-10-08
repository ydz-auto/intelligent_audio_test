# -*- coding: utf-8 -*-
"""auth_service 应用层 —— 命令（写操作）。

CQRS Command 侧：描述对用户与权限的写操作意图。
所有命令为 frozen dataclass，不可变，便于序列化与审计。

归属：auth_service（用户与权限上下文）
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional


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
    operator_id: int = 0


@dataclass(frozen=True)
class GrantPermissionCommand:
    """向用户授予附加权限码。"""
    user_id: int
    permission: str
    operator_id: int = 0


@dataclass(frozen=True)
class RevokePermissionCommand:
    """撤销用户附加权限码。

    permission_id 优先：差量撤销语义按权限点 ID 编排；
    仅给 permission 码时按码解析。
    """
    user_id: int
    permission: str = ''
    permission_id: Optional[int] = None
    operator_id: int = 0


@dataclass(frozen=True)
class CreateUserCommand:
    """创建用户（OAuth 登录场景无密码；本地注册可带密码）。"""
    username: str
    email: Optional[str]
    oauth_provider: str
    oauth_subject: str
    role_id: Optional[int] = None
    role_name: str = ''
    password: str = ''
    operator_id: int = 0


@dataclass(frozen=True)
class DeleteUserCommand:
    """删除用户（软删除，置 status='deleted'）。"""
    user_id: int
    operator_id: int = 0


@dataclass(frozen=True)
class UpdateUserCommand:
    """更新用户资料（username/email/status/password，None=不修改）。"""
    user_id: int
    username: Optional[str] = None
    email: Optional[str] = None
    status: Optional[str] = None
    password: Optional[str] = None
    operator_id: int = 0


@dataclass(frozen=True)
class SetUserRoleCommand:
    """设置用户角色。"""
    user_id: int
    role_id: int
    operator_id: int = 0


@dataclass(frozen=True)
class CreateRoleCommand:
    """创建角色（is_system 固定 False，系统角色只由 seed 管理）。"""
    name: str
    description: str = ''
    permission_codes: List[str] = None
    operator_id: int = 0


@dataclass(frozen=True)
class UpdateRoleCommand:
    """更新角色信息（None=不修改；空串视为不修改由网关层归一）。"""
    role_id: int
    name: Optional[str] = None
    description: Optional[str] = None
    operator_id: int = 0


@dataclass(frozen=True)
class SetRolePermissionsCommand:
    """全量替换角色权限（permission_codes 为权限码列表）。"""
    role_id: int
    permission_codes: List[str] = None
    operator_id: int = 0


@dataclass(frozen=True)
class DeleteRoleCommand:
    """删除角色（连带 role_permissions）。"""
    role_id: int
    operator_id: int = 0
