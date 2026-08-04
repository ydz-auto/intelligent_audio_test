from fastapi import APIRouter
from fastapi.responses import JSONResponse
from api_gateway.application.services.group_service import GroupService
from api_gateway.routes._response import to_response

router = APIRouter()


@router.get('')
def get_all():
    return to_response(GroupService.get_all())


@router.post('')
def create():
    return to_response(GroupService.create())


@router.put('/{group_id}')
def update(group_id: str):
    return to_response(GroupService.update(group_id))


@router.delete('/{group_id}')
def delete(group_id: str):
    return to_response(GroupService.delete(group_id))


@router.post('/move-cases')
def move_cases():
    return to_response(GroupService.move_cases())
