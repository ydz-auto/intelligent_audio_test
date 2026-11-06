# -*- coding: utf-8 -*-
"""INT-2407 增益补偿 20ms 分帧 + 静音帧门限 — 口径回归测试

背景：INT-593 之前的 calculate_gain_compensation 用「整段 RMS」，素材首尾留白 /
句间停顿等静音段会拉低总 RMS，导致补偿增益虚高、播放实际音量偏大。
本卡按上游 V9.7.10 `2f6fd176b` 的口径移植到 V9.7.31 audio_service：

- 20 ms 分帧（帧长按「样本」计 = int(rate×frame_ms/1000)×channels），每帧 mean(x²)；
- `gate = max(max_rms × factor, 32768 × 10^(floor_dbfs/20))`；
- 静音判定语义为 **OR**：帧 RMS 低于 max_rms×factor **或** 低于绝对底即剔除；
- `active = frame_rms > gate`（严格大于），只对活跃帧求 RMS；
- 无活跃帧回退整段 RMS；空数据 / 全零返回 1.0。

明确不照抄上游两处（立体声算错）：`audioop.rms(raw, frame_width)` 与
`full_scale = 2**(8×frame_width-1)`——V9.7.31 按样本算帧长、满量程固定 32768。
"""
import math
import os
import wave

import numpy as np
import pytest

os.environ.setdefault('OSS_ACCESS_KEY', 'test-access')
os.environ.setdefault('OSS_SECRET_KEY', 'test-secret')

from audio_service.infrastructure.audio.audio_driver import (  # noqa: E402
    AudioDriver,
    _FrameRmsAccumulator,
    clear_gain_compensation_cache,
)

TARGET_DBFS = -30.0
FULL_SCALE = 32768.0


def _write_wav(path, rate, channels, sampwidth, samples_i16scale):
    """按 int16 幅度约定写入 WAV（24bit 内部 ×256 升到 s24）。"""
    with wave.open(str(path), 'wb') as w:
        w.setnchannels(channels)
        w.setsampwidth(sampwidth)
        w.setframerate(rate)
        vals = np.asarray(samples_i16scale)
        if sampwidth == 3:
            s24 = (np.clip(vals, -32768, 32767) * 256.0).astype('<i4')
            out = np.empty((s24.size, 3), dtype=np.uint8)
            view = s24.view(np.uint8).reshape(-1, 4)
            out[:, 0], out[:, 1], out[:, 2] = view[:, 0], view[:, 1], view[:, 2]
            w.writeframes(out.tobytes())
        elif sampwidth == 2:
            w.writeframes(vals.astype('<i2').tobytes())
        else:
            raise ValueError(sampwidth)


class _GainCompDriver(AudioDriver):
    """仅承载 calculate_gain_compensation 的最小具体化（ABC 抽象方法桩）。"""

    def get_devices(self):
        return []


def _tone(rate, dbfs, seconds=1.0, channels=1):
    """dbfs 峰值的正弦（RMS 恰为 dbfs dBFS），返回交织样本（int16 口径浮点）。"""
    n = int(rate * seconds)
    t = np.arange(n) / rate
    amp = 10 ** (dbfs / 20.0) * FULL_SCALE * math.sqrt(2.0)
    mono = amp * np.sin(2 * np.pi * 440 * t)
    if channels == 1:
        return mono
    return np.repeat(mono, channels)


def _with_silence_padding(rate, dbfs, seconds=1.0, pad=1.0, channels=1):
    """1 s 数字静音 + seconds 秒 dbfs 正弦 + 1 s 数字静音（首尾留白素材）。"""
    pad_samples = np.zeros(int(rate * pad * channels))
    return np.concatenate([pad_samples, _tone(rate, dbfs, seconds, channels), pad_samples])


def _gain_of(tmp_path, name, rate, channels, sampwidth, samples):
    path = tmp_path / name
    _write_wav(path, rate, channels, sampwidth, samples)
    return _GainCompDriver().calculate_gain_compensation(str(path))


class TestGainGateSilence:
    def test_leading_trailing_silence_uses_active_frames(self, tmp_path):
        """首尾各 1 s 静音 + 中间 1 s -20 dBFS 语音：活跃帧口径 ≈0.316。

        旧整段口径（把 2 s 静音算进 RMS）为 0.548——本用例能区分新旧口径。
        """
        rate, channels = 16000, 1
        samples = _with_silence_padding(rate, -20.0, channels=channels)
        gain = _gain_of(tmp_path, 'padded.wav', rate, channels, 2, samples)
        # -20 dBFS 活跃帧 → 需要 -10 dB
        assert gain == pytest.approx(10 ** (-10.0 / 20.0), rel=5e-3)
        # 与旧整段口径有明确差异（旧口径 ≈0.548，虚高 1.73 倍）
        assert gain < 0.35

    def test_all_zero_returns_unity(self, tmp_path):
        """全零素材：不做补偿（旧实现会算出≈2.8e48 的虚高增益）。"""
        rate = 16000
        samples = np.zeros(rate)
        gain = _gain_of(tmp_path, 'zero.wav', rate, 1, 2, samples)
        assert gain == 1.0

    def test_all_below_abs_floor_falls_back_to_whole_rms(self, tmp_path):
        """整段 -70 dBFS（全部低于绝对底 -60 dBFS）：无活跃帧 → 回退整段 RMS。"""
        rate = 16000
        samples = _tone(rate, -70.0)
        gain = _gain_of(tmp_path, 'floor.wav', rate, 1, 2, samples)
        # 与整段口径等值：按落盘后的 int16 样本算整段 RMS → 补偿到 -30 dBFS
        quantized = np.asarray(samples).astype('<i2').astype(np.float64)
        whole_rms = float(np.sqrt(np.mean(np.square(quantized))))
        whole_rms_db = 20 * math.log10(whole_rms / FULL_SCALE)
        assert gain == pytest.approx(10 ** ((TARGET_DBFS - whole_rms_db) / 20.0),
                                     rel=1e-3)


