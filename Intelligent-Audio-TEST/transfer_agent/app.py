# -*- coding: utf-8 -*-
"""FastAPI application factory for transfer_agent.

职责：跨区传输链路的打包、分片、签名、续传、校验（T-A / T-B 双实例形态）。
启动时初始化 DB / 服务注册 / gRPC server / TTL 过期清理守护线程。
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
from transfer_agent.config.config import Config

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)

from shared.utils.log_handler import get_db_handler
logging.getLogger().addHandler(get_db_handler())

# 全局引用，防止 GC（gRPC server / 清理线程需在 lifespan 之外保持引用）
_grpc_server = None
_sweeper = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时初始化 DB / 服务注册 / gRPC server / 过期清理，关闭时清理。"""
    global _grpc_server, _sweeper

    Config.validate()
    init_db(pool_size=5)
    logger.info("数据库连接池已初始化 (pool_size=5)")

    # 服务注册（Redis 不可用时自动降级本地模式，不阻塞启动）
    registry = RedisServiceRegistry()
    registry.register(Config.SERVICE_NAME, Config.SERVICE_HOST, Config.PORT,
                      grpc_port=Config.GRPC_PORT)

    # 启动 gRPC server
    from transfer_agent.interfaces.grpc.server import start_grpc_server
    try:
        _grpc_server = start_grpc_server(port=Config.GRPC_PORT)
        logger.info("gRPC server started on port %s", Config.GRPC_PORT)
    except Exception as e:
        logger.warning("gRPC server failed to start: %s", e)

    # TTL 过期清理守护线程（中转暂存定时扫描）
    from transfer_agent.application.handlers.transfer_handlers import TransferCommandHandler
    from transfer_agent.application.services.expiry_cleanup_service import ExpiryCleanupService
    _sweeper = ExpiryCleanupService(
        TransferCommandHandler(),
        interval_seconds=Config.TRANSFER_SWEEP_INTERVAL_SECONDS,
    )
    _sweeper.start()

    logger.info("transfer_agent FastAPI app started (zone=%s)", Config.TRANSFER_ZONE)
    yield

    _sweeper.stop()

    if _grpc_server is not None:
        try:
            _grpc_server.stop(0)
            logger.info("gRPC server stopped")
        except Exception as e:
            logger.warning("gRPC server stop error: %s", e)

    logger.info("transfer_agent shutting down")


def create_app(config_name='default') -> FastAPI:
    """Create and configure the FastAPI application for transfer_agent."""
    app = FastAPI(
        title="Intelligent Audio Test - Transfer Agent",
        lifespan=lifespan,
    )

    @app.get('/health')
    def health():
        return {
            'status': 'ok',
            'service': 'transfer_agent',
            'zone': Config.TRANSFER_ZONE,
        }

    # 挂载跨区收包路由（/internal/transfer/*）
    from transfer_agent.interfaces.api.routes import router as transfer_router
    app.include_router(transfer_router)

    return app


app = create_app()


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(
        "transfer_agent.app:app",
        host="0.0.0.0",
        port=Config.PORT,
        workers=1,
        log_level="info",
    )
