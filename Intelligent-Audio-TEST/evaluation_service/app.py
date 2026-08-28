# -*- coding: utf-8 -*-
"""FastAPI application factory for evaluation_service.

职责：评分计算、多轮聚合、重新评估、Dimension CRUD。
保留原有的 gRPC server 启动、评估服务、Redis 注册等初始化逻辑，
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
    logging.getLogger(__name__).debug("python-dotenv 未安装，跳过 .env 加载")

from fastapi import FastAPI

from shared.models.database import init_db
from shared.utils.service_registry import RedisServiceRegistry
from evaluation_service.config.config import Config

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)

# 将 DatabaseLogHandler 挂到 root logger，使标准 logging.getLogger() 调用也走分流逻辑
from shared.utils.log_handler import get_db_handler
logging.getLogger().addHandler(get_db_handler())

# 注入 LoggingPort 实现（domain 层通过 ABC 代理访问日志）
from shared.infrastructure.logging_adapter import inject as _inject_logging_port
_inject_logging_port()

# 全局引用，防止 GC（gRPC server 需要在 lifespan 之外保持引用）
_grpc_server = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时初始化 DB / 评估服务 / 服务注册 / gRPC server，关闭时清理。"""
    global _grpc_server

    Config.validate()
    init_db(pool_size=20)
    logger.info("数据库连接池已初始化 (pool_size=20)")

    # 初始化评估服务
    from evaluation_service.infrastructure.evaluation_service_host import evaluation_service
    logger.info("评估服务初始化完成")

    # 启动维度配置热更新订阅：监听 DimensionConfigChanged 事件，热加载端点配置（无需重启服务）
    try:
        from shared.utils.redis_pubsub import EventBus, EventChannel, EventType
        EventBus().start_subscriber(
            EventChannel.CONFIG_EVENTS,
            {EventType.DIMENSION_CONFIG_CHANGED: lambda _payload: evaluation_service.reload_endpoint_configs()},
            name='DimensionConfigSub',
        )
        logger.info("维度配置热更新订阅线程已启动")
    except Exception as e:
        logger.warning("维度配置热更新订阅启动失败，降级为重启后加载: %s", e)

    # 服务注册
    registry = RedisServiceRegistry()
    registry.register('evaluation_service', Config.SERVICE_HOST, Config.PORT)

    # 启动 gRPC server
    from evaluation_service.interfaces.grpc.server import start_grpc_server
    try:
        _grpc_server = start_grpc_server(port=Config.GRPC_PORT)
        logger.info("gRPC server started on port %s", Config.GRPC_PORT)
    except Exception as e:
        logger.warning("gRPC server failed to start: %s", e)

    # 启动软删除硬清理守护线程（只清理本服务 owned 表 dimensions/categories/test_result_dimensions）
    from evaluation_service.infrastructure.persistence.soft_delete_cleaner import get_cleaner as get_soft_delete_cleaner
    _soft_delete_cleaner = get_soft_delete_cleaner()
    _soft_delete_cleaner.start()

    logger.info("evaluation_service FastAPI app started")
    yield

    # 停止软删除清理线程
    _soft_delete_cleaner.stop()

    # 关闭 gRPC server
    if _grpc_server is not None:
        try:
            _grpc_server.stop(0)
            logger.info("gRPC server stopped")
        except Exception as e:
            logger.warning("gRPC server stop error: %s", e)

    logger.info("evaluation_service shutting down")


def create_app(config_name='default') -> FastAPI:
    """Create and configure the FastAPI application for evaluation_service."""
    app = FastAPI(
        title="Intelligent Audio Test - Evaluation Service",
        lifespan=lifespan,
    )

    @app.get('/health')
    def health():
        return {
            'status': 'ok',
            'service': 'evaluation_service',
        }

    from evaluation_service.interfaces.api.routes import router as eval_router
    app.include_router(eval_router)

    return app


app = create_app()


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(
        "evaluation_service.app:app",
        host="0.0.0.0",
        port=Config.PORT,
        workers=1,
        log_level="info",
    )
