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
    """用户列表（分页，可按状态/关键词/角色过滤）。

    page 从 1 开始计数；page_size 为每页条数。
    status 为 None 表示不过滤状态。
    keyword 为 username/email 模糊匹配；role_id 为角色过滤，None 不过滤。
    """
    page: int = 1
    page_size: int = 20
    status: Optional[str] = None
    keyword: Optional[str] = None
    role_id: Optional[int] = None


@dataclass(frozen=True)
class GetUserPermissionsQuery:
    """获取用户生效权限码列表。"""
    user_id: int


@dataclass(frozen=True)
class ListRolesQuery:
    """列出全部角色。"""
    pass


@dataclass(frozen=True)
class GetRoleQuery:
    """按角色 ID 获取角色（含权限码列表）。"""
    role_id: int


@dataclass(frozen=True)
class ListPermissionsQuery:
    """列出全部权限点。"""
    pass


@dataclass(frozen=True)
class ListUserOverridesQuery:
    """列出用户权限 override 明细（差量授予/撤销记录）。"""
    user_id: int


@dataclass(frozen=True)
class ListOAuthProvidersQuery:
    """列出 OAuth 提供方（include_disabled=False 仅启用，登录页公开列表）。"""
    include_disabled: bool = True


@dataclass(frozen=True)
class GetOAuthProviderQuery:
    """按 ID 获取 OAuth 提供方。"""
    provider_id: int


@dataclass(frozen=True)
class GetOAuthProviderBySlugQuery:
    """按 slug 获取 OAuth 提供方（登录链路定位）。"""
    slug: str


@dataclass(frozen=True)
class VerifyCredentialsQuery:
    """用户名+密码凭证校验（登录链路，只读无副作用）。"""
    username: str
    password: str
