# -*- coding: utf-8 -*-
"""INT-67 ApiRmsSplService（audio_service）单测 — SPL→增益换算（08 设计文档 §3.4/§6）

覆盖：
- 线性近似：gain = 10^((target - SPL_LINEAR_APPROX_BASE_DB)/20)，基准配置化
- 校准点插值：np.interp 多点单调插值
- 插值边界配置化：clamp（默认，端点钳制）/ extrapolate（低于最小点线性外推）
- 未配 SPL：gain=1.0 原始不动（不做 RMS 补偿，设计 §6.4）
- 无映射回退：线性近似
- 增益限幅：映射级 min/max 与全局限幅
- RMS 补偿：归一化到 target_rms_dbfs（默认 -30 dBFS，与 E2E calculate_gain_compensation 一致）
- 组合增益：effective = rms_compensate × spl_gain
"""
import math

import numpy as np
import pytest

from shared.utils.config_manager import config_manager
from audio_service.domain.services.api_rms_spl_service import ApiRmsSplService


def _sine_dbfs(dbfs: float, seconds: float = 0.1, rate: int = 16000) -> np.ndarray:
    """RMS 恰为 10^(dbfs/20) 的正弦（幅值 ×√2 补偿正弦 RMS 系数 1/√2）"""
    t = np.arange(int(rate * seconds)) / rate
    amp = 10.0 ** (dbfs / 20.0) * math.sqrt(2.0)
    return (amp * np.sin(2 * np.pi * 440 * t)).astype(np.float32)


class TestLinearApprox:
    def test_base_spl_gain_is_one(self):
        assert ApiRmsSplService._linear_approx(65.0) == pytest.approx(1.0)

    def test_20db_down_is_tenth(self):
        assert ApiRmsSplService._linear_approx(45.0) == pytest.approx(0.1, rel=1e-6)

    def test_base_configurable(self, monkeypatch):
        monkeypatch.setitem(config_manager.config['audio_render'],
                            'spl_linear_approx_base_db', 70.0)
        assert ApiRmsSplService._linear_approx(70.0) == pytest.approx(1.0)
        assert ApiRmsSplService._linear_approx(50.0) == pytest.approx(0.1, rel=1e-6)


class TestSplToGain:
    def test_no_spl_returns_one(self):
        assert ApiRmsSplService.spl_to_gain(7, None, mapping=None) == 1.0
        assert ApiRmsSplService.spl_to_gain(7, None, mapping={'calibration_points': [
            {'target_spl': 65, 'gain_linear': 2.0}]}) == 1.0

    def test_no_mapping_falls_back_to_linear_approx(self):
        assert ApiRmsSplService.spl_to_gain(7, 65.0) == pytest.approx(1.0)
        assert ApiRmsSplService.spl_to_gain(7, 45.0) == pytest.approx(0.1, rel=1e-6)

    def test_uncalibrated_mapping_reference_shift(self):
        mapping = {'reference_spl': 60.0, 'reference_gain_linear': 2.0,
                   'calibration_status': 'uncalibrated',
                   'min_gain_linear': 0.001, 'max_gain_linear': 100.0}
        assert ApiRmsSplService.spl_to_gain_by_mapping(mapping, 60.0) == pytest.approx(2.0)
        assert ApiRmsSplService.spl_to_gain_by_mapping(mapping, 80.0) == pytest.approx(20.0)

    def test_calibrated_interp(self):
        mapping = {
            'calibration_status': 'calibrated',
            'calibration_points': [
                {'target_spl': 45, 'gain_linear': 0.1},
                {'target_spl': 65, 'gain_linear': 1.0},
                {'target_spl': 85, 'gain_linear': 10.0},
            ],
        }
        assert ApiRmsSplService.spl_to_gain_by_mapping(mapping, 55.0) == pytest.approx(0.55)
        assert ApiRmsSplService.spl_to_gain_by_mapping(mapping, 65.0) == pytest.approx(1.0)

    def test_interp_clamp_boundary_default(self):
        mapping = {
            'calibration_status': 'calibrated',
            'calibration_points': [
                {'target_spl': 55, 'gain_linear': 0.3},
                {'target_spl': 75, 'gain_linear': 3.0},
            ],
        }
        # clamp：低于最小点取最小点增益（np.interp 端点钳制）
        assert ApiRmsSplService.spl_to_gain_by_mapping(mapping, 40.0) == pytest.approx(0.3)
        assert ApiRmsSplService.spl_to_gain_by_mapping(mapping, 90.0) == pytest.approx(3.0)

    def test_interp_extrapolate_boundary(self, monkeypatch):
        monkeypatch.setitem(config_manager.config['audio_render'],
                            'spl_interp_boundary', 'extrapolate')
        mapping = {
            'calibration_status': 'calibrated',
            'calibration_points': [
                {'target_spl': 55, 'gain_linear': 1.0},
                {'target_spl': 75, 'gain_linear': 1.2},
            ],
        }
        # 低于最小点：增益域端点线性外推（斜率 0.01/dB，35 dB → 1.0 - 0.2 = 0.8）
        assert ApiRmsSplService.spl_to_gain_by_mapping(mapping, 35.0) == pytest.approx(0.8, rel=1e-6)
        # 高于最大点仍取端点
        assert ApiRmsSplService.spl_to_gain_by_mapping(mapping, 90.0) == pytest.approx(1.2)
        # 外推为负增益时回退最小点增益（对齐 E2E SPLMappingService 防负增益）
        negative_mapping = {
            'calibration_status': 'calibrated',
            'calibration_points': [
                {'target_spl': 55, 'gain_linear': 0.3},
                {'target_spl': 75, 'gain_linear': 3.0},
            ],
        }
        assert ApiRmsSplService.spl_to_gain_by_mapping(negative_mapping, 35.0) == pytest.approx(0.3)


