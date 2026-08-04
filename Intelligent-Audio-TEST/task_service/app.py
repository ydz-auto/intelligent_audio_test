# -*- coding: utf-8 -*-
"""FastAPI application factory for task_service.

职责：任务调度、分发、进度管理、结果汇总、评估计算。
保留原有的 gRPC server 启动、调度器、评估服务、Redis 注册等初始化逻辑，
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
from task_service.config.config import Config

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
    """启动时初始化 DB / 调度器 / 评估服务 / 服务注册 / gRPC server，关闭时清理。"""
    global _grpc_server

    Config.validate()
    init_db(pool_size=20)
    logger.info("数据库连接池已初始化 (pool_size=20)")

    # 初始化任务调度器
    from task_service.core.execution_engine import execution_engine
    execution_engine._init_scheduler()
    logger.info("任务调度器初始化完成")

    # 初始化评估服务
    from task_service.evaluation.evaluation_service import evaluation_service
    logger.info("评估服务初始化完成")

    # 服务注册
    registry = RedisServiceRegistry()
    registry.register('task_service', Config.SERVICE_HOST, Config.PORT)

    # 启动 gRPC server
    from task_service.grpc.server import start_grpc_server
    try:
        _grpc_server = start_grpc_server(port=Config.GRPC_PORT)
        logger.info("gRPC server started on port %s", Config.GRPC_PORT)
    except Exception as e:
        logger.warning("gRPC server failed to start: %s", e)

    logger.info("task_service FastAPI app started")
    yield

    # 关闭 gRPC server
    if _grpc_server is not None:
        try:
            _grpc_server.stop(0)
            logger.info("gRPC server stopped")
        except Exception as e:
            logger.warning("gRPC server stop error: %s", e)

    logger.info("task_service shutting down")


def create_app(config_name='default') -> FastAPI:
    """Create and configure the FastAPI application for task_service."""
    app = FastAPI(
        title="Intelligent Audio Test - Task Service",
        lifespan=lifespan,
    )

    @app.get('/health')
    def health():
        return {
            'status': 'ok',
            'service': 'task_service',
        }

    return app


app = create_app()


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(
        "task_service.app:app",
        host="0.0.0.0",
        port=Config.PORT,
        workers=1,
        log_level="info",
    )
