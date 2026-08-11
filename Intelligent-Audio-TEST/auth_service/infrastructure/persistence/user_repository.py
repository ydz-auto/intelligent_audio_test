# -*- coding: utf-8 -*-
"""用户与角色仓储 — infrastructure/persistence 层。

封装 User / Role / Permission 等 PO 的持久化操作，在 PO ↔ 领域实体
（UserAggregate / RoleEntity / PermissionEntity）之间做显式转换，向上层
（application / domain 服务）返回纯领域对象，不泄漏 ORM。

归属：auth_service（用户与权限上下文）

事务约定：写操作仅 flush，由调用方决定 commit 时机
（与 task_service 仓储一致，便于组合多个操作为一个工作单元）。
"""
from __future__ import annotations

import logging
from typing import List, Optional, Tuple

from shared.models.database import get_db_session
from auth_service.infrastructure.persistence.models import (
    Permission,
    Role,
    RolePermission,
    User,
    UserPermission,
)
from auth_service.domain.entities.user import UserAggregate, UserStatus
from auth_service.domain.entities.role import PermissionEntity, RoleEntity
from auth_service.domain.repositories.user_repository_abc import (
    UserRepositoryABC,
    RoleRepositoryABC,
)

logger = logging.getLogger(__name__)


# ── PO ↔ Entity 转换函数 ────────────────────────────────────────────


def _query_user_permissions(user_id: int, role_id: Optional[int]) -> List[str]:
    """查询用户生效权限码列表（角色权限 + 用户附加授予权限 - 撤销权限）。

    规则：
    1. 角色权限作为基线集合；
    2. 用户附加权限 granted=True 追加，granted=False 从基线移除；
    3. 返回结果不去重通配 '*'（保留以便上层放行判断）。
    """
    session = get_db_session()
    perms: set = set()

    # 1. 角色权限（通过 role_permissions 关联表 join permissions）
    if role_id:
        role_perms = (
            session.query(Permission.name)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .filter(RolePermission.role_id == role_id)
            .all()
        )
        perms.update(r[0] for r in role_perms)

    # 2. 用户附加权限（授予 / 撤销）
    user_perms = (
        session.query(Permission.name, UserPermission.granted)
        .join(UserPermission, UserPermission.permission_id == Permission.id)
        .filter(UserPermission.user_id == user_id)
        .all()
    )
    for name, granted in user_perms:
        if granted:
            perms.add(name)
        else:
            perms.discard(name)

    return list(perms)


def _query_role_permissions(role_id: int) -> List[str]:
    """查询角色拥有的权限码列表。"""
    session = get_db_session()
    rows = (
        session.query(Permission.name)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .filter(RolePermission.role_id == role_id)
        .all()
    )
    return [r[0] for r in rows]


def _permission_po_to_entity(po: Permission) -> PermissionEntity:
    """Permission PO → PermissionEntity。

    Permission.name 存储的是权限码（如 'audio:create'），映射到 entity.code；
    PO 无独立 display name 字段，entity.name 暂取权限码，module 置空。
    """
    return PermissionEntity(
        id=po.id,
        code=po.name,
        name=po.name,
        module='',
    )


def _role_po_to_entity(po: Role, permissions: Optional[List[str]] = None) -> RoleEntity:
    """Role PO → RoleEntity。

    Args:
        po: Role PO 对象。
        permissions: 权限码列表；为 None 时自动查询该角色的权限。
    """
    if permissions is None:
        permissions = _query_role_permissions(po.id)
    return RoleEntity(
        id=po.id,
        name=po.name,
        description=po.description or '',
        permissions=list(permissions),
    )


def _user_po_to_entity(po: User, permissions: Optional[List[str]] = None) -> UserAggregate:
    """User PO → UserAggregate。

    Args:
        po: User PO 对象。
        permissions: 权限码列表；为 None 时自动查询该用户的生效权限。

    字段映射：
        po.oauth_id         → aggregate.oauth_subject（OAuth 提供商返回的用户唯一 ID）
        po.status=='deleted' → aggregate.deleted（软删除标记由状态派生）
    """
    if permissions is None:
        permissions = _query_user_permissions(po.id, po.role_id)
    return UserAggregate(
        id=po.id,
        username=po.username,
        email=po.email,
        role_id=po.role_id,
        status=po.status,
        permissions=list(permissions),
        deleted=(po.status == UserStatus.DELETED.value),
        oauth_provider=po.oauth_provider,
        oauth_subject=po.oauth_id,
    )


def _apply_user_to_po(aggregate: UserAggregate, po: User) -> None:
    """将 UserAggregate 的可变字段回写到既有 User PO（不处理 id / 密码 / 时间戳）。

    deleted 标记优先于 status：软删除时强制 status='deleted'，
    保证聚合根状态与 PO 持久化状态一致。
    """
    po.username = aggregate.username
    po.email = aggregate.email
    po.role_id = aggregate.role_id
    if aggregate.deleted:
        po.status = UserStatus.DELETED.value
    else:
        po.status = aggregate.status
    po.oauth_provider = aggregate.oauth_provider
    po.oauth_id = aggregate.oauth_subject


# ── UserRepository ──────────────────────────────────────────────────


