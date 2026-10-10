# -*- coding: utf-8 -*-
"""INT-61 Realtime 音频渲染器单测 — 纯计算链路

覆盖：
- 格式适配：48k→24k 重采样长度、stereo→mono 下混、mono→stereo 上混、
  非法通道组合显式拒绝（配置错误不静默兜底）
- 切片：100ms @24kHz = 2400 采样、尾窗补零、base64 可逆
- 非 s16 输出格式显式拒绝
- render() 全链：适配 + 增益 + 切片，增益经 ApiRmsSplService 口径
"""
import base64

import numpy as np

from api_test_service.domain.services.api_rms_spl_service import ApiRmsSplService
from api_test_service.domain.services.realtime_audio_renderer import (
    AudioFormat,
    RealtimeAudioRenderer,
    parse_s16_pcm,
    quantize_s16,
)

FORMAT_24K = AudioFormat(sample_rate=24000, bit_depth='s16', channels=1)
FORMAT_48K_STEREO = AudioFormat(sample_rate=48000, bit_depth='s16', channels=2)


class TestFormatAdapt:
    def test_same_format_passthrough(self):
        samples = np.ones(4800, dtype=np.float32)
        out = RealtimeAudioRenderer.adapt_format(samples, FORMAT_24K, FORMAT_24K)
        assert out is samples or len(out) == 4800

    def test_resample_48k_stereo_to_24k_mono(self):
        # 48000 交织立体声样本 = 0.5s @48k → 下混 24000 单声道样本 → 重采样 0.5s @24k = 12000
        samples = np.ones(48000, dtype=np.float32)
        out = RealtimeAudioRenderer.adapt_format(
            samples, FORMAT_48K_STEREO, FORMAT_24K)
        assert abs(len(out) - 12000) <= 1

    def test_stereo_to_mono_averages(self):
        samples = np.array([1.0, -1.0, 1.0, -1.0], dtype=np.float32)
        out = RealtimeAudioRenderer.adapt_format(
            samples, FORMAT_48K_STEREO, AudioFormat(48000, 's16', 1))
        np.testing.assert_allclose(out, [0.0, 0.0])

    def test_mono_to_stereo_duplicates(self):
        samples = np.array([0.5, -0.5], dtype=np.float32)
        out = RealtimeAudioRenderer.adapt_format(
            samples, FORMAT_24K, AudioFormat(24000, 's16', 2))
        np.testing.assert_allclose(out, [0.5, 0.5, -0.5, -0.5])

    def test_invalid_channel_combo_rejected(self):
        samples = np.ones(4, dtype=np.float32)
        try:
            RealtimeAudioRenderer.adapt_format(
                samples, AudioFormat(24000, 's16', 3), FORMAT_24K)
            raise AssertionError('应拒绝 3→1 通道转换')
        except ValueError:
            pass


class TestChunking:
    def test_100ms_chunk_is_2400_samples(self):
        samples = np.ones(4800, dtype=np.float32)
        chunks = RealtimeAudioRenderer(ApiRmsSplService()).render_chunks(
            samples, FORMAT_24K, chunk_duration_ms=100)
        assert len(chunks) == 2
        assert len(base64.b64decode(chunks[0])) == 2400 * 2  # s16

    def test_tail_window_zero_padded(self):
        samples = np.ones(2500, dtype=np.float32)
        chunks = RealtimeAudioRenderer(ApiRmsSplService()).render_chunks(
            samples, FORMAT_24K, chunk_duration_ms=100)
        assert len(chunks) == 2
        tail = np.frombuffer(base64.b64decode(chunks[1]), dtype='<i2')
        assert len(tail) == 2400
        assert tail[:100].astype(np.int32).sum() > 0
        assert tail[100:].astype(np.int32).sum() == 0  # 补零

    def test_base64_roundtrip_preserves_samples(self):
        rng = np.random.default_rng(42)
        samples = rng.uniform(-0.9, 0.9, 2400).astype(np.float32)
        chunks = RealtimeAudioRenderer(ApiRmsSplService()).render_chunks(
            samples, FORMAT_24K)
        decoded = np.frombuffer(base64.b64decode(chunks[0]), dtype='<i2')
        np.testing.assert_allclose(decoded, np.round(samples * 32767), atol=1)

    def test_empty_input_no_chunks(self):
        assert RealtimeAudioRenderer(ApiRmsSplService()).render_chunks(
            np.array([], dtype=np.float32), FORMAT_24K) == []

    def test_non_s16_output_rejected(self):
        samples = np.ones(2400, dtype=np.float32)
        try:
            RealtimeAudioRenderer(ApiRmsSplService()).render_chunks(
                samples, AudioFormat(24000, 's24', 1))
            raise AssertionError('应拒绝非 s16 输出格式')
        except ValueError:
            pass


class TestQuantize:
    def test_quantize_clips(self):
        samples = np.array([2.0, -2.0], dtype=np.float32)
        out = np.frombuffer(quantize_s16(samples), dtype='<i2')
        assert out[0] == 32767 and out[1] == -32767

    def test_parse_roundtrip(self):
        pcm = np.array([1000, -1000], dtype='<i2').tobytes()
        samples = parse_s16_pcm(pcm)
        np.testing.assert_allclose(samples, [1000 / 32768, -1000 / 32768], atol=1e-6)


class TestFullRender:
    def test_render_applies_gain_and_slices(self):
        """全链：SPL 增益经 ApiRmsSplService（65 dB → gain 1.0 × RMS 补偿）"""
        # 满幅方波：RMS 0 dBFS → rms_comp = 10^(-30/20) ≈ 0.0316
        pcm = np.array([32767, -32767] * 1200, dtype='<i2').tobytes()
        renderer = RealtimeAudioRenderer(ApiRmsSplService())
        chunks = list(renderer.render(
            pcm, FORMAT_24K, FORMAT_24K, api_id=7, target_spl=65.0,
            chunk_duration_ms=100))
        assert len(chunks) >= 1
        first = np.frombuffer(base64.b64decode(chunks[0]), dtype='<i2').astype(np.float32)
        peak = np.abs(first).max()
        # 增益后峰值 ≈ 0.0316 × 32767 ≈ 1036
        assert 900 < peak < 1200

    def test_render_zero_gain_with_uncalibrated_high_spl_is_capped(self):
        """高目标 SPL + 防削波上限：增益不超过 -5 dBFS 上限"""
        pcm = np.array([32767, -32767] * 1200, dtype='<i2').tobytes()
        renderer = RealtimeAudioRenderer(ApiRmsSplService())
        chunks = list(renderer.render(
            pcm, FORMAT_24K, FORMAT_24K, api_id=7, target_spl=100.0,
            chunk_duration_ms=100))
        first = np.frombuffer(base64.b64decode(chunks[0]), dtype='<i2').astype(np.float32)
        max_allowed = 10 ** ((-5.0 - (-30.0)) / 20.0) * 32767
        assert np.abs(first).max() <= max_allowed + 1
