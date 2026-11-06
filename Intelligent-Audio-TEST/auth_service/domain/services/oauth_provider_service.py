# -*- coding: utf-8 -*-
"""OAuth 提供方领域服务 — 纯逻辑，无 IO 依赖（INT-51）。

- 提供方配置校验（slug 规则 / 必填端点 / 字段映射默认值）
- userinfo JSON 字段映射（点路径提取）
- 授权 URL 与 token 请求体构造

本文件不依赖 SQLAlchemy / httpx，便于单元测试。
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlencode

from auth_service.domain.entities.oauth_provider import OAuthProviderEntity
from auth_service.domain.exceptions import AuthDomainError
from shared.models.common_enums import AuthErrorCode

# slug 规则：小写字母/数字/连字符（URL 路径段安全）
_SLUG_PATTERN = re.compile(r'^[a-z0-9]+(?:-[a-z0-9]+)*$')

# 字段映射默认值（对齐 newAPI custom_oauth_provider 设计）
FIELD_DEFAULTS = {
    'user_id_field': 'sub',
    'username_field': 'preferred_username',
    'display_name_field': 'name',
    'email_field': 'email',
}
SCOPES_DEFAULT = 'openid profile email'

# 必填端点（授权码模式三件套）
_REQUIRED_ENDPOINTS = ('authorize_url', 'token_url', 'userinfo_url')


def validate_provider_config(entity: OAuthProviderEntity) -> None:
    """校验提供方配置合法性；就地补齐字段映射默认值。

    校验失败抛 AuthDomainError（OAUTH_SLUG_DUPLICATED /
    OAUTH_PROVIDER_NOT_FOUND 归类错误码由调用方按场景补充；
    配置类错误不设归类码，网关按未知错误码映射 400）。
    """
    if not entity.name or not entity.name.strip():
        raise AuthDomainError('提供方名称不能为空')
    if not entity.slug:
        raise AuthDomainError('slug 不能为空')
    slug = entity.slug.strip().lower()
    if not _SLUG_PATTERN.match(slug):
        raise AuthDomainError(
            'slug 仅允许小写字母、数字与连字符，且不得以连字符开头或结尾')
    entity.slug = slug
    if not entity.client_id:
        raise AuthDomainError('client_id 不能为空')
    if not entity.client_secret:
        raise AuthDomainError('client_secret 不能为空')
    for endpoint in _REQUIRED_ENDPOINTS:
        if not getattr(entity, endpoint):
            raise AuthDomainError(f'{endpoint} 不能为空')
    for attr, default in FIELD_DEFAULTS.items():
        if not getattr(entity, attr):
            setattr(entity, attr, default)
    if not entity.scopes:
        entity.scopes = SCOPES_DEFAULT


def extract_dot_path(data: Dict, path: str) -> str:
    """按点路径从 userinfo dict 提取字段值（缺失返回空串）。

    对齐 newAPI gjson 语义的轻量实现：仅支持逐级 dict 取键；
    提取值统一转字符串（int/bool 等标量 str()）。
    """
    if not path:
        return ''
    current = data
    for part in path.split('.'):
        if not isinstance(current, dict):
            return ''
        current = current.get(part)
        if current is None:
            return ''
    if isinstance(current, (dict, list)):
        return ''
    return str(current)


def map_user_fields(userinfo: Dict,
                    provider: OAuthProviderEntity) -> Tuple[str, str, str, str]:
    """按提供方字段映射从 userinfo 提取 (user_id, username, display_name, email)。

    user_id 为强制项（oauth_subject 落库唯一标识），缺失抛 AuthDomainError。
    """
    user_id = extract_dot_path(userinfo, provider.user_id_field)
    if not user_id:
        raise AuthDomainError(
            f"userinfo 缺少用户标识字段: {provider.user_id_field}")
    username = extract_dot_path(userinfo, provider.username_field)
    display_name = extract_dot_path(userinfo, provider.display_name_field)
    email = extract_dot_path(userinfo, provider.email_field)
    return user_id, username, display_name, email


def build_authorize_url(provider: OAuthProviderEntity, redirect_uri: str,
                        state: str) -> str:
    """构造授权页跳转 URL（scopes 为空时不携带 scope 参数）。"""
    params: Dict[str, str] = {
        'client_id': provider.client_id,
        'redirect_uri': redirect_uri,
        'response_type': 'code',
        'state': state,
    }
    if provider.scopes:
        params['scope'] = provider.scopes
    return f'{provider.authorize_url}?{urlencode(params)}'


def build_token_request(provider: OAuthProviderEntity, code: str,
                        redirect_uri: str) -> Tuple[str, Dict[str, str]]:
    """构造 token 端点请求 (url, form_data)。

    客户端凭证以 POST 表单参数携带（auth_style=params 语义，
    与既有华为云 exchange_token 行为等效）。
    """
    data = {
        'grant_type': 'authorization_code',
        'code': code,
        'client_id': provider.client_id,
        'client_secret': provider.client_secret,
        'redirect_uri': redirect_uri,
    }
    return provider.token_url, data
