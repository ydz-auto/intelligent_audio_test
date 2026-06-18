# 保持向后兼容性，直接导入所有模块
from .utils import (
    register_task_events,
    get_task_events,
    unregister_task_events,
    check_stop
)
from .base_driver import BaseDeviceDriver
from .android_driver import AndroidDriver
from .harmony_driver import (
    HarmonyDriver
)
from .harmony_translation_driver import (
    HarmonyXiaoyiTranslationDriver,
    XiaoyiFace2FaceDriver,
    XiaoyiSimultaneousInterpretationDriver
)
from .harmony_xiaoyihuiji_driver import (
    HarmonyHardenXiaoyiHuiJiDriver)

from .driver_factory import DeviceDriverFactory

# 预创建工厂实例，方便直接调用
device_driver_factory = DeviceDriverFactory()

# 重新导出所有类和函数，确保向后兼容
__all__ = [
    'register_task_events',
    'get_task_events',
    'unregister_task_events',
    'check_stop',
    'BaseDeviceDriver',
    'AndroidDriver',
    'HarmonyDriver',
    'HarmonyXiaoyiTranslationDriver',
    'XiaoyiFace2FaceDriver',
    'XiaoyiSimultaneousInterpretationDriver',
    'HarmonyHardenXiaoyiHuiJiDriver',
    'DeviceDriverFactory',
    'device_driver_factory'
]
