# -*- coding: utf-8 -*-
"""第三方账号绑定仓储抽象接口（INT-147 对齐 V9.7.10 user_oauth_bindings）。

DDD 规则3：Repository 必须继承 ABC。infrastructure/persistence/
oauth_binding_repository.py 提供具体实现。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:  # 避免循环引用，仅用于类型注解
    from auth_service.domain.entities.oauth_binding import OAuthBindingEntity


class OAuthBindingRepositoryABC(ABC):
    """第三方账号绑定仓储抽象接口。"""

    @abstractmethod
    def list_by_user(self, user_id: int) -> List['OAuthBindingEntity']:
        """列出用户全部绑定（按 id 升序）。"""

    @abstractmethod
    def get_by_provider_identity(
        self, provider_id: int, provider_user_id: str,
    ) -> Optional['OAuthBindingEntity']:
        """按第三方身份 (provider_id, provider_user_id) 查绑定。"""

    @abstractmethod
    def get_by_user_and_provider(
        self, user_id: int, provider_id: int,
    ) -> Optional['OAuthBindingEntity']:
        """按 (user_id, provider_id) 查绑定（用户对同一提供方的首条绑定）。"""

    @abstractmethod
    def add(self, user_id: int, provider_id: int, provider_user_id: str) -> int:
        """新增绑定，返回绑定 ID（含 flush，未 commit）。"""

    @abstractmethod
    def delete_by_user_and_provider(self, user_id: int, provider_id: int) -> bool:
        """删除用户对指定提供方的绑定（仅 flush），返回是否删除了行。"""
