from fastapi import APIRouter
from fastapi.responses import JSONResponse
from api_gateway.controllers.group_controller import GroupController
from api_gateway.routes._response import to_response

router = APIRouter()


@router.get('')
def get_all():
    return to_response(GroupController.get_all())


@router.post('')
def create():
    return to_response(GroupController.create())


@router.put('/{group_id}')
def update(group_id: str):
    return to_response(GroupController.update(group_id))


@router.delete('/{group_id}')
def delete(group_id: str):
    return to_response(GroupController.delete(group_id))


@router.post('/move-cases')
def move_cases():
    return to_response(GroupController.move_cases())
