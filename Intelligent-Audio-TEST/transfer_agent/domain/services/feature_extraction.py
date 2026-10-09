# -*- coding: utf-8 -*-
"""特征提取领域服务 — B→C feature_extract 契约的 B 侧预处理（设计文档 §4.3 形态二）。

C 第三方 API 仅接受小参数字段时，出站投递腿先对包内文件提取特征向量、只传特征。
纯计算无 I/O；具体 HTTP 投递在 infrastructure/acl 出站客户端实现。
"""
from __future__ import annotations

import hashlib
import io
import logging
import wave
from abc import ABC, abstractmethod
from typing import Dict

logger = logging.getLogger(__name__)


class FeatureExtractor(ABC):
    """特征提取端口（feature_extract 形态的 B 侧预处理）。"""

    @abstractmethod
    def extract(self, filename: str, content: bytes) -> dict:
        """从文件内容提取特征向量（小体积可序列化 dict）。"""


class AudioFeatureExtractor(FeatureExtractor):
    """默认特征提取器：WAV 头解析（声道/采样率/时长）+ 体积与内容摘要。"""

    def extract(self, filename: str, content: bytes) -> dict:
        features: Dict = {
            'filename': filename,
            'size_bytes': len(content),
            'sha256': hashlib.sha256(content).hexdigest(),
        }
        if filename.lower().endswith('.wav'):
            try:
                with wave.open(io.BytesIO(content), 'rb') as wav:
                    framerate = wav.getframerate() or 0
                    features.update({
                        'channels': wav.getnchannels(),
                        'sample_width': wav.getsampwidth(),
                        'framerate': framerate,
                        'n_frames': wav.getnframes(),
                        'duration_seconds': round(wav.getnframes() / framerate, 6) if framerate else None,
                    })
            except (wave.Error, EOFError) as e:
                logger.warning('WAV 特征解析失败（退化为基础特征）: %s (%s)', filename, e)
        return features
