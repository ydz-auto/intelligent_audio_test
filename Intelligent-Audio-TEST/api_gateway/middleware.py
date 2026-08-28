"""
FastAPI 中间件

- RequestAdapterMiddleware: 将当前请求注入 request_adapter 的 ContextVar
- AuthMiddleware: 认证与权限注入（JWT 解析 → request.state.user_id / permissions）
"""
import json
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from api_gateway.infrastructure.request_adapter import set_current_request
from shared.infrastructure.config import BaseConfig

logger = logging.getLogger(__name__)


class RequestAdapterMiddleware(BaseHTTPMiddleware):
    """将 FastAPI 请求注入 request_adapter 的 ContextVar"""

    async def dispatch(self, request, call_next):
        # 预解析 JSON body（如果 content-type 是 application/json）
        content_type = request.headers.get('content-type', '')
        if 'application/json' in content_type:
            try:
                body = await request.body()
                if body:
                    request.state._json_body = json.loads(body)
                else:
                    request.state._json_body = None
            except Exception:
                request.state._json_body = None
        else:
            request.state._json_body = None

        # 注入到 ContextVar
        set_current_request(request)

        response = await call_next(request)

        # 错误响应(>=400)记录响应体，方便排查问题
        if response.status_code >= 400:
            try:
                resp_body = b""
                async for chunk in response.body_iterator:
                    resp_body += chunk
                resp_text = resp_body.decode('utf-8', errors='replace')[:500]
                logger.info(
                    f"API Response - URL: {request.url.path} | Method: {request.method} | "
                    f"Status: {response.status_code} | Body: {resp_text}"
                )
                # 重建 response（body 已被消费）
                from starlette.responses import Response
                response = Response(
                    content=resp_body,
                    status_code=response.status_code,
                    headers=dict(response.headers),
                    media_type=response.media_type,
                )
            except Exception:
                pass

        # 清理
        set_current_request(None)
        return response


class AuthMiddleware(BaseHTTPMiddleware):
    """认证中间件 — 解析 JWT 并注入用户信息到 request.state"""

    # 无需认证的路由前缀（白名单）
    PUBLIC_PATHS = (
        '/api/v1/auth/login',
        '/api/v1/auth/callback',
        '/api/v1/auth/register',
        '/docs',
        '/openapi.json',
        '/redoc',
        '/health',
        '/socket.io',
    )

    def __init__(self, app, auth_mode: str = 'off'):
        super().__init__(app)
        self.auth_mode = auth_mode

    async def dispatch(self, request, call_next):
        # off 模式：完全跳过认证，注入默认开发用户
        if self.auth_mode == 'off':
            request.state.user_id = 0
            request.state.username = 'dev_user'
            request.state.role_id = 1
            request.state.permissions = ['*']
            return await call_next(request)

        # 白名单路由：跳过认证
        path = request.url.path
        if any(path.startswith(p) for p in self.PUBLIC_PATHS):
            return await call_next(request)

        # 从 Authorization 头提取 Bearer token
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return self._unauthorized('缺少认证令牌')

        token = auth_header[7:]

        # JWT 校验
        try:
            from api_gateway.application.services.auth.token_service import TokenService
            payload = TokenService.verify(token)
        except Exception as e:
            return self._unauthorized(f'令牌无效: {e}')

        # 注入用户信息到 request.state
        request.state.user_id = payload.get('user_id', 0)
        request.state.username = payload.get('username', '')
        request.state.role_id = payload.get('role_id', 0)
        request.state.permissions = payload.get('permissions', [])

        return await call_next(request)

    @staticmethod
    def _unauthorized(detail: str) -> JSONResponse:
        return JSONResponse(
            status_code=401,
            content={'detail': detail},
        )
