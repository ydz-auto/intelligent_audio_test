# -*- coding: utf-8 -*-
"""数字域 RMS→SPL 映射路由（API 灵敏度域，UC-0902）

挂载前缀 /api/v1/digital-spl。区别于 spl_bp.py（/api/v1/spl，设备物理域 SPLMapping）。
"""
from fastapi import APIRouter

from api_gateway.application.services.api_rms_spl.rms_spl_query_service import RmsSplQueryService
from api_gateway.application.services.api_rms_spl.rms_spl_command_service import RmsSplCommandService
from api_gateway.routes._response import to_response
from api_gateway.application.services.auth.dependencies import require_permission

router = APIRouter()


@router.get('')
def get_all(_: None = require_permission('digital_spl:read')):
    return to_response(RmsSplQueryService.get_all())


@router.get('/by-api/{api_id}')
def get_by_api(api_id: int, _: None = require_permission('digital_spl:read')):
    return to_response(RmsSplQueryService.get_by_api(api_id))


@router.get('/{mapping_id}')
def get_one(mapping_id: int, _: None = require_permission('digital_spl:read')):
    return to_response(RmsSplQueryService.get_one(mapping_id))


@router.post('')
def create(_: None = require_permission('digital_spl:create')):
    return to_response(RmsSplCommandService.create())


@router.put('/{mapping_id}')
def update(mapping_id: int, _: None = require_permission('digital_spl:update')):
    return to_response(RmsSplCommandService.update(mapping_id))


@router.delete('/{mapping_id}')
def delete(mapping_id: int, _: None = require_permission('digital_spl:delete')):
    return to_response(RmsSplCommandService.delete(mapping_id))


@router.post('/{mapping_id}/calibrate')
def calibrate(mapping_id: int, _: None = require_permission('digital_spl:create')):
    return to_response(RmsSplCommandService.calibrate(mapping_id))


@router.post('/by-api/{api_id}/set-default')
def set_default(api_id: int, _: None = require_permission('digital_spl:update')):
    return to_response(RmsSplCommandService.set_default(api_id))
