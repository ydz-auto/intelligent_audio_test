# -*- coding: utf-8 -*-
"""Role / Permission 实体 — RBAC 领域实体。

归属：auth_service（用户与权限上下文）
本文件为纯领域对象，不依赖 SQLAlchemy / db.Model。
PO 映射仍在 infrastructure/persistence/models/user_models.py。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class PermissionEntity:
    """权限实体。

    code 采用 '资源:操作' 形式，如 'audio:create'。
    module 标识权限所属业务模块（便于按模块批量授权）。
    """
    id: int
    code: str
    name: str = ''
    module: str = ''


@dataclass
class RoleEntity:
    """角色实体 (RBAC)。

    permissions 为权限码列表（资源:操作）。
    通过 has_permission 判断角色是否拥有某权限。
    """
    id: int
    name: str
    description: str = ''
    permissions: List[str] = field(default_factory=list)

    def has_permission(self, code: str) -> bool:
        """判断角色是否拥有指定权限码（含通配 '*'）。"""
        if not code:
            return False
        return code in self.permissions or '*' in self.permissions
