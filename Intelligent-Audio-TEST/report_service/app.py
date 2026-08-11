# -*- coding: utf-8 -*-
"""FastAPI application factory for report_service.

职责：报告生成、查询、摘要。
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
from report_service.config.config import Config

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

    # gRPC server
    from report_service.interfaces.grpc.server import start_grpc_server
    try:
        _grpc_server = start_grpc_server(port=Config.GRPC_PORT)
        logger.info("gRPC server started on port %s", Config.GRPC_PORT)
    except Exception as e:
        logger.warning("gRPC server failed to start: %s", e)

    # 启动软删除硬清理守护线程（只清理本服务 owned 表 test_reports 及其子表）
    from report_service.infrastructure.persistence.soft_delete_cleaner import get_cleaner as get_soft_delete_cleaner
    _soft_delete_cleaner = get_soft_delete_cleaner()
    _soft_delete_cleaner.start()

    logger.info("report_service FastAPI app started")
    yield

    # 停止软删除清理线程
    _soft_delete_cleaner.stop()

    if _grpc_server is not None:
        try:
            _grpc_server.stop(0)
            logger.info("gRPC server stopped")
        except Exception as e:
            logger.warning("gRPC server stop error: %s", e)

    logger.info("report_service shutting down")


def create_app(config_name='default') -> FastAPI:
    """Create and configure the FastAPI application for report_service."""
    app = FastAPI(
        title="Intelligent Audio Test - Report Service",
        lifespan=lifespan,
    )

    @app.get('/health')
    def health():
        return {
            'status': 'ok',
            'service': 'report_service',
        }

    from report_service.interfaces.api.routes import router as report_router
    app.include_router(report_router)

    return app


app = create_app()


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(
        "report_service.app:app",
        host="0.0.0.0",
        port=Config.PORT,
        workers=1,
        log_level="info",
    )
