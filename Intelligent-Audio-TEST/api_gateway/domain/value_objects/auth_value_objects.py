"""认证领域层 —— 值对象

对齐 DDD 重构方案第八章。封装认证相关的无唯一标识概念。
"""
from dataclasses import dataclass
from typing import List, Optional
from datetime import datetime


@dataclass(frozen=True)
class TokenPayload:
    """JWT payload 值对象"""
    user_id: int
    username: str
    role_id: Optional[int]
    permissions: List[str]
    iat: Optional[datetime] = None
    exp: Optional[datetime] = None


@dataclass(frozen=True)
class OAuthCredential:
    """OAuth 凭证值对象"""
    client_id: str
    client_secret: str
    redirect_uri: str

    def __post_init__(self):
        if not self.client_id or not self.client_secret:
            raise ValueError('client_id 和 client_secret 不能为空')
        if not self.redirect_uri:
            raise ValueError('redirect_uri 不能为空')


@dataclass(frozen=True)
class UserInfo:
    """OAuth 返回的用户信息值对象"""
    username: str
    email: Optional[str] = None
    external_id: Optional[str] = None  # OAuth provider 返回的唯一 ID
    display_name: Optional[str] = None
