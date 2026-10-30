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


# ==================== 逻辑音箱组（静态段，须先于 /{device_id}） ====================


@router.get('/speaker-groups')
def list_speaker_groups(_: None = require_permission('playback:read')):
    """逻辑音箱组：N 个实验室里位置相同的音箱互相对应（含各实验室对应设备）"""
    return to_response(PlaybackQueryService.list_speaker_groups())


@router.post('/speaker-groups')
def create_speaker_group(_: None = require_permission('playback:update')):
    """新建逻辑音箱（body: {name, description?}）"""
    return to_response(PlaybackCommandService.create_speaker_group())


@router.put('/speaker-groups/{group_id}')
def update_speaker_group(group_id: int, _: None = require_permission('playback:update')):
    """重命名/改描述逻辑音箱"""
    return to_response(PlaybackCommandService.update_speaker_group(group_id))


@router.delete('/speaker-groups/{group_id}')
def delete_speaker_group(group_id: int, _: None = require_permission('playback:update')):
    """删除逻辑音箱（连同组内各实验室对应关系）"""
    return to_response(PlaybackCommandService.delete_speaker_group(group_id))


@router.put('/speaker-groups/{group_id}/items')
def set_speaker_group_item(group_id: int, _: None = require_permission('playback:update')):
    """设置逻辑音箱在指定实验室对应的播放设备（body: {lab_id, playback_device_id}）"""
    return to_response(PlaybackCommandService.set_speaker_group_item(group_id))


@router.delete('/speaker-groups/{group_id}/items/{lab_id}')
def delete_speaker_group_item(group_id: int, lab_id: int,
                              _: None = require_permission('playback:update')):
    """移除逻辑音箱在指定实验室的对应设备"""
    return to_response(PlaybackCommandService.delete_speaker_group_item(group_id, lab_id))


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


# INT-1579 播放设备控制（契约 §2.1/§2.2/§2.5）；body 可为空
@router.post('/{device_id}/restart')
def restart(device_id: int, _: None = require_permission('playback:control')):
    """重启播放设备：音频通道层重开 + 重新枚举（不是硬件重启）"""
    return to_response(PlaybackCommandService.restart(device_id))


@router.post('/{device_id}/reset-config')
def reset_config(device_id: int, _: None = require_permission('playback:control')):
    """重置播放设备配置：按硬件重新探测采样率与通道索引（不动声压映射关联）"""
    return to_response(PlaybackCommandService.reset_config(device_id))


@router.get('/{device_id}/diagnosis')
def diagnosis(device_id: int, _: None = require_permission('playback:read')):
    """播放设备诊断（只读，固定 6 项）"""
    return to_response(PlaybackQueryService.diagnosis(device_id))


@router.post('/{device_id}/repair')
def repair(device_id: int, _: None = require_permission('playback:control')):
    """修复播放设备：re-enumerate / reopen-channel 两个安全动作"""
    return to_response(PlaybackCommandService.repair(device_id))
