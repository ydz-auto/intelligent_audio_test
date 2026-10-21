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
# hypium 依赖驱动导入与 _HYPium_AVAILABLE 收敛在 driver_factory.py（INT-1167），
# 本模块只 re-export，不再维护第二份 try/except 导入块（含 HarmonyXiaoyiTranslationDriver）。
from .driver_factory import (
    DeviceDriverFactory,
    device_driver_factory,
    HarmonyDriver,
    HarmonyXiaoyiTranslationDriver,
    XiaoyiFace2FaceDriver,
    XiaoyiSimultaneousInterpretationDriver,
    HarmonyHardenXiaoyiHuiJiDriver,
    Xiaoyilivechat,
    XiaoyilivechatV2,
    HarmonyXiaoyiInputMethodDriver,
    DoubaoChat,
    ChatGptVoiceChat,
)

__all__ = [
    "register_task_events", "get_task_events", "unregister_task_events", "check_stop",
    "BaseDeviceDriver", "AndroidDriver", "PlaudDriver", "DouBaoAndroidAsrDriver",
    "HarmonyDriver", "HarmonyXiaoyiTranslationDriver", "XiaoyiFace2FaceDriver",
    "XiaoyiSimultaneousInterpretationDriver", "HarmonyHardenXiaoyiHuiJiDriver",
    "Xiaoyilivechat", "XiaoyilivechatV2", "ChatGptVoiceChat", "DoubaoChat",
    "HarmonyXiaoyiInputMethodDriver", "DeviceDriverFactory",
    "device_driver_factory", "AppType", "AppVersion", "DevicePlatform", "DriverStatus",
    "DriverRegistry", "DriverNotFoundError", "driver_registry", "register_driver",
    "AppDriver", "DriverContext",
]
