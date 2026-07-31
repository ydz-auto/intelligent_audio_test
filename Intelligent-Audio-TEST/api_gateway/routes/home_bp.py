from fastapi import APIRouter
from fastapi.responses import JSONResponse
from api_gateway.controllers.home_controller import HomeController
from api_gateway.routes._response import to_response

router = APIRouter()


@router.get('/stats/details')
def get_stats_details():
    return to_response(HomeController.get_stats_details())


@router.post('/stats/refresh')
def refresh_stats():
    return to_response(HomeController.refresh_stats())


@router.get('/stats/summary')
def get_stats_summary():
    return to_response(HomeController.get_stats_summary())
