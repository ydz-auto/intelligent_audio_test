# -*- coding: utf-8 -*-
"""OAuth 提供方仓储抽象接口（ABC，INT-51）。

DDD 规则3：Repository 必须继承 ABC。
infrastructure/persistence/oauth_provider_repository.py 提供具体实现。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    from auth_service.domain.entities.oauth_provider import OAuthProviderEntity


class OAuthProviderRepositoryABC(ABC):
    """OAuth 提供方仓储抽象接口。"""

    @abstractmethod
    def get_all(self, include_disabled: bool = True) -> List['OAuthProviderEntity']:
        """列出提供方（include_disabled=False 仅启用，按 id 升序）。"""

    @abstractmethod
    def get_by_id(self, provider_id: int) -> Optional['OAuthProviderEntity']:
        """按 ID 查询提供方。"""

    @abstractmethod
    def get_by_slug(self, slug: str) -> Optional['OAuthProviderEntity']:
        """按 slug 查询提供方（登录链路定位）。"""

    @abstractmethod
    def slug_exists(self, slug: str, exclude_id: int = 0) -> bool:
        """slug 是否已被其他提供方占用（exclude_id 排除自身）。"""

    @abstractmethod
    def add(self, entity: 'OAuthProviderEntity') -> int:
        """新增提供方，返回新 ID（含 flush，未 commit）。"""

    @abstractmethod
    def save(self, entity: 'OAuthProviderEntity') -> bool:
        """更新既有提供方（仅 flush），返回是否存在。"""

    @abstractmethod
    def delete(self, provider_id: int) -> bool:
        """删除提供方（仅 flush），返回是否存在。"""
