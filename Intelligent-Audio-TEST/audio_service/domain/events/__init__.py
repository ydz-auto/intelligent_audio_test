# -*- coding: utf-8 -*-
"""audio_service 音频领域事件 re-export。

re-export：本包作为各事件子模块的统一入口，便于上层以
``from audio_service.domain.events import AudioUploaded`` 形式引用。
"""
from audio_service.domain.events.audio_events import (
    AudioAnnotated,
    AudioDeleted,
    AudioUploaded,
)

__all__ = [
    "AudioUploaded",
    "AudioAnnotated",
    "AudioDeleted",
]
