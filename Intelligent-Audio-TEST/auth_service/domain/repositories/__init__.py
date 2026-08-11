# -*- coding: utf-8 -*-
"""auth_service 领域层 — 仓储接口（ABC）

DDD 规则3：Repository 必须继承 ABC，在 domain 层定义抽象接口，
infrastructure/persistence 层提供具体实现。
"""
from auth_service.domain.repositories.user_repository_abc import (
    UserRepositoryABC,
    RoleRepositoryABC,
)

__all__ = [
    'UserRepositoryABC',
    'RoleRepositoryABC',
]
