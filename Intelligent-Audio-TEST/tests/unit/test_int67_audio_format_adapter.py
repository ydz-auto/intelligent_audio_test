# -*- coding: utf-8 -*-
"""INT-67 AudioFormatAdapter 单测 — 格式适配契约（08 设计文档 §2.3）

覆盖：
- 转换顺序固定「位深 → 采样率 → 通道」：重采样在源声道布局下进行（spy 断言）
- 24bit 防误解析：3 字节小端有符号逐字节重组（±满量程、中值）
- int16 幅度约定解析（物理链路共享）：u8/s16/s24/s32
- 位深归一化 / 量化（防削波）、重采样（同率直返 / 降采样长度 / 交织多声道按帧维度）
- 通道转换（下混均值 / 上混复制 / 其余组合抛配置错误）
- 源格式探测优先级（WAV 头 > 库内元数据 > 库内默认）
- 目标格式解析回退（api.audio_config 缺省 24kHz/s16/mono）
- 容器包装（wav 头字段 / pcm 直返 / 未知容器拒绝）
"""
import io
import wave

import numpy as np
import pytest

from audio_service.domain.services.audio_format_adapter import (
    AudioFormat,
    AudioFormatAdapter,
    BitDepth,
    detect_source_format,
    parse_target_format,
)


def _s16_bytes(samples):
    return (np.clip(np.asarray(samples, dtype=np.float32), -1.0, 1.0)
            * 32767.0).astype('<i2').tobytes()


def _s24_bytes(int_vals):
    vals = np.asarray(int_vals, dtype='<i4')
    out = np.empty((vals.size, 3), dtype=np.uint8)
    view = vals.view(np.uint8).reshape(-1, 4)
    out[:, 0], out[:, 1], out[:, 2] = view[:, 0], view[:, 1], view[:, 2]
    return out.tobytes()


class TestBitDepth:
    def test_from_str_and_props(self):
        assert BitDepth.from_str('s16') is BitDepth.S16
        assert BitDepth.from_str('s24').bytes_per_sample == 3
        assert BitDepth.from_str('s32').full_scale == 2147483648
        with pytest.raises(ValueError):
            BitDepth.from_str('u8')


class TestParse24bit:
    def test_s24_full_scale_negative(self):
        pcm = _s24_bytes([-(1 << 23)])
        out = AudioFormatAdapter.parse_to_float32(pcm, 's24')
        assert out.size == 1
        assert out[0] == pytest.approx(-1.0)

    def test_s24_full_scale_positive(self):
        pcm = _s24_bytes([(1 << 23) - 1])
        out = AudioFormatAdapter.parse_to_float32(pcm, 's24')
        assert out[0] == pytest.approx(1.0 - 1.0 / (1 << 23), abs=1e-6)

    def test_s24_zero_and_trailing_garbage(self):
        pcm = _s24_bytes([0, 12345, -12345]) + b'\xff'  # 尾部不完整字节安全截断
        out = AudioFormatAdapter.parse_to_float32(pcm, 's24')
        assert out.size == 3
        assert out[0] == 0.0

    def test_s16_and_s32_scale(self):
        assert AudioFormatAdapter.parse_to_float32(b'\x00\x80', 's16')[0] == -1.0
        assert AudioFormatAdapter.parse_to_float32(
            (np.array([-(1 << 31)], dtype='<i4')).tobytes(), 's32')[0] == -1.0


class TestToInt16Scale:
    def test_u8_centered(self):
        arr = AudioFormatAdapter.to_int16_scale(bytes([128, 255, 0]), 1)
        assert arr[0] == 0.0
        assert arr[1] == pytest.approx(127.0 * 256.0)
        assert arr[2] == pytest.approx(-128.0 * 256.0)

    def test_s24_maps_to_int16_range(self):
        arr = AudioFormatAdapter.to_int16_scale(_s24_bytes([-(1 << 23), (1 << 23) - 1]), 3)
        assert arr[0] == pytest.approx(-32768.0)
        assert arr[1] == pytest.approx(32767.999, abs=1e-2)

    def test_s32_scaled(self):
        arr = AudioFormatAdapter.to_int16_scale(
            (np.array([-(1 << 31), 65536], dtype='<i4')).tobytes(), 4)
        assert arr[0] == pytest.approx(-32768.0)
        assert arr[1] == pytest.approx(1.0)

    def test_unknown_width_raises(self):
        with pytest.raises(ValueError):
            AudioFormatAdapter.to_int16_scale(b'\x00' * 6, 5)


