# -*- coding: utf-8 -*-
"""auth_service 用户与角色仓储抽象接口（ABC）

DDD 规则3：Repository 必须继承 ABC。本模块定义领域层的仓储抽象接口，
infrastructure/persistence/user_repository.py 提供具体实现
（UserRepository / RoleRepository）。

抽象方法签名与具体实现保持一致，确保上层通过依赖注入使用接口，
不直接依赖 ORM 实现。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, List, Optional, Tuple

if TYPE_CHECKING:  # 避免循环引用，仅用于类型注解
    from auth_service.domain.entities.user import UserAggregate
    from auth_service.domain.entities.role import RoleEntity


class UserRepositoryABC(ABC):
    """用户仓储抽象接口。

    封装 User PO 的查询与持久化，返回 UserAggregate 领域实体。
    """

    @abstractmethod
    def get_by_id(self, user_id: int) -> Optional['UserAggregate']:
        """按用户 ID 查询用户聚合（含生效权限）。"""

    @abstractmethod
    def get_by_username(self, username: str) -> Optional['UserAggregate']:
        """按用户名查询用户聚合（含生效权限）。"""

    @abstractmethod
    def get_by_oauth(self, provider: str, subject: str) -> Optional['UserAggregate']:
        """按 OAuth 提供商与外部主体 ID（oauth_id）查询用户聚合。"""

    @abstractmethod
    def save(self, aggregate: 'UserAggregate') -> None:
        """更新既有用户（按 aggregate.id 定位 PO 并回写字段，仅 flush）。"""

    @abstractmethod
    def add(self, aggregate: 'UserAggregate') -> int:
        """新增用户，返回新用户 ID（含 flush，未 commit）。"""

    @abstractmethod
    def soft_delete(self, user_id: int) -> bool:
        """软删除用户（置 status='deleted'，仅 flush）。"""

    @abstractmethod
    def update_status(self, user_id: int, status: str) -> None:
        """更新用户状态（仅 flush，用户不存在则静默无操作）。"""

    @abstractmethod
    def update_last_login(self, user_id: int, ip: Optional[str] = None) -> None:
        """更新最后登录时间/IP（仅 flush，用户不存在则静默无操作）。"""

    @abstractmethod
    def list_users(
        self,
        page: int = 1,
        page_size: int = 20,
        status: Optional[str] = None,
    ) -> Tuple[int, List['UserAggregate']]:
        """分页查询用户列表，返回 (总数, 当前页用户聚合列表)。"""

    @abstractmethod
    def get_user_permissions(self, user_id: int) -> List[str]:
        """获取用户生效权限码列表（按 user_id 查 role_id 后合并角色与附加权限）。"""


class RoleRepositoryABC(ABC):
    """角色仓储抽象接口。

    封装 Role PO 的查询，返回 RoleEntity 领域实体。
    """

    @abstractmethod
    def get_by_id(self, role_id: int) -> Optional['RoleEntity']:
        """按角色 ID 查询角色实体（含权限码列表）。"""

    @abstractmethod
    def get_all(self) -> List['RoleEntity']:
        """查询全部角色（含权限码列表，按 id 升序）。"""

    @abstractmethod
    def get_role_permissions(self, role_id: int) -> List[str]:
        """获取角色权限码列表。"""
