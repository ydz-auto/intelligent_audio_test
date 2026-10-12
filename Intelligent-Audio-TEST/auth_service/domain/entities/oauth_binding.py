# -*- coding: utf-8 -*-
"""第三方账号绑定领域实体（INT-147 对齐 V9.7.10 user_oauth_bindings）。

归属：auth_service（用户与权限上下文）
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class OAuthBindingEntity:
    """user_oauth_bindings 行的领域表示（不含提供方展示信息）。"""
    id: int
    user_id: int
    provider_id: int
    provider_user_id: str
    created_at: Optional[datetime] = None
