# -*- coding: utf-8 -*-
"""Agent 总开关（INT-2456 / 方案 07 §13-1）。

``AGENT_ENABLED`` 默认关闭。关闭态下 Agent 运行底座（sessions / runs /
events / approvals / skills）与用户模型供应商接口一律返回 503 +
``code=AGENT_DISABLED``，**不转发**到 agent_service；任务、用例、报告等人工
流程不经过这些路由，完全不受影响。

为什么执行点只在网关：agent_service 不发布宿主端口（compose 无 ports 映射），
只消费网关转发的身份头；外部入口只有网关，开关在这里判一次即可，不在
agent_service 另写一套开关口径（避免两处配置漂移后「网关开了、服务关了」）。
"""
from fastapi import HTTPException

from api_gateway.config.config import Config

#: 关闭态错误码；前端按 code 判「功能未启用」，不解析中文文案。
AGENT_DISABLED_CODE = 'AGENT_DISABLED'
AGENT_DISABLED_MESSAGE = 'Agent 未启用'


def require_agent_enabled() -> None:
    """FastAPI 依赖：总开关关闭即 503，上游零调用。

    挂在 APIRouter(dependencies=[...]) 上，对已注册路由一次性生效；鉴权仍由
    AuthMiddleware 先做（无 token 先 401），不会因为开关关闭而放宽认证。
    """
    if not Config.agent_enabled():
        raise HTTPException(
            status_code=503,
            detail={
                'code': AGENT_DISABLED_CODE,
                'message': AGENT_DISABLED_MESSAGE,
            },
        )
