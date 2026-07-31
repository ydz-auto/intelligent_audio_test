"""
FastAPI 中间件 —— 将当前请求注入 request_adapter 的 ContextVar

使旧控制器中的 `from api_gateway.controllers.request_adapter import request`
能够访问 FastAPI 的请求参数。
"""
import json
from starlette.middleware.base import BaseHTTPMiddleware
from api_gateway.controllers.request_adapter import set_current_request


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
        # 清理
        set_current_request(None)
        return response
