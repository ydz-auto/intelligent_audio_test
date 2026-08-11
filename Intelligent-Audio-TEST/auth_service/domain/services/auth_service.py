# -*- coding: utf-8 -*-
"""认证领域服务 — 纯逻辑，无 IO 依赖。

归属：auth_service（用户与权限上下文）
领域服务封装跨实体的纯业务逻辑：
- Token 载荷校验
- 权限判定
- 角色权限与用户附加权限的合并解析

本文件不依赖 SQLAlchemy / db.Model，便于单元测试。
"""
from __future__ import annotations

from typing import Dict, List


def validate_token_payload(payload: Dict) -> bool:
    """校验 JWT 载荷是否包含必要字段且未过期。

    必备字段：user_id / username / exp。
    exp 为 Unix 时间戳（秒），与当前时间比较。
    返回 True 表示载荷合法且在有效期内。
    """
    if not isinstance(payload, dict):
        return False
    if not payload.get('user_id') or not payload.get('username'):
        return False
    exp = payload.get('exp')
    if not isinstance(exp, (int, float)) or exp <= 0:
        return False
    import time
    if exp < time.time():
        return False
    return True


def check_permission(user_permissions: List[str], required: str) -> bool:
    """判断用户权限集合是否覆盖所需权限（含通配 '*'）。

    required 为空则视为不要求权限，直接放行。
    """
    if not required:
        return True
    if not user_permissions:
        return False
    return required in user_permissions or '*' in user_permissions


def resolve_role_permissions(role_perms: List[str], user_perms: List[str]) -> List[str]:
    """合并角色权限与用户附加权限，返回最终生效权限码列表。

    规则：
    - 角色权限作为基线
    - 用户附加权限追加去重
    - 通配符 '*' 优先置顶（若任一来源包含则结果仅保留 '*'）
    - 结果按字母序稳定排序（'*' 除外）
    """
    role_perms = role_perms or []
    user_perms = user_perms or []
    if '*' in role_perms or '*' in user_perms:
        return ['*']
    merged: List[str] = []
    seen = set()
    for perm in role_perms + user_perms:
        if perm and perm not in seen:
            seen.add(perm)
            merged.append(perm)
    merged.sort()
    return merged
