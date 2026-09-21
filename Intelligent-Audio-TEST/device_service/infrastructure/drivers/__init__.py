"""设备驱动包统一入口。"""

from .utils import (
    register_task_events,
    get_task_events,
    unregister_task_events,
    check_stop,
)
from .base_driver import BaseDeviceDriver
from .android_driver import AndroidDriver
from .android_plaud import PlaudDriver
from .android_doubao_asr_driver import DouBaoAndroidAsrDriver
from .driver_types import AppType, AppVersion, DevicePlatform, DriverStatus
from .registry import DriverRegistry, DriverNotFoundError, driver_registry, register_driver
from .contracts import AppDriver, DriverContext

# 导入全部驱动模块，确保装饰器注册在服务启动时完成。
try:
    from .harmony_driver import HarmonyDriver
    from .harmony_translation_driver import (
        HarmonyXiaoyiTranslationDriver,
        XiaoyiFace2FaceDriver,
        XiaoyiSimultaneousInterpretationDriver,
    )
    from .harmony_xiaoyihuiji_driver import HarmonyHardenXiaoyiHuiJiDriver
    from .harmony_xiaoyichat import Xiaoyilivechat
    from .harmony_xiaoyilivechat import XiaoyilivechatV2
    from .harmony_chatgpt import ChatGptVoiceChat
    from .harmony_doubaochat import DoubaoChat
    from .harmony_asr_driver import HarmonyHardenXiaoyi_Input_MethodDriver
except ImportError:
    HarmonyDriver = None
    HarmonyXiaoyiTranslationDriver = None
    XiaoyiFace2FaceDriver = None
    XiaoyiSimultaneousInterpretationDriver = None
    HarmonyHardenXiaoyiHuiJiDriver = None
    Xiaoyilivechat = None
    XiaoyilivechatV2 = None
    ChatGptVoiceChat = None
    DoubaoChat = None
    HarmonyHardenXiaoyi_Input_MethodDriver = None

from .device_driver import DeviceDriverFactory, device_driver_factory

__all__ = [
    "register_task_events", "get_task_events", "unregister_task_events", "check_stop",
    "BaseDeviceDriver", "AndroidDriver", "PlaudDriver", "DouBaoAndroidAsrDriver",
    "HarmonyDriver", "HarmonyXiaoyiTranslationDriver", "XiaoyiFace2FaceDriver",
    "XiaoyiSimultaneousInterpretationDriver", "HarmonyHardenXiaoyiHuiJiDriver",
    "Xiaoyilivechat", "XiaoyilivechatV2", "ChatGptVoiceChat", "DoubaoChat",
    "HarmonyHardenXiaoyi_Input_MethodDriver", "DeviceDriverFactory",
    "device_driver_factory", "AppType", "AppVersion", "DevicePlatform", "DriverStatus",
    "DriverRegistry", "DriverNotFoundError", "driver_registry", "register_driver",
    "AppDriver", "DriverContext",
]
