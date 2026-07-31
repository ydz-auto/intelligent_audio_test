# -*- coding: utf-8 -*-
"""E2E 测试领域值对象。

值对象是不可变的、无唯一标识的业务概念。本模块仅包含纯数据结构与
校验逻辑，不涉及任何 IO（数据库、网络、文件系统）。
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class DeviceId:
    """设备唯一标识值对象"""
    value: int

    def __post_init__(self):
        if self.value is None or self.value < 0:
            raise ValueError("DeviceId 不能为空或负数")

    def __str__(self):
        return str(self.value)


@dataclass(frozen=True)
class AudioConfig:
    """音频播放配置值对象"""
    file_path: str
    device_index: Optional[int] = None
    channel_index: int = 0
    gain: float = 1.0
    loop: bool = False

    def __post_init__(self):
        if not self.file_path:
            raise ValueError("AudioConfig.file_path 不能为空")


@dataclass(frozen=True)
class TestResult:
    """单次测试结果值对象"""
    task_id: str
    tc_rel_id: str
    device_id: str
    round_number: int
    success: bool
    raw_output: Optional[str] = None
    error_message: Optional[str] = None
    algorithm_type: str = "translation"

    @property
    def is_success(self) -> bool:
        return self.success
