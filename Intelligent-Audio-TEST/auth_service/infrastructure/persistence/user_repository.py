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

from sqlalchemy import func, or_, select

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


def _permission_count_expr():
    """列表页「生效权限数」的相关标量子查询（INT-1465）。

    口径与 ``_query_user_permissions`` 一致：角色权限为基线，用户 granted
    追加、revoked 撤销（同一权限既 granted 又 revoked 时按撤销优先）。
    列表只需要这个整数，不需要权限码全集——这里把它并进分页主查询，整页
    只发 1 条 SQL，不额外增加数据库往返（并发 40 下往返会被连接池排队放大）。

    不用 UNION/EXCEPT 派生表：派生表在内层无法引用外层 users 列（PG 需
    LATERAL），因此拆成两段可加计数，两段都按 permission_id 去重：
    1. 角色权限中未被撤销的个数；
    2. 用户 granted 中不在角色基线、且未被撤销的个数。
    """
    role_baseline = select(RolePermission.permission_id).where(
        RolePermission.role_id == User.role_id).correlate(User)
    revoked = select(UserPermission.permission_id).where(
        UserPermission.user_id == User.id,
        UserPermission.granted.is_(False),
    ).correlate(User)
    role_count = (
        select(func.count(func.distinct(RolePermission.permission_id)))
        .where(RolePermission.role_id == User.role_id,
               RolePermission.permission_id.notin_(revoked))
        .correlate(User)
        .scalar_subquery()
    )
    granted_extra_count = (
        select(func.count(func.distinct(UserPermission.permission_id)))
        .where(UserPermission.user_id == User.id,
               UserPermission.granted.is_(True),
               UserPermission.permission_id.notin_(role_baseline),
               UserPermission.permission_id.notin_(revoked))
        .correlate(User)
        .scalar_subquery()
    )
    return role_count + granted_extra_count


def _user_po_to_entity(
    po: User,
    permissions: Optional[List[str]] = None,
    role_name: Optional[str] = None,
) -> UserAggregate:
    """User PO → UserAggregate。

    Args:
        po: User PO 对象。
        permissions: 权限码列表；为 None 时自动查询该用户的生效权限。
            列表查询显式传 []（INT-1465：列表不加载权限，见 list_users）。
        role_name: 角色名；为 None 时按 po.role_id 单查，
            列表查询传批量查好的值避免 N+1。

    字段映射：
        po.oauth_id         → aggregate.oauth_subject（OAuth 提供商返回的用户唯一 ID）
        po.status=='deleted' → aggregate.deleted（软删除标记由状态派生）
        po.role（join roles）→ aggregate.role_name（展示字段）
    """
    if permissions is None:
        permissions = _query_user_permissions(po.id, po.role_id)
    if role_name is None:
        role_name = _role_name_by_id(get_db_session(), po.role_id)
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
        display_name=po.display_name,
        role_name=role_name,
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
    po.display_name = _normalize_display_name(aggregate.display_name)


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


def _normalize_display_name(value: Optional[str]) -> Optional[str]:
    """空/纯空白 display_name 归一化为 None（INT-697）。

    显示名允许为空（NULL，前端兜底 username）；非空按 trim 后落库。
    更新路径由 update_user_fields 的 None=不修改 与 空串=清空 语义承载。
    """
    if value is None:
        return None
    normalized = str(value).strip()
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
            display_name=_normalize_display_name(aggregate.display_name),
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
        display_name: Optional[str] = None,
    ) -> bool:
        """按字段更新用户资料（None=不修改；password 哈希落库，仅 flush）。

        display_name（INT-697）：None=不修改，空串/空白=清空落 NULL，
        非空=设置（与 username/email 的「空串=不修改」语义不同）。

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
        if display_name is not None:
            po.display_name = _normalize_display_name(display_name)
        session.flush()
        return True

    def verify_password(self, account: str, password: str) -> Optional[UserAggregate]:
        """校验 账号(用户名或邮箱)+密码（bcrypt），成功返回用户聚合，失败返回 None。

        INT-147 对齐旧库：username 或 email 任一匹配即可登录
        （单查询 OR 匹配，email 按注册时原值精确比较）。
        用户不存在 / 无密码（OAuth 用户）/ 哈希不匹配 一律返回 None
        （不区分失败原因，避免用户名枚举）。
        """
        import bcrypt
        session = get_db_session()
        po = session.query(User).filter(
            or_(User.username == account, User.email == account),
        ).first()
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

    def verify_password_by_user_id(self, user_id: int, password: str) -> bool:
        """按用户 ID 校验密码（bcrypt），成功返回 True，失败返回 False。

        INT-794 自助改密原密码校验：用户不存在 / 无本地密码（OAuth 用户）/
        哈希不匹配 一律 False（与 verify_password 防枚举语义一致，差异仅在
        按主键定位而非按账号匹配）。
        """
        import bcrypt
        session = get_db_session()
        po = session.query(User).filter_by(id=user_id).first()
        if not po or not po.password_hash:
            return False
        try:
            return bcrypt.checkpw(
                password.encode('utf-8'),
                po.password_hash.encode('utf-8'),
            )
        except ValueError:
            return False

    def count_all(self) -> int:
        """统计非软删除用户总数（首个注册用户 admin 策略判定，INT-147）。

        排除 status='deleted'：全部用户被软删除后，下一次注册允许
        重新引导出 admin（避免系统失去最后一个管理员后无法恢复）。
        """
        session = get_db_session()
        return (
            session.query(User)
            .filter(User.status != UserStatus.DELETED.value)
            .count()
        )

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
        # INT-1465：列表查询不加载生效权限（权限明细仅详情 GetUser 给出）。
        # 原实现逐用户查权限(2 次)+角色名(1 次)是 N+1；上一版整页补 2 条批量
        # 查询虽固定条数，但在并发 40 下仍因连接池排队把端点时延推过验收线。
        # 这里把角色名、生效权限数、总数全部并进分页主查询：
        # - 角色名：LEFT JOIN roles；
        # - 生效权限数：相关标量子查询（_permission_count_expr）；
        # - 总数：count(*) OVER ()，窗口在 LIMIT 之前求值，与独立 count 查询
        #   同义，省掉一次往返。整页只发 1 条 SQL，且与页大小无关。
        rows = (
            q.outerjoin(Role, Role.id == User.role_id)
            .with_entities(
                User,
                Role.name.label('role_name'),
                _permission_count_expr().label('permission_count'),
                func.count().over().label('total_count'),
            )
            .order_by(User.id.asc())
            .offset(max(page - 1, 0) * page_size)
            .limit(page_size)
            .all()
        )
        # 翻到空页时没有行可承载窗口计数，回退一次 count 查询（首页无数据同此）
        total = int(rows[0].total_count) if rows else q.count()
        aggregates = []
        for po, role_name, permission_count, _total in rows:
            aggregate = _user_po_to_entity(
                po, permissions=[], role_name=role_name or '')
            aggregate.permission_count = int(permission_count or 0)
            aggregates.append(aggregate)
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
