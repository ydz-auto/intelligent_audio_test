# -*- coding: utf-8 -*-
"""Agent 总开关 + 灰度白名单（INT-2456 / INT-2478 / 方案 07 §13-1）。

``AGENT_ENABLED`` 默认关闭，是**唯一总闸**。关闭态下 Agent 运行底座
（sessions / runs / events / approvals / skills）与用户模型供应商接口一律
返回 503 + ``code=AGENT_DISABLED``，**不转发**到 agent_service；任务、用例、
报告等人工流程不经过这些路由，完全不受影响。

总闸开启后还可以按租户 / 用户灰度（``AGENT_GRAY_TENANTS`` /
``AGENT_GRAY_USERS``，判定逻辑在 ``shared/agent_access.py``）：配置了白名单
时只有命中者可用，未命中与总闸关闭**表现完全一致**（同一机器码、同一状态
码、不转发上游、不产生后台 run）；两个白名单都不配 = 全员放行，保证现役
``AGENT_ENABLED=true`` 的部署不会因为缺灰度配置整体关闭。

为什么执行点只在网关：agent_service 不发布宿主端口（compose 无 ports 映射），
只消费网关转发的身份头；外部入口只有网关，开关在这里判一次即可，不在
agent_service 另写一套开关口径（避免两处配置漂移后「网关开了、服务关了」）。
"""
import logging

from fastapi import HTTPException, Request

from api_gateway.config.config import Config
from shared.agent_access import AgentAccessDecision, evaluate_agent_access

logger = logging.getLogger(__name__)

#: 关闭态错误码；前端按 code 判「功能未启用」，不解析中文文案。
#: 灰度未命中复用同一码，不新增第二个码（否则前端要写两套分支）。
AGENT_DISABLED_CODE = 'AGENT_DISABLED'
AGENT_DISABLED_MESSAGE = 'Agent 未启用'


def _agent_access_decision(request: Request) -> AgentAccessDecision:
    return evaluate_agent_access(
        master_enabled=Config.agent_enabled(),
        tenant_id=Config.AGENT_DEFAULT_TENANT_ID,
        user_id=getattr(request.state, 'user_id', None),
        gray_tenants=Config.agent_gray_tenants(),
        gray_users=Config.agent_gray_users(),
    )


def require_agent_enabled(request: Request) -> None:
    """FastAPI 依赖：总闸关闭或灰度未命中即 503，上游零调用。

    挂在 APIRouter(dependencies=[...]) 上，对已注册路由一次性生效；鉴权仍由
    AuthMiddleware 先做（无 token 先 401），不会因为开关关闭而放宽认证。

    灰度未命中只记一条不带用户身份的 debug 日志：拒绝原因不区分「总闸关」
    与「不在灰度」，响应体不泄漏白名单是否存在（避免被用来探测灰度名单）。
    """
    decision = _agent_access_decision(request)
    if decision.allowed:
        return
    if decision is AgentAccessDecision.NOT_IN_GRAY:
        logger.debug('Agent 灰度未命中，拒绝访问 %s', request.url.path)
    else:
        logger.debug('Agent 总闸关闭，拒绝访问 %s', request.url.path)
    raise HTTPException(
        status_code=503,
        detail={
            'code': AGENT_DISABLED_CODE,
            'message': AGENT_DISABLED_MESSAGE,
        },
    )