class TestQuantizeResampleChannels:
    def test_quantize_s16_clips(self):
        out = AudioFormatAdapter.quantize(np.array([2.0, -2.0, 0.5], dtype=np.float32), 's16')
        vals = np.frombuffer(out, dtype='<i2')
        assert vals[0] == 32767
        assert vals[1] == -32768
        assert vals[2] == pytest.approx(16383, abs=1)

    def test_resample_same_rate_identity(self):
        samples = np.array([0.1, -0.2, 0.3], dtype=np.float32)
        assert AudioFormatAdapter.resample(samples, 24000, 24000) is samples

    def test_resample_halves_length(self):
        rate = 48000
        t = np.arange(rate, dtype=np.float64) / rate
        sine = (0.5 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
        out = AudioFormatAdapter.resample(sine, 48000, 24000)
        assert out.size == 24000
        # 降采样后 440Hz 正弦能量基本保持
        assert float(np.sqrt(np.mean(out.astype(np.float64) ** 2))) == pytest.approx(0.3535, rel=0.05)

    def test_resample_stereo_by_frames(self):
        # 交织立体声：L 恒 0.5，R 恒 -0.5，按帧维度重采样后逐声道仍恒定
        # （若误把交织流当一维信号会整体畸变，而非仅滤波器启动瞬态）
        rate = 48000
        n = 4800
        inter = np.empty(n * 2, dtype=np.float32)
        inter[0::2] = 0.5
        inter[1::2] = -0.5
        out = AudioFormatAdapter.resample(inter, rate, 24000, channels=2)
        assert out.size == 2400 * 2
        left, right = out[0::2], out[1::2]
        # 瞬态后的中段精确保持（短 edge padding 下 FIR 瞬态仅存在于头尾各若干样本，
        # 与 audio_driver.resample_audio_data 预重采样同款特征）
        assert np.allclose(left[8:-8], 0.5, atol=1e-4)
        assert np.allclose(right[8:-8], -0.5, atol=1e-4)
        # 头部瞬态有界（若误把交织流当一维信号会整体畸变而非边界瞬态）
        assert np.all(np.abs(left[:8] - 0.5) < 0.05)

    def test_downmix_mean(self):
        inter = np.array([1.0, 0.0, -1.0, 1.0], dtype=np.float32)
        out = AudioFormatAdapter.convert_channels(inter, 2, 1)
        assert np.allclose(out, [0.5, 0.0])

    def test_upmix_duplicate(self):
        out = AudioFormatAdapter.convert_channels(np.array([0.5, -0.5], dtype=np.float32), 1, 2)
        assert np.allclose(out, [0.5, 0.5, -0.5, -0.5])

    def test_unsupported_channel_combo_raises(self):
        with pytest.raises(ValueError):
            AudioFormatAdapter.convert_channels(np.zeros(6, dtype=np.float32), 3, 1)


class TestAdaptOrderContract:
    def test_resample_runs_in_source_channel_layout(self, monkeypatch):
        """固定顺序「位深 → 采样率 → 通道」：重采样发生在下混之前（源声道布局）"""
        calls = []

        def spy_resample(samples, src_rate, dst_rate, channels=1):
            calls.append((src_rate, dst_rate, channels))
            return np.zeros(len(samples) * dst_rate // src_rate, dtype=np.float32)

        monkeypatch.setattr(AudioFormatAdapter, 'resample',
                            staticmethod(spy_resample))
        src = AudioFormat(sample_rate=48000, bit_depth='s16', channels=2)
        dst = AudioFormat(sample_rate=16000, bit_depth='s16', channels=1)
        # 交织立体声 s16：4800 帧 × 2ch
        pcm = _s16_bytes(np.zeros(9600))
        AudioFormatAdapter.adapt(pcm, src, dst)
        assert calls, "重采样未被调用"
        assert calls[0] == (48000, 16000, 2), "重采样必须先于通道转换（源声道布局）"


class TestSourceFormatDetection:
    def _wav_bytes(self, rate, channels, sampwidth, frames=b'\x00' * 16):
        buf = io.BytesIO()
        with wave.open(buf, 'wb') as w:
            w.setnchannels(channels)
            w.setsampwidth(sampwidth)
            w.setframerate(rate)
            w.writeframes(frames)
        return buf.getvalue()

    def test_wav_header_priority(self):
        pcm = self._wav_bytes(44100, 2, 3)
        fmt = detect_source_format(pcm, {'sample_rate': 9999, 'channels': 9})
        assert (fmt.sample_rate, fmt.channels, fmt.bit_depth) == (44100, 2, 's24')

    def test_metadata_fallback(self):
        fmt = detect_source_format(b'\x00' * 8, {'sample_rate': 16000, 'channels': 1})
        assert (fmt.sample_rate, fmt.channels, fmt.bit_depth) == (16000, 1, 's16')

    def test_library_default_fallback(self):
        fmt = detect_source_format(b'\x00' * 8, {})
        assert (fmt.sample_rate, fmt.bit_depth, fmt.channels) == (24000, 's16', 1)


class TestTargetFormat:
    def test_default_fallback(self):
        fmt = parse_target_format(None)
        assert (fmt.sample_rate, fmt.bit_depth, fmt.channels, fmt.container) == \
            (24000, 's16', 1, 'pcm')

    def test_partial_override(self):
        fmt = parse_target_format({'sample_rate': 16000, 'channels': 2, 'container': 'wav'})
        assert (fmt.sample_rate, fmt.bit_depth, fmt.channels, fmt.container) == \
            (16000, 's16', 2, 'wav')

    def test_invalid_bit_depth_rejected(self):
        with pytest.raises(ValueError):
            parse_target_format({'bit_depth': 'f32'})


class TestWrapContainer:
    def test_wav_header_fields(self):
        fmt = AudioFormat(sample_rate=16000, bit_depth='s24', channels=2)
        pcm = _s24_bytes([0, 1, -1, 2, -2, 3, -3, 4])
        wrapped = AudioFormatAdapter.wrap_container(pcm, fmt, 'wav')
        with wave.open(io.BytesIO(wrapped), 'rb') as w:
            assert w.getframerate() == 16000
            assert w.getnchannels() == 2
            assert w.getsampwidth() == 3

    def test_pcm_passthrough(self):
        fmt = AudioFormat(sample_rate=16000, bit_depth='s16', channels=1)
        assert AudioFormatAdapter.wrap_container(b'\x01\x02', fmt, 'pcm') == b'\x01\x02'

    def test_unknown_container_rejected(self):
        with pytest.raises(ValueError):
            AudioFormatAdapter.wrap_container(b'', AudioFormat(), 'flac')
