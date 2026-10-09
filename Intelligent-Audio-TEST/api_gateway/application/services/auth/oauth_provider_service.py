# -*- coding: utf-8 -*-
"""自定义 OAuth 提供方网关服务（INT-51 登录体系改造）。

对齐 DDD：网关不直接操作 DB，经 auth_config_service ACL 代理调
auth_service gRPC；OAuth 授权码流程（authorize 跳转 / code 换 token /
userinfo 拉取 / 字段映射）在本服务编排 —— 外部 IdP 表示 → 平台
UserInfo 的转换即 ACL 防腐层职责。

- state 防伪：JWT 签名（purpose=oauth_state，短时效），无服务端存储；
- 管理端 CRUD：client_secret 掩去，更新空串=保留原值；
- 华为云预置提供方：DB 无记录且配置了 HW_OAUTH_* 环境变量时，
  回退到环境配置构造的预置提供方（等效旧行为，避免未 seed 部署断裂）。
"""
from __future__ import annotations

import logging
import secrets
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlencode

import jwt

from api_gateway.config.config import Config
from api_gateway.domain.value_objects.auth_value_objects import UserInfo
from api_gateway.utils.response import success_response
from shared.utils.grpc_json import loads as _loads

logger = logging.getLogger(__name__)

# 预置提供方 slug（华为云，seed 脚本 materialize；历史用户 oauth_provider='huawei'）
PRESET_HUAWEI_SLUG = 'huawei'


class OAuthProviderError(Exception):
    """OAuth 流程失败（登录链路 401 语义）。"""


def _provider_error(resp, default_message: str) -> Tuple[Dict, int]:
    """管理端失败响应：复用 management_common 的 AuthErrorCode → HTTP 映射。

    servicer 失败响应 data 携带 {"error_code": "<AuthErrorCode>"}，
    命中映射表转对应状态码（如 OAUTH_SLUG_DUPLICATED → 409），未知/缺失 400。
    """
    from api_gateway.application.services.auth.management_common import (
        mapped_error_response,
    )
    return mapped_error_response(resp.message, resp.data, default_message)


