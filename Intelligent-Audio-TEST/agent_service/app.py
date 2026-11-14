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
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from agent_service.application.approval_expiry import ApprovalExpiryScanner
from agent_service.config.config import Config
from agent_service.domain.exceptions import (
    ApprovalConflict, ApprovalConfirmationRequired, ApprovalExpired,
    ApprovalNotFound,
    CredentialDecryptError, CredentialKeyUnavailable,
    InvalidContextWindow, InvalidProviderConfiguration,
    InvalidRunTransition, ProviderNotFound, RunNotFound, SessionNotFound,
    SkillGateFailed, SkillImportInvalid, SkillInjectionDetected,
    SkillNameConflict, SkillNotAvailable, SkillNotFound,
    SkillPackageTooLarge, SkillPermissionEscalation, SkillReviewForbidden,
    SkillSelfReviewForbidden, SkillServiceError, SkillStatusInvalid,
)
from agent_service.interfaces.api.upload_limit import (
    SkillImportUploadLimitMiddleware,
)
from agent_service.infrastructure.sandbox.t2_runtime import probe_t2_runtime
from agent_service.interfaces.api.provider_routes import router as provider_router
from agent_service.interfaces.api.memory_routes import router as memory_router
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
    @app.exception_handler(RequestValidationError)
    async def _request_validation_error(_request: Request,
                                        exc: RequestValidationError):
        # INT-2509：FastAPI 默认处理器把整份请求体放进 detail[].input，
        # 供应商接口缺字段时会把明文 api_key 回显给调用方、再由网关抄进
        # 服务日志（违反落地方案 §6.4-2 / §13-4）。这里只回字段定位信息，
        # 任何字段值（input / ctx）一律不回显。
        return JSONResponse(
            status_code=422,
            content={'detail': [
                {
                    'type': str(error.get('type', '')),
                    'loc': list(error.get('loc', ())),
                    'msg': str(error.get('msg', '')),
                }
                for error in exc.errors()
            ]},
        )

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

    # ---- INT-2549 自定义 Skill 域异常（错误码枚举化，不散落字符串）----
    def _skill_error(status_code: int):
        async def _handler(_request: Request, exc: SkillServiceError):
            return JSONResponse(status_code=status_code, content={
                'detail': str(exc) or 'Skill 操作失败',
                'code': exc.code,
                'issues': [
                    {'code': issue.code.value,
                     'severity': issue.severity.value,
                     'skill': issue.skill,
                     'field': getattr(issue, 'field', ''),
                     'message': issue.message}
                    for issue in getattr(exc, 'issues', ())
                ],
            })
        return _handler

    @app.exception_handler(SkillNotFound)
    async def _skill_not_found(_request: Request, exc: SkillNotFound):
        # 不存在 / 非本人 / 无写入口统一 404，不泄漏存在性
        return JSONResponse(status_code=404, content={
            'detail': 'Skill 不存在', 'code': exc.code, 'issues': []})

    app.add_exception_handler(SkillNameConflict, _skill_error(409))
    app.add_exception_handler(SkillPermissionEscalation, _skill_error(403))
    # INT-2551：审核流是权限边界 —— 非管理员 403、自审自批 403，
    # 状态机不允许的迁移 409（与「已处理 / 已撤回」区分不了，都是冲突）。
    app.add_exception_handler(SkillReviewForbidden, _skill_error(403))
    app.add_exception_handler(SkillSelfReviewForbidden, _skill_error(403))
    app.add_exception_handler(SkillStatusInvalid, _skill_error(409))
    app.add_exception_handler(SkillImportInvalid, _skill_error(400))
    # 上传体积超限在读入内存 / 解析 multipart 之前就拒绝（413）
    app.add_exception_handler(SkillPackageTooLarge, _skill_error(413))
    app.add_exception_handler(SkillInjectionDetected, _skill_error(400))
    app.add_exception_handler(SkillGateFailed, _skill_error(409))
    app.add_exception_handler(SkillServiceError, _skill_error(400))

    @app.exception_handler(ApprovalNotFound)
    async def _approval_not_found(_request: Request, _exc: ApprovalNotFound):
        # 不存在 / 非本人 run 的审批单统一 404（不泄漏存在性）
        return JSONResponse(status_code=404, content={'detail': 'not found'})

    @app.exception_handler(ApprovalConflict)
    async def _approval_conflict(_request: Request, exc: ApprovalConflict):
        return JSONResponse(
            status_code=409,
            content={'detail': '审批单已被处理或 run 已收口',
                     'code': exc.code})

    @app.exception_handler(ApprovalExpired)
    async def _approval_expired(_request: Request, exc: ApprovalExpired):
        return JSONResponse(
            status_code=409,
            content={'detail': '审批单已过期，写操作未执行',
                     'code': exc.code})

    @app.exception_handler(ApprovalConfirmationRequired)
    async def _approval_confirmation_required(
            _request: Request, exc: ApprovalConfirmationRequired):
        # 破坏性操作二次确认（INT-2467）：决策未落库，重发时带 confirm=true
        return JSONResponse(
            status_code=400,
            content={'detail': '破坏性操作需要二次确认：请带 confirm=true 重新批准',
                     'code': exc.code, 'tool': exc.tool})


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
        # INT-2466：启动时先把到点的待审批单判过期（幂等）；审批过期与
        # 「是否恢复投递」无关，关闭态同样收敛，避免列表长期停在 PENDING。
        approval_service = getattr(container_obj, 'approval_service', None)
        expiry_scanner = None
        if approval_service is not None:
            try:
                expired_runs = approval_service.expire_due()
                if expired_runs:
                    logger.info('启动过期扫描：%d 个 run 的待审批单转 EXPIRED',
                                len(expired_runs))
            except Exception:  # noqa: BLE001 - 过期扫描失败不阻断启动
                logger.exception('审批过期扫描失败')
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
        # INT-2466：运行期过期扫描 —— TTL 到点且无人决策时，结算后提交 run，
        # 让 Loop 把 APPROVAL_EXPIRED 回灌模型并继续收口（不依赖重启）。
        # 与恢复投递同一条开关：关闭态不产生任何后台 run。
        if approval_service is not None and Config.AGENT_ENABLED:
            expiry_scanner = ApprovalExpiryScanner(
                approvals=approval_service,
                wake_run=container_obj.executor.submit,
                interval_seconds=Config.APPROVAL_EXPIRY_SCAN_INTERVAL_SECONDS)
            expiry_scanner.start()
        logger.info('agent_service started on port %s', Config.PORT)
        try:
            yield
        finally:
            logger.info('agent_service shutting down')
            if expiry_scanner is not None:
                expiry_scanner.stop()
            try:
                container_obj.shutdown()
            except Exception:  # noqa: BLE001
                logger.exception('agent_service 收尾失败')

    app = FastAPI(title='Intelligent Audio Test - Agent Service',
                  lifespan=lifespan)
    _register_error_handlers(app)
    # INT-2549 返工 P3：zip 导入在读入内存 / 解析 multipart 之前按
    # Content-Length 拒绝超大包（网关侧同一口径，见 agent_skill_bp）。
    app.add_middleware(SkillImportUploadLimitMiddleware,
                       max_bytes=Config.SKILL_MAX_UPLOAD_BYTES)

    @app.get('/health')
    def health(request: Request):
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
        # INT-2506：Skill 装载摘要（计数 + 原因码）。错挂载 / 空目录导致 Skill
        # 层整体消失时，这里不再与正常态无差别。
        registry = getattr(
            getattr(request.app.state, 'container', None),
            'skill_registry', None)
        if registry is not None:
            payload['skills'] = {
                'loaded': len(registry.skills),
                'issues': len(registry.issues),
                'issue_codes': sorted({i.code.value for i in registry.issues}),
            }
        return JSONResponse(status_code=200 if db_ok else 503, content=payload)

    app.include_router(agent_router, prefix='/api/v1/agent', tags=['agent'])
    app.include_router(provider_router, prefix='/api/v1/agent',
                       tags=['agent-providers'])
    app.include_router(memory_router, prefix='/api/v1/agent',
                       tags=['agent-memory'])
    return app


app = create_app()


if __name__ == '__main__':
    import uvicorn

    logging.basicConfig(level=logging.INFO)
    uvicorn.run('agent_service.app:app', host='0.0.0.0', port=Config.PORT,
                workers=1, log_level='info')
