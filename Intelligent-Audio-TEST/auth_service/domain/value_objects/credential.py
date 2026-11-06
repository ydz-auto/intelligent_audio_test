# -*- coding: utf-8 -*-
"""认证凭证值对象。

归属：auth_service（用户与权限上下文）
值对象：不可变、无唯一身份，按字段值判等。
本文件为纯领域对象，不依赖 SQLAlchemy / db.Model。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class TokenPayload:
    """JWT 访问令牌载荷。

    exp / iat 为 Unix 时间戳（秒）。
    permissions 为该令牌携带的权限码列表。
    """
    user_id: int
    username: str
    role_id: Optional[int] = None
    permissions: List[str] = field(default_factory=list)
    exp: int = 0
    iat: int = 0


@dataclass
class OAuthCredential:
    """第三方 OAuth 凭证值对象。

    provider 标识 OAuth 提供商（huawei/github/google...）。
    expires_at 为 Unix 时间戳（秒），0 表示不过期或未知。
    """
    provider: str
    access_token: str
    refresh_token: Optional[str] = None
    expires_at: int = 0


@dataclass
class PasswordHash:
    """密码哈希值对象。

    algorithm 标识哈希算法（如 bcrypt / pbkdf2_sha256）。
    salt 可为空（如 bcrypt 自带盐）。
    """
    hash_value: str
    salt: str = ''
    algorithm: str = 'bcrypt'
