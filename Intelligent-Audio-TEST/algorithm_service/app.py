# -*- coding: utf-8 -*-
"""FastAPI application factory for algorithm_service.

职责：算法定义与算法分组管理。
gRPC server 仍为骨架（待 proto 接入），HTTP 入口为 FastAPI + uvicorn。
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
from algorithm_service.config.config import Config

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)

from shared.utils.log_handler import get_db_handler
logging.getLogger().addHandler(get_db_handler())

_grpc_server = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时初始化 DB，关闭时清理。"""
    global _grpc_server

    Config.validate()
    init_db(pool_size=5)
    logger.info("数据库连接池已初始化 (pool_size=5)")

    from algorithm_service.interfaces.grpc.server import start_grpc_server
    try:
        _grpc_server = start_grpc_server(port=Config.GRPC_PORT)
        logger.info("gRPC server started on port %s", Config.GRPC_PORT)
    except Exception as e:
        logger.warning("gRPC server failed to start: %s", e)

    logger.info("algorithm_service FastAPI app started")
    yield

    if _grpc_server is not None:
        try:
            _grpc_server.stop(0)
            logger.info("gRPC server stopped")
        except Exception as e:
            logger.warning("gRPC server stop error: %s", e)

    logger.info("algorithm_service shutting down")


def create_app(config_name='default') -> FastAPI:
    """Create and configure the FastAPI application for algorithm_service."""
    app = FastAPI(
        title="Intelligent Audio Test - Algorithm Service",
        lifespan=lifespan,
    )

    @app.get('/health')
    def health():
        return {
            'status': 'ok',
            'service': 'algorithm_service',
        }

    from algorithm_service.interfaces.api.routes import router as algorithm_router
    app.include_router(algorithm_router)

    return app


app = create_app()


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(
        "algorithm_service.app:app",
        host="0.0.0.0",
        port=Config.PORT,
        workers=1,
        log_level="info",
    )
