# -*- coding: utf-8 -*-
"""Realtime 轮次音频源（INT-61）— 基础设施层

audio_service ACL（元数据）+ 共享存储 load_bytes（字节，local/oss 双 scheme）
→ s16 PCM + 源格式。WAV 容器解析取真实采样率/通道；裸 PCM 按
库内默认格式（24kHz/s16/mono）处理。
"""
from __future__ import annotations

import io
import logging
import wave
from typing import Optional, Tuple

from api_test_service.domain.services.realtime_audio_renderer import AudioFormat

logger = logging.getLogger(__name__)

DEFAULT_SOURCE_FORMAT = AudioFormat(sample_rate=24000, bit_depth='s16', channels=1)


class RoundAudioSource:
    """轮次用户音频字节源"""

    def __init__(self, audio_acl=None, storage_client=None):
        self._audio_acl = audio_acl
        self._storage = storage_client

    def _acl(self):
        if self._audio_acl is None:
            from api_test_service.infrastructure.acl import AudioConfigAclRepositoryImpl
            self._audio_acl = AudioConfigAclRepositoryImpl()
        return self._audio_acl

    def _store(self):
        if self._storage is None:
            from shared.infrastructure.storage import storage
            self._storage = storage
        return self._storage

    def get_pcm(self, audio_id) -> Tuple[bytes, AudioFormat]:
        """按 audio_id 加载音频 → (s16 PCM bytes, 源格式)；加载失败抛异常由执行器定轮次失败"""
        audio = self._acl().get_audio(audio_id)
        if audio is None:
            raise FileNotFoundError(f"音频 {audio_id} 不存在")
        from shared.utils.dto_utils import dto_to_dict
        meta = dto_to_dict(audio) or {}
        file_path = meta.get('file_path')
        if not file_path:
            raise FileNotFoundError(f"音频 {audio_id} 缺少 file_path")

        path = file_path if file_path.startswith(('oss://', 'local://')) \
            else self._store().build_path('audios', file_path)
        data = self._store().load_bytes(path)
        return self._extract_s16_pcm(data)

    @staticmethod
    def _extract_s16_pcm(data: bytes) -> Tuple[bytes, AudioFormat]:
        """WAV 容器 → 剥头取 PCM + 真实格式；非 WAV 按默认格式裸 PCM 处理"""
        try:
            with wave.open(io.BytesIO(data), 'rb') as w:
                sample_rate = w.getframerate()
                channels = w.getnchannels()
                sampwidth = w.getsampwidth()
                pcm = w.readframes(w.getnframes())
            if sampwidth != 2:
                # 非 s16 源转 s16：按采样宽度归一化重打包
                pcm = RoundAudioSource._to_s16(pcm, sampwidth)
            return pcm, AudioFormat(sample_rate=sample_rate, bit_depth='s16', channels=channels)
        except wave.Error:
            return data, DEFAULT_SOURCE_FORMAT

    @staticmethod
    def _to_s16(pcm: bytes, sampwidth: int) -> bytes:
        """任意位深线性 PCM → s16（大端/小端按 WAV 约定 little-endian）"""
        import numpy as np
        if sampwidth == 1:
            samples = np.frombuffer(pcm, dtype=np.uint8).astype(np.float32)
            samples = (samples - 128.0) / 128.0
        elif sampwidth == 3:
            raw = np.frombuffer(pcm[: len(pcm) // 3 * 3], dtype=np.uint8).reshape(-1, 3)
            samples = (
                (raw[:, 0].astype(np.int32))
                | (raw[:, 1].astype(np.int32) << 8)
                | (raw[:, 2].astype(np.int32) << 16)
            )
            samples = np.where(samples >= 1 << 23, samples - (1 << 24), samples)
            samples = samples.astype(np.float32) / float(1 << 23)
        elif sampwidth == 4:
            samples = np.frombuffer(pcm, dtype='<i4').astype(np.float32) / float(1 << 31)
        else:
            raise ValueError(f"不支持的采样宽度: {sampwidth}")
        return (np.clip(samples, -1.0, 1.0) * 32767.0).astype('<i2').tobytes()
