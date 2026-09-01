# -*- coding: utf-8 -*-
"""兼容性 shim：音频上传服务已迁移至 audio_upload 子包。

保留旧导入路径不变：
`from audio_service.application.services.audio_upload_service import AudioUploadService`
`from audio_service.application.services.audio_upload_service import audio_upload_service`

新代码请使用：
`from audio_service.application.services.audio_upload.service import ...`
"""
from audio_service.application.services.audio_upload.service import (
    AudioUploadService,
    audio_upload_service,
)

__all__ = ['AudioUploadService', 'audio_upload_service']
