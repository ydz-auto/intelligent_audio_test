# -*- coding: utf-8 -*-
"""网关侧 Access Token 支撑（INT-1140 / INT-1149）。

- resolve_access_token_identity：AuthMiddleware Bearer 非 JWT 分支经
  auth_service gRPC 查证明文 access token（at_xxx），注入 user_id + 生效权限
  （生效权限 = 用户当前权限 ∩ token scopes，实时 GetUserPermissions 拉取，
  不可用 JWT 快照 / ValidateAccessToken 返回的 scopes 代替）。
- AccessTokenService：个人配置页 Access Token CRUD 转发 auth_service 本组
  HTTP 端点（同前缀 /api/v1/auth/access-tokens，BE1 已实现），以当前登录
  用户 X-User-Id 头鉴权（对齐 /auth/self INT-792 语义），响应透传。

归属：api_gateway（认证上下文；跨服务一律 auth_service gRPC/HTTP + ACL，
不直连 DB，不绕 AuthMiddleware）。
"""
from __future__ import annotations

import logging
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

# 中间件内 gRPC 调用显式 deadline（秒）：覆盖 BaseConfig 默认 60s，
# 防 auth_service 假死把网关事件循环拖死（INT-54 同款失败收敛语义）
_ACCESS_TOKEN_AUTH_GRPC_TIMEOUT_SECONDS = 10
# 网关 → auth_service HTTP 转发超时（秒）
_ACCESS_TOKEN_FORWARD_TIMEOUT_SECONDS = 10


def _intersect_permissions(user_permissions: List[str],
                           token_scopes: List[str]) -> List[str]:
    """生效权限 = 用户当前权限 ∩ token scopes。

    - token scopes 空（空=继承用户全部权限）或含 '*'（管理员 token）→
      用户当前全部权限；
    - 用户为 '*'（管理员用户）→ 按 token scopes 收窄（token 定义上限）；
    - 其余逐码取交集——用户权限被实时收回即从生效集消失（越权 403）。
    """
    if not token_scopes or '*' in token_scopes:
        return list(user_permissions)
    if '*' in user_permissions:
        return list(token_scopes)
    return [p for p in token_scopes if p in user_permissions]


def resolve_access_token_identity(token: str,
                                  ip: str = '') -> Optional[Tuple]:
    """经 auth_service gRPC 查证明文 access token。

    Returns: (user_id, username, role_id, permissions) 或 None（查证失败）。

    失败语义：ValidateAccessToken 返回 success=False（不存在/软删/禁用/
    过期，error_code 供 401 映射）或 RPC 异常 → None，网关中间件据此 401。
    全程不抛异常——AuthMiddleware 内任何异常都会把 500 抛给调用方，
    off 模式必须干净回落 dev_user。
    """
    try:
        from api_gateway.infrastructure.grpc_proxies import auth_config_service
        from shared.proto import auth_service_pb2 as auth_pb
        from shared.utils.grpc_json import loads as _loads

        stub = auth_config_service.stub
        resp = stub.ValidateAccessToken(
            auth_pb.ValidateAccessTokenRequest(token=token, ip=ip or ''),
            timeout=_ACCESS_TOKEN_AUTH_GRPC_TIMEOUT_SECONDS,
        )
        if not resp.success:
            logger.warning('access token 查证失败: %s', resp.message)
            return None
        data = _loads(resp.data, {}) or {}
        token_info = data.get('token') or {}
        user_id = int(token_info.get('user_id') or 0)
        if not user_id:
            return None
        token_scopes = list(token_info.get('scopes') or [])

        # 生效权限 = 用户当前权限 ∩ token scopes：实时拉取用户当前权限。
        # GetUserPermissions 失败时按空权限交集（收紧不放宽，防越权）
        user_permissions: List[str] = []
        try:
            perms_resp = stub.GetUserPermissions(
                auth_pb.GetUserPermissionsRequest(user_id=user_id),
                timeout=_ACCESS_TOKEN_AUTH_GRPC_TIMEOUT_SECONDS,
            )
            if perms_resp.success:
                user_permissions = list(
                    (_loads(perms_resp.data, {}) or {}).get('permissions') or [])
        except Exception:
            logger.warning('GetUserPermissions 拉取失败，按空权限交集',
                           exc_info=True)
        effective = _intersect_permissions(user_permissions, token_scopes)

        # username / role_id 实时拉取（容忍失败，不影响鉴权注入）
        username, role_id = '', 0
        try:
            uresp = stub.GetUser(
                auth_pb.GetUserRequest(user_id=user_id),
                timeout=_ACCESS_TOKEN_AUTH_GRPC_TIMEOUT_SECONDS,
            )
            if uresp.success and uresp.data:
                udata = _loads(uresp.data, {}) or {}
                username = str(udata.get('username') or '')
                role_id = int(udata.get('role_id') or 0)
        except Exception:
            logger.warning('GetUser 拉取用户信息失败，username/role_id 置空',
                           exc_info=True)
        return user_id, username, role_id, effective
    except Exception:
        # RPC 异常（auth_service 不可达/超时）或响应数据异常，统一按查证
        # 失败处理（None → off 模式回落 dev_user / prod 模式 401）
        logger.warning('ValidateAccessToken RPC 调用失败，按查证失败处理',
                       exc_info=True)
        return None


class AccessTokenService:
    """个人 Access Token CRUD 网关转发（INT-1140）。

    auth_service 侧实现同前缀 HTTP CRUD（BE1 INT-1148）；网关路由仅转发
    auth_service 本组 HTTP 端点并透传响应。鉴权为「当前登录用户本人」——
    AuthMiddleware 注入的 request.state.user_id 透传为 X-User-Id 头，
    0（off 模式 dev_user）按未认证 401（对齐 /auth/self 语义）。
    """

    @staticmethod
    def _base_url() -> str:
        from shared.config.service_ports import AUTH_SERVICE_HTTP_PORT
        from api_gateway.config.config import Config
        return f'http://{Config.AUTH_SERVICE_HOST}:{AUTH_SERVICE_HTTP_PORT}'

    @staticmethod
    def forward(method: str, path: str, body=None):
        """转发到 auth_service 同路径端点，响应透传。

        Returns: JSONResponse（状态码与上游一致；上游抖动 → 502 认证服务不可用）。
        """
        import httpx
        from fastapi.responses import JSONResponse
        from api_gateway.infrastructure.request_adapter import get_current_request

        req = get_current_request()
        state = getattr(req, 'state', None) if req is not None else None
        user_id = int(getattr(state, 'user_id', 0) or 0)
        if not user_id:
            return JSONResponse(status_code=401, content={'detail': '未认证'})
        url = AccessTokenService._base_url() + path
        try:
            resp = httpx.request(
                method, url, json=body or None,
                headers={'X-User-Id': str(user_id)},
                timeout=_ACCESS_TOKEN_FORWARD_TIMEOUT_SECONDS,
            )
        except httpx.HTTPError as e:
            logger.warning('auth_service access-token 转发失败: %s', e)
            return JSONResponse(status_code=502,
                                content={'detail': '认证服务不可用'})
        try:
            payload = resp.json()
        except ValueError:
            payload = {'detail': resp.text[:200]}
        return JSONResponse(content=payload, status_code=resp.status_code)
