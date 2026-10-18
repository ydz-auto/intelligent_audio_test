# -*- coding: utf-8 -*-
"""系统健康汇总应用服务（INT-766/INT-787）。

GET /api/v1/system/health 契约：api_gateway 统一信封 {success, code, message,
data}；data.gateway 复用根路径 /health 返回值（status/service/version/
database），data.auth 探测 auth_service /health（HTTP 5009，勿混 5001
task_service）。

auth 探测降级语义（INT-766 契约审核必须项②）：auth_service 探测失败
（连接拒绝/超时/非 200/非 JSON）不得拖垮整卡 —— 返回 200 信封 + auth
{status:'error', service:'auth_service'}（前端映射「异常」徽章），仅网关
自身不可用才整卡失败。读侧，无副作用。
"""
import logging

import httpx

from api_gateway.config.config import Config
from api_gateway.utils.response import success_response
from shared.config.service_ports import AUTH_SERVICE_HTTP_PORT
from shared.constants.database import database_name_of

logger = logging.getLogger(__name__)

# auth 探测超时（秒）：短超时保证端点不被下游拖垮（契约审核必须项②）
AUTH_PROBE_TIMEOUT_SECONDS = 2


class SystemHealthService:
    """系统健康汇总读侧服务。"""

    @staticmethod
    def _gateway_health() -> dict:
        """网关自身健康：与根路径 /health 同口径（PLATFORM_VERSION + 库名）。"""
        return {
            'status': 'ok',
            'service': 'api_gateway',
            'version': Config.PLATFORM_VERSION,
            'database': database_name_of(Config.DATABASE_URL),
        }

    @staticmethod
    def _probe_auth() -> dict:
        """探测 auth_service /health（HTTP 5009）；失败降级 error，不抛异常。"""
        url = f'http://{Config.AUTH_SERVICE_HOST}:{AUTH_SERVICE_HTTP_PORT}/health'
        try:
            # trust_env=False：忽略系统代理（Windows 注册表代理会劫持 localhost 请求）
            resp = httpx.get(url, timeout=AUTH_PROBE_TIMEOUT_SECONDS, trust_env=False)
            body = resp.json()
            return {
                'status': body.get('status', 'error'),
                'service': body.get('service', 'auth_service'),
            }
        except Exception as exc:
            logger.warning("auth_service 健康探测失败: %s (%s)", url, exc)
            return {'status': 'error', 'service': 'auth_service'}

    @staticmethod
    def get_system_health():
        """聚合网关自身 + 认证服务健康，返回统一信封。"""
        return success_response(data={
            'gateway': SystemHealthService._gateway_health(),
            'auth': SystemHealthService._probe_auth(),
        }, message='ok')
