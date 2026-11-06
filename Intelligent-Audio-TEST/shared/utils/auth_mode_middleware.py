# -*- coding: utf-8 -*-
"""认证模式提示头中间件（INT-406）——共享中间件组件。

每个 API 响应携带当前 AUTH_MODE，调用方/前端自检一眼可见 AUTH_MODE=off
的免认证风险态（对偶前端 INT-181 构建期强制显式注入 VITE_AUTH_MODE）。
头名与取值均来自 shared.constants.auth_mode（枚举/配置化，拒绝魔法字符串）。

对齐 shared/utils/naming_middleware.py 的共享中间件先例：api_gateway 与
auth_service 各自 create_app 中注册本中间件，避免跨服务 import 网关模块。
"""
from starlette.middleware.base import BaseHTTPMiddleware


class AuthModeHeaderMiddleware(BaseHTTPMiddleware):
    """认证模式提示头中间件——给每个响应注入 ``X-Auth-Mode`` 头。"""

    def __init__(self, app, auth_mode: str = 'off'):
        super().__init__(app)
        self.auth_mode = auth_mode

    async def dispatch(self, request, call_next):
        response = await call_next(request)
        from shared.constants.auth_mode import AUTH_MODE_HEADER, normalize_auth_mode
        response.headers[AUTH_MODE_HEADER] = normalize_auth_mode(self.auth_mode)
        return response
