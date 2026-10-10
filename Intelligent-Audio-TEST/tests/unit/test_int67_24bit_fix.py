# -*- coding: utf-8 -*-
"""INT-67 24bit 防误解析回归测试 — 物理链路三处解析点

背景：24bit 音频原先落 else 分支按 int16 解析（audio_driver.calculate_gain_compensation
与 _create_multi_callback），_resample_to_file 无条件按 int16 读帧——24bit 素材
RMS 补偿、播放混音、文件级重采样三处全部产生错误幅度。

修复：三处统一走 AudioFormatAdapter.to_int16_scale（3 字节小端逐字节重组）。

覆盖：
- calculate_gain_compensation 对 24bit WAV 计算出正确 RMS 增益（与 16bit 等效幅度一致）
- _resample_to_file 对 24bit 源按实际采样宽度解析（输出长度与幅度正确）
"""
import io
import math
import os
import wave

import numpy as np
import pytest

# audio_driver → shared.infrastructure.storage → BaseConfig 要求 OSS 凭据环境变量，
# 测试环境仅需可导入（不真正访问 OSS），缺省占位
os.environ.setdefault('OSS_ACCESS_KEY', 'test-access')
os.environ.setdefault('OSS_SECRET_KEY', 'test-secret')

from audio_service.infrastructure.audio.audio_driver import AudioDriver
from audio_service.infrastructure.audio._engine_audio_prepare_mixin import (
    EngineAudioPrepareMixin,
)


def _write_wav(path, rate, channels, sampwidth, samples_i16scale):
    """按 int16 幅度约定写入 WAV（24bit 内部 ×256 升到 s24）"""
    with wave.open(str(path), 'wb') as w:
        w.setnchannels(channels)
        w.setsampwidth(sampwidth)
        w.setframerate(rate)
        if sampwidth == 3:
            vals = np.clip(np.asarray(samples_i16scale), -32768, 32767) * 256.0
            vals = vals.astype('<i4')
            out = np.empty((vals.size, 3), dtype=np.uint8)
            view = vals.view(np.uint8).reshape(-1, 4)
            out[:, 0], out[:, 1], out[:, 2] = view[:, 0], view[:, 1], view[:, 2]
            w.writeframes(out.tobytes())
        elif sampwidth == 2:
            w.writeframes(np.asarray(samples_i16scale, dtype='<i2').tobytes())
        else:
            raise ValueError(sampwidth)


class _GainCompDriver(AudioDriver):
    """仅承载 calculate_gain_compensation 的最小具体化（ABC 抽象方法桩）"""

    def get_devices(self):
        return []


class TestGainCompensation24bit:
    @pytest.mark.parametrize('sampwidth', [2, 3])
    def test_same_amplitude_same_gain_across_bit_depth(self, tmp_path, sampwidth):
        """同一幅度（int16 口径）的 16bit 与 24bit 素材必须得到相同增益补偿"""
        rate = 16000
        t = np.arange(rate) / rate
        # RMS 恰为 -30 dBFS 的正弦（幅值 ×√2 补偿 1/√2 系数）
        amp = 10 ** (-30.0 / 20.0) * 32768.0 * math.sqrt(2.0)
        samples = amp * np.sin(2 * np.pi * 440 * t)
        path = tmp_path / f'tone_{sampwidth}bit.wav'
        _write_wav(path, rate, 1, sampwidth, samples)
        gain = _GainCompDriver().calculate_gain_compensation(str(path))
        assert gain == pytest.approx(1.0, rel=1e-3)

    def test_quiet_24bit_boosted_correctly(self, tmp_path):
        rate = 16000
        t = np.arange(rate) / rate
        amp = 10 ** (-60.0 / 20.0) * 32768.0 * math.sqrt(2.0)
        samples = amp * np.sin(2 * np.pi * 440 * t)
        path = tmp_path / 'quiet_24bit.wav'
        _write_wav(path, rate, 1, 3, samples)
        gain = _GainCompDriver().calculate_gain_compensation(str(path))
        # -60 dBFS → -30 dBFS 需要 +30 dB
        assert gain == pytest.approx(10 ** 1.5, rel=1e-3)


class TestResampleToFile24bit:
    def test_24bit_source_parsed_by_actual_sampwidth(self, tmp_path, monkeypatch):
        """24bit 源重采样：按实际采样宽度解析（旧实现按 int16 读帧会得到双倍样本数与垃圾幅度）"""
        monkeypatch.setenv('RESAMPLE_TEMP_PATH', str(tmp_path / 'resample_tmp'))
        src_rate, dst_rate = 8000, 4000
        n = src_rate  # 1 秒
        # 恒定直流 -4096（int16 口径）→ s24 内部 -4096*256
        samples = np.full(n, -4096.0)
        src = tmp_path / 'src_24bit.wav'
        _write_wav(src, src_rate, 1, 3, samples)

        mixin = EngineAudioPrepareMixin.__new__(EngineAudioPrepareMixin)

        class _FakeEngine:
            # 本测聚焦 24bit 帧解析（重采样前的环节），重采样以恒等抽取替身
            def resample_audio_data(self, data, orig_rate, target_rate):
                return data[:int(len(data) * target_rate / orig_rate)]

        mixin._get_driver = lambda: _FakeEngine()
        out_path = mixin._resample_to_file(str(src), dst_rate, 1, audio_id=901)
        assert out_path, "24bit 重采样失败"
        with wave.open(out_path, 'rb') as w:
            assert w.getsampwidth() == 2
            assert w.getframerate() == dst_rate
            assert w.getnframes() == dst_rate
            vals = np.frombuffer(w.readframes(w.getnframes()), dtype='<i2')
        # 直流幅度保持（int16 口径）
        assert abs(float(np.mean(vals)) + 4096.0) < 8.0
