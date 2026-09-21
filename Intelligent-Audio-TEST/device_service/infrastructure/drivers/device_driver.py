# 设备驱动工厂单例。
# 具体驱动和工具仍可直接从对应子模块导入；这里保留统一运行时入口。
from .driver_factory import DeviceDriverFactory

device_driver_factory = DeviceDriverFactory()

from .driver_types import AppType, AppVersion, DevicePlatform, DriverStatus
from .registry import DriverRegistry, DriverNotFoundError, driver_registry, register_driver
from .contracts import AppDriver, DriverContext

__all__ = [
    "DeviceDriverFactory", "device_driver_factory",
    "AppType", "AppVersion", "DevicePlatform", "DriverStatus",
    "DriverRegistry", "DriverNotFoundError", "driver_registry", "register_driver",
    "AppDriver", "DriverContext",
]
