# -*- coding: utf-8 -*-
"""第三方账号绑定仓储 — infrastructure/persistence 层（INT-147 对齐 V9.7.10）。

封装 UserOAuthBinding PO 的持久化操作，PO ↔ OAuthBindingEntity 显式转换，
向上层返回纯领域对象，不泄漏 ORM。

事务约定：写操作仅 flush，由调用方决定 commit 时机（与 auth_service
其他仓储一致）。
"""
from __future__ import annotations

import logging
from typing import List, Optional

from shared.models.database import get_db_session
from auth_service.infrastructure.persistence.models import UserOAuthBinding
from auth_service.domain.entities.oauth_binding import OAuthBindingEntity
from auth_service.domain.repositories.oauth_binding_repository_abc import (
    OAuthBindingRepositoryABC,
)

logger = logging.getLogger(__name__)


def _po_to_entity(po: UserOAuthBinding) -> OAuthBindingEntity:
    """UserOAuthBinding PO → OAuthBindingEntity。"""
    return OAuthBindingEntity(
        id=po.id,
        user_id=po.user_id,
        provider_id=po.provider_id,
        provider_user_id=po.provider_user_id,
        created_at=po.created_at,
    )


class OAuthBindingRepository(OAuthBindingRepositoryABC):
    """第三方账号绑定仓储。"""

    def list_by_user(self, user_id: int) -> List[OAuthBindingEntity]:
        """列出用户全部绑定（按 id 升序）。"""
        session = get_db_session()
        pos = (
            session.query(UserOAuthBinding)
            .filter_by(user_id=user_id)
            .order_by(UserOAuthBinding.id.asc())
            .all()
        )
        return [_po_to_entity(po) for po in pos]

    def get_by_provider_identity(
        self, provider_id: int, provider_user_id: str,
    ) -> Optional[OAuthBindingEntity]:
        """按第三方身份 (provider_id, provider_user_id) 查绑定。"""
        session = get_db_session()
        po = session.query(UserOAuthBinding).filter_by(
            provider_id=provider_id, provider_user_id=provider_user_id,
        ).first()
        return _po_to_entity(po) if po else None

    def get_by_user_and_provider(
        self, user_id: int, provider_id: int,
    ) -> Optional[OAuthBindingEntity]:
        """按 (user_id, provider_id) 查绑定。"""
        session = get_db_session()
        po = session.query(UserOAuthBinding).filter_by(
            user_id=user_id, provider_id=provider_id,
        ).first()
        return _po_to_entity(po) if po else None

    def add(self, user_id: int, provider_id: int, provider_user_id: str) -> int:
        """新增绑定，返回绑定 ID（含 flush，未 commit）。"""
        session = get_db_session()
        po = UserOAuthBinding(
            user_id=user_id,
            provider_id=provider_id,
            provider_user_id=provider_user_id,
        )
        session.add(po)
        session.flush()
        return po.id

    def delete_by_user_and_provider(self, user_id: int, provider_id: int) -> bool:
        """删除用户对指定提供方的绑定（仅 flush），返回是否删除了行。"""
        session = get_db_session()
        deleted = (
            session.query(UserOAuthBinding)
            .filter_by(user_id=user_id, provider_id=provider_id)
            .delete(synchronize_session=False)
        )
        session.flush()
        return deleted > 0


# ── 模块级单例 ──────────────────────────────────────────────────────

oauth_binding_repository = OAuthBindingRepository()
