"""
API Gateway 服务启动入口 —— FastAPI + DDD 版
职责：HTTP 路由、WebSocket 日志推送、SSE 事件流、服务注册
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
from fastapi.responses import JSONResponse

from shared.models.database import init_db
from shared.utils.service_registry import RedisServiceRegistry
from api_gateway.config.config import Config

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时初始化，关闭时清理"""
    Config.validate()
    init_db(pool_size=3)
    app.state.audio_storage_path = Config.AUDIO_STORAGE_PATH

    # 初始化 Socket.IO 管理器（UC-1001：日志统一经 EventBus 转发，
    # 不再注入 log_handler 直发回调 set_ws_broadcast_callback）
    from api_gateway.websocket.socketio_server import ws_manager
    from shared.utils.log_handler import set_socketio, get_db_handler
    set_socketio(ws_manager)

    # 将 DatabaseLogHandler 挂到 root logger，使标准 logging.getLogger() 调用也走分流逻辑
    root_logger = logging.getLogger()
    root_logger.addHandler(get_db_handler())
    root_logger.setLevel(logging.INFO)

    # 保存主线程事件循环，供后台线程的事件转发使用
    import asyncio as _asyncio
    try:
        ws_manager._main_loop = _asyncio.get_running_loop()
    except RuntimeError as e:
        logger.debug("获取运行中事件循环失败: %s", e)

    # 服务注册
    registry = RedisServiceRegistry()
    registry.register('api_gateway', Config.SERVICE_HOST, Config.PORT)

    # 启动 EventBus 五通道转发线程：订阅 TASK/CASE/DEVICE/REPORT/CONFIG 事件，
    # 把面向前端的实时事件（task_log/task_progress/import_progress/报告生成）转发给 Socket.IO
    from api_gateway.infrastructure.event_bus_forwarder import start_event_forwarder
    start_event_forwarder(ws_manager)

    # 软删除硬清理已下沉至各微服务（各自只清理 owned 表），api_gateway 不再负责
    logger.info("API Gateway (FastAPI + DDD) started on port %s", Config.PORT)
    yield
    logger.info("API Gateway shutting down")


def create_app(config_name='default') -> FastAPI:
    app = FastAPI(
        title="Intelligent Audio Test - API Gateway (DDD)",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 注册 request_adapter 中间件（将 FastAPI 请求注入 ContextVar）
    from api_gateway.middleware import RequestAdapterMiddleware, AuthMiddleware
    from shared.utils.naming_middleware import NamingAliasMiddleware
    app.add_middleware(RequestAdapterMiddleware)
    app.add_middleware(AuthMiddleware, auth_mode=Config.AUTH_MODE)
    app.add_middleware(NamingAliasMiddleware)

    # 注册 API 路由
    from api_gateway.routes.auth_bp import router as auth_router
    from api_gateway.routes.testcase_bp import router as testcase_router
    from api_gateway.routes.group_bp import router as group_router
    from api_gateway.routes.device_bp import router as device_router
    from api_gateway.routes.playback_bp import router as playback_router
    from api_gateway.routes.report_bp import router as report_router
    from api_gateway.routes.task_bp import router as task_router
    from api_gateway.routes.published_task_bp import router as published_task_router
    from api_gateway.routes.api_bp import router as api_router
    from api_gateway.routes.execution_bp import router as execution_router
    from api_gateway.routes.audio_bp import router as audio_router
    from api_gateway.routes.evaluation_bp import router as evaluation_router
    from api_gateway.routes.log_bp import router as log_router
    from api_gateway.routes.spl_bp import router as spl_router
    from api_gateway.routes.digital_spl_bp import router as digital_spl_router
    from api_gateway.routes.algorithm_bp import router as algorithm_router
    from api_gateway.routes.tag_bp import router as tag_router
    from api_gateway.routes.home_bp import router as home_router
    from api_gateway.routes.sse_bp import router as sse_router
    from api_gateway.routes.data_transfer_bp import router as data_transfer_router
    from api_gateway.routes.benchmark_bp import router as benchmark_router
    from api_gateway.routes.user_bp import router as user_router
    from api_gateway.routes.role_bp import router as role_router
    from api_gateway.routes.oauth_bp import router as oauth_router

    app.include_router(auth_router, prefix='/api/v1/auth', tags=['auth'])
    app.include_router(user_router, prefix='/api/v1/auth', tags=['auth-management'])
    app.include_router(role_router, prefix='/api/v1/auth', tags=['auth-management'])
    app.include_router(oauth_router, prefix='/api/v1/auth', tags=['oauth-management'])
    app.include_router(testcase_router, prefix='/api/v1/testcases', tags=['testcases'])
    app.include_router(group_router, prefix='/api/v1/groups', tags=['groups'])
    app.include_router(device_router, prefix='/api/v1/test-devices', tags=['devices'])
    app.include_router(playback_router, prefix='/api/v1/playback-devices', tags=['playback'])
    app.include_router(report_router, prefix='/api/v1/reports', tags=['reports'])
    app.include_router(task_router, prefix='/api/v1/tasks', tags=['tasks'])
    app.include_router(published_task_router, prefix='/api/v1/published-tasks', tags=['published-tasks'])
    app.include_router(api_router, prefix='/api/v1/apis', tags=['apis'])
    app.include_router(execution_router, prefix='/api/v1/execution', tags=['execution'])
    app.include_router(audio_router, prefix='/api/v1/audios', tags=['audios'])
    app.include_router(evaluation_router, prefix='/api/v1/evaluation', tags=['evaluation'])
    app.include_router(log_router, prefix='/api/v1/logs', tags=['logs'])
    app.include_router(spl_router, prefix='/api/v1/spl', tags=['spl'])
    app.include_router(digital_spl_router, prefix='/api/v1/digital-spl', tags=['digital-spl'])
    app.include_router(algorithm_router, prefix='/api/v1/algorithm', tags=['algorithm'])
    app.include_router(tag_router, prefix='/api/v1/tags', tags=['tags'])
    app.include_router(home_router, prefix='/api/v1/home', tags=['home'])
    app.include_router(sse_router, prefix='/api/v1/sse', tags=['sse'])
    app.include_router(data_transfer_router, prefix='/api/v1/data-transfer', tags=['data-transfer'])
    app.include_router(benchmark_router, prefix='/api/v1/benchmarks', tags=['benchmarks'])

    # 挂载 Socket.IO ASGI 子应用（前端 socket.io-client 连 /socket.io/）
    from api_gateway.websocket.socketio_server import sio_app
    app.mount('/socket.io', sio_app)

    @app.get('/health')
    def health():
        # PLATFORM_VERSION 标记：tests/api 健康检查据此区分 V9.7.31 与同端口
        # 的 V9.7.10 单体版，避免跨版本误连产生假失败
        return {'status': 'ok', 'service': 'api_gateway',
                'version': Config.PLATFORM_VERSION}

    return app


app = create_app()


if __name__ == '__main__':
    import uvicorn
    logging.basicConfig(level=logging.INFO)
    uvicorn.run(
        "api_gateway.app:app",
        host="0.0.0.0",
        port=Config.PORT,
        workers=1,
        log_level="info",
    )
