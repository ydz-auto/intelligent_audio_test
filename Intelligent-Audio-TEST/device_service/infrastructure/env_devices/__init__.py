# -*- coding: utf-8 -*-
"""
环境设备实现包

提供测试环境设备的硬件实现和工厂模式。
管理导轨、声压计、人工嘴等辅助设备。

使用方式：
    from device_service.infrastructure.env_devices.factory import EnvDeviceFactory

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

# 注册内置设备类型到工厂（导入即注册，副作用）
from device_service.infrastructure.env_devices.factory import EnvDeviceFactory
from device_service.infrastructure.env_devices.rail import RailEnvDevice, SerialRailEnvDevice
from device_service.infrastructure.env_devices.modbus_tcp import ModbusTcpEnvDevice
from device_service.infrastructure.env_devices.siemens_s7_modbus import SiemensS7ModbusEnvDevice

EnvDeviceFactory.register('rail', RailEnvDevice)
EnvDeviceFactory.register('serial_rail', SerialRailEnvDevice)
EnvDeviceFactory.register('modbus_tcp', ModbusTcpEnvDevice)
EnvDeviceFactory.register('siemens_s7_modbus', SiemensS7ModbusEnvDevice)
