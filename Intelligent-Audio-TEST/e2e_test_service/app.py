# -*- coding: utf-8 -*-
"""FastAPI application factory for e2e_test_service.

职责：E2E 测试执行、设备通信、音频播放、SPL 映射。
保留原有的 gRPC server 启动、Redis 注册、e2e_service 初始化等逻辑，
仅将原 http.server HTTP 入口替换为 FastAPI + uvicorn。
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
from shared.utils.service_registry import RedisServiceRegistry
from e2e_test_service.core.e2e_service import e2e_service
from e2e_test_service.config.config import Config

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)

# 将 DatabaseLogHandler 挂到 root logger，使标准 logging.getLogger() 调用也走分流逻辑
from shared.utils.log_handler import get_db_handler
logging.getLogger().addHandler(get_db_handler())

# 全局引用，防止 GC（gRPC server 需要在 lifespan 之外保持引用）
_grpc_server = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时初始化 DB / e2e_service / 服务注册 / gRPC server，关闭时清理。"""
    global _grpc_server

    Config.validate()
    init_db(pool_size=5)
    logger.info("数据库连接池已初始化 (pool_size=5)")

    e2e_service.init_app()
    logger.info("e2e_service 初始化完成")

    lab_name = Config.LAB_NAME
    registry = RedisServiceRegistry()
    registry.register('e2e_test_service',
                     Config.SERVICE_HOST, Config.PORT,
                     grpc_port=Config.GRPC_PORT,
                     capabilities={'labs': [lab_name]})
    logger.info("e2e_test_service 已注册到 Redis (lab=%s)", lab_name)

    from e2e_test_service.grpc.server import start_grpc_server
    try:
        _grpc_server = start_grpc_server(port=Config.GRPC_PORT)
        logger.info("gRPC server started on port %s", Config.GRPC_PORT)
    except Exception as e:
        logger.warning("gRPC server failed to start: %s", e)

    logger.info("e2e_test_service FastAPI app started")
    yield

    # 关闭 gRPC server
    if _grpc_server is not None:
        try:
            _grpc_server.stop(0)
            logger.info("gRPC server stopped")
        except Exception as e:
            logger.warning("gRPC server stop error: %s", e)

    logger.info("e2e_test_service shutting down")


def create_app(config_name='default') -> FastAPI:
    """Create and configure the FastAPI application for e2e_test_service."""
    app = FastAPI(
        title="Intelligent Audio Test - E2E Test Service",
        lifespan=lifespan,
    )

    @app.get('/health')
    def health():
        return {
            'status': 'ok',
            'service': 'e2e_test_service',
        }

    return app


app = create_app()


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(
        "e2e_test_service.app:app",
        host="0.0.0.0",
        port=Config.PORT,
        workers=1,
        log_level="info",
    )
