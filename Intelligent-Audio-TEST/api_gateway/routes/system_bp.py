# -*- coding: utf-8 -*-
"""系统健康路由（INT-766/INT-787）：GET /api/v1/system/health

聚合网关自身 + 认证服务健康，返回统一信封；公开无权限（权限语义同根路径
/health，白名单见 AuthMiddleware.PUBLIC_PATHS）。
"""
from fastapi import APIRouter

from api_gateway.application.services.system_health_service import SystemHealthService
from api_gateway.routes._response import to_response

router = APIRouter()


@router.get('/health')
def get_system_health():
    """系统健康汇总（网关 + 认证服务）。"""
    return to_response(SystemHealthService.get_system_health())
