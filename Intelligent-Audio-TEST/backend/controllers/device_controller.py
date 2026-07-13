from flask import request, current_app
from backend.models.models import Device, DeviceTag, TaskDevice
from backend.models.database import db
from backend.utils.web.response import success_response, error_response
from backend.utils.web.log_handler import log_not_emit
from backend.utils.device_driver import device_driver_factory
from backend.schemas.common import IdData
from backend.schemas.device import (
    DeviceHealthItem,
    DeviceItem,
    DeviceListData,
    DeviceListQuery,
    DeviceScanItem,
    DeviceStatusItem,
    DeviceStatusListData,
    DeviceStatusQuery,
    DeviceTestData,
    DeviceCreateSchema,
    DeviceUpdateSchema,
    DeviceHealthCheckRequest,
)
from datetime import datetime, timezone, timedelta
from backend.utils.common.query_utils import now_cst
import time
import random

class DeviceController:
    @staticmethod
    def _log(level, content, task_id=None, test_case_id=None, api_id=None, category='execution', module='TestDevice', **kwargs):
        """统一日志记录方法"""
        log_not_emit(
            level=level,
            module=module,
            content=content,
            category=category,
            source='backend',
            task_id=task_id,
            api_id=api_id,
            test_case_id=test_case_id,
            **kwargs
        )

    # 获取所有注册设备
    @staticmethod
    def get_all():
        query_params_dict = {k: v[0] if isinstance(v, list) else v for k, v in request.args.to_dict().items()}
        query_params = DeviceListQuery.model_validate(query_params_dict)
        
        page = query_params.page
        per_page = query_params.per_page
        keyword = query_params.keyword
        status = query_params.status
        device_type = query_params.device_type
        algorithm_type = query_params.algorithm_type

        query = Device.query.filter_by(deleted=False)

        if keyword:
            query = query.filter(
                (Device.name.like(f'%{keyword}%')) | 
                (Device.model.like(f'%{keyword}%')) |
                (Device.location.like(f'%{keyword}%')) |
                (Device.serial_number.like(f'%{keyword}%')) |
                (Device.app_name.like(f'%{keyword}%')) |
                (Device.ip.like(f'%{keyword}%'))
            )
        
        if status:
            query = query.filter(Device.status == status)
        
        if device_type:
            query = query.filter(Device.type == device_type)
        
        if algorithm_type:
            query = query.filter(Device.supported_algorithms.contains([algorithm_type]))

        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        devices = pagination.items

        data = []
        for device in devices:
            device_data = DeviceItem(
                id=device.id,
                name=device.name,
                model=device.model,
                description=device.description,
                type=device.type,
                system=device.system,
                system_version=device.system_version,
                app_name=device.app_name,
                app_version=device.app_version,
                location=device.location,
                max_audio_duration=device.max_audio_duration,
                needs_prompt_audio=device.needs_prompt_audio,
                prompt_config=device.prompt_config,
                connection_type=device.connection_type,
                keywords=device.keywords,
                serial_number=device.serial_number,
                ip=getattr(device, 'ip', None),
                status=device.status,
                last_online_at=device.last_online_at.isoformat() if device.last_online_at else None,
                created_at=device.created_at.isoformat() if device.created_at else None,
                updated_at=device.updated_at.isoformat() if device.updated_at else None,
                supported_algorithms=device.supported_algorithms or [],
            )
            
            # 添加驱动名称
            if device.keywords:
                device_data.driver_name = device_driver_factory.get_driver_name_by_keywords(device.system, device.keywords)
            
            data.append(device_data)
        
        return success_response(
            DeviceListData(
                items=data,
                total=pagination.total,
                page=pagination.page,
                per_page=pagination.per_page,
                pages=pagination.pages,
            )
        )

    # 批量获取设备状态 (用于 HTTP 轮询降级)
    @staticmethod
    def get_statuses():
        query_params_dict = {k: v[0] if isinstance(v, list) else v for k, v in request.args.to_dict().items()}
        query_params = DeviceStatusQuery.model_validate(query_params_dict)
        device_ids = query_params.ids
        
        if not device_ids:
            devices = Device.query.filter_by(deleted=False).all()
        else:
            devices = Device.query.filter(Device.id.in_(device_ids), Device.deleted == False).all()
        
        data = []
        for device in devices:
            data.append(
                DeviceStatusItem(
                    id=device.id,
                    name=device.name,
                    status=device.status,
                    last_online_at=device.last_online_at.isoformat() if device.last_online_at else None,
                )
            )
        return success_response(DeviceStatusListData(items=data, total=len(data)))

    # 扫描物理设备
    @staticmethod
    def scan():
        """
        触发驱动层扫描 Android, iOS, HarmonyOS 设备
        即使在 mock 模式下也会先尝试扫描真实设备，真实设备为空时才返回 mock 数据
        """
        all_devices = []
        
        # 1. 扫描 Android（不受 mock 模式影响，始终扫描真实设备）
        android_driver = device_driver_factory.get_driver('Android')
        if android_driver:
            # 保存原始 mock 状态，临时关闭以扫描真实设备
            original_mock_mode = getattr(android_driver, '_mock_mode', False)
            if hasattr(android_driver, '_mock_mode'):
                android_driver._mock_mode = False
            all_devices.extend(android_driver.scan())
            # 恢复 mock 状态
            if hasattr(android_driver, '_mock_mode'):
                android_driver._mock_mode = original_mock_mode
            
        # 2. 扫描 iOS（不受 mock 模式影响）
        ios_driver = device_driver_factory.get_driver('iOS')
        if ios_driver:
            original_mock_mode = getattr(ios_driver, '_mock_mode', False)
            if hasattr(ios_driver, '_mock_mode'):
                ios_driver._mock_mode = False
            all_devices.extend(ios_driver.scan())
            if hasattr(ios_driver, '_mock_mode'):
                ios_driver._mock_mode = original_mock_mode
            
        # 3. 扫描 HarmonyOS（不受 mock 模式影响）
        harmony_driver = device_driver_factory.get_driver('HarmonyOS')
        if harmony_driver:
            original_mock_mode = getattr(harmony_driver, '_mock_mode', False)
            if hasattr(harmony_driver, '_mock_mode'):
                harmony_driver._mock_mode = False
            all_devices.extend(harmony_driver.scan())
            if hasattr(harmony_driver, '_mock_mode'):
                harmony_driver._mock_mode = original_mock_mode

        # 如果没有扫描到任何设备，且处于 mock 模式，返回 mock 数据作为备用
        if not all_devices and device_driver_factory.get_mock_mode():
            all_devices = [
                {"serial": "mock-android-1", "model": "Mock Android Device", "system": "Android", "status": "online"},
                {"serial": "mock-ios-1", "model": "Mock iPhone (iPhone15,2)", "system": "iOS", "status": "online"},
                {"serial": "mock-harmony-1", "model": "Mock HarmonyOS Device", "system": "HarmonyOS", "status": "online"}
            ]
        # 如果在 DEBUG 模式且没有任何设备，返回调试用的模拟数据
        elif not all_devices and current_app.config.get('DEBUG'):
            all_devices = [
                {"serial": "emulator-5554", "model": "Pixel 6 Pro", "system": "Android", "status": "online"},
                {"serial": "00008101-001A246C0A02001E", "model": "iPhone 13", "system": "iOS", "status": "online"},
                {"serial": "DEMO-HARMONY-001", "model": "Mate 60 Pro", "system": "HarmonyOS", "status": "online"}
            ]

        # 检查哪些设备已经注册在数据库中
        registered_serials = [d.name for d in Device.query.filter_by(deleted=False).all()] # 假设 name 存储了 serial 或者有其他对应关系
        for device in all_devices:
            # 这里简单地用 model 或 serial 匹配，实际应根据业务逻辑调整
            device['is_registered'] = device['serial'] in registered_serials or device['model'] in registered_serials
            # 统一字段名以兼容前端
            device['id'] = device.get('serial')
            device['name'] = f"{device['system']} {device['model']}"
            device['type'] = 'phone'
            device['system_version'] = 'Unknown'
            device['app_name'] = 'Default App'
            device['app_version'] = '1.0.0'
            device['ip'] = '127.0.0.1'

        return success_response([DeviceScanItem(**d) for d in all_devices], f"成功扫描到 {len(all_devices)} 个在线设备")

    # 测试设备
    @staticmethod
    def test(device_id):
        device = Device.query.filter_by(id=device_id, deleted=False).first()
        if not device:
            return error_response("未找到设备", 404)
        
        try:
            # 使用驱动工厂获取驱动并执行唤醒
            driver = device_driver_factory.get_driver(device.system, keywords=device.keywords)
            if driver:
                driver.unlock(device.serial_number or device.ip)
            
            wakeup_cmd = "input keyevent KEYCODE_WAKEUP" if device.system == 'Android' else "wake screen"
            
            # 写入日志
            DeviceController._log(
                level='INFO',
                category='DeviceTest',
                source=f'Device:{device.name}',
                content=f"正在尝试唤醒设备: {device.name}, 发送指令: {wakeup_cmd}",
                device_id=device.id
            )

            return success_response(
                DeviceTestData(id=device.id, status=device.status, wakeup_command=wakeup_cmd),
                "唤醒指令已发送，正在测试",
            )
        except Exception as e:
            db.session.rollback()
            return error_response(str(e))

    # 停止测试
    @staticmethod
    def stop_test(device_id):
        device = Device.query.filter_by(id=device_id, deleted=False).first()
        if not device:
            return error_response("未找到设备", 404)
        
        try:
            return success_response(DeviceTestData(id=device.id, status=device.status), "测试已停止")
        except Exception as e:
            db.session.rollback()
            return error_response(str(e))

    @staticmethod
    def get_driver_keywords():
        """获取所有已注册的驱动关键字"""
        try:
            keywords_data = device_driver_factory.get_registered_keywords()
            return success_response(keywords_data, "获取驱动关键字成功")
        except Exception as e:
            return error_response(str(e))

    # 获取单个设备详情
    @staticmethod
    def get_one(device_id):
        device = Device.query.filter_by(id=device_id, deleted=False).first()
        if not device:
            return error_response("未找到设备", 404)
        
        data = DeviceItem(
            id=device.id,
            name=device.name,
            model=device.model,
            description=device.description,
            type=device.type,
            system=device.system,
            system_version=device.system_version,
            app_name=device.app_name,
            app_version=device.app_version,
            location=device.location,
            max_audio_duration=device.max_audio_duration,
            needs_prompt_audio=device.needs_prompt_audio,
            prompt_config=device.prompt_config,
            connection_type=device.connection_type,
            keywords=device.keywords,
            serial_number=device.serial_number,
            ip=getattr(device, 'ip', None),
            status=device.status,
            last_online_at=device.last_online_at.isoformat() if device.last_online_at else None,
            created_at=device.created_at.isoformat() if device.created_at else None,
            updated_at=device.updated_at.isoformat() if device.updated_at else None,
            supported_algorithms=device.supported_algorithms or [],
        )
        # 添加驱动名称
        if device.keywords:
            data.driver_name = device_driver_factory.get_driver_name_by_keywords(device.system, device.keywords)
            
        return success_response(data)

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

            from backend.utils.report.stats_cache import refresh_stats_cache
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

            from backend.utils.report.stats_cache import refresh_stats_cache
            refresh_stats_cache()

            return success_response(None, "设备已删除 (逻辑删除)")
        except Exception as e:
            db.session.rollback()
            return error_response(str(e))

    # 批量健康检查
    @staticmethod
    def health_check():
        try:
            req = DeviceHealthCheckRequest.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"请求数据验证失败: {str(e)}", 400)
        
        device_ids = req.device_ids or []
        
        if not device_ids:
            devices = Device.query.filter_by(deleted=False).all()
        else:
            devices = Device.query.filter(Device.id.in_(device_ids), Device.deleted==False).all()

        if not devices:
            return success_response([], "没有可检查的设备")

        health_results = []
        
        # 同步执行健康检查，直接返回结果
        for device in devices:
            # 模拟连接测试 (ADB/Ping)
            time.sleep(random.uniform(0.5, 2.0)) # 模拟耗时
            
            # 实际检查设备是否在线
            is_online = False
            try:
                driver = device_driver_factory.get_driver(device.system)
                from backend.utils.web.log_handler import log_and_emit
                if driver:
                    log_and_emit('DEBUG', 'DeviceHealthCheck', f'开始扫描 {device.system} 设备 {device.name} (ID: {device.id})', device_id=device.id, push_to_websocket=False)
                    
                    # 临时关闭 mock 模式以扫描真实设备
                    original_mock_mode = getattr(driver, '_mock_mode', False)
                    if hasattr(driver, '_mock_mode'):
                        driver._mock_mode = False
                    
                    online_devices = driver.scan()
                    
                    # 恢复 mock 模式状态
                    if hasattr(driver, '_mock_mode'):
                        driver._mock_mode = original_mock_mode
                    
                    log_and_emit('DEBUG', 'DeviceHealthCheck', f'扫描完成，找到 {len(online_devices)} 个在线 {device.system} 设备', device_id=device.id, push_to_websocket=False)
                    serial_number = device.serial_number
                    if serial_number:
                        log_and_emit('DEBUG', 'DeviceHealthCheck', f'检查设备 {device.name} (ID: {device.id}) 的序列号 {serial_number} 是否在线', device_id=device.id, push_to_websocket=False)
                        for online_device in online_devices:
                            if online_device['serial'] == serial_number:
                                is_online = True
                                log_and_emit('INFO', 'DeviceHealthCheck', f'设备 {device.name} (ID: {device.id}) 在线', device_id=device.id, push_to_websocket=False)
                                break
                        if not is_online:
                            log_and_emit('WARN', 'DeviceHealthCheck', f'设备 {device.name} (ID: {device.id}) 离线', device_id=device.id, push_to_websocket=False)
                else:
                    log_and_emit('ERROR', 'DeviceHealthCheck', f'未找到 {device.system} 设备驱动', device_id=device.id, push_to_websocket=False)
            except Exception as scan_error:
                log_and_emit('ERROR', 'DeviceHealthCheck', f'扫描设备 {device.name} (ID: {device.id}) 状态失败: {str(scan_error)}', device_id=device.id, push_to_websocket=False)
            
            device.status = 'online' if is_online else 'offline'
            if is_online:
                device.last_online_at = now_cst()
            
            db.session.commit()
            
            # 收集健康检查结果
            health_results.append(
                DeviceHealthItem(
                    id=device.id,
                    name=device.name,
                    status=device.status,
                    last_online_at=device.last_online_at.isoformat() if device.last_online_at else None,
                    model=device.model,
                    system=device.system,
                )
            )
        
        return success_response(health_results, f"成功完成 {len(health_results)} 个设备的健康检查")

    # 获取可用设备详情列表 (用于自动填充)
    @staticmethod
    def get_available_serials():
        """
        获取通过 ADB/HDC 命令扫描到的可用设备详细信息列表
        即使在 mock 模式下也会先尝试扫描真实设备，真实设备为空时才返回 mock 数据
        """
        all_devices = []
        
        try:
            # 扫描 Android 设备 (使用 ADB，不受 mock 模式影响)
            android_driver = device_driver_factory.get_driver('Android')
            if android_driver:
                original_mock_mode = getattr(android_driver, '_mock_mode', False)
                if hasattr(android_driver, '_mock_mode'):
                    android_driver._mock_mode = False
                android_devices = android_driver.scan()
                all_devices.extend(android_devices)
                if hasattr(android_driver, '_mock_mode'):
                    android_driver._mock_mode = original_mock_mode
            
            # 扫描 iOS 设备（不受 mock 模式影响）
            ios_driver = device_driver_factory.get_driver('iOS')
            if ios_driver:
                original_mock_mode = getattr(ios_driver, '_mock_mode', False)
                if hasattr(ios_driver, '_mock_mode'):
                    ios_driver._mock_mode = False
                ios_devices = ios_driver.scan()
                all_devices.extend(ios_devices)
                if hasattr(ios_driver, '_mock_mode'):
                    ios_driver._mock_mode = original_mock_mode
            
            # 扫描 HarmonyOS 设备（不受 mock 模式影响）
            harmony_driver = device_driver_factory.get_driver('HarmonyOS')
            if harmony_driver:
                original_mock_mode = getattr(harmony_driver, '_mock_mode', False)
                if hasattr(harmony_driver, '_mock_mode'):
                    harmony_driver._mock_mode = False
                harmony_devices = harmony_driver.scan()
                all_devices.extend(harmony_devices)
                if hasattr(harmony_driver, '_mock_mode'):
                    harmony_driver._mock_mode = original_mock_mode
            
        except Exception as e:
            log_not_emit('ERROR', 'device_controller', f'扫描设备详细信息时出错: {e}', category='device')
        
        # 如果没有扫描到任何设备，且处于 mock 模式，返回 mock 数据作为备用
        if not all_devices and device_driver_factory.get_mock_mode():
            all_devices = [
                {"serial": "mock-android-1", "model": "Mock Android Device", "system": "android", "system_version": "Unknown", "app_name": "com.larus.nova", "app_version": "1.0.0"},
                {"serial": "mock-ios-1", "model": "Mock iPhone (iPhone15,2)", "system": "ios", "system_version": "Unknown", "app_name": "com.larus.ios", "app_version": "1.0.0"},
                {"serial": "mock-harmony-1", "model": "Mock HarmonyOS Device", "system": "harmonyos", "system_version": "Unknown", "app_name": "com.larus.harmony", "app_version": "1.0.0"}
            ]
        # 如果在 DEBUG 模式且没有任何设备，返回调试用的模拟数据
        elif not all_devices and current_app.config.get('DEBUG'):
            all_devices = [
                {"serial": "MOCK-ADB-123456", "model": "Pixel 6 Pro", "system": "android", "system_version": "13.0", "app_name": "Default App", "app_version": "1.0.0"},
                {"serial": "MOCK-IOS-789012", "model": "iPhone 14", "system": "ios", "system_version": "16.5", "app_name": "Default App", "app_version": "1.0.0"}
            ]
        
        # 去重 (按 serial)
        seen_serials = set()
        unique_devices = []
        for d in all_devices:
            if d.get('serial') and d['serial'] not in seen_serials:
                seen_serials.add(d['serial'])
                unique_devices.append(d)
        
        return success_response([DeviceScanItem(**d) for d in unique_devices], f"成功获取 {len(unique_devices)} 个设备详细信息")
