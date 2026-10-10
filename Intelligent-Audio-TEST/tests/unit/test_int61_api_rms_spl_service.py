# -*- coding: utf-8 -*-
"""INT-61 ApiRmsSplService 单测 — 数字域 RMS→SPL 口径

覆盖：
- 线性近似（无映射）：gain = 10^((spl-65)/20)，65 dB ↔ 1.0
- 校准点插值：np.interp 单调插值
- 增益限幅：min/max_gain_linear 裁剪
- RMS dBFS：正弦/静音/空载荷
- 输出口径：rms_dbfs_to_spl 以映射参考平移（输入/输出同映射对象，口径对称）
- 推送增益组合：RMS 补偿 × SPL 增益，防削波上限
- 对称对照：与 E2E 增益链路公式对称（effective = rms_comp × spl_gain）
"""
import math

import numpy as np

from api_test_service.domain.entities.api_rms_spl_mapping import (
    ApiRmsSplMapping,
    CalibrationPoint,
)
from api_test_service.domain.services.api_rms_spl_service import ApiRmsSplService


class _RepoStub:
    def __init__(self, mapping):
        self._mapping = mapping

    def get_default_mapping(self, api_id):
        return self._mapping


def _uncalibrated_mapping(**kw):
    return ApiRmsSplMapping(id=1, api_id=7, **kw)


def _calibrated_mapping():
    return ApiRmsSplMapping(
        id=2, api_id=7,
        calibration_status='calibrated',
        calibration_points=[
            CalibrationPoint(target_spl=45, gain_linear=0.1),
            CalibrationPoint(target_spl=65, gain_linear=1.0),
            CalibrationPoint(target_spl=85, gain_linear=10.0),
        ],
    )


class TestLinearApprox:
    def test_reference_spl_gain_is_one(self):
        assert ApiRmsSplService.linear_approx(65.0) == pytest_approx(1.0)

    def test_minus_10db_is_tenth(self):
        assert abs(ApiRmsSplService.linear_approx(55.0) - 10 ** (-10 / 20)) < 1e-9

    def test_plus_20db_is_tenfold(self):
        assert abs(ApiRmsSplService.linear_approx(85.0) - 10.0) < 1e-9

    def test_spl_to_gain_without_mapping_uses_linear_approx(self):
        service = ApiRmsSplService(repository=None)
        assert abs(service.spl_to_gain(7, 55.0) - 10 ** (-10 / 20)) < 1e-9

    def test_spl_to_gain_with_repository(self):
        service = ApiRmsSplService(repository=_RepoStub(_uncalibrated_mapping()))
        assert abs(service.spl_to_gain(7, 65.0) - 1.0) < 1e-9


class TestCalibratedInterp:
    def test_exact_points(self):
        service = ApiRmsSplService()
        gain = service.spl_to_gain_by_mapping(_calibrated_mapping(), 65.0)
        assert abs(gain - 1.0) < 1e-9

    def test_midpoint_interpolation(self):
        service = ApiRmsSplService()
        gain = service.spl_to_gain_by_mapping(_calibrated_mapping(), 55.0)
        # np.interp 线性插值：45→0.1 与 65→1.0 之间 55 → 0.55
        assert abs(gain - 0.55) < 1e-9

    def test_out_of_range_clamps_to_limit(self):
        service = ApiRmsSplService()
        gain = service.spl_to_gain_by_mapping(_calibrated_mapping(), 120.0)
        assert gain == pytest_approx(10.0)  # max_gain_linear


class TestGainLimit:
    def test_uncalibrated_gain_clamped(self):
        mapping = _uncalibrated_mapping(max_gain_linear=2.0)
        gain = ApiRmsSplService.spl_to_gain_by_mapping(mapping, 95.0)  # 线性近似 10^1.5
        assert gain == pytest_approx(2.0)


class TestRmsDbfs:
    def test_silence_is_minus_120(self):
        assert ApiRmsSplService.calculate_rms_dbfs(b'\x00\x00' * 100) == -120.0

    def test_empty_is_minus_120(self):
        assert ApiRmsSplService.calculate_rms_dbfs(b'') == -120.0

    def test_full_scale_square_wave(self):
        # 交替 ±32767 → RMS ≈ 1.0 → 0 dBFS
        pcm = np.array([32767, -32767] * 500, dtype='<i2').tobytes()
        assert abs(ApiRmsSplService.calculate_rms_dbfs(pcm)) < 0.01

    def test_known_amplitude(self):
        # 幅值 0.5 方波 → RMS 0.5 → 约 -6.02 dBFS
        pcm = np.array([16384, -16384] * 500, dtype='<i2').tobytes()
        assert abs(ApiRmsSplService.calculate_rms_dbfs(pcm) - (-6.02)) < 0.01


class TestOutputSpl:
    def test_reference_level_maps_to_reference_spl(self):
        """输出口径对称：-30 dBFS（RMS 补偿基准）→ 映射参考 SPL"""
        assert ApiRmsSplService.rms_dbfs_to_spl(-30.0) == pytest_approx(65.0)

    def test_mapping_reference_shift(self):
        mapping = _uncalibrated_mapping(reference_spl=70.0)
        assert ApiRmsSplService.rms_dbfs_to_spl(-30.0, mapping) == pytest_approx(70.0)

    def test_plus_6db_shift(self):
        assert ApiRmsSplService.rms_dbfs_to_spl(-24.0) == pytest_approx(71.0)


class TestPushGain:
    def test_rms_compensation_times_spl_gain(self):
        """对称对照：effective = rms_comp × spl_gain（与 E2E 增益链路同构）"""
        service = ApiRmsSplService(repository=_RepoStub(_uncalibrated_mapping()))
        # 幅值 0.5 方波：RMS -6.02 dBFS → rms_comp = 10^((-30 - (-6.02))/20) ≈ 0.0631
        pcm = np.array([16384, -16384] * 500, dtype='<i2').tobytes()
        gain = service.compute_push_gain(pcm, api_id=7, target_spl=65.0)
        expected_rms_comp = 10 ** ((-30.0 - (-6.02)) / 20.0)
        assert abs(gain - expected_rms_comp * 1.0) < 1e-6

    def test_push_gain_never_exceeds_anti_clip_ceiling(self):
        """防削波：补偿后能量不超过 -5 dBFS 上限"""
        service = ApiRmsSplService(repository=_RepoStub(_uncalibrated_mapping()))
        pcm = np.array([32767, -32767] * 500, dtype='<i2').tobytes()
        gain = service.compute_push_gain(pcm, api_id=7, target_spl=100.0)
        max_allowed = 10 ** ((-5.0 - (-30.0)) / 20.0)
        assert gain <= max_allowed + 1e-9


def pytest_approx(value, tol=1e-6):
    class _Approx:
        def __eq__(self, other):
            return abs(other - value) <= tol

        def __repr__(self):
            return f'≈{value}'
    return _Approx()
