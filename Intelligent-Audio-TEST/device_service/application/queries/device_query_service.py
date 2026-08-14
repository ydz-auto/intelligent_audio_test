# -*- coding: utf-8 -*-
"""设备 Query 应用服务（读侧）

把原 DeviceCrudService 的读操作（get_all/get_one/get_statuses/
get_driver_keywords/get_available_serials）拆分到独立的 DeviceQueryService。
- 不再依赖 request 对象，改为接收 dict 参数
- 返回 dict（{success, message, data, code}），由 servicer 层包装为 gRPC 响应
- 查询逻辑中调用本地的 device_driver_factory（device_service 已有）
"""
import logging

from shared.utils.log_handler import log_not_emit
from device_service.domain.repositories import DeviceRepositoryInterface

logger = logging.getLogger(__name__)


class DeviceQueryService:
    """设备 Query 应用服务（读侧）"""

    def __init__(self, repo: DeviceRepositoryInterface = None):
        if repo is None:
            from device_service.infrastructure.persistence.device_repository import device_repository
            repo = device_repository
        self.repo = repo

    def get_all(self, page: int = 1, per_page: int = 10, keyword: str = None,
                status: str = None, device_type: str = None,
                algorithm_type: str = None) -> dict:
        """分页查询设备列表"""
        try:
            result = self.repo.list_devices(
                page=page, per_page=per_page, keyword=keyword,
                status=status, device_type=device_type, algorithm_type=algorithm_type,
            )

            # 添加驱动名称
            from device_service.infrastructure.drivers.device_driver import device_driver_factory
            for device_data in result['items']:
                if device_data.get('keywords'):
                    device_data['driver_name'] = device_driver_factory.get_driver_name_by_keywords(
                        device_data['system'], device_data['keywords']
                    )

            return {'success': True, 'message': 'Success', 'data': result, 'code': 200}
        except Exception as e:
            logger.error("get_all failed: %s", e, exc_info=True)
            return {'success': False, 'message': str(e), 'data': None, 'code': 400}

    def get_statuses(self, device_ids: list = None) -> dict:
        """批量获取设备状态"""
        try:
            data = self.repo.get_device_statuses(device_ids)
            return {
                'success': True,
                'message': 'Success',
                'data': {'items': data, 'total': len(data)},
                'code': 200,
            }
        except Exception as e:
            return {'success': False, 'message': str(e), 'data': None, 'code': 400}

    def get_one(self, device_id: int) -> dict:
        """查询设备详情"""
        device = self.repo.get_device(device_id)
        if not device:
            return {'success': False, 'message': '未找到设备', 'data': None, 'code': 404}

        data = device.to_dict()

        from device_service.infrastructure.drivers.device_driver import device_driver_factory
        if device.keywords:
            data['driver_name'] = device_driver_factory.get_driver_name_by_keywords(
                device.system, device.keywords
            )

        return {'success': True, 'message': 'Success', 'data': data, 'code': 200}

    def get_driver_keywords(self) -> dict:
        """获取所有已注册的驱动关键字"""
        try:
            from device_service.infrastructure.drivers.device_driver import device_driver_factory
            keywords_data = device_driver_factory.get_registered_keywords()
            return {'success': True, 'message': '获取驱动关键字成功', 'data': keywords_data, 'code': 200}
        except Exception as e:
            return {'success': False, 'message': str(e), 'data': None, 'code': 400}

    def get_available_serials(self) -> dict:
        """获取可用设备序列号"""
        from device_service.infrastructure.drivers.device_driver import device_driver_factory

        all_devices = []

        try:
            android_driver = device_driver_factory.get_driver('Android')
            if android_driver:
                original_mock_mode = getattr(android_driver, '_mock_mode', False)
                if hasattr(android_driver, '_mock_mode'):
                    android_driver._mock_mode = False
                all_devices.extend(android_driver.scan())
                if hasattr(android_driver, '_mock_mode'):
                    android_driver._mock_mode = original_mock_mode

            ios_driver = device_driver_factory.get_driver('iOS')
            if ios_driver:
                original_mock_mode = getattr(ios_driver, '_mock_mode', False)
                if hasattr(ios_driver, '_mock_mode'):
                    ios_driver._mock_mode = False
                all_devices.extend(ios_driver.scan())
                if hasattr(ios_driver, '_mock_mode'):
                    ios_driver._mock_mode = original_mock_mode

            harmony_driver = device_driver_factory.get_driver('HarmonyOS')
            if harmony_driver:
                original_mock_mode = getattr(harmony_driver, '_mock_mode', False)
                if hasattr(harmony_driver, '_mock_mode'):
                    harmony_driver._mock_mode = False
                all_devices.extend(harmony_driver.scan())
                if hasattr(harmony_driver, '_mock_mode'):
                    harmony_driver._mock_mode = original_mock_mode

        except Exception as e:
            log_not_emit('ERROR', 'device_controller', f'扫描设备详细信息时出错: {e}', category='device')

        if not all_devices and device_driver_factory.get_mock_mode():
            all_devices = [
                {"serial": "mock-android-1", "model": "Mock Android Device", "system": "android", "system_version": "Unknown", "app_name": "com.larus.nova", "app_version": "1.0.0"},
                {"serial": "mock-ios-1", "model": "Mock iPhone (iPhone15,2)", "system": "ios", "system_version": "Unknown", "app_name": "com.larus.ios", "app_version": "1.0.0"},
                {"serial": "mock-harmony-1", "model": "Mock HarmonyOS Device", "system": "harmonyos", "system_version": "Unknown", "app_name": "com.larus.harmony", "app_version": "1.0.0"}
            ]

        seen_serials = set()
        unique_devices = []
        for d in all_devices:
            if d.get('serial') and d['serial'] not in seen_serials:
                seen_serials.add(d['serial'])
                unique_devices.append(d)

        return {
            'success': True,
            'message': f'成功获取 {len(unique_devices)} 个设备详细信息',
            'data': unique_devices,
            'code': 200,
        }


# 模块级实例
device_query_service = DeviceQueryService()
