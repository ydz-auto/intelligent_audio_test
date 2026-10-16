"""api_gateway 实验室路由（INT-493/INT-537 拆分①）

契约对照设计文档 §5.1/§5.2（实现前缀 /api/v1）：
- GET    /api/v1/laboratories           列表（?status=&page=&per_page=）
- GET    /api/v1/laboratories/{id}      详情（含 counts）
- POST   /api/v1/laboratories           创建 → 201；code 唯一（软删冲突 409）
- PUT    /api/v1/laboratories/{id}      更新
- DELETE /api/v1/laboratories/{id}      软删；有设备/播放设备/用例引用 → 409
- GET    /api/v1/laboratories/{id}/summary   资源统计
- GET    /api/v1/laboratories/{lab_id}/devices / playback_devices / test_cases
         （复用各 List RPC，lab_id 过滤随拆分②③ RPC 就绪后联动）

权限：查看复用 device:read；写操作 lab:create/update/delete（父卡 §4.6）。
路由顺序：/{lab_id}/summary、/devices 等静态子路径先于 /{lab_id} 注册
（同 device_bp 先例，避免被 int 校验拦截 422）。
"""
from fastapi import APIRouter

from api_gateway.routes._response import to_response
from api_gateway.application.services.auth.dependencies import require_permission
from api_gateway.application.services.laboratory.laboratory_query_service import (
    LaboratoryQueryService,
)
from api_gateway.application.services.laboratory.laboratory_command_service import (
    LaboratoryCommandService,
)

router = APIRouter()


@router.get('')
def list_laboratories(_: None = require_permission('device:read')):
    return to_response(LaboratoryQueryService.list())


@router.get('/{lab_id}/summary')
def get_laboratory_summary(lab_id: int, _: None = require_permission('device:read')):
    return to_response(LaboratoryQueryService.summary(lab_id))


@router.get('/{lab_id}/devices')
def get_laboratory_devices(lab_id: int, _: None = require_permission('device:read')):
    return to_response(LaboratoryQueryService.devices(lab_id))


@router.get('/{lab_id}/playback_devices')
def get_laboratory_playback_devices(lab_id: int, _: None = require_permission('device:read')):
    return to_response(LaboratoryQueryService.playback_devices(lab_id))


@router.get('/{lab_id}/test_cases')
def get_laboratory_test_cases(lab_id: int, _: None = require_permission('device:read')):
    return to_response(LaboratoryQueryService.test_cases(lab_id))


@router.get('/{lab_id}')
def get_laboratory(lab_id: int, _: None = require_permission('device:read')):
    return to_response(LaboratoryQueryService.get(lab_id))


@router.post('')
def create_laboratory(_: None = require_permission('lab:create')):
    return to_response(LaboratoryCommandService.create())


@router.put('/{lab_id}')
def update_laboratory(lab_id: int, _: None = require_permission('lab:update')):
    return to_response(LaboratoryCommandService.update(lab_id))


@router.delete('/{lab_id}')
def delete_laboratory(lab_id: int, _: None = require_permission('lab:delete')):
    return to_response(LaboratoryCommandService.delete(lab_id))
