# -*- coding: utf-8 -*-
"""agent_service 启动入口（FastAPI）。

职责：唯一 Agent Loop 宿主、REST/SSE 端点、重启恢复与 worker 生命周期。
配置项全部来自 agent_service/config（env + agent_defaults.json）。
"""
import logging
import os
import sys
from contextlib import asynccontextmanager
from typing import Optional

current_dir = os.path.dirname(os.path.abspath(__file__))
project_dir = os.path.dirname(current_dir)
if project_dir not in sys.path:
    sys.path.insert(0, project_dir)

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(project_dir, '.env'))
except ImportError:
    logging.getLogger(__name__).debug('python-dotenv 未安装，跳过 .env 加载')

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from agent_service.config.config import Config
from agent_service.domain.exceptions import (
    InvalidRunTransition, RunNotFound, SessionNotFound,
)
from agent_service.interfaces.api.routes import router as agent_router

logger = logging.getLogger(__name__)


def _register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(SessionNotFound)
    async def _session_not_found(_request: Request, _exc: SessionNotFound):
        return JSONResponse(status_code=404, content={'detail': 'not found'})

    @app.exception_handler(RunNotFound)
    async def _run_not_found(_request: Request, _exc: RunNotFound):
        return JSONResponse(status_code=404, content={'detail': 'not found'})

    @app.exception_handler(InvalidRunTransition)
    async def _invalid_transition(_request: Request,
                                  exc: InvalidRunTransition):
        return JSONResponse(
            status_code=409,
            content={'detail': '非法的 Run 状态迁移',
                     'current': exc.current, 'target': exc.target},
        )


def create_app(container=None) -> FastAPI:
    """创建应用。``container`` 仅测试传入；生产为 None 时自建组合根。"""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        Config.validate()
        owns_container = container is None
        if owns_container:
            from shared.models.database import create_db_session, init_db
            init_db(pool_size=Config.DB_POOL_SIZE)
            from agent_service.wiring import build_container
            app.state.container = build_container(create_db_session)
        else:
            app.state.container = container

        container_obj = app.state.container
        if Config.RECOVERY_ON_STARTUP:
            try:
                resumable = container_obj.recovery.recover()
                for run_id in resumable:
                    container_obj.executor.submit(run_id)
                if resumable:
                    logger.info('重启恢复：重新投递 %d 个 run', len(resumable))
            except Exception:  # noqa: BLE001 - 恢复失败不阻断服务启动
                logger.exception('重启恢复失败')
        logger.info('agent_service started on port %s', Config.PORT)
        try:
            yield
        finally:
            logger.info('agent_service shutting down')
            try:
                container_obj.shutdown()
            except Exception:  # noqa: BLE001
                logger.exception('agent_service 收尾失败')

    app = FastAPI(title='Intelligent Audio Test - Agent Service',
                  lifespan=lifespan)
    _register_error_handlers(app)

    @app.get('/health')
    def health():
        return {
            'status': 'ok',
            'service': Config.SERVICE_NAME,
            'version': Config.PLATFORM_VERSION,
            'llm_model': Config.LLM_MODEL,
        }

    app.include_router(agent_router, prefix='/api/v1/agent', tags=['agent'])
    return app


app = create_app()


if __name__ == '__main__':
    import uvicorn

    logging.basicConfig(level=logging.INFO)
    uvicorn.run('agent_service.app:app', host='0.0.0.0', port=Config.PORT,
                workers=1, log_level='info')
