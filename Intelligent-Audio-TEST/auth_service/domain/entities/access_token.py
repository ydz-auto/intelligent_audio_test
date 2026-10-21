# -*- coding: utf-8 -*-
"""Access Token 聚合根 — 外部 agent / skill / MCP 鉴权令牌领域实体。

归属：auth_service（用户与权限上下文）
本文件为纯领域对象，不依赖 SQLAlchemy / db.Model。
PO 映射在 infrastructure/persistence/models/access_token_models.py。

对齐 new-api user_access_tokens 口径（INT-1140/INT-1142 评审 §1）：
- 明文 token 只生成一次（创建响应），库中只存 SHA-256 哈希 + 末 4 位 hint；
- scopes 用现有 RBAC 权限码（scripts/migrations/202608/seed_rbac.py 130 权限点），
  空列表 = 继承用户全部权限；
- expires_at None = 永不过期（对外契约 0=永不过期）；
- 软删（deleted_at）+ status（enabled|disabled），对齐本平台收藏/回收站语义
  （new-api 为硬删，本卡采用软删，取舍见 INT-1148 实现说明）。
"""
from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import List, Optional

# 明文 token 前缀常量（对外契约，BE2 网关鉴权分支与 skill/MCP 共用）
TOKEN_PREFIX = 'at_'
# 明文 token 后缀随机部分长度：32 hex（≈128bit 熵）
_TOKEN_RANDOM_HEX = 32

# 东八区（与 shared/models/database.utc8now 同口径）
_UTC8 = timezone(timedelta(hours=8))


class AccessTokenStatus(str, Enum):
    """token 状态枚举。"""
    ENABLED = 'enabled'      # 启用
    DISABLED = 'disabled'    # 禁用


def generate_token() -> str:
    """生成明文 token：`at_` + 32 hex（≈128bit）。

    明文仅创建响应返回一次；库中只落 sha256 哈希与末 4 位 hint。
    """
    return TOKEN_PREFIX + secrets.token_hex(_TOKEN_RANDOM_HEX // 2)


def hash_token(plaintext: str) -> str:
    """明文 token → SHA-256 hex digest（64 字符）。"""
    return hashlib.sha256(plaintext.encode('utf-8')).hexdigest()


def token_hint_of(plaintext: str) -> str:
    """明文 token 末 4 位（列表/详情展示掩码用）。"""
    return plaintext[-4:]


def utc8_now() -> datetime:
    """当前东八区时间（expires_at / last_used_at / deleted_at 统一口径）。"""
    return datetime.now(_UTC8).replace(tzinfo=None)


@dataclass
class AccessTokenAggregate:
    """Access Token 聚合根。

    所有字段为纯数据，不耦合任何 ORM；可变行为方法就地修改聚合状态，
    由仓储 save() 回写 PO。
    """
    id: Optional[int] = None
    user_id: int = 0
    name: str = ''
    token_hash: str = ''
    token_hint: str = ''
    scopes: List[str] = field(default_factory=list)   # 空列表=继承用户全部权限
    expires_at: Optional[datetime] = None             # None=永不过期
    status: str = AccessTokenStatus.ENABLED.value
    last_used_at: Optional[datetime] = None
    last_used_ip: Optional[str] = None
    created_at: Optional[datetime] = None
    deleted_at: Optional[datetime] = None

    # ---- 状态 ----
    def is_enabled(self) -> bool:
        """是否可用：enabled 且未软删。"""
        return (
            self.deleted_at is None
            and self.status == AccessTokenStatus.ENABLED.value
        )

    def is_expired(self, now: Optional[datetime] = None) -> bool:
        """是否过期：expires_at None = 永不过期。"""
        if self.expires_at is None:
            return False
        return (now or utc8_now()) >= self.expires_at

    def deactivate(self) -> None:
        """禁用 token。"""
        self.status = AccessTokenStatus.DISABLED.value

    def activate(self) -> None:
        """重新启用 token。"""
        self.status = AccessTokenStatus.ENABLED.value
