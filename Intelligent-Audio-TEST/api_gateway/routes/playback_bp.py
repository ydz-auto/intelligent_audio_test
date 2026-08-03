from fastapi import APIRouter
from fastapi.responses import JSONResponse
from api_gateway.controllers.playback_controller import PlaybackController
from api_gateway.routes._response import to_response

router = APIRouter()


@router.get('')
def get_all():
    return to_response(PlaybackController.get_all())


@router.get('/{device_id}')
def get_one(device_id: int):
    return to_response(PlaybackController.get_one(device_id))


@router.post('')
def create():
    return to_response(PlaybackController.create())


@router.put('/{device_id}')
def update(device_id: int):
    return to_response(PlaybackController.update(device_id))


@router.delete('/{device_id}')
def delete(device_id: int):
    return to_response(PlaybackController.delete(device_id))


@router.post('/scan')
def scan():
    return to_response(PlaybackController.scan())


@router.post('/{device_id}/associate-spl')
def associate_spl(device_id: int):
    return to_response(PlaybackController.associate_spl(device_id))


@router.post('/{device_id}/test')
def test(device_id: int):
    return to_response(PlaybackController.test(device_id))


@router.post('/{device_id}/stop-test')
def stop_test(device_id: int):
    return to_response(PlaybackController.stop_test(device_id))


@router.get('/check-status')
def check_status():
    return to_response(PlaybackController.check_status())
