# -*- coding: utf-8 -*-
"""第三方账号绑定网关服务（INT-147 对齐旧库 GET/DELETE /oauth/bindings）。

对齐 DDD：网关不直接操作 DB，经 auth_config_service ACL 代理调
auth_service gRPC；intent=bind 完成侧在此校验绑定票据（回调跳转无
Authorization 头，票据把已验真的第三方身份带回已认证 API 通道落库）。
错误映射见 management_common（AuthErrorCode → 400/403/404/409）。
"""
from __future__ import annotations

from typing import Dict, Tuple

from api_gateway.application.services.auth.oauth_provider_service import (
    OAuthProviderError,
    OAuthProviderService,
)
from api_gateway.utils.error_codes import ErrorCode
from api_gateway.utils.response import error_response, success_response


def _provider_error(resp, default_message: str) -> Tuple[Dict, int]:
    """gRPC 失败 → HTTP 错误响应（复用 AuthErrorCode 映射语义）。"""
    from api_gateway.application.services.auth.management_common import (
        mapped_error_response,
    )
    return mapped_error_response(resp.message, resp.data, default_message)


class OAuthBindingGatewayService:
    """第三方账号绑定：列表 / 绑定完成（票据）/ 解绑"""

    @staticmethod
    def list_bindings(user_id: int) -> Tuple[Dict, int]:
        """当前用户绑定列表（含提供方展示信息，无凭证字段）。"""
        from api_gateway.infrastructure.grpc_proxies import auth_config_service
        from shared.utils.grpc_json import loads as _loads
        resp = auth_config_service.stub.ListUserOAuthBindings(
            _pb().ListUserOAuthBindingsRequest(user_id=user_id))
        if not resp.success:
            return _provider_error(resp, '查询绑定列表失败')
        data = _loads(resp.data, {}) or {}
        return success_response({'bindings': data.get('bindings', [])})

    @staticmethod
    def complete_bind(user_id: int, bind_ticket: str) -> Tuple[Dict, int]:
        """校验绑定票据并落库绑定（幂等；身份冲突返回失败）。"""
        try:
            identity = OAuthProviderService.verify_bind_ticket(bind_ticket)
        except OAuthProviderError as e:
            return error_response(str(e),
                                  code=ErrorCode.INVALID_PARAMS, http_code=400)
        from api_gateway.infrastructure.grpc_proxies import auth_config_service
        from shared.utils.grpc_json import loads as _loads
        resp = auth_config_service.stub.BindUserOAuthIdentity(
            _pb().BindUserOAuthIdentityRequest(
                user_id=user_id,
                provider_id=identity['provider_id'],
                provider_user_id=identity['provider_user_id'],
            ))
        if not resp.success:
            return _provider_error(resp, '绑定失败')
        return success_response(_loads(resp.data, {}) or {}, '绑定成功')

    @staticmethod
    def unbind(user_id: int, provider_id: int) -> Tuple[Dict, int]:
        """解绑指定提供方（幂等，无绑定亦成功，对齐旧库 DELETE 语义）。"""
        from api_gateway.infrastructure.grpc_proxies import auth_config_service
        resp = auth_config_service.stub.UnbindUserOAuthIdentity(
            _pb().UnbindUserOAuthIdentityRequest(
                user_id=user_id, provider_id=provider_id))
        if not resp.success:
            return _provider_error(resp, '解绑失败')
        return success_response(None, '解绑成功')


def _pb():
    """延迟导入 pb2（避免导入期 gRPC 依赖）。"""
    from shared.proto import auth_service_pb2 as auth_pb
    return auth_pb
