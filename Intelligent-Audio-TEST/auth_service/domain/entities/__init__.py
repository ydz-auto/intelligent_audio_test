# -*- coding: utf-8 -*-
"""领域实体包 — 聚合根与实体。

re-export User 聚合根与 Role / Permission 实体。
"""
from .user import UserAggregate, UserStatus
from .role import RoleEntity, PermissionEntity

__all__ = [
    'UserAggregate',
    'UserStatus',
    'RoleEntity',
    'PermissionEntity',
]
