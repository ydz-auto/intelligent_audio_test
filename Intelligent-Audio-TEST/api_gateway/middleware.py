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

        # 预解析 multipart/form-data（分片上传等文件表单，INT-106）：
        # 字段进 _form_data，文件进 _files，经 request_adapter 的
        # form / files 代理以 Flask 语义消费
        if 'multipart/form-data' in content_type:
            request.state._form_data = {}
            request.state._files = {}
            try:
                # INT-111：必须先经 body() 缓存原始请求体。BaseHTTPMiddleware 的
                # _CachedRequest 仅在 _body 已缓存时才向下游回灌 body，只调 form()
                # （内部走 stream()）会把流耗尽且不回灌 → 下游 FastAPI 原生
                # UploadFile 路由拿到空 body → 422（import/preview 回归根因）。
                # _body 已缓存后 form() 从缓存体解析，两者共用无冲突。
                await request.body()
                form = await request.form()
                fields, files = {}, {}
                for key, value in form.multi_items():
                    if hasattr(value, 'file') and hasattr(value, 'filename'):
                        files[key] = value
                    else:
                        fields[key] = value
                request.state._form_data = fields
                request.state._files = files
            except Exception:
                logger.warning("multipart 表单解析失败: %s", request.url.path,
                               exc_info=True)

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

    # 无需认证的路由前缀（白名单）。
    # 匹配按路径段边界（见 _is_public_path）：/api/v1/auth/oauth 不得误伤
    # /api/v1/auth/oauth-providers 这类共享字符串前缀的管理端路径
    PUBLIC_PATHS = (
        '/api/v1/auth/login',
        '/api/v1/auth/callback',
        '/api/v1/auth/register',
        # INT-179：登录前 RSA 公钥下发（旧库路径别名，与 /login/encryption-key
        # 同源）——公钥用于加密登录密码，拿公钥本身不得先登录
        '/api/v1/auth/encryption-key',
        # INT-179：refresh 路由自解析 Bearer 并自验签（过期 token 须由路由
        # 返回刷新失败语义，而非被网关在路由前拦死）
        '/api/v1/auth/refresh',
        '/api/v1/auth/oauth',  # INT-51：提供方列表 / 授权跳转 / 授权回调
        '/docs',
        '/openapi.json',
        '/redoc',
        '/health',
        '/socket.io',
    )

    def __init__(self, app, auth_mode: str = 'off'):
        super().__init__(app)
        self.auth_mode = auth_mode

    @classmethod
    def _is_public_path(cls, path: str) -> bool:
        return any(
            path == p or path.startswith(p.rstrip('/') + '/')
            for p in cls.PUBLIC_PATHS
        )

    async def dispatch(self, request, call_next):
        from shared.infrastructure.user_context import (
            set_current_user_id, set_current_user_is_admin,
        )

        # off 模式：完全跳过认证，注入默认开发用户
        if self.auth_mode == 'off':
            request.state.user_id = 0
            request.state.username = 'dev_user'
            request.state.role_id = 1
            request.state.permissions = ['*']
            # INT-141：user_id=0 归一化为 None（未认证），不充当真实操作人；
            # dev 身份 permissions=['*'] → admin，出站 gRPC 自动透传
            set_current_user_id(None)
            set_current_user_is_admin(True)
            try:
                return await call_next(request)
            finally:
                set_current_user_id(None)
                set_current_user_is_admin(False)

        # 白名单路由：跳过认证
        if self._is_public_path(request.url.path):
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

        # INT-141：操作人上下文（出站 gRPC 拦截器自动附加 x-user-id /
        # x-user-is-admin metadata，下游服务据此填 CUD 操作人列与 purge 鉴权）
        set_current_user_id(request.state.user_id)
        set_current_user_is_admin('*' in (request.state.permissions or []))
        try:
            return await call_next(request)
        finally:
            set_current_user_id(None)
            set_current_user_is_admin(False)

    @staticmethod
    def _unauthorized(detail: str) -> JSONResponse:
        return JSONResponse(
            status_code=401,
            content={'detail': detail},
        )