class TestGainGateChannelDepth:
    def test_stereo_same_gain_as_mono(self, tmp_path):
        """立体声与单声道同幅度同增益（防上游 frame_width 当字节宽/满量程的口径 bug）。"""
        rate = 16000
        mono = _with_silence_padding(rate, -20.0, channels=1)
        stereo = _with_silence_padding(rate, -20.0, channels=2)
        gain_mono = _gain_of(tmp_path, 'mono.wav', rate, 1, 2, mono)
        gain_stereo = _gain_of(tmp_path, 'stereo.wav', rate, 2, 2, stereo)
        assert gain_stereo == pytest.approx(gain_mono, rel=1e-3)
        assert gain_stereo == pytest.approx(10 ** (-10.0 / 20.0), rel=5e-3)

    def test_24bit_padded_matches_16bit(self, tmp_path):
        """24bit 首尾留白素材与 16bit 同结果（24bit 走 to_int16_scale）。"""
        rate = 16000
        samples = _with_silence_padding(rate, -20.0, channels=1)
        gain_16 = _gain_of(tmp_path, 'padded16.wav', rate, 1, 2, samples)
        gain_24 = _gain_of(tmp_path, 'padded24.wav', rate, 1, 3, samples)
        assert gain_24 == pytest.approx(gain_16, rel=1e-3)


class TestFrameAccumulatorBlockBoundary:
    def test_carries_residual_samples_across_blocks(self):
        """非整除采样率（11025 Hz → 220 样本/帧）下块边界余样本跨块续拼，帧不错位。

        1 s 块 = 11025 样本 = 50 帧 + 25 样本余；不跨块保留会让帧边界每块漂移 25 样本。
        用随机样本对比「一次性全量分帧」的参考值，任何样本丢失/错位都会暴露。
        """
        rate, frame_ms = 11025, 20
        frame_samples = max(1, int(rate * frame_ms / 1000))  # 220
        total = rate * 2
        rng = np.random.default_rng(2407)
        samples = (rng.standard_normal(total) * 3000.0).astype(np.float32)

        acc = _FrameRmsAccumulator(frame_samples)
        for start in range(0, total, rate):  # 1 s 分块，与驱动读取一致
            acc.feed(samples[start:start + rate])
        got = acc.frame_sq_means()

        expected_frames = total // frame_samples  # 100
        assert got.shape == (expected_frames,)
        reference = np.mean(
            samples[:expected_frames * frame_samples]
            .reshape(-1, frame_samples).astype(np.float64) ** 2,
            axis=1)
        assert np.allclose(got, reference, rtol=1e-6, atol=1e-6)


class TestGainGateConfig:
    def test_target_and_gate_params_read_from_audio_render(self, tmp_path, monkeypatch):
        """目标电平与三个门限参数全部从 audio_render 段读取（代码内保留同名默认）。"""
        import audio_service.infrastructure.audio.audio_driver as drv_mod

        seen = []
        values = {
            'target_rms_dbfs': -40.0,
            'gain_gate_frame_ms': 20,
            'gain_gate_threshold_factor': 0.1,
            'gain_gate_abs_floor_dbfs': -60.0,
        }

        def fake_get_value(section, key, default=None):
            seen.append((section, key))
            return values.get(key, default)

        monkeypatch.setattr(drv_mod.config_manager, 'get_value', fake_get_value)
        gain = _gain_of(tmp_path, 'cfg.wav', 16000, 1, 2, _tone(16000, -20.0))
        # 目标改为 -40 dBFS：-20 dBFS 素材需要 -20 dB 增益
        assert gain == pytest.approx(10 ** (-20.0 / 20.0), rel=5e-3)
        assert {sec for sec, _ in seen} == {'audio_render'}
        assert {key for _, key in seen} >= set(values)


class TestGainGateCache:
    def test_same_file_calls_compute_once(self, tmp_path, monkeypatch):
        """同文件两次调用只进一次 _compute（沿用 INT-593 缓存语义，缓存包装不动）。"""
        driver = _GainCompDriver()
        samples = _with_silence_padding(16000, -20.0, channels=1)
        path = tmp_path / 'cached.wav'
        _write_wav(path, 16000, 1, 2, samples)

        calls = []
        monkeypatch.setattr(
            driver, '_compute_gain_compensation',
            lambda p: (calls.append(p) or 1.0))
        clear_gain_compensation_cache()
        try:
            assert driver.calculate_gain_compensation(str(path)) == 1.0
            assert driver.calculate_gain_compensation(str(path)) == 1.0
            assert len(calls) == 1
        finally:
            clear_gain_compensation_cache()
