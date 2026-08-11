from fastapi import APIRouter
from fastapi.responses import JSONResponse
from api_gateway.application.services.device.device_query_service import DeviceQueryService
from api_gateway.application.services.device.device_command_service import DeviceCommandService
from api_gateway.routes._response import to_response
from api_gateway.application.services.auth.dependencies import require_permission

router = APIRouter()


@router.get('')
def get_all(_: None = require_permission('device:read')):
    return to_response(DeviceQueryService.get_all())


@router.get('/status')
def get_statuses(_: None = require_permission('device:read')):
    return to_response(DeviceQueryService.get_statuses())


@router.get('/driver-keywords')
def get_driver_keywords(_: None = require_permission('device:read')):
    return to_response(DeviceQueryService.get_driver_keywords())


@router.get('/serials')
def get_available_serials(_: None = require_permission('device:read')):
    return to_response(DeviceQueryService.get_available_serials())


@router.get('/{device_id}')
def get_one(device_id: int, _: None = require_permission('device:read')):
    return to_response(DeviceQueryService.get_one(device_id))


@router.post('')
def create(_: None = require_permission('device:create')):
    return to_response(DeviceCommandService.create())


@router.put('/{device_id}')
def update(device_id: int, _: None = require_permission('device:update')):
    return to_response(DeviceCommandService.update(device_id))


@router.delete('/{device_id}')
def delete(device_id: int, _: None = require_permission('device:delete')):
    return to_response(DeviceCommandService.delete(device_id))


@router.post('/health-check')
def health_check(_: None = require_permission('device:control')):
    return to_response(DeviceQueryService.health_check())


@router.post('/scan')
def scan(_: None = require_permission('device:control')):
    return to_response(DeviceQueryService.scan())


@router.post('/{device_id}/test')
def test(device_id: int, _: None = require_permission('device:control')):
    return to_response(DeviceQueryService.test(device_id))


@router.post('/{device_id}/stop-test')
def stop_test(device_id: int, _: None = require_permission('device:control')):
    return to_response(DeviceQueryService.stop_test(device_id))
