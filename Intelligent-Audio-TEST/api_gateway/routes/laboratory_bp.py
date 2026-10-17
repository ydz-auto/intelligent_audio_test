from fastapi import APIRouter

from api_gateway.application.services.auth.dependencies import require_permission
from api_gateway.application.services.device.laboratory_command_service import LaboratoryCommandService
from api_gateway.application.services.device.laboratory_query_service import LaboratoryQueryService
from api_gateway.routes._response import to_response

router = APIRouter()

# INT-655 实验室管理（设备页「更多操作」→「实验室管理」；实验室扩展功能设计.md §5.1）。
# 挂载前缀 /api/v1/laboratories（app.py）。静态段 /{lab_id}/summary 先于 /{lab_id} 注册。
# 权限：查看 device:read（INT-487 §6.26 建议），写操作暂用 device:* 码
#（lab:* 单立码待后端立项后切换）。


@router.get('')
def get_all(_: None = require_permission('device:read')):
    return to_response(LaboratoryQueryService.get_all())


@router.get('/{lab_id}/summary')
def get_summary(lab_id: int, _: None = require_permission('device:read')):
    return to_response(LaboratoryQueryService.get_summary(lab_id))


@router.get('/{lab_id}')
def get_one(lab_id: int, _: None = require_permission('device:read')):
    return to_response(LaboratoryQueryService.get_one(lab_id))


@router.post('')
def create(_: None = require_permission('device:create')):
    return to_response(LaboratoryCommandService.create())


@router.put('/{lab_id}')
def update(lab_id: int, _: None = require_permission('device:update')):
    return to_response(LaboratoryCommandService.update(lab_id))


@router.delete('/{lab_id}')
def delete(lab_id: int, _: None = require_permission('device:delete')):
    return to_response(LaboratoryCommandService.delete(lab_id))
