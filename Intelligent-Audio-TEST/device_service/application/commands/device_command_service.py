# -*- coding: utf-8 -*-
"""设备 Command 应用服务（写侧）

把原 DeviceCrudService 的写操作（create/update/delete/scan/test/stop_test/health_check）
拆分到独立的 DeviceCommandService。
- 不再依赖 request 对象，改为接收 dict 参数
- 返回 dict（{success, message, data, code}），由 servicer 层包装为 gRPC 响应
- 设备扫描/测试逻辑中调用本地的 device_driver_factory（device_service 已有）
"""
import time
import random
import logging

from shared.utils.query_utils import now_cst
from shared.utils.log_handler import log_not_emit, log_and_emit
from api_gateway.application.services.stats_cache import refresh_stats_cache
from device_service.domain.repositories import DeviceRepositoryInterface

logger = logging.getLogger(__name__)


class DeviceCommandService:
    """设备 Command 应用服务（写侧）"""

    def __init__(self, repo: DeviceRepositoryInterface = None):
        if repo is None:
            from device_service.infrastructure.persistence.device_repository import device_repository
            repo = device_repository
        self.repo = repo

    @staticmethod
    def _log(level, content, task_id=None, test_case_id=None, api_id=None,
             category='execution', module='TestDevice', **kwargs):
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

    # ========== 写操作 ==========

    def create(self, data: dict) -> dict:
        """注册新设备（含设备扫描在线检查）"""
        try:
            new_device = self.repo.create_device(data)

            try:
                refresh_stats_cache()
            except Exception:
                logger.debug("创建设备后刷新统计缓存失败", exc_info=True)

            # 创建设备后立即检查设备是否在线
            try:
                from device_service.infrastructure.drivers.device_driver import device_driver_factory
                driver = device_driver_factory.get_driver(new_device.system)
                if driver:
                    online_devices = driver.scan()
                    serial_number = new_device.serial_number
                    if serial_number:
                        for online_device in online_devices:
                            if online_device['serial'] == serial_number:
                                self.repo.update_device_status(
                                    new_device.id, 'online', now_cst()
                                )
                                break
            except Exception as scan_error:
                log_not_emit('ERROR', 'device_controller',
                             f'扫描设备状态失败: {scan_error}', category='device')

            return {
                'success': True,
                'message': '设备注册成功',
                'data': {'id': new_device.id},
                'code': 201,
            }
        except Exception as e:
            return {'success': False, 'message': str(e), 'data': None, 'code': 400}

    def update(self, device_id: int, data: dict) -> dict:
        """更新设备信息"""
        device = self.repo.get_device(device_id)
        if not device:
            return {'success': False, 'message': '未找到设备', 'data': None, 'code': 404}

        try:
            validated_dict = {k: v for k, v in data.items() if v is not None}
            updated = self.repo.update_device(device_id, validated_dict)
            if not updated:
                return {'success': False, 'message': '未找到设备', 'data': None, 'code': 404}
            return {'success': True, 'message': '设备信息更新成功', 'data': None, 'code': 200}
        except Exception as e:
            return {'success': False, 'message': str(e), 'data': None, 'code': 400}

    def delete(self, device_id: int) -> dict:
        """软删除设备（含引用检查 TaskDevice）"""
        device = self.repo.get_device(device_id)
        if not device:
            return {'success': False, 'message': '未找到设备', 'data': None, 'code': 404}

        if self.repo.check_device_in_tasks(device_id):
            return {
                'success': False,
                'message': '该设备已关联测试任务，无法删除',
                'data': None,
                'code': 400,
            }

        try:
            self.repo.delete_device_tags(device_id)
            self.repo.delete_device(device_id)

            try:
                refresh_stats_cache()
            except Exception:
                logger.debug("删除设备后刷新统计缓存失败 device_id=%s", device_id, exc_info=True)

            return {
                'success': True,
                'message': '设备已删除 (逻辑删除)',
                'data': None,
                'code': 200,
            }
        except Exception as e:
            return {'success': False, 'message': str(e), 'data': None, 'code': 400}

    def scan(self) -> dict:
        """扫描物理设备（Android/iOS/HarmonyOS）"""
        from device_service.infrastructure.drivers.device_driver import device_driver_factory

        all_devices = []

        # 1. 扫描 Android
        android_driver = device_driver_factory.get_driver('Android')
        if android_driver:
            original_mock_mode = getattr(android_driver, '_mock_mode', False)
            if hasattr(android_driver, '_mock_mode'):
                android_driver._mock_mode = False
            all_devices.extend(android_driver.scan())
            if hasattr(android_driver, '_mock_mode'):
                android_driver._mock_mode = original_mock_mode

        # 2. 扫描 iOS
        ios_driver = device_driver_factory.get_driver('iOS')
        if ios_driver:
            original_mock_mode = getattr(ios_driver, '_mock_mode', False)
            if hasattr(ios_driver, '_mock_mode'):
                ios_driver._mock_mode = False
            all_devices.extend(ios_driver.scan())
            if hasattr(ios_driver, '_mock_mode'):
                ios_driver._mock_mode = original_mock_mode

        # 3. 扫描 HarmonyOS
        harmony_driver = device_driver_factory.get_driver('HarmonyOS')
        if harmony_driver:
            original_mock_mode = getattr(harmony_driver, '_mock_mode', False)
            if hasattr(harmony_driver, '_mock_mode'):
                harmony_driver._mock_mode = False
            all_devices.extend(harmony_driver.scan())
            if hasattr(harmony_driver, '_mock_mode'):
                harmony_driver._mock_mode = original_mock_mode

        if not all_devices and device_driver_factory.get_mock_mode():
            all_devices = [
                {"serial": "mock-android-1", "model": "Mock Android Device", "system": "Android", "status": "online"},
                {"serial": "mock-ios-1", "model": "Mock iPhone (iPhone15,2)", "system": "iOS", "status": "online"},
                {"serial": "mock-harmony-1", "model": "Mock HarmonyOS Device", "system": "HarmonyOS", "status": "online"}
            ]

        registered_serials = self.repo.get_all_device_serials()
        for device in all_devices:
            device['is_registered'] = device['serial'] in registered_serials or device['model'] in registered_serials
            device['id'] = device.get('serial')
            device['name'] = f"{device['system']} {device['model']}"
            device['type'] = 'phone'
            device['system_version'] = 'Unknown'
            device['app_name'] = 'Default App'
            device['app_version'] = '1.0.0'
            device['ip'] = device.get('ip', '')

        return {
            'success': True,
            'message': f'成功扫描到 {len(all_devices)} 个在线设备',
            'data': all_devices,
            'code': 200,
        }

    def test(self, device_id: int) -> dict:
        """测试设备（唤醒）"""
        device = self.repo.get_device(device_id)
        if not device:
            return {'success': False, 'message': '未找到设备', 'data': None, 'code': 404}

        try:
            from device_service.infrastructure.drivers.device_driver import device_driver_factory
            driver = device_driver_factory.get_driver(device.system, keywords=device.keywords)
            if driver:
                driver.unlock(device.serial_number or device.ip)

            wakeup_cmd = "input keyevent KEYCODE_WAKEUP" if device.system == 'Android' else "wake screen"

            self._log(
                level='INFO',
                category='DeviceTest',
                source=f'Device:{device.name}',
                content=f"正在尝试唤醒设备: {device.name}, 发送指令: {wakeup_cmd}",
                device_id=device.id
            )

            return {
                'success': True,
                'message': '唤醒指令已发送，正在测试',
                'data': {'id': device.id, 'status': device.status, 'wakeup_command': wakeup_cmd},
                'code': 200,
            }
        except Exception as e:
            return {'success': False, 'message': str(e), 'data': None, 'code': 400}

    def stop_test(self, device_id: int) -> dict:
        """停止测试"""
        device = self.repo.get_device(device_id)
        if not device:
            return {'success': False, 'message': '未找到设备', 'data': None, 'code': 404}

        return {
            'success': True,
            'message': '测试已停止',
            'data': {'id': device.id, 'status': device.status},
            'code': 200,
        }

    def health_check(self, device_ids: list = None) -> dict:
        """批量健康检查"""
        from device_service.infrastructure.drivers.device_driver import device_driver_factory

        if not device_ids:
            # 查询所有设备
            result = self.repo.list_devices(page=1, per_page=99999)
            devices = result['items']
        else:
            devices = []
            for did in device_ids:
                d = self.repo.get_device(did)
                if d:
                    devices.append(d.to_dict())

        if not devices:
            return {'success': True, 'message': '没有可检查的设备', 'data': [], 'code': 200}

        health_results = []

        for device_data in devices:
            time.sleep(random.uniform(0.5, 2.0))

            is_online = False
            try:
                driver = device_driver_factory.get_driver(device_data['system'])
                if driver:
                    original_mock_mode = getattr(driver, '_mock_mode', False)
                    if hasattr(driver, '_mock_mode'):
                        driver._mock_mode = False

                    online_devices = driver.scan()

                    if hasattr(driver, '_mock_mode'):
                        driver._mock_mode = original_mock_mode

                    serial_number = device_data.get('serial_number')
                    if serial_number:
                        for online_device in online_devices:
                            if online_device['serial'] == serial_number:
                                is_online = True
                                break
            except Exception as scan_error:
                logger.debug("健康检查扫描设备时发生异常 device_id=%s error=%s", device_data.get('id'), scan_error, exc_info=True)

            new_status = 'online' if is_online else 'offline'
            self.repo.update_device_status(
                device_data['id'], new_status,
                now_cst() if is_online else None
            )

            health_results.append({
                'id': device_data['id'],
                'name': device_data['name'],
                'status': new_status,
                'last_online_at': now_cst().isoformat() if is_online else None,
                'model': device_data.get('model'),
                'system': device_data.get('system'),
            })

        return {
            'success': True,
            'message': f'成功完成 {len(health_results)} 个设备的健康检查',
            'data': health_results,
            'code': 200,
        }


# 模块级实例
device_command_service = DeviceCommandService()
