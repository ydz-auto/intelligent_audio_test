# -*- coding: utf-8 -*-
"""auth_service Access Token 仓储抽象接口（ABC）

DDD 规则3：Repository 必须继承 ABC。本模块定义领域层的仓储抽象接口，
infrastructure/persistence/access_token_repository.py 提供具体实现
（AccessTokenRepository）。

抽象方法签名与具体实现保持一致，确保上层通过依赖注入使用接口，
不直接依赖 ORM 实现。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:  # 避免循环引用，仅用于类型注解
    from auth_service.domain.entities.access_token import AccessTokenAggregate


class AccessTokenRepositoryABC(ABC):
    """Access Token 仓储抽象接口。

    封装 access_tokens PO 的查询与持久化，返回 AccessTokenAggregate 领域实体。
    事务约定与用户/角色仓储一致：写操作仅 flush，commit 由 interfaces 层决定。
    """

    @abstractmethod
    def get_by_id(self, token_id: int,
                  user_id: Optional[int] = None) -> Optional['AccessTokenAggregate']:
        """按 token ID 查询（含软删行；user_id 提供时校验归属，不匹配返回 None）。"""

    @abstractmethod
    def get_by_hash(self, token_hash: str) -> Optional['AccessTokenAggregate']:
        """按 SHA-256 哈希查询 token（含软删行，供 ValidateAccessToken 判定）。"""

    @abstractmethod
    def list_by_user(self, user_id: int) -> List['AccessTokenAggregate']:
        """列出用户全部 token（含软删行，按 created_at 升序）。"""

    @abstractmethod
    def count_active_by_user(self, user_id: int) -> int:
        """统计用户未软删 token 数（每用户上限判定）。"""

    @abstractmethod
    def add(self, aggregate: 'AccessTokenAggregate') -> int:
        """新增 token，返回新 token ID（含 flush，未 commit）。"""

    @abstractmethod
    def save(self, aggregate: 'AccessTokenAggregate') -> bool:
        """更新既有 token（按 aggregate.id 定位 PO 回写字段，仅 flush），返回是否存在。"""

    @abstractmethod
    def soft_delete(self, token_id: int,
                    user_id: Optional[int] = None) -> bool:
        """软删除 token（置 deleted_at，仅 flush），返回是否存在。"""

    @abstractmethod
    def update_last_used(self, token_id: int, ip: Optional[str],
                         used_at: datetime) -> bool:
        """更新最后使用时间/IP（仅 flush），返回是否存在。"""
