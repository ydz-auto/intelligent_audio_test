# -*- coding: utf-8 -*-
"""ApiRmsSplService — 被测 API 数字域 RMS→SPL 口径服务（INT-67，08 设计文档 §3.4）

与 E2E SPLMappingService（audio_service，物理设备域）对称的 API 类数字域实现，
三种 API 模式（非实时/流式/Realtime）通用。混音 Step 3b 在 audio_service 进程内
执行，映射数据由消费端随 render_config 传入（api 1:N ApiRmsSplMapping 归属
api_test_service，audio_service 不反向依赖）：

- 有校准点 → target_spl↔gain_linear 线性插值（np.interp，边界行为配置化）
- 无校准点 → 参考基准 × 10^(diff/20)
- 无映射   → 线性近似 gain = 10^((target - SPL_LINEAR_APPROX_BASE_DB) / 20)
- 未配 SPL → gain = 1.0，原始 RMS 不变（格式适配仍执行，设计 §6.4）

结果经映射级/全局增益限幅，防配置错误导致静音/爆音。
"""
from __future__ import annotations

import numpy as np

from shared.utils.config_manager import config_manager

# 全局增益限幅（与 E2E SPLMappingService 口径一致：基准 -30 dBFS，上限 -5 dBFS）
GLOBAL_BASE_LEVEL_DB = -30.0
GLOBAL_MAX_OUTPUT_DB = -5.0
GLOBAL_MIN_GAIN_LINEAR = 10 ** (-70.0 / 20.0)
GLOBAL_MAX_GAIN_LINEAR = 10 ** ((GLOBAL_MAX_OUTPUT_DB - GLOBAL_BASE_LEVEL_DB) / 20.0)


def _render_cfg(key: str, default):
    return config_manager.get_value('audio_render', key, default)


