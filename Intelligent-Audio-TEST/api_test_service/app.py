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
    logging.getLogger(__name__).debug("python-dotenv 未安装，跳过 .env 加载")

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

# 将 DatabaseLogHandler 挂到 root logger，使标准 logging.getLogger() 调用也走分流逻辑
from shared.utils.log_handler import get_db_handler
logging.getLogger().addHandler(get_db_handler())

_grpc_server = None

# 多副本注册地址覆盖键：部署侧显式指定本副本对外可达地址时使用
_ADVERTISE_HOST_ENV = 'API_TEST_ADVERTISE_HOST'


def _self_advertise_host():
    """本实例在服务注册表中的对外地址：环境变量覆盖 > 本机解析 > SERVICE_HOST 兜底

    多副本下 host 必须逐实例可直达（亲和路由按 host:grpc_port 精确寻址），
    容器内解析自身 hostname 得到独立 IP；解析失败回退 SERVICE_HOST 保持旧行为。
    """
    import os
    import socket
    override = os.environ.get(_ADVERTISE_HOST_ENV)
    if override:
        return override
    try:
        return socket.gethostbyname(socket.gethostname())
    except Exception as e:
        logger.warning("解析本机注册地址失败，回退 SERVICE_HOST: %s", e)
        return Config.SERVICE_HOST


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

    # 服务注册。多副本（--scale / deploy.replicas）下每个副本必须以可直达的
    # 唯一地址在册——会话亲和路由（§5.2）按注册表的 host:grpc_port 精确寻址
    # 持有实例；SERVICE_HOST 形如服务名（DNS 负载均衡）时双副本注册出相同
    # host，亲和路由退化为轮询。故缺省解析本机地址，部署侧可用环境变量覆盖。
    registry = RedisServiceRegistry()
    registry.register('api_test_service',
                      _self_advertise_host(), Config.PORT,
                      grpc_port=Config.GRPC_PORT)

    # 启动 gRPC server
    from api_test_service.interfaces.grpc.server import start_grpc_server
    try:
        _grpc_server = start_grpc_server(port=Config.GRPC_PORT)
        logger.info("gRPC server started on port %s", Config.GRPC_PORT)
    except Exception as e:
        logger.warning("gRPC server failed to start: %s", e)

    # 启动软删除硬清理守护线程（只清理本服务 owned 表 apis）
    from api_test_service.infrastructure.persistence.soft_delete_cleaner import get_cleaner as get_soft_delete_cleaner
    _soft_delete_cleaner = get_soft_delete_cleaner()
    _soft_delete_cleaner.start()

    logger.info("api_test_service FastAPI app started on port %s", Config.PORT)
    yield
    logger.info("api_test_service shutting down")
    _soft_delete_cleaner.stop()
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
