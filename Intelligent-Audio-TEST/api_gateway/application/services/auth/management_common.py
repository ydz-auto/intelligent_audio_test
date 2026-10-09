# -*- coding: utf-8 -*-
"""用户/角色管理端点公共支撑（INT-30）。

- JWT 时效提示常量（单一来源）：管理写接口响应体统一注入 notice，
  提示权限变更对已签发令牌不即时生效；强失效（Redis 黑名单）本期未实现。
- AuthErrorCode → HTTP 状态码映射：gRPC 失败响应 data 携带
  {"error_code": "<AuthErrorCode>"}，未知/缺失一律 400。
- auth_service gRPC 调用统一入口（经 auth_config_service ACL 代理）。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Tuple

from api_gateway.infrastructure.grpc_proxies import auth_config_service
from api_gateway.utils.error_codes import ErrorCode
from api_gateway.utils.response import error_response, success_response
from shared.models.common_enums import AuthErrorCode
from shared.utils.grpc_json import loads as _loads

logger = logging.getLogger(__name__)

PERMISSION_CHANGE_NOTICE = (
    '权限变更对已签发令牌不即时生效，最长延迟至令牌过期（24h）；'
    '强失效（Redis 黑名单）本期未实现'
)

# AuthErrorCode → HTTP 状态码（spec §五.6：400/403/404/409，未知 → 400）
_ERROR_HTTP_STATUS = {
    AuthErrorCode.USER_NOT_FOUND: 404,
    AuthErrorCode.ROLE_NOT_FOUND: 404,
    AuthErrorCode.PERMISSION_NOT_FOUND: 404,
    AuthErrorCode.USERNAME_DUPLICATED: 400,
    AuthErrorCode.ROLE_NAME_DUPLICATED: 400,
    AuthErrorCode.ROLE_IS_SYSTEM: 400,
    AuthErrorCode.ROLE_IN_USE: 409,
    AuthErrorCode.WILDCARD_FORBIDDEN: 400,
    AuthErrorCode.SELF_OPERATION_FORBIDDEN: 403,
    AuthErrorCode.PERMISSION_NOT_GRANTED: 400,
    # 自定义 OAuth 提供方（INT-51）
    AuthErrorCode.OAUTH_PROVIDER_NOT_FOUND: 404,
    AuthErrorCode.OAUTH_SLUG_DUPLICATED: 409,
    AuthErrorCode.OAUTH_PROVIDER_ENABLED_EXISTS: 409,
}


def with_notice(result: Tuple[Dict, int]) -> Tuple[Dict, int]:
    """向 success_response/error_response 生成的 (payload, http_code) 注入 notice。"""
    payload, http_code = result
    payload['notice'] = PERMISSION_CHANGE_NOTICE
    return payload, http_code


def current_operator_id() -> int:
    """当前登录用户 ID（AuthMiddleware 注入 request.state.user_id）。"""
    from api_gateway.infrastructure.request_adapter import get_current_request
    req = get_current_request()
    if req is None:
        return 0
    return int(getattr(req.state, 'user_id', 0) or 0)


def call_auth_rpc(rpc_name: str, request_msg: Any,
                  default_error: str = '操作失败') -> Tuple[Any, Any]:
    """调用 auth_service gRPC 并按 error_code 映射 HTTP 状态码。

    Returns:
        成功: (data_dict_or_None, None)
        失败: (None, (payload, http_code)) —— payload 直接可返回。
    """
    stub = auth_config_service.stub
    resp = getattr(stub, rpc_name)(request_msg)
    if resp.success:
        return (_loads(resp.data, {}) or {}), None
    error_code = _parse_error_code(resp.data)
    http_code = _ERROR_HTTP_STATUS.get(error_code, 400)
    message = resp.message or default_error
    logger.warning('auth RPC %s 失败: %s (error_code=%s)',
                   rpc_name, message, error_code.value if error_code else '')
    payload, _ = error_response(message, code=ErrorCode.OPERATION_FAILED,
                                http_code=http_code)
    return None, (payload, http_code)


def mapped_error_response(message: str, data: str,
                          default_error: str = '操作失败') -> Tuple[Dict, int]:
    """已获得的失败 AuthResponse → HTTP 错误响应（按 data.error_code 映射）。

    供网关侧自行调用 stub 的管理路径复用 call_auth_rpc 同款映射语义
    （AuthErrorCode 命中 _ERROR_HTTP_STATUS，缺失/未知一律 400）。
    """
    error_code = _parse_error_code(data)
    http_code = _ERROR_HTTP_STATUS.get(error_code, 400)
    payload, _ = error_response(message or default_error,
                                code=ErrorCode.OPERATION_FAILED,
                                http_code=http_code)
    return payload, http_code


def _parse_error_code(data: str) -> Any:
    """解析失败响应 data 中的 error_code（缺失/未知返回 None）。"""
    try:
        payload = _loads(data, None) or {}
        return AuthErrorCode(payload.get('error_code'))
    except Exception:
        return None
