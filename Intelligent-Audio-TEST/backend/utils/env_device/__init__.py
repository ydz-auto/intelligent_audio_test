# -*- coding: utf-8 -*-
"""
环境设备包

提供测试环境设备的统一抽象和工厂模式。
与 device_driver（被测设备驱动）平行，管理导轨、声压计、人工嘴等辅助设备。

使用方式：
    from backend.utils.env_device import EnvDeviceFactory

    # 从配置批量创建设备
    devices = EnvDeviceFactory.create_from_config([
        {"device_type": "rail", "name": "1号导轨"},
        {"device_type": "serial_rail", "port": "COM3", "baud_rate": 115200},
    ])

    # 每轮测试的设置/恢复
    for dev in devices:
        dev.connect()
    for dev in devices:
        state = dev.setup({"distance_cm": 50})
        # ... 执行测试 ...
        dev.teardown(state)
    for dev in devices:
        dev.disconnect()
"""

from backend.utils.env_device.base_env_device import BaseEnvDevice
from backend.utils.env_device.env_device_factory import EnvDeviceFactory
from backend.utils.env_device.rail import RailEnvDevice, SerialRailEnvDevice

# 注册内置设备类型到工厂
EnvDeviceFactory.register('rail', RailEnvDevice)
EnvDeviceFactory.register('serial_rail', SerialRailEnvDevice)

__all__ = [
    'BaseEnvDevice',
    'EnvDeviceFactory',
    'RailEnvDevice',
    'SerialRailEnvDevice',
]
