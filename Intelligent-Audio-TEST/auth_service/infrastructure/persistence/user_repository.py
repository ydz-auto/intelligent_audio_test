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
from typing import Dict, List, Optional, Tuple

from sqlalchemy import or_

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


def _hash_password(password: str) -> str:
    """明文密码 → bcrypt 哈希（infrastructure 层职责，聚合根不持有密码）。"""
    import bcrypt
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


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
        description=po.description or '',
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
        is_system=bool(po.is_system),
    )


def _role_name_by_id(session, role_id: Optional[int]) -> str:
    """按角色 ID 查角色名（无匹配返回空串）。"""
    if not role_id:
        return ''
    row = session.query(Role.name).filter_by(id=role_id).first()
    return row[0] if row else ''


def _user_po_to_entity(po: User, permissions: Optional[List[str]] = None) -> UserAggregate:
    """User PO → UserAggregate。

    Args:
        po: User PO 对象。
        permissions: 权限码列表；为 None 时自动查询该用户的生效权限。

    字段映射：
        po.oauth_id         → aggregate.oauth_subject（OAuth 提供商返回的用户唯一 ID）
        po.status=='deleted' → aggregate.deleted（软删除标记由状态派生）
        po.role（join roles）→ aggregate.role_name（展示字段）
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
        role_name=_role_name_by_id(get_db_session(), po.role_id),
        created_at=po.created_at,
        updated_at=po.updated_at,
        last_login_at=po.last_login_at,
    )


def _apply_user_to_po(aggregate: UserAggregate, po: User) -> None:
    """将 UserAggregate 的可变字段回写到既有 User PO（不处理 id / 密码 / 时间戳）。

    deleted 标记优先于 status：软删除时强制 status='deleted'，
    保证聚合根状态与 PO 持久化状态一致。
    """
    po.username = aggregate.username
    po.email = _normalize_email(aggregate.email)
    po.role_id = aggregate.role_id
    if aggregate.deleted:
        po.status = UserStatus.DELETED.value
    else:
        po.status = aggregate.status
    po.oauth_provider = aggregate.oauth_provider
    po.oauth_id = aggregate.oauth_subject


def _normalize_email(email: Optional[str]) -> Optional[str]:
    """空/纯空白 email 归一化为 None（INT-84）。

    历史库 users.email 带 UNIQUE 约束（users_email_key），空串占位会导致
    第二个空邮箱用户必撞唯一约束；PG 唯一索引对 NULL 不生效，注册/建号
    传空邮箱时统一落 NULL。非空 email 按原值（trim 后）落库。
    """
    if email is None:
        return None
    normalized = str(email).strip()
    return normalized or None


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

    def add(self, aggregate: UserAggregate, password: Optional[str] = None) -> int:
        """新增用户，返回新用户 ID（含 flush，未 commit）。

        Args:
            aggregate: 用户聚合。
            password: 明文密码（本地注册用户）；哈希在本基础设施层完成，
                聚合根不持有密码；为 None 表示无密码（OAuth 用户）。
        """
        session = get_db_session()
        po = User(
            username=aggregate.username,
            email=_normalize_email(aggregate.email),
            role_id=aggregate.role_id,
            status=UserStatus.DELETED.value if aggregate.deleted else aggregate.status,
            oauth_provider=aggregate.oauth_provider,
            oauth_id=aggregate.oauth_subject,
            password_hash=_hash_password(password) if password else None,
        )
        session.add(po)
        session.flush()
        return po.id

    def soft_delete(self, user_id: int) -> bool:
        """软删除用户（置 status='deleted' 并解除角色引用，仅 flush）。

        role_id 置空：软删除用户不再占用角色引用，
        避免 ROLE_IN_USE 误判（删除角色被迫"迁移已删除用户"）。

        Returns:
            True 表示找到并删除；False 表示用户不存在。
        """
        session = get_db_session()
        po = session.query(User).filter_by(id=user_id).first()
        if not po:
            return False
        po.status = UserStatus.DELETED.value
        po.role_id = None
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

    def update_user_fields(
        self,
        user_id: int,
        username: Optional[str] = None,
        email: Optional[str] = None,
        status: Optional[str] = None,
        password: Optional[str] = None,
    ) -> bool:
        """按字段更新用户资料（None=不修改；password 哈希落库，仅 flush）。

        Returns:
            用户是否存在。
        """
        session = get_db_session()
        po = session.query(User).filter_by(id=user_id).first()
        if not po:
            return False
        if username is not None:
            po.username = username
        if email is not None:
            po.email = _normalize_email(email)
        if status is not None:
            po.status = status
        if password is not None:
            po.password_hash = _hash_password(password)
        session.flush()
        return True

    def verify_password(self, username: str, password: str) -> Optional[UserAggregate]:
        """校验用户名+密码（bcrypt），成功返回用户聚合，失败返回 None。

        用户不存在 / 无密码（OAuth 用户）/ 哈希不匹配 一律返回 None
        （不区分失败原因，避免用户名枚举）。
        """
        import bcrypt
        session = get_db_session()
        po = session.query(User).filter_by(username=username).first()
        if not po or not po.password_hash:
            return None
        try:
            if not bcrypt.checkpw(
                    password.encode('utf-8'),
                    po.password_hash.encode('utf-8')):
                return None
        except ValueError:
            return None
        return _user_po_to_entity(po)

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
        keyword: Optional[str] = None,
        role_id: Optional[int] = None,
    ) -> Tuple[int, List[UserAggregate]]:
        """分页查询用户列表，返回 (总数, 当前页用户聚合列表)。

        Args:
            page: 页码，从 1 开始计数。
            page_size: 每页条数。
            status: 用户状态过滤；为 None 表示不过滤，
                    为 'active'/'inactive'/'locked' 时按 status 字段精确匹配，
                    不返回 status='deleted' 的软删除记录。
            keyword: username/email 模糊匹配（大小写不敏感），空值不过滤。
            role_id: 角色过滤，空值不过滤。
        """
        session = get_db_session()
        q = session.query(User).filter(User.status != UserStatus.DELETED.value)
        if status:
            q = q.filter(User.status == status)
        if keyword:
            like = f'%{keyword}%'
            q = q.filter(
                or_(User.username.ilike(like), User.email.ilike(like)),
            )
        if role_id:
            q = q.filter(User.role_id == role_id)
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

    # ---- 用户权限 override（差量授予/撤销持久化，INT-30 修复点） ----

    def upsert_override(self, user_id: int, permission_id: int, granted: bool) -> None:
        """按 (user_id, permission_id) 差量 upsert 用户权限 override 行（仅 flush）。

        既有行更新 granted 方向，无行插入新记录。
        user_permissions 表无 (user_id, permission_id) 唯一约束，
        以先查后写保证单线程幂等；并发重复行由 _query_user_permissions
        按集合语义兜底（唯一索引 migration 后置独立卡）。
        """
        session = get_db_session()
        row = (
            session.query(UserPermission)
            .filter(
                UserPermission.user_id == user_id,
                UserPermission.permission_id == permission_id,
            )
            .first()
        )
        if row is not None:
            row.granted = granted
        else:
            session.add(UserPermission(
                user_id=user_id, permission_id=permission_id, granted=granted,
            ))
        session.flush()

    def delete_override(self, user_id: int, permission_id: int) -> int:
        """删除用户权限 override 行（仅 flush），返回删除行数。"""
        session = get_db_session()
        deleted = (
            session.query(UserPermission)
            .filter(
                UserPermission.user_id == user_id,
                UserPermission.permission_id == permission_id,
            )
            .delete(synchronize_session=False)
        )
        session.flush()
        return deleted

    def list_overrides(self, user_id: int) -> List[dict]:
        """列出用户全部 override 明细（含权限码），granted 方向原样返回。"""
        session = get_db_session()
        rows = (
            session.query(UserPermission.permission_id, Permission.name, UserPermission.granted)
            .join(Permission, Permission.id == UserPermission.permission_id)
            .filter(UserPermission.user_id == user_id)
            .order_by(UserPermission.permission_id.asc())
            .all()
        )
        return [
            {'permission_id': pid, 'code': code, 'granted': bool(granted)}
            for pid, code, granted in rows
        ]

    def get_user_role_baseline(self, user_id: int) -> List[str]:
        """获取用户角色基线权限码集合（不经 override 修正的原始角色权限）。"""
        session = get_db_session()
        po = session.query(User).filter_by(id=user_id).first()
        if not po:
            return []
        return _query_role_permissions(po.role_id) if po.role_id else []


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

    # ---- 角色与权限点管理（INT-30） ----

    def get_by_name(self, name: str) -> Optional[RoleEntity]:
        """按角色名查询角色实体（含权限码列表）。"""
        session = get_db_session()
        po = session.query(Role).filter_by(name=name).first()
        if not po:
            return None
        return _role_po_to_entity(po)

    def add(self, name: str, description: str = '',
            is_system: bool = False) -> int:
        """新增角色，返回新角色 ID（含 flush，未 commit）。"""
        session = get_db_session()
        po = Role(name=name, description=description or '', is_system=is_system)
        session.add(po)
        session.flush()
        return po.id

    def save(self, entity: RoleEntity) -> bool:
        """更新既有角色（name/description；仅 flush），返回角色是否存在。"""
        session = get_db_session()
        po = session.query(Role).filter_by(id=entity.id).first()
        if not po:
            return False
        po.name = entity.name
        po.description = entity.description or ''
        session.flush()
        return True

    def delete(self, role_id: int) -> bool:
        """删除角色并连带删除 role_permissions 行（仅 flush），返回角色是否存在。"""
        session = get_db_session()
        po = session.query(Role).filter_by(id=role_id).first()
        if not po:
            return False
        session.query(RolePermission).filter_by(role_id=role_id).delete(
            synchronize_session=False)
        session.delete(po)
        session.flush()
        return True

    def set_permissions(self, role_id: int, permission_ids: List[int]) -> None:
        """全量替换角色-权限映射（去重；仅 flush）。"""
        session = get_db_session()
        session.query(RolePermission).filter_by(role_id=role_id).delete(
            synchronize_session=False)
        for pid in dict.fromkeys(permission_ids):
            session.add(RolePermission(role_id=role_id, permission_id=pid))
        session.flush()

    def count_users(self, role_id: int) -> int:
        """统计引用该角色的用户数（users.role_id 计数，软删除用户不计入）。

        软删除已在删除时清 role_id，此处再按状态排除以兜底历史数据。
        """
        session = get_db_session()
        return (
            session.query(User)
            .filter(User.role_id == role_id)
            .filter(User.status != UserStatus.DELETED.value)
            .count()
        )

    def get_permission_by_code(self, code: str) -> Optional[PermissionEntity]:
        """按权限码查询权限点。"""
        session = get_db_session()
        po = session.query(Permission).filter_by(name=code).first()
        return _permission_po_to_entity(po) if po else None

    def get_permission_by_id(self, permission_id: int) -> Optional[PermissionEntity]:
        """按 ID 查询权限点。"""
        session = get_db_session()
        po = session.query(Permission).filter_by(id=permission_id).first()
        return _permission_po_to_entity(po) if po else None

    def list_permissions(self) -> List[PermissionEntity]:
        """列出全部权限点（按 id 升序）。"""
        session = get_db_session()
        pos = session.query(Permission).order_by(Permission.id.asc()).all()
        return [_permission_po_to_entity(po) for po in pos]


# ── 模块级单例 ──────────────────────────────────────────────────────

user_repository = UserRepository()
role_repository = RoleRepository()
