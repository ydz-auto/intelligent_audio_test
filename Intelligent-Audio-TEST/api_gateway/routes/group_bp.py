from fastapi import APIRouter
from fastapi.responses import JSONResponse
from api_gateway.application.services.group_service import GroupService
from api_gateway.routes._response import to_response
from api_gateway.application.services.auth.dependencies import require_permission
from api_gateway.application.services.visibility.visibility_service import VisibilityService
from api_gateway.schemas.visibility import VisibilityUpdateRequest

router = APIRouter()


@router.get('')
def get_all(_: None = require_permission('group:read')):
    return to_response(GroupService.get_all())


@router.post('')
def create(_: None = require_permission('group:create')):
    return to_response(GroupService.create())


@router.put('/{group_id}')
def update(group_id: str, _: None = require_permission('group:update')):
    return to_response(GroupService.update(group_id))


@router.delete('/{group_id}')
def delete(group_id: str, _: None = require_permission('group:delete')):
    return to_response(GroupService.delete(group_id))


@router.post('/move-cases')
def move_cases(_: None = require_permission('group:update')):
    return to_response(GroupService.move_cases())

# INT-466：分组可见性切换（资源:share + owner 校验，admin 豁免）
@router.patch('/{group_id}/visibility')
def update_visibility(group_id: str, body: VisibilityUpdateRequest,
                      _: None = require_permission('group:share')):
    return to_response(VisibilityService.update_group_visibility(group_id, body.visibility))
