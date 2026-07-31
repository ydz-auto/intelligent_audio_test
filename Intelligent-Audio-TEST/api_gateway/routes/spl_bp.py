from fastapi import APIRouter
from fastapi.responses import JSONResponse
from api_gateway.controllers.spl_controller import SPLController
from api_gateway.routes._response import to_response

router = APIRouter()


@router.get('')
def get_all():
    return to_response(SPLController.get_all())


@router.get('/{mapping_id}')
def get_one(mapping_id: int):
    return to_response(SPLController.get_one(mapping_id))


@router.post('')
def create():
    return to_response(SPLController.create())


@router.put('/{mapping_id}')
def update(mapping_id: int):
    return to_response(SPLController.update(mapping_id))


@router.delete('/{mapping_id}')
def delete(mapping_id: int):
    return to_response(SPLController.delete(mapping_id))


@router.post('/{mapping_id}/calibrate')
def calibrate(mapping_id: int):
    return to_response(SPLController.calibrate(mapping_id))


@router.get('/{mapping_id}/history')
def get_history(mapping_id: int):
    return to_response(SPLController.get_history(mapping_id))


@router.get('/{mapping_id}/calibration-data')
def get_calibration_data(mapping_id: int):
    return to_response(SPLController.get_calibration_data(mapping_id))


@router.get('/stats')
def get_stats():
    return to_response(SPLController.get_stats())


@router.get('/by-device/{device_id}')
def get_by_device(device_id: int):
    return to_response(SPLController.get_by_device(device_id))


@router.post('/test-tone')
def play_test_tone():
    return to_response(SPLController.play_test_tone())


@router.post('/test-tone/stop')
def stop_test_tone():
    return to_response(SPLController.stop_test_tone())
