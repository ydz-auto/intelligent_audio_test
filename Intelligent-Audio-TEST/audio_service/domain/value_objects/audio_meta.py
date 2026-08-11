# -*- coding: utf-8 -*-
"""音频元数据值对象 - AudioMeta。

值对象是不可变的、无唯一标识的业务概念。AudioMeta 描述音频文件的核心
物理元数据。本模块为纯领域模型，不涉及任何 IO。
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AudioMeta:
    """音频元数据值对象

    承载音频文件的物理属性：时长、采样率、声道数、格式。
    所有字段为不可变标量，便于跨层安全传递。
    """
    duration: float
    sample_rate: int
    channels: int
    format: str

    def __post_init__(self) -> None:
        """构造后校验：核心字段必须合法"""
        if self.duration < 0:
            raise ValueError("AudioMeta.duration 不能为负数")
        if self.sample_rate <= 0:
            raise ValueError("AudioMeta.sample_rate 必须为正数")
        if self.channels <= 0:
            raise ValueError("AudioMeta.channels 必须为正数")
        if not self.format:
            raise ValueError("AudioMeta.format 不能为空")

    @property
    def is_stereo(self) -> bool:
        """是否为立体声"""
        return self.channels >= 2
