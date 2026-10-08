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

from auth_service.domain.entities.user import UserStatus
from auth_service.domain.exceptions import AuthDomainError
from shared.models.common_enums import AuthErrorCode


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


# ---- 管理校验纯函数（INT-30，无 IO，可单测） ----

# 用户管理写接口允许直接设置的状态（deleted 只能走软删除 DeleteUser）
_ASSIGNABLE_STATUSES = (
    UserStatus.ACTIVE.value,
    UserStatus.INACTIVE.value,
    UserStatus.LOCKED.value,
)

# 系统内置管理员角色名（其 '*' 通配权限不可被角色权限替换移除）
_ADMIN_ROLE_NAME = 'admin'


def validate_status_transition(status: str) -> None:
    """校验用户状态值合法性（active/inactive/locked）。

    'deleted' 不允许经此路径设置 —— 软删除统一走 DeleteUser 命令；
    非法状态抛 AuthDomainError（无归类错误码，网关按未知错误码映射 400）。
    """
    if status not in _ASSIGNABLE_STATUSES:
        raise AuthDomainError(
            f'非法用户状态: {status!r}（允许: {", ".join(_ASSIGNABLE_STATUSES)}）',
        )


def validate_grant(perm: str) -> None:
    """校验授予用户的附加权限码合法性：拒绝通配 '*'。"""
    if not perm:
        raise AuthDomainError('权限码不能为空', AuthErrorCode.PERMISSION_NOT_FOUND)
    if perm == '*':
        raise AuthDomainError(
            '不允许授予通配权限 *', AuthErrorCode.WILDCARD_FORBIDDEN,
        )


def validate_revoke(perm: str) -> None:
    """校验撤销用户权限合法性：拒绝通配 '*'。

    撤销与授予必须双向封禁：对基线含 '*' 的用户写 granted=False 覆盖行
    会清空其生效权限，且重新授予被 WILDCARD_FORBIDDEN 拒绝，无 API 恢复路径。
    """
    if perm == '*':
        raise AuthDomainError(
            '不允许撤销通配权限 *', AuthErrorCode.WILDCARD_FORBIDDEN,
        )


def validate_role_deletion(is_system: bool, user_ref_count: int) -> None:
    """校验角色删除前置条件。

    - is_system=True → 拒绝（ROLE_IS_SYSTEM）
    - 有用户引用（users.role_id 计数>0）→ 拒绝（ROLE_IN_USE），提示先迁移
    """
    if is_system:
        raise AuthDomainError(
            '系统内置角色不允许删除', AuthErrorCode.ROLE_IS_SYSTEM,
        )
    if user_ref_count and user_ref_count > 0:
        raise AuthDomainError(
            f'角色仍被 {user_ref_count} 个用户引用，请先迁移用户角色',
            AuthErrorCode.ROLE_IN_USE,
        )


def validate_role_permission_set(role_name: str, new_codes: List[str]) -> None:
    """校验角色权限全量替换：admin 角色的 '*' 通配权限不可移除。"""
    if role_name == _ADMIN_ROLE_NAME and '*' not in (new_codes or []):
        raise AuthDomainError(
            'admin 角色的通配权限 * 不可移除', AuthErrorCode.WILDCARD_FORBIDDEN,
        )
