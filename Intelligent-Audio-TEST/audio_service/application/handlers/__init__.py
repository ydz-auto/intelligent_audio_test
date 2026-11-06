# -*- coding: utf-8 -*-
"""audio_service CQRS Handler 入口。

Handler 接收 Command/Query 对象，编排领域服务/仓储完成操作。
Servicer 层通过此入口调用，不再直接 import 旧 audio_crud_service。
"""
from audio_service.application.handlers.audio_command_handler import AudioCommandHandler
from audio_service.application.handlers.audio_query_handler import AudioQueryHandler
from audio_service.application.handlers.audio_upload_handler import AudioUploadHandler

# 模块级单例（servicer 注入）
audio_command_handler = AudioCommandHandler()
audio_query_handler = AudioQueryHandler()
audio_upload_handler = AudioUploadHandler()

__all__ = [
    "AudioCommandHandler",
    "AudioQueryHandler",
    "AudioUploadHandler",
    "audio_command_handler",
    "audio_query_handler",
    "audio_upload_handler",
]
