# -*- coding: utf-8 -*-
"""audio_service 仓储接口（ABC）。

遵循依赖倒置：domain 层定义接口，infrastructure/persistence 层实现。
application/handlers 层依赖此接口，不直接 import 具体仓储实现。
"""
from audio_service.domain.repositories.audio_repository_abc import (
    AudioRepositoryInterface,
    UploadRepositoryInterface,
)

__all__ = [
    "AudioRepositoryInterface",
    "UploadRepositoryInterface",
]
