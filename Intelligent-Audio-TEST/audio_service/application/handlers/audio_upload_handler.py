# -*- coding: utf-8 -*-
"""上传命令处理器（CQRS 写侧）。

接收上传相关 Command，委托 audio_upload_service（application/services）执行。
上传逻辑复杂（分片合并/转码/OSS），保留为 application/services 子服务。
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from audio_service.application.commands.audio_upload_commands import (
    PresignUploadCommand,
    PresignPartCommand,
    CompleteDirectUploadCommand,
    InitUploadTaskCommand,
    RegisterUploadFileCommand,
    UploadChunkCommand,
    MergeChunksCommand,
    GetUploadProgressQuery,
    UrlImportCommand,
)

logger = logging.getLogger(__name__)


class AudioUploadHandler:
    """上传命令处理器。

    委托 audio_upload_service（application/services）执行上传逻辑。
    """

    def __init__(self) -> None:
        self._upload_service = None

    @property
    def upload_service(self):
        if self._upload_service is None:
            from audio_service.application.services.audio_upload_service import audio_upload_service
            self._upload_service = audio_upload_service
        return self._upload_service

    def handle_presign_upload(self, cmd: PresignUploadCommand) -> Dict[str, Any]:
        return self.upload_service.presign_upload(cmd.data)

    def handle_presign_part(self, cmd: PresignPartCommand) -> Dict[str, Any]:
        return self.upload_service.presign_part(cmd.data)

    def handle_complete_direct_upload(self, cmd: CompleteDirectUploadCommand) -> Dict[str, Any]:
        return self.upload_service.complete_direct_upload(cmd.data)

    def handle_init_upload_task(self, cmd: InitUploadTaskCommand) -> Dict[str, Any]:
        return self.upload_service.init_upload_task(cmd.data)

    def handle_register_upload_file(self, cmd: RegisterUploadFileCommand) -> Dict[str, Any]:
        return self.upload_service.register_upload_file(cmd.data)

    def handle_upload_chunk(self, cmd: UploadChunkCommand) -> Dict[str, Any]:
        return self.upload_service.upload_chunk(cmd.data)

    def handle_merge_chunks(self, cmd: MergeChunksCommand) -> Dict[str, Any]:
        return self.upload_service.merge_chunks(cmd.data)

    def handle_get_upload_progress(self, query: GetUploadProgressQuery) -> Dict[str, Any]:
        return self.upload_service.get_upload_progress(query.data)

    def handle_url_import(self, cmd: UrlImportCommand) -> Dict[str, Any]:
        return self.upload_service.url_import(cmd.data)
