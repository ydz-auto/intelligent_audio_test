# -*- coding: utf-8 -*-
"""HTTP 请求级 DB session scope 中间件（INT-90 缺陷 A）。

纯 ASGI 中间件（非 BaseHTTPMiddleware）：请求开始时绑定请求级 session scope，
请求结束（含异常、流式响应收尾）时解绑并 remove_db_session() 把该请求的
session 连接归还连接池。

作用：
- 线程池 worker 线程先后处理的不同请求不再共享 session——事务内失败毒化
  （PendingRollbackError）不跨请求存活；
- 请求结束后不再滞留开着的连接（idle in transaction 堆积）。

ContextVar 经 anyio 线程池下发，sync 路由在 worker 线程内拿到同一 scope 键；
非 http scope（websocket / lifespan）原样放行；不经本中间件的进程（gRPC
服务、后台线程）回落线程级 scope，行为同旧版（见 shared/models/database.py）。
"""


class DbSessionScopeMiddleware:
    """请求级 DB session scope 绑定与清理（每个 FastAPI 应用注册一次）。"""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            await self.app(scope, receive, send)
            return
        from shared.models.database import (
            bind_request_session_scope,
            release_request_session_scope,
        )
        token = bind_request_session_scope()
        try:
            await self.app(scope, receive, send)
        finally:
            try:
                release_request_session_scope(token)
            except Exception:
                import logging
                logging.getLogger(__name__).debug(
                    "请求级 DB session 清理失败", exc_info=True)
