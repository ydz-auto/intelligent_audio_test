# -*- coding: utf-8 -*-
"""声压级映射与校准实体 - SPLMapping / CalibrationHistory。

这两个对象在 e2e 测试上下文中均为独立实体（不构成聚合根），用于描述
播放设备的声压级映射与校准历史。本模块为纯领域模型，不依赖
SQLAlchemy/db.Model，亦不包含任何 IO 调用。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class SPLMappingEntity:
    """声压级映射实体

    描述播放设备在特定距离下，目标声压级与数字增益之间的对应关系。
    calibrated_at 为校准发生时间（Unix 时间戳，秒）。
    """
    id: Optional[int] = None
    device_id: Optional[int] = None
    spl_value: float = 0.0
    frequency: int = 1000
    calibrated_at: float = 0.0
    # 扩展属性（与 PO 同名字段，供上层直接访问，避免感知 PO）
    name: str = ""
    description: str = ""
    device_type: str = ""
    distance: float = 1.0
    target_spl: Optional[float] = None
    digital_gain: Optional[float] = None
    test_frequency: int = 1000
    calibration_status: str = "uncalibrated"
    calibration_data: Any = None
    deleted: bool = False
    created_at: Any = None
    updated_at: Any = None


@dataclass
class CalibrationHistoryEntity:
    """校准历史实体

    记录某次校准操作的结果与执行者。calibrated_at 为 Unix 时间戳（秒）。
    """
    id: Optional[int] = None
    device_id: Optional[int] = None
    calibrated_at: float = 0.0
    result: str = ""
    operator: str = ""
