# -*- coding: utf-8 -*-
"""auth_service 应用层 —— Access Token 查询（读操作）。

CQRS Query 侧：描述对 access_tokens 的读操作请求。
所有查询为 frozen dataclass，不可变。

归属：auth_service（用户与权限上下文，INT-1140）
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ListAccessTokensQuery:
    """列出当前用户未软删 token（掩码展示由接口层处理）。"""
    user_id: int


@dataclass(frozen=True)
class GetAccessTokenQuery:
    """按 ID 获取 token 详情（归属校验：token_id 必须属于 user_id）。"""
    token_id: int
    user_id: int


@dataclass(frozen=True)
class ValidateAccessTokenQuery:
    """校验明文 token（BE2 网关鉴权分支经 gRPC 调用）。

    校验通过后更新 last_used_at/last_used_ip，并返回有效 scopes
    （token.scopes 非空=按清单；空=继承用户全部权限，实时拉取）。
    """
    token: str
    ip: Optional[str] = None


@dataclass(frozen=True)
class GetAccessTokenByHashQuery:
    """按 SHA-256 哈希获取 token（服务间内部查询，不做 last_used 更新）。"""
    token_hash: str
