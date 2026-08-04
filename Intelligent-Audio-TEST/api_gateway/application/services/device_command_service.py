import logging

from api_gateway.infrastructure.request_adapter import request
from shared.models.models import Device, DeviceTag, TaskDevice
from shared.models.database import db
from shared.utils.response import success_response, error_response
from shared.utils.log_handler import log_not_emit
# 跨服务调用：通过 gRPC DeviceService 调用设备驱动工厂
from api_gateway.infrastructure.grpc_proxies import device_driver_factory
from api_gateway.schemas.common import IdData
from api_gateway.schemas.device import (
    DeviceCreateSchema,
    DeviceUpdateSchema,
)
from shared.utils.query_utils import now_cst

logger = logging.getLogger(__name__)


class DeviceCommandService:
    """设备写操作 Service（CQRS Command Side）。

    承载 DeviceController 中 CRUD 与批量操作方法，保持原有逻辑不变。
    """

    # 注册新设备
    @staticmethod
    def create():
        try:
            req = DeviceCreateSchema.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"请求数据验证失败: {str(e)}", 400)

        try:
            new_device = Device(
                name=req.name,
                model=req.model,
                description=req.description,
                type=req.type,
                system=req.system,
                system_version=req.system_version,
                app_name=req.app_name,
                app_version=req.app_version,
                location=req.location,
                max_audio_duration=req.max_audio_duration,
                needs_prompt_audio=req.needs_prompt_audio or False,
                prompt_config=req.prompt_config,
                connection_type=req.connection_type,
                keywords=req.keywords,
                serial_number=req.serial_number,
                ip=req.ip,
                status=req.status or 'offline',
                supported_algorithms=req.supported_algorithms or [],
            )
            db.session.add(new_device)
            db.session.commit()

            from shared.utils.report.stats_cache import refresh_stats_cache
            refresh_stats_cache()

            # 创建设备后立即检查设备是否在线
            try:
                driver = device_driver_factory.get_driver(new_device.system)
                if driver:
                    # 扫描当前系统的在线设备
                    online_devices = driver.scan()
                    # 检查新设备的序列号是否在在线设备列表中
                    serial_number = new_device.serial_number
                    if serial_number:
                        for online_device in online_devices:
                            if online_device['serial'] == serial_number:
                                # 如果设备在线，更新状态
                                new_device.status = 'online'
                                new_device.last_online_at = now_cst()
                                db.session.commit()
                                break
            except Exception as scan_error:
                # 扫描失败不影响设备创建，只记录日志
                log_not_emit('ERROR', 'device_controller', f'扫描设备状态失败: {scan_error}', category='device')
            
            return success_response(IdData(id=new_device.id), "设备注册成功", code=0, http_code=201)
        except Exception as e:
            db.session.rollback()
            return error_response(str(e))

    # 更新设备信息
    @staticmethod
    def update(device_id):
        device = Device.query.filter_by(id=device_id, deleted=False).first()
        if not device:
            return error_response("未找到设备", 404)

        try:
            req = DeviceUpdateSchema.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"请求数据验证失败: {str(e)}", 400)
        
        validated_dict = req.model_dump(by_alias=True, exclude_none=True)
        
        try:
            for key, value in validated_dict.items():
                setattr(device, key, value)
            
            device.updated_at = now_cst()
            db.session.commit()
            return success_response(None, "设备信息更新成功")
        except Exception as e:
            db.session.rollback()
            return error_response(str(e))

    # 删除设备
    @staticmethod
    def delete(device_id):
        device = Device.query.filter_by(id=device_id, deleted=False).first()
        if not device:
            return error_response("未找到设备", 404)

        # 引用检查：检查该设备是否有关联的任务
        related_task = TaskDevice.query.filter_by(device_id=device_id).first()
        if related_task:
            return error_response("该设备已关联测试任务，无法删除", 400)

        try:
            # 清理标签关联
            DeviceTag.query.filter_by(device_id=device_id).delete()
            
            # 逻辑删除
            device.deleted = True
            device.updated_at = now_cst()
            db.session.commit()

            from shared.utils.report.stats_cache import refresh_stats_cache
            refresh_stats_cache()

            return success_response(None, "设备已删除 (逻辑删除)")
        except Exception as e:
            db.session.rollback()
            return error_response(str(e))
