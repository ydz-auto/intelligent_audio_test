# -*- coding: utf-8 -*-
"""TENANT 级作用域的写权限判定（INT-2551 §4.4「来源与优先级」）。

``TENANT`` 层「可写 = 租户管理员」。判定是**双条件**，两条都在服务端
复核，任一缺失即拒绝（前端隐藏入口不算数）：

1. RBAC 权限码 ``agent:skill:admin``（网关已按它鉴权，服务端再验一次，
   防止绕过网关直接调用本服务 / 内部调用只带一半凭据）；
2. 租户管理员角色：网关按认证身份解析出的 ``is_admin`` 标记（JWT 角色，
   与 ``shared.infrastructure.user_context`` 的 admin 判定同一口径），经
   ``X-User-Is-Admin`` 下发，本服务不自行解析令牌。

租户归属单独由 ``tenant_id`` 保证（``X-Tenant-Id`` 由网关按部署租户下发，
客户端伪造无效）：管理员只能写**本租户**的 TENANT Skill。
"""
from typing import Iterable

from agent_service.domain.exceptions import SkillReviewForbidden

# 网关 RBAC 权限码（与 api_gateway/routes/agent_skill_bp.py、seed_rbac.py 同一值）
TENANT_ADMIN_PERMISSION = 'agent:skill:admin'
WILDCARD_PERMISSION = '*'


def is_tenant_admin(*, permissions: Iterable[str] = (),
                    is_admin: bool = False) -> bool:
    """双条件是否都满足（只读判定，不抛异常）。"""
    if not is_admin:
        return False
    granted = {item for item in (permissions or ()) if item}
    return (WILDCARD_PERMISSION in granted
            or TENANT_ADMIN_PERMISSION in granted)


def ensure_tenant_admin(*, permissions: Iterable[str] = (),
                        is_admin: bool = False) -> None:
    """不满足双条件即抛 ``SKILL_REVIEW_FORBIDDEN``（对外 403）。"""
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
