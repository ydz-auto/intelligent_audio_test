# -*- coding: utf-8 -*-
"""ApiRmsSplMapping 领域实体 — 被测 API 的数字域 RMS→SPL 映射（INT-61）

与 E2E SPLMapping（物理设备 dB SPL → gain）对称：本实体挂在被测 API 上（1:N），
语义为被测 API 数字域 dB → gain（校准 API 输入灵敏度）。纯逻辑，无 IO 依赖。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from shared.models.common_enums import CalibrationStatus


@dataclass
class CalibrationPoint:
    """单条校准测量点：目标 SPL ↔ 线性增益 ↔ 实测 RMS dBFS"""

    target_spl: float
    gain_linear: float
    rms_dbfs: Optional[float] = None


@dataclass
class ApiRmsSplMapping:
    """被测 API RMS→SPL 映射实体

    - reference_spl / reference_gain_linear：未校准时的参考基准（65 dB / 1.0）
    - calibration_points：有校准点时按 SPL→gain 线性插值
    - min/max_gain_linear：增益限幅，防配置错误导致静音/爆音
    """

    id: Optional[int]
    api_id: int
    name: str = ''
    vendor: str = ''
    protocol: str = 'websocket'
    reference_spl: float = 65.0
    reference_gain_linear: float = 1.0
    calibration_status: str = CalibrationStatus.UNCALIBRATED.value
    calibration_points: List[CalibrationPoint] = field(default_factory=list)
    min_gain_linear: float = 0.001
    max_gain_linear: float = 10.0
    deleted: bool = False

    def is_calibrated(self) -> bool:
        return (
            self.calibration_status == CalibrationStatus.CALIBRATED.value
            and bool(self.calibration_points)
        )

    def replace_calibration_points(self, points: List[CalibrationPoint]) -> None:
        """以本次校准测得的完整点集替换既有校准点并自动置为已校准

        校准是一次完整测量会话：新点集整体取代旧曲线（而非追加），
        避免重复校准在同一 target_spl 上累积重复点破坏插值。
        """
        self.calibration_points = list(points)
        self.calibration_status = CalibrationStatus.CALIBRATED.value
