# -*- coding: utf-8 -*-
"""OAuth 提供方领域实体（INT-51 登录体系改造）。

归属：auth_service（用户与权限上下文）
纯领域对象，不依赖 SQLAlchemy；PO 见
infrastructure/persistence/models/oauth_provider_models.py。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class OAuthProviderEntity:
    """自定义 OAuth 提供方（授权码模式）。

    client_secret 仅在服务端内存流转，任何对外返回路径
    （gRPC 管理查询 / 登录页公开列表）一律不携带。
    """
    id: Optional[int] = None
    name: str = ''
    slug: str = ''
    icon: str = ''
    enabled: bool = False
    client_id: str = ''
    client_secret: str = ''
    authorize_url: str = ''
    token_url: str = ''
    userinfo_url: str = ''
    scopes: str = ''
    # userinfo JSON 字段映射（点路径，如 'data.user.id'）
    user_id_field: str = 'sub'
    username_field: str = 'preferred_username'
    display_name_field: str = 'name'
    email_field: str = 'email'
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def to_public_dict(self) -> dict:
        """登录页公开信息（无任何凭证字段）。"""
        return {
            'id': self.id,
            'name': self.name,
            'slug': self.slug,
            'icon': self.icon,
            'enabled': self.enabled,
        }

    def to_admin_dict(self) -> dict:
        """管理端详情（掩去 client_secret，仅回传是否已配置）。"""
        return {
            'id': self.id,
            'name': self.name,
            'slug': self.slug,
            'icon': self.icon,
            'enabled': self.enabled,
            'client_id': self.client_id,
            'has_client_secret': bool(self.client_secret),
            'authorize_url': self.authorize_url,
            'token_url': self.token_url,
            'userinfo_url': self.userinfo_url,
            'scopes': self.scopes,
            'user_id_field': self.user_id_field,
            'username_field': self.username_field,
            'display_name_field': self.display_name_field,
            'email_field': self.email_field,
            'created_at': self.created_at.isoformat() if self.created_at else '',
            'updated_at': self.updated_at.isoformat() if self.updated_at else '',
        }
