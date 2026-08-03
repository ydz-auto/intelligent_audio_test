# -*- coding: utf-8 -*-
"""设备注册表基础设施。

封装对已有 device/ 和 drivers/ 模块的访问，为应用层提供统一的
设备查询与驱动获取接口。设备注册表通过 gRPC DeviceService 调用
设备驱动工厂（driver_factory.py），与 e2e_test_service 进程解耦。
"""

from typing import Dict, List, Optional


class DeviceRegistry:
    """设备注册表

    委托给已有的 E2EDeviceManager（core/e2e_device_manager.py）查询任务
    关联的设备列表，并通过 gRPC 获取设备驱动。
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._device_manager = None
        return cls._instance

    @property
    def device_manager(self):
        """懒加载 E2EDeviceManager，委托给 e2e_executor"""
        if self._device_manager is None:
            from e2e_test_service.core.e2e_service import e2e_service
            # E2EDeviceManager 需要绑定一个 executor 实例
            self._device_manager = e2e_service.executor._device_manager
        return self._device_manager

    def get_devices_for_task(self, task_id: str, case_config: Dict) -> Dict:
        """获取任务关联的设备列表

        委托给 E2EDeviceManager.get_device_info()（core/e2e_device_manager.py）。
        """
        return self.device_manager.get_device_info(task_id, case_config)

    def list_device_info(self, task_id: str, case_config: Dict) -> List[Dict]:
        """获取设备信息列表（便捷方法）"""
        result = self.get_devices_for_task(task_id, case_config)
        if not result.get('success'):
            return []
        return result.get('data', {}).get('device_info_list', [])
