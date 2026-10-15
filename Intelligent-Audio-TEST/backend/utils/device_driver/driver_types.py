"""驱动标识约定 — 消除魔法字符串。

驱动元数据由驱动类自行声明（app_type / version / platform）:
    app_type × version × platform
    'plaud'  × 'v1'    × android
    'doubao' × 'v1'    × harmonyos

约定:
    app_type / version 为驱动自定义字符串，注册表按字符串匹配；
    platform 使用 DevicePlatform 枚举。
    version: 'v1' = 初版/当前稳定版，resolve 优先精确匹配，找不到降级到 'v1'。
"""

from enum import Enum


class DevicePlatform(str, Enum):
    """设备平台维度"""
    ANDROID = "android"
    HARMONYOS = "harmonyos"
    IOS = "ios"


class DriverStatus(str, Enum):
    """驱动运行状态 — 供注册表和管理界面使用"""
    AVAILABLE = "available"
    MISSING_DEPENDENCY = "missing_dependency"
    DISABLED = "disabled"
