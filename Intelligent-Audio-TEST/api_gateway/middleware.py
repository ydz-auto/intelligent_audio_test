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
        # INT-180：当前生效认证模式（启动自检）——登录前前端就要比对
        # VITE_AUTH_MODE 与后端 AUTH_MODE，拿 mode 本身不得先登录
        '/api/v1/auth/mode',
        '/api/v1/auth/oauth',  # INT-51：提供方列表 / 授权跳转 / 授权回调
        # INT-674：站点配置（公开展示数据，登录页品牌角标需未登录态可取）
        '/api/v1/home/site',
        # INT-971：报告分享公开读取（token 在 handler 内自校验：密码/访问口径/
        # 过期；可选 Bearer 解析得 user_id 供 login/specific 判定）
        '/api/v1/reports/shared',
        # INT-766/INT-787：系统健康汇总（网关 + 认证服务）——「关于」页
        # 状态卡登录前也要能取真实健康数据，须公开（AUTH_MODE=prod 强制态下
        # 匿名可访问，语义同根路径 /health）
        '/api/v1/system/health',
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

        auth_header = request.headers.get('Authorization', '')
        bearer = auth_header[7:] if auth_header.startswith('Bearer ') else ''

        # off 模式：可选认证（INT-774 方案 A，INT-751 拍板）——Bearer 有合法
        # 身份注入真实 user_id；无/无效 token 保持 None 空态。Bearer 身份优先
        # JWT，其次 access token（INT-1140）——外部 agent 持真实 token 必须先
        # 尝试 access token 查证，再回落 dev_user，不得被降级为 dev_user
        # 管理员权限（真栈/测试栈行为一致）。
        if self.auth_mode == 'off':
            if bearer:
                identity = self._resolve_bearer(request, bearer)
                if identity is not None:
                    self._inject_identity(request, identity)
                    # INT-141：操作人上下文（出站 gRPC 自动附加 x-user-id /
                    # x-user-is-admin metadata，下游服务据此填 CUD 操作人列）
                    set_current_user_id(request.state.user_id)
                    set_current_user_is_admin(
                        '*' in (request.state.permissions or []))
                    try:
                        return await call_next(request)
                    finally:
                        set_current_user_id(None)
                        set_current_user_is_admin(False)
            # 无/无效 token → None 空态（user_id=0 归一化为 None，不充当真实
            # 操作人；dev 身份 permissions=['*'] → admin，出站 gRPC 自动透传）
            request.state.user_id = 0
            request.state.username = 'dev_user'
            request.state.role_id = 1
            request.state.permissions = ['*']
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
        if not auth_header.startswith('Bearer '):
            return self._unauthorized('缺少认证令牌')

        token = auth_header[7:]

        # Bearer 单分支切换（INT-1140）：JWT 优先，非 JWT → access token
        # 查证（外部 agent 经 skill/MCP 持明文 token 调本网关）。两者均无效
        # → 401。不写兼容层、不留双口径：前端仍只认 Bearer。
        identity = self._resolve_bearer(request, token)
        if identity is None:
            return self._unauthorized('令牌无效')

        # 注入用户信息到 request.state
        self._inject_identity(request, identity)

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
    def _resolve_bearer(request, token):
        """Bearer 身份解析：JWT 优先，失败回落 access token 查证（INT-1140）。

        Returns: (user_id, username, role_id, permissions) 或 None（均无效）。
        """
        try:
            from api_gateway.application.services.auth.token_service import TokenService
            payload = TokenService.verify(token)
        except Exception:
            return AuthMiddleware._resolve_access_token(request, token)
        return (
            payload.get('user_id', 0),
            payload.get('username', ''),
            payload.get('role_id', 0),
            payload.get('permissions', []),
        )

    @staticmethod
    def _resolve_access_token(request, token):
        """Access token 查证（INT-1140）：经 auth_service gRPC 校验并计算
        生效权限 = 用户当前权限 ∩ token scopes。失败返回 None（401 语义）。
        """
        from api_gateway.application.services.auth.access_token_service import (
            resolve_access_token_identity,
        )
        client = getattr(request, 'client', None)
        ip = client.host if client else ''
        return resolve_access_token_identity(token, ip)

    @staticmethod
    def _inject_identity(request, identity):
        """把身份元组注入 request.state（与既有 JWT 注入字段完全一致）。"""
        request.state.user_id, request.state.username, \
            request.state.role_id, request.state.permissions = identity

    @staticmethod
    def _unauthorized(detail: str) -> JSONResponse:
        return JSONResponse(
            status_code=401,
            content={'detail': detail},
        )


# INT-406：认证模式提示头中间件（共享组件，见 shared/utils/auth_mode_middleware.py）。
# 在此 re-export，保持 api_gateway.middleware 为网关中间件统一入口
from shared.utils.auth_mode_middleware import AuthModeHeaderMiddleware  # noqa: E402
