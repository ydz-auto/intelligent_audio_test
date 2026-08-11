# -*- coding: utf-8 -*-
"""FastAPI application factory for auth_service.

职责：用户管理、角色与权限管理、认证校验。
gRPC server 仍为骨架（待 proto 接入），HTTP 入口替换为 FastAPI + uvicorn。
"""
import os
import sys
import logging
from contextlib import asynccontextmanager

current_dir = os.path.dirname(os.path.abspath(__file__))
project_dir = os.path.dirname(current_dir)
sys.path.insert(0, project_dir)

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(project_dir, '.env'))
except ImportError:
    pass

from fastapi import FastAPI

from shared.models.database import init_db
from auth_service.config.config import Config

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)

from shared.utils.log_handler import get_db_handler
logging.getLogger().addHandler(get_db_handler())

# 全局引用，防止 GC（gRPC server 需要在 lifespan 之外保持引用）
_grpc_server = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时初始化 DB，关闭时清理。"""
    global _grpc_server

    Config.validate()
    init_db(pool_size=5)
    logger.info("数据库连接池已初始化 (pool_size=5)")

    from auth_service.interfaces.grpc.server import start_grpc_server
    try:
        _grpc_server = start_grpc_server(port=Config.GRPC_PORT)
        logger.info("gRPC server started on port %s", Config.GRPC_PORT)
    except Exception as e:
        logger.warning("gRPC server failed to start: %s", e)

    logger.info("auth_service FastAPI app started")
    yield

    if _grpc_server is not None:
        try:
            _grpc_server.stop(0)
            logger.info("gRPC server stopped")
        except Exception as e:
            logger.warning("gRPC server stop error: %s", e)

    logger.info("auth_service shutting down")


def create_app(config_name='default') -> FastAPI:
    """Create and configure the FastAPI application for auth_service."""
    app = FastAPI(
        title="Intelligent Audio Test - Auth Service",
        lifespan=lifespan,
    )

    @app.get('/health')
    def health():
        return {
            'status': 'ok',
            'service': 'auth_service',
        }

    # 注册认证路由
    from auth_service.interfaces.api.routes import router as auth_router
    app.include_router(auth_router)

    return app


app = create_app()


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(
        "auth_service.app:app",
        host="0.0.0.0",
        port=Config.PORT,
        workers=1,
        log_level="info",
    )
