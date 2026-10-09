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
    from auth_service.domain.entities.role import PermissionEntity, RoleEntity


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
    def add(self, aggregate: 'UserAggregate', password: Optional[str] = None) -> int:
        """新增用户，返回新用户 ID（含 flush，未 commit）。

        password 为明文密码（本地注册用户），由基础设施层哈希；None 表示无密码。
        """

    @abstractmethod
    def soft_delete(self, user_id: int) -> bool:
        """软删除用户（置 status='deleted'，仅 flush）。"""

    @abstractmethod
    def update_status(self, user_id: int, status: str) -> None:
        """更新用户状态（仅 flush，用户不存在则静默无操作）。"""

    @abstractmethod
    def update_user_fields(
        self,
        user_id: int,
        username: Optional[str] = None,
        email: Optional[str] = None,
        status: Optional[str] = None,
        password: Optional[str] = None,
    ) -> bool:
        """按字段更新用户资料（None=不修改；password 哈希落库，仅 flush）。"""

    @abstractmethod
    def verify_password(self, username: str, password: str) -> Optional['UserAggregate']:
        """校验用户名+密码（bcrypt），成功返回用户聚合，失败返回 None。"""

    @abstractmethod
    def update_last_login(self, user_id: int, ip: Optional[str] = None) -> None:
        """更新最后登录时间/IP（仅 flush，用户不存在则静默无操作）。"""

    @abstractmethod
    def list_users(
        self,
        page: int = 1,
        page_size: int = 20,
        status: Optional[str] = None,
        keyword: Optional[str] = None,
        role_id: Optional[int] = None,
    ) -> Tuple[int, List['UserAggregate']]:
        """分页查询用户列表，返回 (总数, 当前页用户聚合列表)。

        keyword 为 username/email 模糊匹配；role_id 为角色过滤，空值不过滤。
        """

    @abstractmethod
    def get_user_permissions(self, user_id: int) -> List[str]:
        """获取用户生效权限码列表（按 user_id 查 role_id 后合并角色与附加权限）。"""

    @abstractmethod
    def upsert_override(self, user_id: int, permission_id: int, granted: bool) -> None:
        """按 (user_id, permission_id) 差量 upsert 用户权限 override 行（仅 flush）。"""

    @abstractmethod
    def delete_override(self, user_id: int, permission_id: int) -> int:
        """删除用户权限 override 行（仅 flush），返回删除行数。"""

    @abstractmethod
    def list_overrides(self, user_id: int) -> List[dict]:
        """列出用户全部 override 明细 [{permission_id, code, granted}]。"""

    @abstractmethod
    def get_user_role_baseline(self, user_id: int) -> List[str]:
        """获取用户角色基线权限码集合（不经 override 修正）。"""


class RoleRepositoryABC(ABC):
    """角色仓储抽象接口。

    封装 Role PO 的查询与持久化，返回 RoleEntity 领域实体。
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

    @abstractmethod
    def get_by_name(self, name: str) -> Optional['RoleEntity']:
        """按角色名查询角色实体（含权限码列表）。"""

    @abstractmethod
    def add(self, name: str, description: str = '', is_system: bool = False) -> int:
        """新增角色，返回新角色 ID（含 flush，未 commit）。"""

    @abstractmethod
    def save(self, entity: 'RoleEntity') -> bool:
        """更新既有角色（name/description；仅 flush），返回角色是否存在。"""

    @abstractmethod
    def delete(self, role_id: int) -> bool:
        """删除角色并连带删除 role_permissions 行（仅 flush），返回角色是否存在。"""

    @abstractmethod
    def set_permissions(self, role_id: int, permission_ids: List[int]) -> None:
        """全量替换角色-权限映射（去重；仅 flush）。"""

    @abstractmethod
    def count_users(self, role_id: int) -> int:
        """统计引用该角色的用户数（users.role_id 计数）。"""

    @abstractmethod
    def get_permission_by_code(self, code: str) -> Optional['PermissionEntity']:
        """按权限码查询权限点。"""

    @abstractmethod
    def get_permission_by_id(self, permission_id: int) -> Optional['PermissionEntity']:
        """按 ID 查询权限点。"""

    @abstractmethod
    def list_permissions(self) -> List['PermissionEntity']:
        """列出全部权限点（按 id 升序）。"""
