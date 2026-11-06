# -*- coding: utf-8 -*-
"""领域服务包 — 纯逻辑，无 IO 依赖。

re-export 认证领域服务函数。
"""
from .auth_service import (
    validate_token_payload,
    check_permission,
    resolve_role_permissions,
)

__all__ = [
    'validate_token_payload',
    'check_permission',
    'resolve_role_permissions',
]