class UserRepository(UserRepositoryABC):
    """用户仓储：封装 User PO 的查询与持久化，返回 UserAggregate 领域实体。"""

    def get_by_id(self, user_id: int) -> Optional[UserAggregate]:
        """按用户 ID 查询用户聚合（含生效权限）。"""
        session = get_db_session()
        po = session.query(User).filter_by(id=user_id).first()
        if not po:
            return None
        return _user_po_to_entity(po)

    def get_by_username(self, username: str) -> Optional[UserAggregate]:
        """按用户名查询用户聚合（含生效权限）。"""
        session = get_db_session()
        po = session.query(User).filter_by(username=username).first()
        if not po:
            return None
        return _user_po_to_entity(po)

    def get_by_oauth(self, provider: str, subject: str) -> Optional[UserAggregate]:
        """按 OAuth 提供商与外部主体 ID（oauth_id）查询用户聚合。"""
        session = get_db_session()
        po = session.query(User).filter_by(
            oauth_provider=provider, oauth_id=subject
        ).first()
        if not po:
            return None
        return _user_po_to_entity(po)

    def save(self, aggregate: UserAggregate) -> None:
        """更新既有用户（按 aggregate.id 定位 PO 并回写字段，仅 flush）。"""
        if aggregate.id is None:
            raise ValueError('save 需要既有用户 ID，新增请使用 add()')
        session = get_db_session()
        po = session.query(User).filter_by(id=aggregate.id).first()
        if not po:
            raise ValueError(f'用户不存在: id={aggregate.id}')
        _apply_user_to_po(aggregate, po)
        session.flush()

    def add(self, aggregate: UserAggregate) -> int:
        """新增用户，返回新用户 ID（含 flush，未 commit）。"""
        session = get_db_session()
        po = User(
            username=aggregate.username,
            email=aggregate.email,
            role_id=aggregate.role_id,
            status=UserStatus.DELETED.value if aggregate.deleted else aggregate.status,
            oauth_provider=aggregate.oauth_provider,
            oauth_id=aggregate.oauth_subject,
        )
        session.add(po)
        session.flush()
        return po.id

    def soft_delete(self, user_id: int) -> bool:
        """软删除用户（置 status='deleted'，仅 flush）。

        Returns:
            True 表示找到并删除；False 表示用户不存在。
        """
        session = get_db_session()
        po = session.query(User).filter_by(id=user_id).first()
        if not po:
            return False
        po.status = UserStatus.DELETED.value
        session.flush()
        return True

    def update_status(self, user_id: int, status: str) -> None:
        """更新用户状态（仅 flush，用户不存在则静默无操作）。"""
        session = get_db_session()
        po = session.query(User).filter_by(id=user_id).first()
        if not po:
            return
        po.status = status
        session.flush()

    def update_last_login(self, user_id: int, ip: Optional[str] = None) -> None:
        """更新最后登录时间/IP（仅 flush，用户不存在则静默无操作）。"""
        from datetime import datetime, timezone
        session = get_db_session()
        po = session.query(User).filter_by(id=user_id).first()
        if not po:
            return
        po.last_login_at = datetime.now(timezone.utc)
        if ip:
            po.last_login_ip = ip
        session.flush()

    def list_users(
        self,
        page: int = 1,
        page_size: int = 20,
        status: Optional[str] = None,
    ) -> Tuple[int, List[UserAggregate]]:
        """分页查询用户列表，返回 (总数, 当前页用户聚合列表)。

        Args:
            page: 页码，从 1 开始计数。
            page_size: 每页条数。
            status: 用户状态过滤；为 None 表示不过滤，
                    为 'active'/'inactive'/'locked' 时按 status 字段精确匹配，
                    不返回 status='deleted' 的软删除记录。
        """
        session = get_db_session()
        q = session.query(User).filter(User.status != UserStatus.DELETED.value)
        if status:
            q = q.filter(User.status == status)
        total = q.count()
        pos = (
            q.order_by(User.id.asc())
            .offset(max(page - 1, 0) * page_size)
            .limit(page_size)
            .all()
        )
        aggregates = [_user_po_to_entity(po) for po in pos]
        return total, aggregates

    def get_user_permissions(self, user_id: int) -> List[str]:
        """获取用户生效权限码列表（按 user_id 查 role_id 后合并角色与附加权限）。"""
        session = get_db_session()
        po = session.query(User).filter_by(id=user_id).first()
        if not po:
            return []
        return _query_user_permissions(po.id, po.role_id)


# ── RoleRepository ──────────────────────────────────────────────────


class RoleRepository(RoleRepositoryABC):
    """角色仓储：封装 Role PO 的查询，返回 RoleEntity 领域实体。"""

    def get_by_id(self, role_id: int) -> Optional[RoleEntity]:
        """按角色 ID 查询角色实体（含权限码列表）。"""
        session = get_db_session()
        po = session.query(Role).filter_by(id=role_id).first()
        if not po:
            return None
        return _role_po_to_entity(po)

    def get_all(self) -> List[RoleEntity]:
        """查询全部角色（含权限码列表，按 id 升序）。"""
        session = get_db_session()
        pos = session.query(Role).order_by(Role.id.asc()).all()
        return [_role_po_to_entity(po) for po in pos]

    def get_role_permissions(self, role_id: int) -> List[str]:
        """获取角色权限码列表。"""
        return _query_role_permissions(role_id)


# ── 模块级单例 ──────────────────────────────────────────────────────

user_repository = UserRepository()
role_repository = RoleRepository()
