# 兼容旧入口，同时确保所有带装饰器的驱动模块在启动时完成注册。
from .utils import register_task_events, get_task_events, unregister_task_events, check_stop
from .base_driver import BaseDeviceDriver
from .android_driver import AndroidDriver
from .android_plaud import PlaudDriver
from .android_doubao_asr_driver import DouBaoAndroidAsrDriver
from .driver_factory import DeviceDriverFactory
from .driver_types import AppType, AppVersion, DevicePlatform, DriverStatus
from .registry import DriverRegistry, DriverNotFoundError, driver_registry, register_driver

try:
    from .harmony_driver import HarmonyDriver
    from .harmony_translation_driver import (
        HarmonyXiaoyiTranslationDriver, XiaoyiFace2FaceDriver,
        XiaoyiSimultaneousInterpretationDriver)
    from .harmony_xiaoyihuiji_driver import HarmonyHardenXiaoyiHuiJiDriver
    from .harmony_xiaoyichat import Xiaoyilivechat
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
    ChatGptVoiceChat = None
    DoubaoChat = None
    HarmonyHardenXiaoyi_Input_MethodDriver = None

device_driver_factory = DeviceDriverFactory()

__all__ = [
    'register_task_events', 'get_task_events', 'unregister_task_events', 'check_stop',
    'BaseDeviceDriver', 'AndroidDriver', 'PlaudDriver', 'DouBaoAndroidAsrDriver',
    'HarmonyDriver', 'HarmonyXiaoyiTranslationDriver', 'XiaoyiFace2FaceDriver',
    'XiaoyiSimultaneousInterpretationDriver', 'HarmonyHardenXiaoyiHuiJiDriver',
    'Xiaoyilivechat', 'ChatGptVoiceChat', 'DoubaoChat',
    'HarmonyHardenXiaoyi_Input_MethodDriver', 'DeviceDriverFactory',
    'device_driver_factory', 'AppType', 'AppVersion', 'DevicePlatform',
    'DriverStatus', 'DriverRegistry', 'DriverNotFoundError', 'driver_registry',
    'register_driver'
]
