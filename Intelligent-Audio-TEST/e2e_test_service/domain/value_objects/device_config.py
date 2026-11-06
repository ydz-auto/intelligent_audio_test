# -*- coding: utf-8 -*-
"""设备配置值对象 - DeviceConfig。

值对象是不可变的、无唯一标识的业务概念。DeviceConfig 描述被测/播放设备
的配置参数集合。本模块为纯领域模型，不涉及任何 IO。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass(frozen=True)
class DeviceConfig:
    """设备配置值对象

    以不可变字典形式承载设备配置（如采样率、通道索引、增益、提示词配置等）。
    使用默认工厂避免可变默认参数陷阱。
    """
    sample_rate: int = 48000
    channel_index: int = 0
    gain: float = 1.0
    extra: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """构造后校验：采样率与增益必须为正"""
        if self.sample_rate <= 0:
            raise ValueError("DeviceConfig.sample_rate 必须为正数")
        if self.gain < 0:
            raise ValueError("DeviceConfig.gain 不能为负数")

    def merge(self, other: "DeviceConfig") -> "DeviceConfig":
        """返回与另一配置合并后的新值对象（other 优先）"""
        merged_extra = {**self.extra, **other.extra}
        return DeviceConfig(
            sample_rate=other.sample_rate or self.sample_rate,
            channel_index=other.channel_index or self.channel_index,
            gain=other.gain if other.gain != 1.0 else self.gain,
            extra=merged_extra,
        )
