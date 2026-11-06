# -*- coding: utf-8 -*-
"""认证与权限领域异常。

归属：auth_service（用户与权限上下文）
领域校验失败统一抛 AuthDomainError，携带 AuthErrorCode；
interfaces 层（gRPC servicer）捕获后按 error_code 写入失败响应 data，
由 api_gateway 映射 HTTP 状态码（400/403/404/409，未知一律 400）。
"""
from __future__ import annotations

from shared.models.common_enums import AuthErrorCode


class AuthDomainError(Exception):
    """领域校验失败异常，error_code 为 AuthErrorCode 成员（None 表示未归类错误）。"""

    def __init__(self, message: str,
                 error_code: AuthErrorCode = None):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
