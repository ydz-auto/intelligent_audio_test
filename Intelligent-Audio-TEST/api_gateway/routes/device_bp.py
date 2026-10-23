from typing import Optional

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from api_gateway.application.services.device.device_query_service import DeviceQueryService
from api_gateway.application.services.device.device_command_service import DeviceCommandService
from api_gateway.application.services.device.device_import_export_service import ResourceImportExportService
from api_gateway.routes._response import to_response
from api_gateway.application.services.auth.dependencies import require_permission

router = APIRouter()

# 说明：FastAPI 按注册顺序匹配路由，静态一段路径（/status、/device-groups、
# /alarm-rules、/alarms、/batch 等）必须先于 /{device_id} 注册，
# 否则会被 device_id: int 校验拦截返回 422。

# ==================== 设备查询（读侧） ====================


@router.get('')
def get_all(_: None = require_permission('device:read')):
    return to_response(DeviceQueryService.get_all())


@router.get('/status')
def get_statuses(_: None = require_permission('device:read')):
    return to_response(DeviceQueryService.get_statuses())


@router.get('/driver-keywords')
def get_driver_keywords(_: None = require_permission('device:read')):
    return to_response(DeviceQueryService.get_driver_keywords())


@router.get('/serials')
def get_available_serials(_: None = require_permission('device:read')):
    return to_response(DeviceQueryService.get_available_serials())


@router.get('/status-history')
def get_status_history_all(_: None = require_permission('device:read')):
    """设备状态历史/趋势查询（全设备，INT-80）"""
    return to_response(DeviceQueryService.get_status_history())


@router.get('/monitor-stats')
def get_monitor_stats(
    start_date: str = Query(..., description='起始日期 YYYY-MM-DD（含）'),
    end_date: str = Query(..., description='结束日期 YYYY-MM-DD（含）'),
    device_ids: Optional[str] = Query(None, description='逗号分隔的设备 id'),
    lab_id: Optional[int] = Query(None),
    granularity: str = Query('day', description='本期仅 day'),
    _: None = require_permission('device:read'),
):
    """设备监控统计（INT-1578）：历史监控 → 统计分析四图的数据源。

    静态段必须注册在 /{device_id} 之前；start_date / end_date 缺参由 FastAPI 返回 422，
    区间与粒度校验按契约返回 400。
    """
    return to_response(DeviceQueryService.get_monitor_stats(
        start_date=start_date, end_date=end_date, device_ids=device_ids,
        lab_id=lab_id, granularity=granularity,
    ))


# ==================== INT-80 设备分组 ====================


@router.get('/device-groups')
def get_device_groups(_: None = require_permission('device:read')):
    return to_response(DeviceQueryService.get_groups())


@router.post('/device-groups')
def create_device_group(_: None = require_permission('device:create')):
    return to_response(DeviceCommandService.create_group())


@router.get('/device-groups/{group_id}')
def get_device_group(group_id: str, _: None = require_permission('device:read')):
    return to_response(DeviceQueryService.get_group(group_id))


@router.put('/device-groups/{group_id}')
def update_device_group(group_id: str, _: None = require_permission('device:update')):
    return to_response(DeviceCommandService.update_group(group_id))


@router.put('/device-groups/{group_id}/move')
def move_device_group(group_id: str, _: None = require_permission('device:update')):
    """移动设备分组到新父级（INT-832），body {parent_id: string|null}"""
    return to_response(DeviceCommandService.move_group(group_id))


@router.delete('/device-groups/{group_id}')
def delete_device_group(group_id: str, _: None = require_permission('device:delete')):
    return to_response(DeviceCommandService.delete_group(group_id))


@router.post('/device-groups/{group_id}/devices')
def add_devices_to_group(group_id: str, _: None = require_permission('device:update')):
    return to_response(DeviceCommandService.add_group_devices(group_id))


@router.post('/device-groups/{group_id}/remove-devices')
def remove_devices_from_group(group_id: str, _: None = require_permission('device:update')):
    # 用 POST 承载移除语义：批量 device_ids 走 JSON body（DELETE body 前端 fetch 不发送）
    return to_response(DeviceCommandService.remove_group_devices(group_id))


# ==================== INT-80 监控告警 ====================


@router.get('/alarm-rules')
def get_alarm_rules(_: None = require_permission('device:read')):
    return to_response(DeviceQueryService.get_alarm_rules())


