# -*- coding: utf-8 -*-
"""audio_service 领域服务 re-export。

re-export：本包作为各服务子模块的统一入口。
"""
from audio_service.domain.services.upload_scheduler import UploadScheduler

__all__ = [
    "UploadScheduler",
]
