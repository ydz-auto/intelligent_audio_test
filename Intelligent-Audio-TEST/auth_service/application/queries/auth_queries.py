# -*- coding: utf-8 -*-
"""auth_service 应用层 —— 查询（读操作）。

CQRS Query 侧：描述对用户与权限的读操作请求。
所有查询为 frozen dataclass，不可变。

归属：auth_service（用户与权限上下文）
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class GetUserQuery:
    """按用户 ID 获取用户聚合。"""
    user_id: int


@dataclass(frozen=True)
class GetUserByUsernameQuery:
    """按用户名获取用户聚合。"""
    username: str


@dataclass(frozen=True)
class GetUserByOAuthQuery:
    """按 OAuth 提供商与外部主体 ID 获取用户聚合。"""
    provider: str
    subject: str


@dataclass(frozen=True)
class ListUsersQuery:
    """用户列表（分页，可按状态过滤）。

    page 从 1 开始计数；page_size 为每页条数。
    status 为 None 表示不过滤状态。
    """
    page: int = 1
    page_size: int = 20
    status: Optional[str] = None


@dataclass(frozen=True)
class GetUserPermissionsQuery:
    """获取用户生效权限码列表。"""
    user_id: int


@dataclass(frozen=True)
class ListRolesQuery:
    """列出全部角色。"""
    pass
