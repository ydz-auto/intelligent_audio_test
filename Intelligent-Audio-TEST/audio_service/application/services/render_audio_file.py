# -*- coding: utf-8 -*-
"""RenderAudioFile — 整段混音出口（INT-67，08 设计文档 §3.2 / §五 5A/6A）

HTTP 非实时路径：等所有音频齐了 → 一次性混整段 → 完整 PCM（wav/pcm 按
target_format.container 包装）→ unary 返回，消费端一次性 HTTP POST。

Step 5A 整段混音叠加（float32 缓冲）
Step 6A 整段量化输出（np.clip 按目标位深满量程 → wrap_container，无切片）
"""
from __future__ import annotations

import base64
from typing import Dict

import numpy as np

from audio_service.application.services.audio_stream_orchestrator import (
    AudioKind,
    AudioStreamOrchestrator,
    RenderContext,
)
from audio_service.domain.services.audio_format_adapter import AudioFormatAdapter


class RenderAudioFile:
    """HTTP 非实时混音：整段混音 → 整文件聚合返回"""

    @staticmethod
    def mix(context: RenderContext) -> np.ndarray:
        """Step 5A：整段混音叠加（float32 缓冲，一次性混完）"""
        fmt = context.target_format
        channels = max(1, fmt.channels)
        total_samples = context.total_frames * channels
        mix_buffer = np.zeros(total_samples, dtype=np.float32)

        for src_idx, start_frame in context.placements:
            src = context.sources[src_idx]
            if src.samples is None or src.samples.size == 0:
                continue
            gained = src.samples * src.gain_linear
            if src.kind == AudioKind.NOISE and src.loop:
                # 铺满整个混音缓冲（帧粒度平铺，缓冲按交织样本索引）
                n = gained.size
                if n == 0:
                    continue
                start_sample = start_frame * channels
                tail = (total_samples - start_sample) % n
                reps = (total_samples - start_sample) // n
                if start_sample >= total_samples:
                    continue
                if reps > 0:
                    mix_buffer[start_sample:start_sample + reps * n] += np.tile(gained, reps)
                if tail > 0:
                    mix_buffer[start_sample + reps * n:
                               start_sample + reps * n + tail] += gained[:tail]
            else:
                start_sample = start_frame * channels
                end_sample = min(start_sample + gained.size, total_samples)
                if start_sample < 0 or start_sample >= total_samples:
                    continue
                mix_buffer[start_sample:end_sample] += gained[:end_sample - start_sample]

        return mix_buffer

    @staticmethod
    def render(context: RenderContext) -> Dict:
        """整段混音流程 Step 5A/6A → 完整文件产物

        返回：{container, audio_base64, sample_rate, bit_depth, channels, duration_ms}
        """
        fmt = context.target_format
        mix_buffer = RenderAudioFile.mix(context)
        pcm_bytes = AudioFormatAdapter.quantize(mix_buffer, fmt.bit_depth)
        container = (fmt.container or 'pcm').lower()
        audio_bytes = AudioFormatAdapter.wrap_container(pcm_bytes, fmt, container)
        return {
            'container': container,
            'audio_base64': base64.b64encode(audio_bytes).decode('ascii'),
            'sample_rate': fmt.sample_rate,
            'bit_depth': fmt.bit_depth,
            'channels': fmt.channels,
            'duration_ms': int(round(context.total_frames * 1000.0 / fmt.sample_rate))
            if fmt.sample_rate else 0,
            'chunk_duration_ms': AudioStreamOrchestrator.chunk_duration_ms(),
        }
