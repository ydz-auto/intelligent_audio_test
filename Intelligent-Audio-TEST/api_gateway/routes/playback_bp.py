from fastapi import APIRouter
from fastapi.responses import JSONResponse
from api_gateway.application.services.playback_query_service import PlaybackQueryService
from api_gateway.application.services.playback_command_service import PlaybackCommandService
from api_gateway.routes._response import to_response

router = APIRouter()


@router.get('')
def get_all():
    return to_response(PlaybackQueryService.get_all())


@router.get('/{device_id}')
def get_one(device_id: int):
    return to_response(PlaybackQueryService.get_one(device_id))


@router.post('')
def create():
    return to_response(PlaybackCommandService.create())


@router.put('/{device_id}')
def update(device_id: int):
    return to_response(PlaybackCommandService.update(device_id))


@router.delete('/{device_id}')
def delete(device_id: int):
    return to_response(PlaybackCommandService.delete(device_id))


@router.post('/scan')
def scan():
    return to_response(PlaybackQueryService.scan())


@router.post('/{device_id}/associate-spl')
def associate_spl(device_id: int):
    return to_response(PlaybackCommandService.associate_spl(device_id))


@router.post('/{device_id}/test')
def test(device_id: int):
    return to_response(PlaybackCommandService.test(device_id))


@router.post('/{device_id}/stop-test')
def stop_test(device_id: int):
    return to_response(PlaybackCommandService.stop_test(device_id))


@router.get('/check-status')
def check_status():
    return to_response(PlaybackQueryService.check_status())
