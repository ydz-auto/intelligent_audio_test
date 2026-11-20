# -*- coding: utf-8 -*-
"""管理员级 RBAC 权限码的跨服务单一来源（INT-2594 P3）。

网关（``api_gateway``）与 agent 服务（``agent_service``）必须对「谁是
租户管理员」用同一字面值判定，否则会出现「网关放行、服务端 403」的
权限码空转。实现不再各写一份字符串：

- ``WILDCARD_PERMISSION``：超级通配，内置 ``admin`` 角色持有；
- ``SKILL_ADMIN_PERMISSION``：TENANT 级共享 Skill 与发布审核的专属码，
  显式授予自定义租户管理员角色（``scripts/migrations/202608/seed_rbac.py``）。

两者都是**管理员级授予**：持码即具备该域的管理员能力，网关据同一
permissions 集合算出 ``X-User-Is-Admin`` 下发，服务端复核「该标记 +
管理员级权限码」。两半**同源**（同一个 permissions 集合），不是两个
独立来源 —— 服务端复核用于拦截绕过网关的内部调用，而不是第二道身份
凭据。若需要真正独立的管理员来源，属于另一次设计口径调整。
"""
from typing import Iterable

WILDCARD_PERMISSION = '*'
SKILL_ADMIN_PERMISSION = 'agent:skill:admin'


def has_admin_credential(permissions: Iterable[str] = ()) -> bool:
    """是否持有管理员级授予（通配或专属管理员权限码）。"""
    granted = {item for item in (permissions or ()) if item}
    return (WILDCARD_PERMISSION in granted
            or SKILL_ADMIN_PERMISSION in granted)


__all__ = [
    'SKILL_ADMIN_PERMISSION', 'WILDCARD_PERMISSION', 'has_admin_credential',
]