class ApiRmsSplService:
    """被测 API RMS→SPL 口径服务（域服务，纯计算；映射数据驱动，无 IO）"""

    LINEAR_APPROX_BASE_DB_KEY = 'spl_linear_approx_base_db'
    INTERP_BOUNDARY_KEY = 'spl_interp_boundary'   # clamp | extrapolate
    TARGET_RMS_DBFS_KEY = 'target_rms_dbfs'

    @staticmethod
    def linear_approx_base_db() -> float:
        """SPL_LINEAR_APPROX_BASE_DB：线性近似基准 SPL（默认 65 dB ↔ 1.0）"""
        return float(_render_cfg(ApiRmsSplService.LINEAR_APPROX_BASE_DB_KEY, 65.0))

    @staticmethod
    def target_rms_dbfs() -> float:
        """RMS 补偿目标（归一化基准，默认 -30 dBFS，与 E2E calculate_gain_compensation 一致）"""
        return float(_render_cfg(ApiRmsSplService.TARGET_RMS_DBFS_KEY, -30.0))

    # ── Step 3b：目标 SPL → 线性增益 ──

    @staticmethod
    def spl_to_gain(api_id, target_spl, mapping: dict = None) -> float:
        """按被测 API 映射计算增益；无映射时线性近似。

        mapping 为 render_config 传入的映射数据 dict：
        {calibration_status, calibration_points: [{target_spl, gain_linear}],
         reference_spl, reference_gain_linear, min_gain_linear, max_gain_linear}
        """
        if target_spl is None:
            return 1.0
        if not mapping:
            return ApiRmsSplService._linear_approx(target_spl)
        return ApiRmsSplService.spl_to_gain_by_mapping(mapping, target_spl)

    @staticmethod
    def spl_to_gain_by_mapping(mapping: dict, target_spl: float) -> float:
        """用随请求传入的映射数据计算（消费端预载，避免服务端反向查库）"""
        gain = ApiRmsSplService._calculate_gain(mapping, target_spl)
        return ApiRmsSplService._apply_gain_limit(mapping, gain)

    @staticmethod
    def _calculate_gain(mapping: dict, target_spl: float) -> float:
        """有校准点 → np.interp 线性插值（边界行为配置化）；否则参考基准平移"""
        status = str(mapping.get('calibration_status', ''))
        points = mapping.get('calibration_points') or []
        if status == 'calibrated' and points:
            valid = [p for p in points
                     if isinstance(p, dict) and p.get('target_spl') is not None
                     and p.get('gain_linear') is not None]
            if valid:
                ordered = sorted(valid, key=lambda p: p['target_spl'])
                xs = [float(p['target_spl']) for p in ordered]
                ys = [float(p['gain_linear']) for p in ordered]
                return ApiRmsSplService._interp_with_boundary(xs, ys, float(target_spl))
        reference_spl = float(mapping.get('reference_spl', 65.0) or 65.0)
        reference_gain = float(mapping.get('reference_gain_linear', 1.0) or 1.0)
        return reference_gain * (10.0 ** ((float(target_spl) - reference_spl) / 20.0))

    @staticmethod
    def _interp_with_boundary(xs, ys, target_spl: float) -> float:
        """插值边界行为（audio_render.spl_interp_boundary）：

        - clamp（默认）：np.interp 端点钳制（低于最小点取最小点增益）
        - extrapolate：低于最小点按端点线性外推（对齐 E2E SPLMappingService），
          外推非正增益回退最小点增益；高于最大点两端点一致取端点增益
        """
        boundary = str(_render_cfg(ApiRmsSplService.INTERP_BOUNDARY_KEY, 'clamp')).lower()
        if boundary == 'extrapolate' and target_spl < xs[0]:
            if len(xs) >= 2:
                coeffs = np.polyfit(xs, ys, 1)
                extrapolated = float(np.polyval(coeffs, target_spl))
                if extrapolated > 0:
                    return extrapolated
            return ys[0]
        return float(np.interp(target_spl, xs, ys))

    @staticmethod
    def _apply_gain_limit(mapping: dict, gain_linear: float) -> float:
        """限幅：映射级 min/max 优先，全局限幅兜底"""
        mapping_min = mapping.get('min_gain_linear')
        mapping_max = mapping.get('max_gain_linear')
        lower = float(mapping_min) if mapping_min is not None else GLOBAL_MIN_GAIN_LINEAR
        upper = float(mapping_max) if mapping_max is not None else GLOBAL_MAX_GAIN_LINEAR
        return float(min(max(gain_linear, min(lower, upper)), max(lower, upper)))

    @staticmethod
    def _linear_approx(target_spl: float) -> float:
        """无映射时的线性近似：gain = 10^((target - SPL_LINEAR_APPROX_BASE_DB) / 20)"""
        return 10.0 ** ((float(target_spl) - ApiRmsSplService.linear_approx_base_db()) / 20.0)

    # ── Step 3a：RMS 补偿（归一化到目标 dBFS） ──

    @staticmethod
    def rms_compensate(samples: np.ndarray) -> float:
        """float32 [-1,1] 采样序列的 RMS 补偿增益（归一化到 target_rms_dbfs）。

        current_db = 20·log10(rms)；gain_db = target - current；静音不补偿。
        """
        if samples is None or samples.size == 0:
            return 1.0
        rms = float(np.sqrt(np.mean(np.square(samples.astype(np.float64)))))
        if rms <= 0.0:
            return 1.0
        current_db = 20.0 * np.log10(rms)
        gain_db = ApiRmsSplService.target_rms_dbfs() - current_db
        return float(10.0 ** (gain_db / 20.0))

    @staticmethod
    def compute_source_gain(samples: np.ndarray, target_spl, mapping: dict = None) -> float:
        """单源有效增益 = rms_compensate × spl_gain（设计 §6.3 API 链路）。

        未配 SPL（target_spl is None）→ 1.0 原始不动（不补偿，设计 §6.4）。
        """
        if target_spl is None:
            return 1.0
        return float(ApiRmsSplService.rms_compensate(samples)
                     * ApiRmsSplService.spl_to_gain(None, target_spl, mapping=mapping))
