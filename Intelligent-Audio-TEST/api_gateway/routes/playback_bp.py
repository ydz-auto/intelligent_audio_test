from fastapi import APIRouter
from fastapi.responses import JSONResponse
from api_gateway.application.services.playback.playback_query_service import PlaybackQueryService
from api_gateway.application.services.playback.playback_command_service import PlaybackCommandService
from api_gateway.application.services.device.device_import_export_service import ResourceImportExportService
from api_gateway.routes._response import to_response
from api_gateway.application.services.auth.dependencies import require_permission

router = APIRouter()


@router.get('')
def get_all(_: None = require_permission('playback:read')):
    return to_response(PlaybackQueryService.get_all())


# 字面路由必须先于动态路由 /{device_id} 注册，否则 /check-status 被捕获并解析 int 失败（INT-399）
@router.get('/check-status')
def check_status(_: None = require_permission('playback:read')):
    return to_response(PlaybackQueryService.check_status())


# INT-816 导入导出（静态段，须先于 /{device_id} 注册）
@router.get('/export')
def export_playback_devices(_: None = require_permission('playback:read')):
    """导出播放设备（json/excel 文件流，ids/format 可选；CQRS 查询侧无副作用）"""
    return to_response(ResourceImportExportService.export('playback-devices'))


@router.post('/import')
def import_playback_devices(_: None = require_permission('playback:create')):
    """导入播放设备（multipart 文件），按 device_unique_id 匹配更新/新建/跳过"""
    return to_response(ResourceImportExportService.import_resource('playback-devices'))


@router.get('/{device_id}')
def get_one(device_id: int, _: None = require_permission('playback:read')):
    return to_response(PlaybackQueryService.get_one(device_id))


@router.post('')
def create(_: None = require_permission('playback:create')):
    return to_response(PlaybackCommandService.create())


@router.put('/{device_id}')
def update(device_id: int, _: None = require_permission('playback:update')):
    return to_response(PlaybackCommandService.update(device_id))


@router.delete('/{device_id}')
def delete(device_id: int, _: None = require_permission('playback:delete')):
    return to_response(PlaybackCommandService.delete(device_id))


@router.post('/scan')
def scan(_: None = require_permission('playback:control')):
    return to_response(PlaybackQueryService.scan())


@router.post('/{device_id}/associate-spl')
def associate_spl(device_id: int, _: None = require_permission('playback:control')):
    return to_response(PlaybackCommandService.associate_spl(device_id))


@router.post('/{device_id}/test')
def test(device_id: int, _: None = require_permission('playback:control')):
    return to_response(PlaybackCommandService.test(device_id))


@router.post('/{device_id}/stop-test')
def stop_test(device_id: int, _: None = require_permission('playback:control')):
    return to_response(PlaybackCommandService.stop_test(device_id))
