from fastapi import APIRouter
from fastapi.responses import JSONResponse
from api_gateway.application.services.device_query_service import DeviceQueryService
from api_gateway.application.services.device_command_service import DeviceCommandService
from api_gateway.routes._response import to_response

router = APIRouter()


@router.get('')
def get_all():
    return to_response(DeviceQueryService.get_all())


@router.get('/status')
def get_statuses():
    return to_response(DeviceQueryService.get_statuses())


@router.get('/{device_id}')
def get_one(device_id: int):
    return to_response(DeviceQueryService.get_one(device_id))


@router.post('')
def create():
    return to_response(DeviceCommandService.create())


@router.put('/{device_id}')
def update(device_id: int):
    return to_response(DeviceCommandService.update(device_id))


@router.delete('/{device_id}')
def delete(device_id: int):
    return to_response(DeviceCommandService.delete(device_id))


@router.post('/health-check')
def health_check():
    return to_response(DeviceQueryService.health_check())


@router.post('/scan')
def scan():
    return to_response(DeviceQueryService.scan())


@router.post('/{device_id}/test')
def test(device_id: int):
    return to_response(DeviceQueryService.test(device_id))


@router.post('/{device_id}/stop-test')
def stop_test(device_id: int):
    return to_response(DeviceQueryService.stop_test(device_id))


@router.get('/driver-keywords')
def get_driver_keywords():
    return to_response(DeviceQueryService.get_driver_keywords())


@router.get('/serials')
def get_available_serials():
    return to_response(DeviceQueryService.get_available_serials())
