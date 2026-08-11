# -*- coding: utf-8 -*-
"""auth_service 持久化对象（PO）包。

归属：auth_service（用户与权限上下文）
表：roles / permissions / role_permissions / user_permissions
     / users / oauth_clients / oauth_refresh_tokens

P5 改造：PO 定义真正下沉到本包，shared/models/models/user_models.py
中的 PO 改为从这里 re-export。

注意：ReportStatus / TaskStatus / ReportType 三个枚举不是 PO（无 __tablename__），
是跨服务共享枚举，保留在 shared/models/common_enums.py 中。
"""
from .user_models import (
    Role,
    Permission,
    RolePermission,
    UserPermission,
    User,
    OAuthClient,
    OAuthRefreshToken,
)

__all__ = [
    'Role', 'Permission', 'RolePermission', 'UserPermission',
    'User', 'OAuthClient', 'OAuthRefreshToken',
]
