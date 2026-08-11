"""认证领域层 —— 实体

对齐 DDD 重构方案第八章「用户与权限上下文」的 domain 层。
User 为聚合根，封装认证相关领域逻辑。
"""
from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime


@dataclass
class AuthUser:
    """用户聚合根（认证上下文）

    与 shared/models/models/user_models.py 的 User ORM 映射对应，
    但这里只保留认证流程需要的字段，是领域模型而非持久化对象。
    """
    id: int
    username: str
    role_id: Optional[int] = None
    role_name: str = ''
    permissions: List[str] = field(default_factory=list)
    is_active: bool = True
    created_at: Optional[datetime] = None

    def has_permission(self, perm: str) -> bool:
        """领域方法：检查用户是否拥有指定权限"""
        if '*' in self.permissions:
            return True
        return perm in self.permissions

    def has_any_permission(self, *perms: str) -> bool:
        """领域方法：检查用户是否拥有给定权限之一"""
        if '*' in self.permissions:
            return True
        return bool(set(perms) & set(self.permissions))
