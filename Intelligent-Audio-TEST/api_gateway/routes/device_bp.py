from fastapi import APIRouter
from fastapi.responses import JSONResponse
from api_gateway.controllers.device_controller import DeviceController
from api_gateway.routes._response import to_response

router = APIRouter()


@router.get('')
def get_all():
    return to_response(DeviceController.get_all())


@router.get('/status')
def get_statuses():
    return to_response(DeviceController.get_statuses())


@router.get('/{device_id}')
def get_one(device_id: int):
    return to_response(DeviceController.get_one(device_id))


@router.post('')
def create():
    return to_response(DeviceController.create())


@router.put('/{device_id}')
def update(device_id: int):
    return to_response(DeviceController.update(device_id))


@router.delete('/{device_id}')
def delete(device_id: int):
    return to_response(DeviceController.delete(device_id))


@router.post('/health-check')
def health_check():
    return to_response(DeviceController.health_check())


@router.post('/scan')
def scan():
    return to_response(DeviceController.scan())


@router.post('/{device_id}/test')
def test(device_id: int):
    return to_response(DeviceController.test(device_id))


@router.post('/{device_id}/stop-test')
def stop_test(device_id: int):
    return to_response(DeviceController.stop_test(device_id))


@router.get('/driver-keywords')
def get_driver_keywords():
    return to_response(DeviceController.get_driver_keywords())


@router.get('/serials')
def get_available_serials():
    return to_response(DeviceController.get_available_serials())
