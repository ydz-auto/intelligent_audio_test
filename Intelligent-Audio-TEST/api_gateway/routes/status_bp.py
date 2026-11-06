# -*- coding: utf-8 -*-
"""站点状态路由（INT-620）：GET /api/status

对位 newAPI `/api/status`；输出 snake_case `{ api_base_url, server_address }`，
前端 infrastructure/statusApi.ts 是唯一 snake→camel 转换层。权限码 status:read。
"""
from fastapi import APIRouter, Request

from api_gateway.application.services.auth.dependencies import require_permission
from api_gateway.application.services.site_status_service import SiteStatusService
from api_gateway.routes._response import to_response

router = APIRouter()


@router.get('/status')
def get_site_status(request: Request, _: None = require_permission('status:read')):
    """站点状态（API 根地址 + 服务器地址）。"""
    return to_response(SiteStatusService.get_site_status(request))
