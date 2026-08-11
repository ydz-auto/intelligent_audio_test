# -*- coding: utf-8 -*-
"""audio_service 领域值对象 re-export。

re-export：本包作为各值对象子模块的统一入口。
"""
from audio_service.domain.value_objects.audio_meta import AudioMeta

__all__ = [
    "AudioMeta",
]
