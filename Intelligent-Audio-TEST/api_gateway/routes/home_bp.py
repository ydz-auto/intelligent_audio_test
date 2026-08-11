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
