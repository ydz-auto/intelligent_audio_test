# -*- coding: utf-8 -*-
"""音频领域事件 - AudioUploaded/AudioAnnotated/AudioDeleted。

领域事件表示领域中已经发生的事实，供上层（应用层/基础设施层）订阅
以触发副作用（推送进度、写日志、同步状态等）。事件本身只携带数据，
不包含处理逻辑。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class AudioUploaded:
    """音频已上传事件"""
    audio_id: int
    filename: str
    file_size: int = 0
    timestamp: float = 0.0


@dataclass(frozen=True)
class AudioAnnotated:
    """音频已标注事件"""
    audio_id: int
    annotation_id: int
    content: Optional[str] = None
    timestamp: float = 0.0


@dataclass(frozen=True)
class AudioDeleted:
    """音频已删除事件（逻辑删除）"""
    audio_id: int
    operator: Optional[str] = None
    timestamp: float = 0.0
