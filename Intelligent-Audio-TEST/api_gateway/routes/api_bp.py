from fastapi import APIRouter
from fastapi.responses import JSONResponse
from api_gateway.application.services.api.api_query_service import ApiQueryService
from api_gateway.application.services.api.api_command_service import ApiCommandService
from api_gateway.routes._response import to_response
from api_gateway.application.services.auth.dependencies import require_permission

router = APIRouter()


@router.get('')
def get_all():
    return to_response(ApiQueryService.get_all())


@router.get('/{api_id}')
def get_one(api_id: int):
    return to_response(ApiQueryService.get_one(api_id))


@router.post('')
def create():
    return to_response(ApiCommandService.create())


@router.put('/{api_id}')
def update(api_id: int):
    return to_response(ApiCommandService.update(api_id))


@router.delete('/{api_id}')
def delete(api_id: int, _: None = require_permission('api_config:delete')):
    return to_response(ApiCommandService.delete(api_id))


@router.post('/{api_id}/health')
def health_check(api_id: int, _: None = require_permission('api_config:read')):
    return to_response(ApiQueryService.health_check(api_id))


@router.api_route('/{api_id}/test', methods=['POST', 'GET'])
def test_connection(api_id: int):
    return to_response(ApiQueryService.test_connection(api_id))


@router.post('/{api_id}/stop-test')
def stop_test(api_id: int, _: None = require_permission('api_config:test')):
    return to_response(ApiQueryService.stop_test(api_id))
