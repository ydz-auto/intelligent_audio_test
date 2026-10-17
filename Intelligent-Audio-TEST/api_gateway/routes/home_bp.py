from fastapi import APIRouter
from fastapi.responses import JSONResponse
from api_gateway.application.services.home_service import HomeService
from api_gateway.routes._response import to_response
from api_gateway.application.services.auth.dependencies import require_permission

router = APIRouter()


@router.get('/stats/details')
def get_stats_details(_: None = require_permission('home:read')):
    return to_response(HomeService.get_stats_details())


@router.post('/stats/refresh')
def refresh_stats(_: None = require_permission('home:refresh')):
    return to_response(HomeService.refresh_stats())


@router.get('/stats/summary')
def get_stats_summary(_: None = require_permission('home:read')):
    return to_response(HomeService.get_stats_summary())


@router.get('/site')
def get_site_config():
    """站点配置（公开，无需登录）：system_name/version/logo/support_email。

    INT-674：登录页品牌角标需未登录态取站点配置，故不挂 require_permission，
    由 AuthMiddleware.PUBLIC_PATHS 白名单放行（见 middleware.py）。
    """
    return to_response(HomeService.get_site_config())
