# -*- coding: utf-8 -*-
"""OAuth 提供方仓储 — infrastructure/persistence 层（INT-51）。

封装 CustomOAuthProvider PO 的持久化操作，在 PO ↔ 领域实体
（OAuthProviderEntity）之间做显式转换，向上层返回纯领域对象。

事务约定：写操作仅 flush，由调用方（gRPC servicer）决定 commit 时机。
"""
from __future__ import annotations

from typing import List, Optional

from shared.models.database import get_db_session
from auth_service.infrastructure.persistence.models import CustomOAuthProvider
from auth_service.domain.entities.oauth_provider import OAuthProviderEntity
from auth_service.domain.repositories.oauth_provider_repository_abc import (
    OAuthProviderRepositoryABC,
)


def _po_to_entity(po: CustomOAuthProvider) -> OAuthProviderEntity:
    """CustomOAuthProvider PO → OAuthProviderEntity。"""
    return OAuthProviderEntity(
        id=po.id,
        name=po.name,
        slug=po.slug,
        icon=po.icon or '',
        enabled=bool(po.enabled),
        client_id=po.client_id,
        client_secret=po.client_secret,
        authorize_url=po.authorize_url,
        token_url=po.token_url,
        userinfo_url=po.userinfo_url,
        scopes=po.scopes or '',
        user_id_field=po.user_id_field,
        username_field=po.username_field,
        display_name_field=po.display_name_field,
        email_field=po.email_field,
        created_at=po.created_at,
        updated_at=po.updated_at,
    )


class OAuthProviderRepository(OAuthProviderRepositoryABC):
    """OAuth 提供方仓储。"""

    def get_all(self, include_disabled: bool = True) -> List[OAuthProviderEntity]:
        """列出提供方（include_disabled=False 仅启用，按 id 升序）。"""
        session = get_db_session()
        q = session.query(CustomOAuthProvider)
        if not include_disabled:
            q = q.filter(CustomOAuthProvider.enabled.is_(True))
        return [_po_to_entity(po) for po in q.order_by(CustomOAuthProvider.id.asc()).all()]

    def get_by_id(self, provider_id: int) -> Optional[OAuthProviderEntity]:
        """按 ID 查询提供方。"""
        session = get_db_session()
        po = session.query(CustomOAuthProvider).filter_by(id=provider_id).first()
        return _po_to_entity(po) if po else None

    def get_by_slug(self, slug: str) -> Optional[OAuthProviderEntity]:
        """按 slug 查询提供方（登录链路定位）。"""
        session = get_db_session()
        po = session.query(CustomOAuthProvider).filter_by(slug=slug).first()
        return _po_to_entity(po) if po else None

    def slug_exists(self, slug: str, exclude_id: int = 0) -> bool:
        """slug 是否已被其他提供方占用（exclude_id 排除自身）。"""
        session = get_db_session()
        q = session.query(CustomOAuthProvider.id).filter_by(slug=slug)
        if exclude_id:
            q = q.filter(CustomOAuthProvider.id != exclude_id)
        return q.first() is not None

    def add(self, entity: OAuthProviderEntity) -> int:
        """新增提供方，返回新 ID（含 flush，未 commit）。"""
        session = get_db_session()
        po = CustomOAuthProvider(
            name=entity.name,
            slug=entity.slug,
            icon=entity.icon,
            enabled=entity.enabled,
            client_id=entity.client_id,
            client_secret=entity.client_secret,
            authorize_url=entity.authorize_url,
            token_url=entity.token_url,
            userinfo_url=entity.userinfo_url,
            scopes=entity.scopes,
            user_id_field=entity.user_id_field,
            username_field=entity.username_field,
            display_name_field=entity.display_name_field,
            email_field=entity.email_field,
        )
        session.add(po)
        session.flush()
        return po.id

    def save(self, entity: OAuthProviderEntity) -> bool:
        """更新既有提供方可变字段（仅 flush），返回是否存在。"""
        session = get_db_session()
        po = session.query(CustomOAuthProvider).filter_by(id=entity.id).first()
        if not po:
            return False
        po.name = entity.name
        po.slug = entity.slug
        po.icon = entity.icon
        po.enabled = entity.enabled
        po.client_id = entity.client_id
        po.client_secret = entity.client_secret
        po.authorize_url = entity.authorize_url
        po.token_url = entity.token_url
        po.userinfo_url = entity.userinfo_url
        po.scopes = entity.scopes
        po.user_id_field = entity.user_id_field
        po.username_field = entity.username_field
        po.display_name_field = entity.display_name_field
        po.email_field = entity.email_field
        session.flush()
        return True

    def delete(self, provider_id: int) -> bool:
        """删除提供方（仅 flush），返回是否存在。"""
        session = get_db_session()
        po = session.query(CustomOAuthProvider).filter_by(id=provider_id).first()
        if not po:
            return False
        session.delete(po)
        session.flush()
        return True


# ── 模块级单例 ──────────────────────────────────────────────────────

oauth_provider_repository = OAuthProviderRepository()
