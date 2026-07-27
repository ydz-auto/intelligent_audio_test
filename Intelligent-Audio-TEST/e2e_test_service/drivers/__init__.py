from .utils import (
    register_task_events,
    get_task_events,
    unregister_task_events,
    check_stop
)
from .base_driver import BaseDeviceDriver
from .android_driver import AndroidDriver
from .android_doubao_asr_driver import DouBaoAndroidAsrDriver

# 鸿蒙驱动依赖 hypium（华为内部测试框架，非 PyPI 包）
# hypium 不可用时跳过这些驱动，不影响其他功能
try:
    from .harmony_driver import HarmonyDriver
    from .harmony_translation_driver import (
        HarmonyXiaoyiTranslationDriver,
        XiaoyiFace2FaceDriver,
        XiaoyiSimultaneousInterpretationDriver
    )
    from .harmony_xiaoyihuiji_driver import HarmonyHardenXiaoyiHuiJiDriver
    from .harmony_xiaoyichat import Xiaoyilivechat
    from .harmony_asr_driver import HarmonyHardenXiaoyi_Input_MethodDriver
    _HYPium_AVAILABLE = True
except ImportError:
    HarmonyDriver = None
    HarmonyXiaoyiTranslationDriver = None
    XiaoyiFace2FaceDriver = None
    XiaoyiSimultaneousInterpretationDriver = None
    HarmonyHardenXiaoyiHuiJiDriver = None
    Xiaoyilivechat = None
    HarmonyHardenXiaoyi_Input_MethodDriver = None
    _HYPium_AVAILABLE = False

from .driver_factory import DeviceDriverFactory
from .device_driver import device_driver_factory

__all__ = [
    'register_task_events',
    'get_task_events',
    'unregister_task_events',
    'check_stop',
    'BaseDeviceDriver',
    'AndroidDriver',
    'DouBaoAndroidAsrDriver',
    'HarmonyDriver',
    'HarmonyXiaoyiTranslationDriver',
    'XiaoyiFace2FaceDriver',
    'XiaoyiSimultaneousInterpretationDriver',
    'HarmonyHardenXiaoyiHuiJiDriver',
    'Xiaoyilivechat',
    'HarmonyHardenXiaoyi_Input_MethodDriver',
    'DeviceDriverFactory',
    'device_driver_factory'
]