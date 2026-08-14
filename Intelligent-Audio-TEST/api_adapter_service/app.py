# -*- coding: utf-8 -*-
"""FastAPI application factory for api_adapter_service."""

import os
import sys
import threading
from contextlib import asynccontextmanager

current_dir = os.path.dirname(os.path.abspath(__file__))
project_dir = os.path.dirname(current_dir)
sys.path.insert(0, project_dir)

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(project_dir, '.env'))
except ImportError:
    import logging
    logging.getLogger(__name__).debug("python-dotenv 未安装，跳过 .env 加载")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api_adapter_service.services.session_store import session_store
from api_adapter_service.utils.config import config
from api_adapter_service.utils.logger import logger


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时初始化，关闭时清理"""
    # 后台线程：定期清理过期 session
    import time

    def _cleanup_loop():
        while True:
            time.sleep(120)
            try:
                cleaned = session_store.cleanup_expired()
                if cleaned:
                    logger.info(f'Cleaned up {cleaned} expired sessions')
            except Exception as e:
                logger.error(f'Session cleanup error: {e}')

    cleanup_thread = threading.Thread(target=_cleanup_loop, daemon=True)
    cleanup_thread.start()

    logger.info('api_adapter_service FastAPI app started')
    yield
    logger.info('api_adapter_service shutting down')


def create_app(config_name='default') -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Intelligent Audio Test - API Adapter Service",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 注册路由
    from api_adapter_service.routes.api import router as api_router
    app.include_router(api_router, tags=['adapter'])

    @app.get('/health')
    def health():
        from api_adapter_service.services.task_manager import task_manager
        return {
            'status': 'healthy',
            'service': 'api_adapter_service',
            'dialog_sessions': session_store.get_session_count(),
            'total_tasks': task_manager.get_task_count(),
            'supported_modes': ['streaming', 'dialog'],
        }

    return app


app = create_app()


if __name__ == '__main__':
    import uvicorn
    port = int(os.environ.get('ADAPTER_SERVICE_HTTP_PORT', '5008'))
    uvicorn.run(
        "api_adapter_service.app:app",
        host="0.0.0.0",
        port=port,
        workers=1,
        log_level="info",
    )