@router.post('/alarm-rules')
def create_alarm_rule(_: None = require_permission('device:update')):
    return to_response(DeviceCommandService.create_alarm_rule())


@router.put('/alarm-rules/{rule_id}')
def update_alarm_rule(rule_id: int, _: None = require_permission('device:update')):
    return to_response(DeviceCommandService.update_alarm_rule(rule_id))


@router.delete('/alarm-rules/{rule_id}')
def delete_alarm_rule(rule_id: int, _: None = require_permission('device:update')):
    return to_response(DeviceCommandService.delete_alarm_rule(rule_id))


@router.get('/alarms')
def get_alarms(_: None = require_permission('device:read')):
    return to_response(DeviceQueryService.get_alarms())


@router.post('/alarms/{alarm_id}/acknowledge')
def acknowledge_alarm(alarm_id: int, _: None = require_permission('device:control')):
    return to_response(DeviceCommandService.acknowledge_alarm(alarm_id))


# ==================== INT-80 批量操作 ====================


@router.post('/batch')
def batch_action(_: None = require_permission('device:control')):
    return to_response(DeviceCommandService.batch_action())


# ==================== 设备写操作 ====================


@router.post('')
def create(_: None = require_permission('device:create')):
    return to_response(DeviceCommandService.create())


@router.post('/health-check')
def health_check(_: None = require_permission('device:control')):
    return to_response(DeviceQueryService.health_check())


@router.post('/scan')
def scan(_: None = require_permission('device:control')):
    return to_response(DeviceQueryService.scan())


# ==================== INT-80 设备操作端点 ====================


@router.post('/{device_id}/connect')
def connect_device(device_id: int, _: None = require_permission('device:control')):
    return to_response(DeviceCommandService.control(device_id, 'connect'))


@router.post('/{device_id}/disconnect')
def disconnect_device(device_id: int, _: None = require_permission('device:control')):
    return to_response(DeviceCommandService.control(device_id, 'disconnect'))


@router.post('/{device_id}/reboot')
def reboot_device(device_id: int, _: None = require_permission('device:control')):
    return to_response(DeviceCommandService.control(device_id, 'reboot'))


@router.post('/{device_id}/shutdown')
def shutdown_device(device_id: int, _: None = require_permission('device:control')):
    return to_response(DeviceCommandService.control(device_id, 'shutdown'))


@router.post('/{device_id}/install-app')
def install_app(device_id: int, _: None = require_permission('device:control')):
    return to_response(DeviceCommandService.control(device_id, 'install_app'))


@router.post('/{device_id}/uninstall-app')
def uninstall_app(device_id: int, _: None = require_permission('device:control')):
    return to_response(DeviceCommandService.control(device_id, 'uninstall_app'))


@router.get('/{device_id}/status-history')
def get_device_status_history(device_id: int, _: None = require_permission('device:read')):
    """单设备状态历史/趋势查询（INT-80）"""
    return to_response(DeviceQueryService.get_status_history(device_id))


# ==================== INT-816 导入导出（静态段，须先于 /{device_id} 注册） ====================


@router.get('/export')
def export_devices(_: None = require_permission('device:read')):
    """导出测试设备（json/excel 文件流，ids/format 可选；CQRS 查询侧无副作用）"""
    return to_response(ResourceImportExportService.export('test-devices'))


@router.post('/import')
def import_devices(_: None = require_permission('device:create')):
    """导入测试设备（multipart 文件），按 serial_number 匹配更新/新建/跳过"""
    return to_response(ResourceImportExportService.import_resource('test-devices'))


# ==================== 原有设备路由（动态段置底） ====================


@router.get('/{device_id}')
def get_one(device_id: int, _: None = require_permission('device:read')):
    return to_response(DeviceQueryService.get_one(device_id))


@router.put('/{device_id}')
def update(device_id: int, _: None = require_permission('device:update')):
    return to_response(DeviceCommandService.update(device_id))


@router.delete('/{device_id}')
def delete(device_id: int, _: None = require_permission('device:delete')):
    return to_response(DeviceCommandService.delete(device_id))


@router.post('/{device_id}/test')
def test(device_id: int, _: None = require_permission('device:control')):
    return to_response(DeviceQueryService.test(device_id))


@router.post('/{device_id}/stop-test')
def stop_test(device_id: int, _: None = require_permission('device:control')):
    return to_response(DeviceQueryService.stop_test(device_id))
