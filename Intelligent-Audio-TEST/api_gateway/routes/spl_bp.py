from fastapi import APIRouter
from fastapi.responses import JSONResponse
from api_gateway.application.services.spl.spl_query_service import SPLQueryService
from api_gateway.application.services.spl.spl_command_service import SPLCommandService
from api_gateway.routes._response import to_response
from api_gateway.application.services.auth.dependencies import require_permission

router = APIRouter()


@router.get('')
def get_all(_: None = require_permission('spl:read')):
    return to_response(SPLQueryService.get_all())


@router.get('/stats')
def get_stats(_: None = require_permission('spl:read')):
    return to_response(SPLQueryService.get_stats())


@router.get('/by-device/{device_id}')
def get_by_device(device_id: int, _: None = require_permission('spl:read')):
    return to_response(SPLQueryService.get_by_device(device_id))


# ==================== INT-1383 批量导入（静态段，须先于 /{mapping_id} 注册） ====================


@router.post('/import')
def import_mappings(_: None = require_permission('spl:create')):
    """批量导入 SPL 映射（multipart 文件，CSV/XLSX/JSON；纯新增）"""
    return to_response(SPLCommandService.import_mappings())


@router.get('/import-template')
def get_import_template(_: None = require_permission('spl:read')):
    """下载 SPL 导入模板（CSV 列头 + 示例行）"""
    return to_response(SPLCommandService.get_import_template())


@router.get('/{mapping_id}')
def get_one(mapping_id: int, _: None = require_permission('spl:read')):
    return to_response(SPLQueryService.get_one(mapping_id))


@router.post('')
def create(_: None = require_permission('spl:create')):
    return to_response(SPLCommandService.create())


@router.put('/{mapping_id}')
def update(mapping_id: int, _: None = require_permission('spl:update')):
    return to_response(SPLCommandService.update(mapping_id))


@router.delete('/{mapping_id}')
def delete(mapping_id: int, _: None = require_permission('spl:delete')):
    return to_response(SPLCommandService.delete(mapping_id))


@router.post('/{mapping_id}/calibrate')
def calibrate(mapping_id: int, _: None = require_permission('spl:create')):
    return to_response(SPLCommandService.calibrate(mapping_id))


@router.get('/{mapping_id}/history')
def get_history(mapping_id: int, _: None = require_permission('spl:read')):
    return to_response(SPLQueryService.get_history(mapping_id))


@router.get('/{mapping_id}/calibration-data')
def get_calibration_data(mapping_id: int, _: None = require_permission('spl:read')):
    return to_response(SPLQueryService.get_calibration_data(mapping_id))


@router.post('/test-tone')
def play_test_tone(_: None = require_permission('spl:test_tone')):
    return to_response(SPLCommandService.play_test_tone())


@router.post('/test-tone/stop')
def stop_test_tone(_: None = require_permission('spl:test_tone')):
    return to_response(SPLCommandService.stop_test_tone())
