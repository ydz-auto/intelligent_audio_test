# -*- coding: utf-8 -*-
"""Realtime 流式音频渲染器（INT-61）— 域服务，纯计算无 IO

与设计文档 RenderAudioStream（100ms 滑窗流式混音）对称的 Realtime 推送链路
本卡实现（多源时间轴混音由 audio_service RenderAudioStream 收口后切换，
当前承担：单源格式适配 → RMS 补偿 + SPL 增益 → 100ms 切片 → base64）：

  Step 2 格式适配：源 PCM → 目标格式（采样率/位深/通道，AudioFormatAdapter 同规则）
  Step 3 增益：effective = rms_compensate × spl_gain（ApiRmsSplService 口径）
  Step 5B/6B：100ms 滑窗切片 → 逐窗量化 → base64 PCM chunk
"""
from __future__ import annotations

import base64
import math
from dataclasses import dataclass
from typing import Iterator, List

import numpy as np
from scipy.signal import resample_poly

from api_test_service.domain.services.api_rms_spl_service import ApiRmsSplService


@dataclass(frozen=True)
class AudioFormat:
    """不可变音频格式（与 audio_service AudioFormatAdapter 值域一致）"""

    sample_rate: int = 24000
    bit_depth: str = 's16'
    channels: int = 1

    @property
    def bytes_per_sample(self) -> int:
        return {'s16': 2, 's24': 3, 's32': 4}[self.bit_depth]

    @property
    def full_scale(self) -> float:
        return float({'s16': 32768, 's24': 8388608, 's32': 2147483648}[self.bit_depth])


def parse_s16_pcm(pcm_bytes: bytes) -> np.ndarray:
    """s16 PCM bytes → float32 归一化 [-1, 1]"""
    usable = pcm_bytes[: len(pcm_bytes) // 2 * 2]
    samples = np.frombuffer(usable, dtype=np.int16).astype(np.float32) / 32768.0
    return samples


def quantize_s16(samples: np.ndarray) -> bytes:
    """float [-1,1] → s16 PCM bytes（防削波裁剪）"""
    clipped = np.clip(samples, -1.0, 1.0)
    return (clipped * 32767.0).astype('<i2').tobytes()


class RealtimeAudioRenderer:
    """Realtime 推送音频渲染器"""

    DEFAULT_CHUNK_MS = 100

    def __init__(self, spl_service: ApiRmsSplService):
        self._spl_service = spl_service

    # ── Step 2：格式适配（交织 PCM：先通道下混 → 再采样率重采样）──
    @staticmethod
    def adapt_format(samples: np.ndarray, src: AudioFormat, dst: AudioFormat) -> np.ndarray:
        out = samples
        if src.channels != dst.channels:
            out = RealtimeAudioRenderer._convert_channels(out, src.channels, dst.channels)
        if src.sample_rate != dst.sample_rate:
            out = RealtimeAudioRenderer._resample(out, src.sample_rate, dst.sample_rate)
        return out

    @staticmethod
    def _resample(samples: np.ndarray, src_rate: int, dst_rate: int) -> np.ndarray:
        if samples.size == 0 or src_rate == dst_rate:
            return samples
        gcd = math.gcd(int(src_rate), int(dst_rate))
        up, down = int(dst_rate) // gcd, int(src_rate) // gcd
        return resample_poly(samples, up, down).astype(np.float32)

    @staticmethod
    def _convert_channels(samples: np.ndarray, src_ch: int, dst_ch: int) -> np.ndarray:
        if src_ch == dst_ch:
            return samples
        if src_ch == 2 and dst_ch == 1:
            frames = samples[: len(samples) // 2 * 2].reshape(-1, 2)
            return frames.mean(axis=1).astype(np.float32)
        if src_ch == 1 and dst_ch == 2:
            return np.repeat(samples, 2).astype(np.float32)
        raise ValueError(f"不支持的通道转换: {src_ch} → {dst_ch}（配置错误不静默兜底）")

    # ── Step 3：RMS 补偿 + SPL 增益 ──
    def apply_gain(self, samples: np.ndarray, push_gain: float) -> np.ndarray:
        """施加推送增益（ApiRmsSplService.compute_push_gain 产出），防削波"""
        return np.clip(samples * float(push_gain), -1.0, 1.0)

    def compute_push_gain(self, pcm_bytes: bytes, api_id, target_spl: float,
                          mapping=None) -> float:
        """单源推送增益：RMS 补偿 × SPL 增益（口径与 E2E/API 对称）"""
        return self._spl_service.compute_push_gain(pcm_bytes, api_id, target_spl, mapping=mapping)

    # ── Step 5B/6B：100ms 滑窗切片 → base64 ──
    def render_chunks(self, samples: np.ndarray, fmt: AudioFormat,
                      chunk_duration_ms: int = DEFAULT_CHUNK_MS) -> List[str]:
        """float 采样序列 → 100ms base64 s16 chunk 列表（不足一窗补零）

        本卡输出位深固定 s16（Realtime WS 事件协议的输入格式），
        非 s16 目标格式属配置错误，显式拒绝不静默兜底。
        """
        if fmt.bit_depth != 's16':
            raise ValueError(f"Realtime 推送仅支持 s16 输出，当前配置: {fmt.bit_depth}")
        chunk_samples = max(1, int(fmt.sample_rate * chunk_duration_ms / 1000))
        total = len(samples)
        if total == 0:
            return []
        windows = math.ceil(total / chunk_samples)
        chunks: List[str] = []
        for w in range(windows):
            window = samples[w * chunk_samples: (w + 1) * chunk_samples]
            if len(window) < chunk_samples:
                window = np.pad(window, (0, chunk_samples - len(window)))
            chunks.append(base64.b64encode(quantize_s16(window)).decode('ascii'))
        return chunks

    def render(self, pcm_bytes: bytes, src_format: AudioFormat, dst_format: AudioFormat,
               api_id=None, target_spl: float = 65.0,
               chunk_duration_ms: int = DEFAULT_CHUNK_MS,
               mapping=None) -> Iterator[str]:
        """完整渲染链：适配 → 增益 → 切片，逐 chunk yield（executor 决定推送节奏）"""
        samples = parse_s16_pcm(pcm_bytes)
        samples = self.adapt_format(samples, src_format, dst_format)
        gain = self.compute_push_gain(pcm_bytes, api_id, target_spl, mapping=mapping)
        samples = self.apply_gain(samples, gain)
        yield from self.render_chunks(samples, dst_format, chunk_duration_ms)
