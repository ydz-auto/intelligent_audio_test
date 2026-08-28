"""驱动类型枚举 — 消除魔法字符串，统一驱动标识。

三维正交标识一个驱动:
    AppType     × AppVersion × DevicePlatform
    'plaud'     × 'v1'       × 'android'
    'xiaoyi_livechat' × 'v2' × 'harmonyos'
"""

from enum import Enum


class DevicePlatform(str, Enum):
    """设备平台维度"""
    ANDROID = "android"
    HARMONYOS = "harmonyos"
    IOS = "ios"


class AppType(str, Enum):
    """应用类型维度 — 同 App 多版本共享同一 app_type"""
    # 基础平台驱动（无特定 App）
    ANDROID_BASE = "android_base"
    HARMONY_BASE = "harmony_base"

    # 专用应用驱动
    PLAUD = "plaud"
    DOUBAO_ASR = "doubao_asr"
    XIAOYI_FACE2FACE = "xiaoyi_face2face"
    XIAOYI_SIMULTANEOUS = "xiaoyi_simultaneous"
    XIAOYI_HUIJI = "xiaoyi_huiji"
    XIAOYI_LIVECHAT = "xiaoyi_livechat"
    XIAOYI_INPUT_METHOD = "xiaoyi_input_method"


class AppVersion(str, Enum):
    """应用版本维度 — 同 App 多版本适配

    约定:
        V1   = 初版/当前稳定版
        V2   = 第二版
        LATEST = 别名，resolve 时优先精确匹配，找不到降级到 V1
    """
    V1 = "v1"
    V2 = "v2"
    LATEST = "latest"


class DriverStatus(str, Enum):
    """驱动运行状态 — 供注册表和管理界面使用"""
    AVAILABLE = "available"
    MISSING_DEPENDENCY = "missing_dependency"
    DISABLED = "disabled"
