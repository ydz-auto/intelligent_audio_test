# -*- coding: utf-8 -*-
"""ApiRmsSplService — 被测 API 数字域 RMS→SPL 口径服务（INT-61）

与 E2E SPLMappingService（audio_service，物理域）对称的 API 类数字域实现：
- 输入侧：spl_to_gain(api_id, target_spl) — 推送用户音频时按目标 SPL 求增益
- 输出侧：calculate_rms_dbfs(pcm) + rms_dbfs_to_spl — AI 输出音频实测口径，
  与 E2E/API 结果对称可比

有校准点时按 SPL→gain 线性插值；无映射/未校准时线性近似
gain = 10^((target - 65) / 20)；结果经映射限幅。纯计算，查表经仓储端口注入。
"""
from __future__ import annotations

import logging
from typing import Optional

import numpy as np

from api_test_service.domain.entities.api_rms_spl_mapping import ApiRmsSplMapping

logger = logging.getLogger(__name__)


class ApiRmsSplService:
    """被测 API RMS→SPL 口径服务（域服务，无 IO）"""

    BASE_LEVEL_DB = -30.0      # RMS 补偿基准：归一化到 -30 dBFS
    MAX_OUTPUT_DB = -5.0       # 防削波上限
    REFERENCE_SPL = 65.0       # 线性近似基准 SPL

    def __init__(self, repository=None):
        self._repository = repository

    # ── 输入侧：目标 SPL → 推送增益 ──
    def spl_to_gain(self, api_id, target_spl: float,
                    mapping: Optional[ApiRmsSplMapping] = None) -> float:
        """按被测 API 的映射计算目标 SPL 对应线性增益。

        优先使用调用方传入的 mapping（避免重复查表）；
        无映射时线性近似：gain = 10^((target - 65) / 20)。
        """
        if mapping is None and self._repository is not None and api_id is not None:
            mapping = self._repository.get_default_mapping(api_id)
        if mapping is None:
            return self.linear_approx(target_spl)
        return self.spl_to_gain_by_mapping(mapping, target_spl)

    @staticmethod
    def spl_to_gain_by_mapping(mapping: ApiRmsSplMapping, target_spl: float) -> float:
        """直接用映射对象计算（避免重复查 DB）"""
        gain = ApiRmsSplService._calculate_gain(mapping, target_spl)
        return ApiRmsSplService._apply_gain_limit(mapping, gain)

    @staticmethod
    def _calculate_gain(mapping: ApiRmsSplMapping, target_spl: float) -> float:
        """有校准点 → np.interp 线性插值；否则参考增益 × 10^(diff/20)"""
        if mapping.is_calibrated():
            points = sorted(mapping.calibration_points, key=lambda p: p.target_spl)
            xs = [p.target_spl for p in points]
            ys = [p.gain_linear for p in points]
            return float(np.interp(target_spl, xs, ys))
        diff = target_spl - mapping.reference_spl
        return mapping.reference_gain_linear * (10.0 ** (diff / 20.0))

    @staticmethod
    def _apply_gain_limit(mapping: ApiRmsSplMapping, gain_linear: float) -> float:
        return float(min(max(gain_linear, mapping.min_gain_linear), mapping.max_gain_linear))

    @staticmethod
    def linear_approx(target_spl: float) -> float:
        """无校准时的线性近似：以 65 dB ↔ 1.0 为基准"""
        return 10.0 ** ((target_spl - ApiRmsSplService.REFERENCE_SPL) / 20.0)

    # ── 输出侧：AI 音频实测口径 ──
    @staticmethod
    def calculate_rms_dbfs(pcm_bytes: bytes) -> float:
        """计算 PCM(s16) 的 RMS dBFS；静音返回 -120.0"""
        if not pcm_bytes:
            return -120.0
        samples = np.frombuffer(pcm_bytes[: len(pcm_bytes) // 2 * 2], dtype=np.int16)
        if samples.size == 0:
            return -120.0
        x = samples.astype(np.float64) / 32768.0
        rms = float(np.sqrt(np.mean(np.square(x))))
        if rms <= 0.0:
            return -120.0
        return round(20.0 * np.log10(rms), 2)

    @staticmethod
    def rms_dbfs_to_spl(rms_dbfs: float, mapping: Optional[ApiRmsSplMapping] = None) -> float:
        """实测 RMS dBFS → 口径 SPL：以映射参考点（或 65 dB ↔ -30 dBFS 基准）平移。

        与输入侧同一映射对象，保证输入/输出口径对称：
        spl = reference_spl + (rms_dbfs - BASE_LEVEL_DB)
        """
        ref_spl = mapping.reference_spl if mapping is not None else ApiRmsSplService.REFERENCE_SPL
        return round(ref_spl + (rms_dbfs - ApiRmsSplService.BASE_LEVEL_DB), 2)

    # ── 推送链路组合：RMS 补偿 + SPL 增益（与 E2E effective = rms_comp × spl_gain 对称）──
    def compute_push_gain(self, pcm_bytes: bytes, api_id,
                          target_spl: float,
                          mapping: Optional[ApiRmsSplMapping] = None) -> float:
        """计算单源推送增益：RMS 补偿（归一化到 -30 dBFS）× SPL 增益，防削波限幅。

        与 E2E 增益链路 effective = audio_gain × GLOBAL_SAFE × gain_comp 对称：
        Realtime 侧 effective = rms_compensate × spl_gain。
        """
        rms_dbfs = self.calculate_rms_dbfs(pcm_bytes)
        rms_comp = (
            10.0 ** ((self.BASE_LEVEL_DB - rms_dbfs) / 20.0)
            if rms_dbfs > -120.0 else 1.0
        )
        spl_gain = self.spl_to_gain(api_id, target_spl, mapping=mapping)
        effective = rms_comp * spl_gain
        # 防削波：补偿后能量不超过 MAX_OUTPUT_DB
        max_allowed = 10.0 ** ((self.MAX_OUTPUT_DB - self.BASE_LEVEL_DB) / 20.0)
        return float(min(effective, max_allowed))
