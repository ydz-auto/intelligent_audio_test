# -*- coding: utf-8 -*-
"""auth_service 应用层 —— Access Token 命令（写操作）。

CQRS Command 侧：描述对 access_tokens 的写操作意图。
所有命令为 frozen dataclass，不可变，便于序列化与审计。

归属：auth_service（用户与权限上下文，INT-1140）
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional


@dataclass(frozen=True)
class CreateAccessTokenCommand:
    """创建 Access Token。

    scopes: RBAC 权限码列表；None/空列表 = 继承用户全部权限。
    expires_at: 显式过期时间；None = 永不过期。
    default_expiry: True（路由层「未传 expires_at」归一）时，handler 取
        Config.ACCESS_TOKEN_DEFAULT_EXPIRY_DAYS 计算默认有效期。
    明文 token 仅创建响应返回一次，库中只存 SHA-256 哈希 + 末 4 位 hint。
    """
    user_id: int
    name: str
    scopes: Optional[List[str]] = None
    expires_at: Optional[datetime] = None
    default_expiry: bool = False
    operator_id: int = 0


@dataclass(frozen=True)
class UpdateAccessTokenCommand:
    """更新 Access Token（None=不修改）。

    scopes 显式传空列表 = 清空（回到继承用户全部权限）；None = 不修改。
    status 取值 enabled|disabled。
    expires_at + update_expires_at=True 时应用过期时间（None=清空为永不过期），
    update_expires_at 沿袭 UpdateOAuthProvider 的 update_enabled 显式标记范式。
    """
    token_id: int
    user_id: int
    name: Optional[str] = None
    scopes: Optional[List[str]] = None
    status: Optional[str] = None
    expires_at: Optional[datetime] = None
    update_expires_at: bool = False
    operator_id: int = 0


@dataclass(frozen=True)
class DeleteAccessTokenCommand:
    """软删除 Access Token（置 deleted_at，保留行供审计/回收站语义）。"""
    token_id: int
    user_id: int
    operator_id: int = 0
