"""
API Test Service 服务启动入口 —— FastAPI + DDD 版
职责：API 测试执行、并发控制、健康监控
不需要物理设备，可水平扩展
"""
import os
import sys
import logging
from contextlib import asynccontextmanager

# 确保能找到 shared 包
current_dir = os.path.dirname(os.path.abspath(__file__))
project_dir = os.path.dirname(current_dir)
sys.path.insert(0, project_dir)

# 加载 .env 环境变量
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(project_dir, '.env'))
except ImportError:
    pass

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from shared.models.database import init_db
from shared.utils.service_registry import RedisServiceRegistry
from api_test_service.core.api_test_service import api_test_service
from api_test_service.config.config import Config

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)

_grpc_server = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时初始化，关闭时清理

    DB session 由原生 SQLAlchemy scoped_session 管理，
    gRPC 线程由 DbScopeInterceptor 自动清理，后台线程池在线程入口/出口手动清理。
    """
    global _grpc_server
    Config.validate()
    init_db(pool_size=5)
    api_test_service.init_app()  # 不再传 app

    # 服务注册
    registry = RedisServiceRegistry()
    registry.register('api_test_service',
                      Config.SERVICE_HOST, Config.PORT,
                      grpc_port=Config.GRPC_PORT)

    # 启动 gRPC server
    from api_test_service.grpc.server import start_grpc_server
    try:
        _grpc_server = start_grpc_server(port=Config.GRPC_PORT)
        logger.info("gRPC server started on port %s", Config.GRPC_PORT)
    except Exception as e:
        logger.warning("gRPC server failed to start: %s", e)

    logger.info("api_test_service FastAPI app started on port %s", Config.PORT)
    yield
    logger.info("api_test_service shutting down")
    if _grpc_server:
        _grpc_server.stop(0)


def create_app(config_name='default') -> FastAPI:
    """创建并配置 FastAPI 应用。"""
    app = FastAPI(
        title="Intelligent Audio Test - API Test Service",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get('/health')
    @app.get('/internal/health')
    def health():
        return {'status': 'ok', 'service': 'api_test_service'}

    return app


app = create_app()


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(
        "api_test_service.app:app",
        host="0.0.0.0",
        port=Config.PORT,
        workers=1,
        log_level="info",
    )
