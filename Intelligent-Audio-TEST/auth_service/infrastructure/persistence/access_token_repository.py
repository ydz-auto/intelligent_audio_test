# -*- coding: utf-8 -*-
"""Access Token 仓储 — infrastructure/persistence 层。

封装 AccessToken PO 的持久化操作，在 PO ↔ 领域实体
（AccessTokenAggregate）之间做显式转换，向上层（application / domain
服务）返回纯领域对象，不泄漏 ORM。

归属：auth_service（用户与权限上下文）

事务约定：写操作仅 flush，由调用方决定 commit 时机
（与 user_repository 一致，便于组合多个操作为一个工作单元）。
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from shared.models.database import get_db_session
from auth_service.infrastructure.persistence.models import AccessToken
from auth_service.domain.entities.access_token import (
    AccessTokenAggregate,
    AccessTokenStatus,
)
from auth_service.domain.repositories.access_token_repository_abc import (
    AccessTokenRepositoryABC,
)


# ── PO ↔ Entity 转换函数 ────────────────────────────────────────────


def _po_to_entity(po: AccessToken) -> AccessTokenAggregate:
    """AccessToken PO → AccessTokenAggregate。"""
    return AccessTokenAggregate(
        id=po.id,
        user_id=po.user_id,
        name=po.name,
        token_hash=po.token_hash,
        token_hint=po.token_hint,
        scopes=list(po.scopes or []),
        expires_at=po.expires_at,
        status=po.status,
        last_used_at=po.last_used_at,
        last_used_ip=po.last_used_ip,
        created_at=po.created_at,
        deleted_at=po.deleted_at,
    )


def _apply_entity_to_po(aggregate: AccessTokenAggregate, po: AccessToken) -> None:
    """将 AccessTokenAggregate 的可变字段回写到既有 PO（不处理 id / 哈希 / 时间戳）。"""
    po.user_id = aggregate.user_id
    po.name = aggregate.name
    po.scopes = list(aggregate.scopes or [])
    po.expires_at = aggregate.expires_at
    po.status = aggregate.status
    po.deleted_at = aggregate.deleted_at


# ── AccessTokenRepository ────────────────────────────────────────────


class AccessTokenRepository(AccessTokenRepositoryABC):
    """Access Token 仓储：封装 access_tokens PO 的查询与持久化。"""

    def get_by_id(self, token_id: int,
                  user_id: Optional[int] = None) -> Optional[AccessTokenAggregate]:
        """按 token ID 查询（含软删行；user_id 提供时校验归属）。"""
        session = get_db_session()
        q = session.query(AccessToken).filter_by(id=token_id)
        if user_id is not None:
            q = q.filter(AccessToken.user_id == user_id)
        po = q.first()
        return _po_to_entity(po) if po else None

    def get_by_hash(self, token_hash: str) -> Optional[AccessTokenAggregate]:
        """按 SHA-256 哈希查询 token（含软删行，供 ValidateAccessToken 判定）。"""
        session = get_db_session()
        po = session.query(AccessToken).filter_by(token_hash=token_hash).first()
        return _po_to_entity(po) if po else None

    def list_by_user(self, user_id: int) -> List[AccessTokenAggregate]:
        """列出用户全部 token（含软删行，按 created_at 升序）。"""
        session = get_db_session()
        pos = (
            session.query(AccessToken)
            .filter(AccessToken.user_id == user_id)
            .order_by(AccessToken.created_at.asc(), AccessToken.id.asc())
            .all()
        )
        return [_po_to_entity(po) for po in pos]

    def count_active_by_user(self, user_id: int) -> int:
        """统计用户未软删 token 数（每用户上限判定）。"""
        session = get_db_session()
        return (
            session.query(AccessToken)
            .filter(AccessToken.user_id == user_id)
            .filter(AccessToken.deleted_at.is_(None))
            .count()
        )

    def add(self, aggregate: AccessTokenAggregate) -> int:
        """新增 token，返回新 token ID（含 flush，未 commit）。"""
        session = get_db_session()
        po = AccessToken(
            user_id=aggregate.user_id,
            name=aggregate.name,
            token_hash=aggregate.token_hash,
            token_hint=aggregate.token_hint,
            scopes=list(aggregate.scopes or []),
            expires_at=aggregate.expires_at,
            status=aggregate.status,
        )
        session.add(po)
        session.flush()
        return po.id

    def save(self, aggregate: AccessTokenAggregate) -> bool:
        """更新既有 token（按 aggregate.id 定位 PO 回写字段，仅 flush）。"""
        if aggregate.id is None:
            raise ValueError('save 需要既有 token ID，新增请使用 add()')
        session = get_db_session()
        po = session.query(AccessToken).filter_by(id=aggregate.id).first()
        if not po:
            return False
        _apply_entity_to_po(aggregate, po)
        session.flush()
        return True

    def soft_delete(self, token_id: int,
                    user_id: Optional[int] = None) -> bool:
        """软删除 token（置 deleted_at，仅 flush），返回是否存在。"""
        session = get_db_session()
        q = session.query(AccessToken).filter_by(id=token_id)
        if user_id is not None:
            q = q.filter(AccessToken.user_id == user_id)
        po = q.first()
        if not po:
            return False
        po.deleted_at = _utc8_now()
        session.flush()
        return True

    def update_last_used(self, token_id: int, ip: Optional[str],
                         used_at: datetime) -> bool:
        """更新最后使用时间/IP（仅 flush），返回是否存在。"""
        session = get_db_session()
        po = session.query(AccessToken).filter_by(id=token_id).first()
        if not po:
            return False
        po.last_used_at = used_at
        if ip:
            po.last_used_ip = ip
        session.flush()
        return True


def _utc8_now() -> datetime:
    """当前东八区时间（naive，与 entities.access_token.utc8_now 同口径）。"""
    from datetime import timezone, timedelta
    return datetime.now(timezone(timedelta(hours=8))).replace(tzinfo=None)


# ── 模块级单例 ──────────────────────────────────────────────────────

access_token_repository = AccessTokenRepository()
