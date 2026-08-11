# -*- coding: utf-8 -*-
"""device_service 设备领域实体 re-export。

实体拥有唯一标识（ID），其属性可变。DeviceAggregate 与 PlaybackDeviceAggregate
为聚合根，统一管理设备属性及其边界内的标签集合。

re-export：本包作为各实体子模块的统一入口，便于上层以
``from device_service.domain.entities import DeviceAggregate`` 形式引用。
"""
from device_service.domain.entities.device import (
    DeviceAggregate,
    DeviceSnapshot,
    DeviceTagEntity,
)
from device_service.domain.entities.playback_device import (
    PlaybackDeviceAggregate,
    PlaybackDeviceSnapshot,
)
from device_service.domain.entities.spl import (
    CalibrationHistoryEntity,
    SPLMappingEntity,
)

__all__ = [
    # 被测设备聚合
    "DeviceAggregate",
    "DeviceTagEntity",
    "DeviceSnapshot",
    # 播放设备聚合
    "PlaybackDeviceAggregate",
    "PlaybackDeviceSnapshot",
    # 声压级映射与校准
    "SPLMappingEntity",
    "CalibrationHistoryEntity",
]
