# 设备驱动工厂单例
# 历史上的 re-export 已移除，请直接从各子模块导入具体驱动/工具：
#     from e2e_test_service.drivers.utils import register_task_events
#     from e2e_test_service.drivers.base_driver import BaseDeviceDriver
from .driver_factory import DeviceDriverFactory

# 预创建工厂实例，方便直接调用
device_driver_factory = DeviceDriverFactory()
