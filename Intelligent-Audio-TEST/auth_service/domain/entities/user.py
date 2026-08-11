# -*- coding: utf-8 -*-
"""User 聚合根 — 用户领域实体。

归属：auth_service（用户与权限上下文）
本文件为纯领域对象，不依赖 SQLAlchemy / db.Model。
PO 映射仍在 infrastructure/persistence/models/user_models.py。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class UserStatus(Enum):
    """用户状态枚举。"""
    ACTIVE = 'active'        # 正常
    INACTIVE = 'inactive'    # 未激活
    LOCKED = 'locked'        # 锁定
    DELETED = 'deleted'      # 已删除


@dataclass
class UserAggregate:
    """用户聚合根。

    持有用户身份、状态、角色与权限集合，封装用户行为。
    所有字段为纯数据，不耦合任何 ORM。
    """
    id: Optional[int] = None
    username: str = ''
    email: Optional[str] = None
    role_id: Optional[int] = None
    status: str = 'active'
    permissions: List[str] = field(default_factory=list)
    deleted: bool = False
    oauth_provider: Optional[str] = None
    oauth_subject: Optional[str] = None

    # ---- 状态变更 ----
    def lock(self) -> None:
        """锁定用户账户。"""
        self.status = UserStatus.LOCKED.value

    def unlock(self) -> None:
        """解锁用户账户（恢复为 active）。"""
        self.status = UserStatus.ACTIVE.value

    def is_active(self) -> bool:
        """是否处于可用状态（active 且未删除）。"""
        return (
            not self.deleted
            and self.status == UserStatus.ACTIVE.value
        )

    # ---- 权限 ----
    def has_permission(self, perm: str) -> bool:
        """判断是否拥有指定权限码（含通配 '*'）。"""
        if not self.is_active():
            return False
        if not perm:
            return False
        return perm in self.permissions or '*' in self.permissions

    def grant_permission(self, perm: str) -> None:
        """授予权限码（去重，幂等）。"""
        if not perm:
            return
        if perm not in self.permissions:
            self.permissions.append(perm)

    def revoke_permission(self, perm: str) -> None:
        """撤销权限码（不存在则无操作，幂等）。"""
        if perm in self.permissions:
            self.permissions.remove(perm)
