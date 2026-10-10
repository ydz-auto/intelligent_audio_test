# -*- coding: utf-8 -*-
"""RenderAudioStream — 逐帧流式混音出口（INT-67，08 设计文档 §3.3 / §五 5B/6B）

HTTP 流式 / WebSocket Realtime 路径：按 100ms 滑动窗口逐帧混音 → 逐窗口
量化 → base64 PCM chunk → yield（servicer 逐 chunk 流式返回，消费端
SSE/WS 推送 + sleep 模拟实时速率）。

Step 5B 按 100ms 窗口逐帧混音（窗口内叠加）
Step 6B 逐窗口量化 → base64 PCM chunk（不足一窗补零，保证恒定 chunk 时长）
"""
from __future__ import annotations

import base64
from typing import Dict, Iterator

import numpy as np

from audio_service.application.services.audio_stream_orchestrator import (
    AudioKind,
    AudioStreamOrchestrator,
    RenderContext,
)
from audio_service.domain.services.audio_format_adapter import AudioFormatAdapter


class RenderAudioStream:
    """流式混音：100ms 窗口逐帧混音 → 逐窗口量化输出"""

    @staticmethod
    def render(context: RenderContext) -> Iterator[Dict]:
        """Step 5B/6B：按窗口推进混音，逐窗口 yield chunk

        chunk：{sequence, data(base64), is_last}；窗口边界帧对齐，
        不足一窗补零（Realtime 推送按恒定 chunk 时长 sleep）。
        """
        fmt = context.target_format
        channels = max(1, fmt.channels)
        rate = fmt.sample_rate
        window_frames = max(1, int(rate * AudioStreamOrchestrator.chunk_duration_ms() / 1000))
        total_frames = context.total_frames

        sequence = 0
        for w0 in range(0, total_frames, window_frames):
            w1 = min(w0 + window_frames, total_frames)
            # 恒定窗缓冲：末窗不足一窗的部分保持补零（Realtime 按恒定 chunk 时长 sleep）
            window = np.zeros(window_frames * channels, dtype=np.float32)

            for src_idx, start_frame in context.placements:
                src = context.sources[src_idx]
                if src.samples is None or src.samples.size == 0:
                    continue
                gained = src.samples * src.gain_linear
                if src.kind == AudioKind.NOISE and src.loop:
                    # loop 噪声：整缓冲平铺的模块索引窗口切片
                    n = gained.size
                    if n == 0:
                        continue
                    lo = (w0 - start_frame) * channels
                    hi = (w1 - start_frame) * channels
                    if hi <= 0:
                        continue
                    if lo < 0:
                        # 起始帧落在窗口内：前段补零，其余从平铺流取
                        pad = -lo
                        take = min(hi, n)
                        window[pad:pad + take] += gained[:take]
                        rest_start, rest_len = take, hi - take
                        if rest_len > 0:
                            idx = np.arange(rest_start, rest_start + rest_len) % n
                            window[pad + take:pad + hi] += gained[idx]
                    else:
                        idx = np.arange(lo, hi) % n
                        window[:hi - lo] += gained[idx]
                else:
                    lo = (w0 - start_frame) * channels
                    hi = (w1 - start_frame) * channels
                    if hi <= 0 or lo >= gained.size:
                        continue
                    src_lo = max(0, lo)
                    seg = gained[src_lo:min(hi, gained.size)]
                    if seg.size:
                        window[src_lo - lo:src_lo - lo + seg.size] += seg

            is_last = w1 >= total_frames
            yield {
                'sequence': sequence,
                'data': base64.b64encode(
                    AudioFormatAdapter.quantize(window, fmt.bit_depth)).decode('ascii'),
                'is_last': is_last,
            }
            sequence += 1
