from fastapi import APIRouter
from fastapi.responses import JSONResponse
from api_gateway.controllers.api_controller import APIController
from api_gateway.routes._response import to_response

router = APIRouter()


@router.get('')
def get_all():
    return to_response(APIController.get_all())


@router.get('/{api_id}')
def get_one(api_id: int):
    return to_response(APIController.get_one(api_id))


@router.post('')
def create():
    return to_response(APIController.create())


@router.put('/{api_id}')
def update(api_id: int):
    return to_response(APIController.update(api_id))


@router.delete('/{api_id}')
def delete(api_id: int):
    return to_response(APIController.delete(api_id))


@router.post('/{api_id}/health')
def health_check(api_id: int):
    return to_response(APIController.health_check(api_id))


@router.api_route('/{api_id}/test', methods=['POST', 'GET'])
def test_connection(api_id: int):
    return to_response(APIController.test_connection(api_id))


@router.post('/{api_id}/stop-test')
def stop_test(api_id: int):
    return to_response(APIController.stop_test(api_id))
