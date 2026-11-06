"""驱动类型标识 — 封闭集合枚举 + 驱动状态。

AppType / AppVersion 为**自定义开放值**（每个新 App 驱动自声明字符串，如
"plaud"/"xiaoyi_huiji"，V9.7.10 语义），不做枚举封闭——枚举化后每新增一个
App 都要改本文件，违背「驱动自声明元数据」设计（INT-1167 追加裁定 2026-10-21）。
仅保留封闭集合 DevicePlatform 与驱动运行状态 DriverStatus。
"""

from enum import Enum


class DevicePlatform(str, Enum):
    """设备平台维度 — 封闭集合（android/harmonyos/ios）"""
    ANDROID = "android"
    HARMONYOS = "harmonyos"
    IOS = "ios"


class DriverStatus(str, Enum):
    """驱动运行状态 — 供注册表和管理界面使用"""
    AVAILABLE = "available"
    MISSING_DEPENDENCY = "missing_dependency"
    DISABLED = "disabled"
