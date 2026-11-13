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
    CredentialDecryptError, CredentialKeyUnavailable,
    InvalidContextWindow, InvalidProviderConfiguration,
    InvalidRunTransition, ProviderNotFound, RunNotFound, SessionNotFound,
    SkillNotAvailable,
)
from agent_service.infrastructure.sandbox.t2_runtime import probe_t2_runtime
from agent_service.interfaces.api.provider_routes import router as provider_router
from agent_service.interfaces.api.routes import router as agent_router

logger = logging.getLogger(__name__)


def _probe_database() -> tuple:
    """DB 连通探测：SELECT 1（连接池已由 init_db 建好，走 pre_ping 自愈）。

    DB 不可用时 agent_service 无法读写 run / event，health 必须报 503，
    否则 compose 健康门会用一个「活着但什么也做不了」的容器放行。
    """
    try:
        from sqlalchemy import text

        from shared.models.database import get_engine
        engine = get_engine()
        if engine is None:
            return False, '数据库未初始化（DATABASE_URL 未生效）'
        with engine.connect() as conn:
            conn.execute(text('SELECT 1'))
        return True, ''
    except Exception as exc:  # noqa: BLE001 - 健康探测不抛，只回报状态
        logger.warning('health: 数据库探测失败：%s', exc)
        return False, str(exc)


def _probe_redis() -> tuple:
    """Redis 连通探测。

    仅当唤醒后端为 redis 时探测：Redis 只承担 SSE 唤醒（正文仍回表读），
    不可用时退化为轮询，故失败只降级不判死（见 wakeup.RedisRunWakeup）。
    """
    if Config.EVENT_WAKEUP_BACKEND != 'redis':
        return True, '唤醒后端为 local，跳过 Redis 探测'
    try:
        import redis
        client = redis.from_url(Config.REDIS_URL, socket_connect_timeout=1,
                                socket_timeout=1)
        client.ping()
        return True, ''
    except Exception as exc:  # noqa: BLE001
        logger.warning('health: Redis 探测失败（SSE 退化为轮询）：%s', exc)
        return False, str(exc)


def _register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(SessionNotFound)
    async def _session_not_found(_request: Request, _exc: SessionNotFound):
        return JSONResponse(status_code=404, content={'detail': 'not found'})

    @app.exception_handler(RunNotFound)
    async def _run_not_found(_request: Request, _exc: RunNotFound):
        return JSONResponse(status_code=404, content={'detail': 'not found'})

    @app.exception_handler(ProviderNotFound)
    async def _provider_not_found(_request: Request, _exc: ProviderNotFound):
        return JSONResponse(status_code=404, content={'detail': 'not found'})

    @app.exception_handler(InvalidContextWindow)
    async def _invalid_window(_request: Request, exc: InvalidContextWindow):
        return JSONResponse(
            status_code=400,
            content={'detail': str(exc), 'code': 'INVALID_CONTEXT_WINDOW'})

    @app.exception_handler(InvalidProviderConfiguration)
    async def _invalid_provider(_request: Request,
                                exc: InvalidProviderConfiguration):
        return JSONResponse(
            status_code=400,
            content={'detail': str(exc),
                     'code': 'INVALID_PROVIDER_CONFIGURATION'})

    @app.exception_handler(CredentialKeyUnavailable)
    async def _credential_key_unavailable(_request: Request,
                                          _exc: CredentialKeyUnavailable):
        # 不把主密钥相关细节回给调用方
        return JSONResponse(
            status_code=503,
            content={'detail': 'credential store unavailable',
                     'code': 'CREDENTIAL_STORE_UNAVAILABLE'})

    @app.exception_handler(CredentialDecryptError)
    async def _credential_decrypt_error(_request: Request,
                                        _exc: CredentialDecryptError):
        return JSONResponse(
            status_code=500,
            content={'detail': 'credential decrypt failed',
                     'code': 'CREDENTIAL_DECRYPT_FAILED'})

    @app.exception_handler(InvalidRunTransition)
    async def _invalid_transition(_request: Request,
                                  exc: InvalidRunTransition):
        return JSONResponse(
            status_code=409,
            content={'detail': '非法的 Run 状态迁移',
                     'current': exc.current, 'target': exc.target},
        )

    @app.exception_handler(SkillNotAvailable)
    async def _skill_not_available(_request: Request, exc: SkillNotAvailable):
        # 未注册与权限不足统一 400：不区分「存在但无权」，避免泄漏 Skill 清单
        return JSONResponse(status_code=400,
                            content={'detail': 'Skill 不可用'})


def create_app(container=None) -> FastAPI:
    """创建应用。``container`` 仅测试传入；生产为 None 时自建组合根。"""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        Config.validate()
        owns_container = container is None
        if owns_container:
            # INT-2456：三个部署挂载点缺一即启动失败（不静默忽略空目录）。
            Config.validate_mounts()
            from shared.models.database import create_db_session, init_db
            init_db(pool_size=Config.DB_POOL_SIZE)
            from agent_service.wiring import build_container
            app.state.container = build_container(create_db_session)
        else:
            app.state.container = container

        container_obj = app.state.container
        # INT-2529：总开关关闭态不产生任何后台 run —— 恢复投递同样门控在
        # AGENT_ENABLED 之下；网关入口的 require_agent_enabled 仍是唯一入口门，
        # 这里只是同一条开关在「重启自启」这一侧的落实，不新增第二个开关名。
        if not Config.AGENT_ENABLED:
            logger.info(
                'AGENT_ENABLED=false：跳过启动恢复投递（关闭态不产生后台 run）')
        elif Config.RECOVERY_ON_STARTUP:
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
        """健康检查：DB / Redis 连通 + T2 运行时可见性（INT-2456）。

        - DB 不可用 → 503（无法读写 run/event，容器不可用）；
        - Redis 不可用 → 200 + degraded（只影响 SSE 唤醒，已退化为轮询）；
        - ``t2_runtime`` 为可见性结论（available / unavailable），不影响本服务
          存活：T2 执行缺失时由沙箱按 T2_RUNTIME_UNAVAILABLE 明确拒绝。
        """
        db_ok, db_detail = _probe_database()
        redis_ok, redis_detail = _probe_redis()
        t2 = probe_t2_runtime(Config.T2_RUNTIME)
        if not db_ok:
            status = 'error'
        elif not redis_ok:
            status = 'degraded'
        else:
            status = 'ok'
        payload = {
            'status': status,
            'service': Config.SERVICE_NAME,
            'version': Config.PLATFORM_VERSION,
            'llm_mode': 'user_provider',
            'checks': {
                'database': {'status': 'ok' if db_ok else 'error',
                             'detail': db_detail},
                'redis': {'status': 'ok' if redis_ok else 'error',
                          'detail': redis_detail},
            },
            't2_runtime': t2.as_health(),
        }
        return JSONResponse(status_code=200 if db_ok else 503, content=payload)

    app.include_router(agent_router, prefix='/api/v1/agent', tags=['agent'])
    app.include_router(provider_router, prefix='/api/v1/agent',
                       tags=['agent-providers'])
    return app


app = create_app()


if __name__ == '__main__':
    import uvicorn

    logging.basicConfig(level=logging.INFO)
    uvicorn.run('agent_service.app:app', host='0.0.0.0', port=Config.PORT,
                workers=1, log_level='info')
