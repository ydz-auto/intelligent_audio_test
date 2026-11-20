# -*- coding: utf-8 -*-
"""TENANT 级作用域的写权限判定（INT-2551 §4.4「来源与优先级」）。

``TENANT`` 层「可写 = 租户管理员」。判定由服务端复核，缺一即拒绝
（前端隐藏入口不算数）：

1. 管理员级权限码：通配 ``*``（内置 admin 角色）或专属码
   ``agent:skill:admin``（显式授予自定义租户管理员角色）。网关按同一
   permissions 集合鉴权，服务端再验一次，防止绕过网关直连本服务；
2. 租户管理员标记：网关按认证身份解析出的 ``is_admin``，经
   ``X-User-Is-Admin`` 下发，本服务不自行解析令牌。

注意两半**同源**（都来自同一个 permissions 集合，见
``shared.constants.permissions.has_admin_credential``），不是两个独立凭据；
保留服务端复核是为了拦截「绕过网关的内部调用只带一半凭据」。若需要真正
独立的管理员来源，属于另一次设计口径调整（INT-2594 P3 审计备注）。

租户归属单独由 ``tenant_id`` 保证（``X-Tenant-Id`` 由网关按部署租户下发，
客户端伪造无效）：管理员只能写**本租户**的 TENANT Skill。
"""
from typing import Iterable

from agent_service.domain.exceptions import SkillReviewForbidden
from shared.constants.permissions import (
    SKILL_ADMIN_PERMISSION, WILDCARD_PERMISSION,
)

# 网关 RBAC 权限码（与 api_gateway/routes/agent_skill_bp.py、seed_rbac.py
# 同一值，字面值只存在于 shared.constants.permissions）
TENANT_ADMIN_PERMISSION = SKILL_ADMIN_PERMISSION


def is_tenant_admin(*, permissions: Iterable[str] = (),
                    is_admin: bool = False) -> bool:
    """管理员级授予是否成立（只读判定，不抛异常）。"""
    if not is_admin:
        return False
    granted = {item for item in (permissions or ()) if item}
    return (WILDCARD_PERMISSION in granted
            or TENANT_ADMIN_PERMISSION in granted)


def ensure_tenant_admin(*, permissions: Iterable[str] = (),
                        is_admin: bool = False) -> None:
    """不满足管理员级授予即抛 ``SKILL_REVIEW_FORBIDDEN``（对外 403）。"""
    if is_tenant_admin(permissions=permissions, is_admin=is_admin):
        return
    granted = {item for item in (permissions or ()) if item}
    if not is_admin:
        raise SkillReviewForbidden(
            'TENANT 级 Skill 仅租户管理员可操作：当前身份不具备管理员角色')
    if TENANT_ADMIN_PERMISSION not in granted:
        raise SkillReviewForbidden(
            f'TENANT 级 Skill 仅租户管理员可操作：缺少权限码 '
            f'{TENANT_ADMIN_PERMISSION}')


__all__ = [
    'TENANT_ADMIN_PERMISSION', 'WILDCARD_PERMISSION', 'ensure_tenant_admin',
    'is_tenant_admin',
]