class TestGainLimit:
    def test_mapping_level_limit(self):
        mapping = {'reference_spl': 65.0, 'reference_gain_linear': 1.0,
                   'min_gain_linear': 0.05, 'max_gain_linear': 5.0}
        assert ApiRmsSplService.spl_to_gain_by_mapping(mapping, 25.0) == pytest.approx(0.05)
        assert ApiRmsSplService.spl_to_gain_by_mapping(mapping, 105.0) == pytest.approx(5.0)

    def test_global_limit_backstop(self):
        # 无映射级限幅时，全局限幅（-70dB ~ -25dB 增益窗）兜底
        mapping = {'reference_spl': 65.0, 'reference_gain_linear': 1.0}
        gain = ApiRmsSplService.spl_to_gain_by_mapping(mapping, 1000.0)
        assert gain <= 10 ** ((-5.0 - (-30.0)) / 20.0) + 1e-9


class TestRmsCompensate:
    def test_at_target_dbfs_gain_is_one(self):
        samples = _sine_dbfs(-30.0)
        assert ApiRmsSplService.rms_compensate(samples) == pytest.approx(1.0, rel=1e-6)

    def test_quiet_signal_boosted(self):
        samples = _sine_dbfs(-60.0)
        assert ApiRmsSplService.rms_compensate(samples) == pytest.approx(10 ** 1.5, rel=1e-6)

    def test_silent_signal_no_compensation(self):
        assert ApiRmsSplService.rms_compensate(np.zeros(1600, dtype=np.float32)) == 1.0
        assert ApiRmsSplService.rms_compensate(np.zeros(0, dtype=np.float32)) == 1.0

    def test_target_rms_configurable(self, monkeypatch):
        monkeypatch.setitem(config_manager.config['audio_render'],
                            'target_rms_dbfs', -20.0)
        samples = _sine_dbfs(-30.0)
        assert ApiRmsSplService.rms_compensate(samples) == pytest.approx(10 ** 0.5, rel=1e-6)


class TestComputeSourceGain:
    def test_no_spl_passthrough(self):
        quiet = _sine_dbfs(-60.0)
        assert ApiRmsSplService.compute_source_gain(quiet, None, mapping=None) == 1.0

    def test_effective_is_comp_times_spl_gain(self):
        samples = _sine_dbfs(-60.0)
        effective = ApiRmsSplService.compute_source_gain(samples, 65.0, mapping=None)
        assert effective == pytest.approx(
            ApiRmsSplService.rms_compensate(samples) * 1.0, rel=1e-6)

    def test_mapped_gain_applied(self):
        samples = _sine_dbfs(-30.0)
        mapping = {'reference_spl': 55.0, 'reference_gain_linear': 1.0}
        effective = ApiRmsSplService.compute_source_gain(samples, 55.0, mapping=mapping)
        assert effective == pytest.approx(1.0, rel=1e-6)