class OAuthProviderService:
    """OAuth 提供方：登录页公开列表 / 管理端 CRUD / 授权码流程编排"""

    # ---------- 登录页（公开） ----------

    @staticmethod
    def list_public_providers() -> List[Dict]:
        """已启用提供方公开信息（登录页动态渲染，无凭证字段）。"""
        from api_gateway.infrastructure.grpc_proxies import auth_config_service
        resp = auth_config_service.stub.ListEnabledOAuthProviders(
            _pb().ListEnabledOAuthProvidersRequest())
        if not resp.success:
            logger.warning('ListEnabledOAuthProviders 失败: %s', resp.message)
            return []
        data = _loads(resp.data, {}) or {}
        return [
            {'id': p.get('id'), 'name': p.get('name', ''),
             'slug': p.get('slug', ''), 'icon': p.get('icon', '')}
            for p in (data.get('providers') or [])
        ]

    # ---------- 管理端 ----------

    @staticmethod
    def list_providers() -> Tuple[Dict, int]:
        """全部提供方（含禁用；client_secret 掩去）。"""
        from api_gateway.infrastructure.grpc_proxies import auth_config_service
        resp = auth_config_service.stub.ListOAuthProviders(
            _pb().ListOAuthProvidersRequest(include_disabled=True))
        if not resp.success:
            return _provider_error(resp, '查询提供方失败')
        data = _loads(resp.data, {}) or {}
        return success_response({'providers': data.get('providers', [])})

    @staticmethod
    def get_provider(provider_id: int) -> Tuple[Dict, int]:
        """提供方详情（client_secret 掩去，仅回传是否已配置）。"""
        from api_gateway.infrastructure.grpc_proxies import auth_config_service
        resp = auth_config_service.stub.GetOAuthProvider(
            _pb().GetOAuthProviderRequest(provider_id=provider_id))
        if not resp.success:
            return _provider_error(resp, '提供方不存在')
        return success_response(_loads(resp.data, {}) or {})

    @staticmethod
    def create_provider(body: Dict, operator_id: int) -> Tuple[Dict, int]:
        """创建提供方（name/slug/client_id/client_secret/三端点必填）。"""
        from api_gateway.infrastructure.grpc_proxies import auth_config_service
        resp = auth_config_service.stub.CreateOAuthProvider(
            _pb().CreateOAuthProviderRequest(
                name=(body.get('name') or '').strip(),
                slug=(body.get('slug') or '').strip(),
                icon=body.get('icon') or '',
                enabled=bool(body.get('enabled', False)),
                client_id=body.get('client_id') or '',
                client_secret=body.get('client_secret') or '',
                authorize_url=body.get('authorize_url') or '',
                token_url=body.get('token_url') or '',
                userinfo_url=body.get('userinfo_url') or '',
                scopes=body.get('scopes') or '',
                user_id_field=body.get('user_id_field') or '',
                username_field=body.get('username_field') or '',
                display_name_field=body.get('display_name_field') or '',
                email_field=body.get('email_field') or '',
                operator_id=operator_id,
            ))
        if not resp.success:
            return _provider_error(resp, '创建提供方失败')
        data = _loads(resp.data, {}) or {}
        return success_response(
            {'provider_id': data.get('provider_id')}, '创建成功',
            http_code=201)

    @staticmethod
    def update_provider(provider_id: int, body: Dict,
                        operator_id: int) -> Tuple[Dict, int]:
        """更新提供方（body 键缺省=不修改；client_secret 空串=保留原值）。"""
        req = _pb().UpdateOAuthProviderRequest(
            provider_id=provider_id,
            name=body.get('name') or '',
            slug=body.get('slug') or '',
            icon=body.get('icon') or '',
            client_id=body.get('client_id') or '',
            client_secret=body.get('client_secret') or '',
            authorize_url=body.get('authorize_url') or '',
            token_url=body.get('token_url') or '',
            userinfo_url=body.get('userinfo_url') or '',
            scopes=body.get('scopes') or '',
            user_id_field=body.get('user_id_field') or '',
            username_field=body.get('username_field') or '',
            display_name_field=body.get('display_name_field') or '',
            email_field=body.get('email_field') or '',
            operator_id=operator_id,
        )
        if 'enabled' in body:
            req.update_enabled = True
            req.enabled = bool(body.get('enabled'))
        from api_gateway.infrastructure.grpc_proxies import auth_config_service
        resp = auth_config_service.stub.UpdateOAuthProvider(req)
        if not resp.success:
            return _provider_error(resp, '更新提供方失败')
        return success_response(None, '更新成功')

    @staticmethod
    def delete_provider(provider_id: int, operator_id: int) -> Tuple[Dict, int]:
        """删除提供方。"""
        from api_gateway.infrastructure.grpc_proxies import auth_config_service
        resp = auth_config_service.stub.DeleteOAuthProvider(
            _pb().DeleteOAuthProviderRequest(
                provider_id=provider_id, operator_id=operator_id))
        if not resp.success:
            return _provider_error(resp, '删除提供方失败')
        return success_response(None, '删除成功')

    # ---------- 授权码流程 ----------

    @staticmethod
    def get_provider_config(slug: str, include_disabled: bool = False
                            ) -> Optional[Dict]:
        """按 slug 取提供方完整配置（DB；华为云 slug 回退环境预置）。"""
        from api_gateway.infrastructure.grpc_proxies import auth_config_service
        resp = auth_config_service.stub.GetOAuthProviderBySlug(
            _pb().GetOAuthProviderBySlugRequest(slug=slug))
        if resp.success and resp.data:
            data = _loads(resp.data, {}) or {}
            if data:
                return data
        if slug == PRESET_HUAWEI_SLUG and Config.HW_OAUTH_CLIENT_ID:
            # 兼容回退：未执行 seed 的部署，以环境变量构造预置提供方
            # （等效旧 HuaweiOAuthProvider 硬编码行为）
            logger.info('huawei 提供方未配置，回退环境预置（等效旧行为）')
            return _huawei_preset_config()
        return None

    @staticmethod
    def build_authorize_url(config: Dict, redirect_uri: str) -> str:
        """构造授权页跳转 URL（state 为短时效签名 token）。

        ACL 内联实现（不跨服务 import auth_service 领域模块）：
        scopes 为空时不携带 scope 参数。
        """
        state = OAuthProviderService._sign_state(config['slug'])
        params = {
            'client_id': config.get('client_id', ''),
            'redirect_uri': redirect_uri,
            'response_type': 'code',
            'state': state,
        }
        if config.get('scopes'):
            params['scope'] = config['scopes']
        return f"{config.get('authorize_url', '')}?{urlencode(params)}"

    @staticmethod
    def handle_callback(slug: str, code: str, state: str,
                        redirect_uri: str) -> UserInfo:
        """回调编排：state 校验 → 换 token → 拉 userinfo → 字段映射。

        失败抛 OAuthProviderError（路由层映射 401）。
        """
        config = OAuthProviderService.get_provider_config(slug)
        if config is None:
            raise OAuthProviderError(f'OAuth 提供方不存在或未启用: {slug}')
        OAuthProviderService._verify_state(state, slug)

        token = OAuthProviderService._exchange_token(config, code, redirect_uri)
        userinfo = OAuthProviderService._fetch_userinfo(config, token)
        user_id, username, display_name, email = OAuthProviderService._map_fields(
            config, userinfo)
        return UserInfo(
            username=username or f'{slug}_{user_id}',
            email=email or None,
            external_id=user_id,
            display_name=display_name or None,
        )

    # ---- 内部方法 ----

    @staticmethod
    def _sign_state(slug: str) -> str:
        """签发 OAuth state（JWT，purpose=oauth_state，短时效防 CSRF/重放）。"""
        now = jwt_ts()
        payload = {
            'purpose': 'oauth_state',
            'slug': slug,
            'nonce': secrets.token_urlsafe(16),
            'iat': now,
            'exp': now + Config.OAUTH_STATE_TTL_SECONDS,
        }
        return jwt.encode(payload, Config.JWT_SECRET,
                          algorithm=Config.JWT_ALGORITHM)

    @staticmethod
    def _verify_state(state: str, slug: str) -> None:
        """校验 state 签名/时效/slug 一致性，失败抛 OAuthProviderError。"""
        try:
            payload = jwt.decode(state, Config.JWT_SECRET,
                                 algorithms=[Config.JWT_ALGORITHM])
        except Exception as e:
            raise OAuthProviderError(f'state 校验失败: {e}') from e
        if payload.get('purpose') != 'oauth_state':
            raise OAuthProviderError('state 用途不符')
        if payload.get('slug') != slug:
            raise OAuthProviderError('state 与提供方不匹配')

    @staticmethod
    def _exchange_token(config: Dict, code: str, redirect_uri: str) -> str:
        """授权码换 access_token（客户端凭证以 POST 表单参数携带）。"""
        import httpx
        data = {
            'grant_type': 'authorization_code',
            'code': code,
            'client_id': config.get('client_id', ''),
            'client_secret': config.get('client_secret', ''),
            'redirect_uri': redirect_uri,
        }
        resp = httpx.post(config.get('token_url', ''), data=data, timeout=10)
        resp.raise_for_status()
        token = resp.json().get('access_token')
        if not token:
            raise OAuthProviderError('提供方未返回 access_token')
        return token

    @staticmethod
    def _fetch_userinfo(config: Dict, access_token: str) -> Dict:
        """access_token 拉取 userinfo。"""
        import httpx
        headers = {'Authorization': f'Bearer {access_token}',
                   'Accept': 'application/json'}
        resp = httpx.get(config.get('userinfo_url', ''),
                         headers=headers, timeout=10)
        resp.raise_for_status()
        return resp.json()

    @staticmethod
    def _map_fields(config: Dict, userinfo: Dict) -> Tuple[str, str, str, str]:
        """按提供方字段映射提取 (user_id, username, display_name, email)。

        ACL 防腐层：外部 IdP userinfo 表示 → 平台 UserInfo；
        点路径提取（如 'data.user.id'），user_id 缺失视为映射失败。
        """
        def _extract(path: str) -> str:
            current = userinfo
            for part in (path or '').split('.'):
                if not part:
                    return ''
                if not isinstance(current, dict):
                    return ''
                current = current.get(part)
                if current is None:
                    return ''
            if isinstance(current, (dict, list)):
                return ''
            return str(current)

        user_id = _extract(config.get('user_id_field') or 'sub')
        if not user_id:
            raise OAuthProviderError(
                f"userinfo 缺少用户标识字段: {config.get('user_id_field')}")
        username = _extract(config.get('username_field')
                            or 'preferred_username')
        display_name = _extract(config.get('display_name_field') or 'name')
        email = _extract(config.get('email_field') or 'email')
        return user_id, username, display_name, email


def jwt_ts() -> int:
    """当前 Unix 时间戳（秒）。"""
    import time
    return int(time.time())


def _huawei_preset_config() -> Dict:
    """环境变量构造的华为云预置提供方配置（兼容回退）。"""
    return {
        'id': 0,
        'name': '华为云',
        'slug': PRESET_HUAWEI_SLUG,
        'icon': '',
        'enabled': True,
        'client_id': Config.HW_OAUTH_CLIENT_ID,
        'client_secret': Config.HW_OAUTH_CLIENT_SECRET,
        'authorize_url': Config.HW_OAUTH_AUTHORIZE_URL,
        'token_url': Config.HW_OAUTH_TOKEN_URL,
        'userinfo_url': Config.HW_OAUTH_USERINFO_URL,
        'scopes': '',
        'user_id_field': 'sub',
        'username_field': 'preferred_username',
        'display_name_field': 'name',
        'email_field': 'email',
    }


def _pb():
    """延迟导入 pb2（避免导入期 gRPC 依赖）。"""
    from shared.proto import auth_service_pb2 as auth_pb
    return auth_pb
