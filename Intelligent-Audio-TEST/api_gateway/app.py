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
    pass

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
    init_db(pool_size=5)
    app.state.audio_storage_path = Config.AUDIO_STORAGE_PATH

    # 初始化 WebSocket 日志推送回调
    # 使用 Socket.IO 服务端（兼容前端 socket.io-client），替代原生 WS
    from api_gateway.websocket.socketio_server import ws_manager, sio
    from shared.utils.log_handler import set_ws_broadcast_callback, get_db_handler
    set_ws_broadcast_callback(ws_manager.broadcast_log_sync)
    from shared.utils.log_handler import set_socketio
    set_socketio(ws_manager)

    # 将 DatabaseLogHandler 挂到 root logger，使标准 logging.getLogger() 调用也走分流逻辑
    root_logger = logging.getLogger()
    root_logger.addHandler(get_db_handler())
    root_logger.setLevel(logging.INFO)

    # 保存主线程事件循环，供后台线程的 broadcast_log_sync 使用
    import asyncio as _asyncio
    try:
        ws_manager._main_loop = _asyncio.get_running_loop()
    except RuntimeError:
        pass

    # 服务注册
    registry = RedisServiceRegistry()
    registry.register('api_gateway', Config.SERVICE_HOST, Config.PORT)

    # 启动 Redis PubSub 订阅线程：转发 task_service / e2e_test_service 等子服务发来的日志和进度
    _start_redis_subscriber(sio, ws_manager)

    # 软删除硬清理已下沉至各微服务（各自只清理 owned 表），api_gateway 不再负责
    logger.info("API Gateway (FastAPI + DDD) started on port %s", Config.PORT)
    yield
    logger.info("API Gateway shutting down")


def _start_redis_subscriber(sio, ws_manager):
    """启动后台线程订阅 Redis task_logs / task_progress 频道，转发给前端 Socket.IO"""
    import threading
    from shared.utils.redis_pubsub import RedisPubSub
    from shared.infrastructure.config import BaseConfig

    def _handle_message(channel, data):
        """处理一条 Redis 消息，转发到前端 Socket.IO"""
        import asyncio
        loop = ws_manager._main_loop
        if not (loop and loop.is_running()):
            return

        if channel == 'task_logs':
            log_payload = data.get('log_payload', {})
            task_id = data.get('task_id')
            if task_id:
                asyncio.run_coroutine_threadsafe(
                    sio.emit('task_log', {'taskId': str(task_id), 'log': log_payload}, namespace='/ws/logs'),
                    loop
                )

        elif channel == 'task_progress':
            event_name = data.get('event', 'task_progress')
            event_data = data.get('data', {})
            asyncio.run_coroutine_threadsafe(
                sio.emit(event_name, event_data, namespace='/'),
                loop
            )

    def _subscriber_loop():
        print(f"[RedisSubscriber] starting, subscribing to task_logs + task_progress on {BaseConfig.REDIS_URL}", flush=True)
        RedisPubSub().subscribe(['task_logs', 'task_progress'], _handle_message)

    t = threading.Thread(target=_subscriber_loop, daemon=True)
    t.start()


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
    from api_gateway.routes.api_bp import router as api_router
    from api_gateway.routes.execution_bp import router as execution_router
    from api_gateway.routes.audio_bp import router as audio_router
    from api_gateway.routes.evaluation_bp import router as evaluation_router
    from api_gateway.routes.log_bp import router as log_router
    from api_gateway.routes.spl_bp import router as spl_router
    from api_gateway.routes.algorithm_bp import router as algorithm_router
    from api_gateway.routes.tag_bp import router as tag_router
    from api_gateway.routes.home_bp import router as home_router
    from api_gateway.routes.sse_bp import router as sse_router

    app.include_router(auth_router, prefix='/api/v1/auth', tags=['auth'])
    app.include_router(testcase_router, prefix='/api/v1/testcases', tags=['testcases'])
    app.include_router(group_router, prefix='/api/v1/groups', tags=['groups'])
    app.include_router(device_router, prefix='/api/v1/test-devices', tags=['devices'])
    app.include_router(playback_router, prefix='/api/v1/playback-devices', tags=['playback'])
    app.include_router(report_router, prefix='/api/v1/reports', tags=['reports'])
    app.include_router(task_router, prefix='/api/v1/tasks', tags=['tasks'])
    app.include_router(api_router, prefix='/api/v1/apis', tags=['apis'])
    app.include_router(execution_router, prefix='/api/v1/execution', tags=['execution'])
    app.include_router(audio_router, prefix='/api/v1/audios', tags=['audios'])
    app.include_router(evaluation_router, prefix='/api/v1/evaluation', tags=['evaluation'])
    app.include_router(log_router, prefix='/api/v1/logs', tags=['logs'])
    app.include_router(spl_router, prefix='/api/v1/spl', tags=['spl'])
    app.include_router(algorithm_router, prefix='/api/v1/algorithm', tags=['algorithm'])
    app.include_router(tag_router, prefix='/api/v1/tags', tags=['tags'])
    app.include_router(home_router, prefix='/api/v1/home', tags=['home'])
    app.include_router(sse_router, prefix='/api/v1/sse', tags=['sse'])

    # 挂载 Socket.IO ASGI 子应用（前端 socket.io-client 连 /socket.io/）
    from api_gateway.websocket.socketio_server import sio_app
    app.mount('/socket.io', sio_app)

    @app.get('/health')
    def health():
        return {'status': 'ok', 'service': 'api_gateway'}

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
