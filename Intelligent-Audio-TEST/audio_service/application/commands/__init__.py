# -*- coding: utf-8 -*-
"""audio_service 写模型命令（Command）定义。

CQRS Command：frozen dataclass，仅描述写意图，不含业务逻辑。
handler 接收 Command 后编排领域服务/仓储完成写操作。
"""
from audio_service.application.commands.audio_commands import (
    UpdateAudioMetadataCommand,
    BatchUpdateAnnotationsCommand,
    BatchActionAudiosCommand,
    DeleteAudioCommand,
    UpdateAudioAlgorithmsCommand,
    BatchUpdateAudioAlgorithmsCommand,
    ConvertAudioCommand,
    PreviewAudioCommand,
    StopPreviewAudioCommand,
    PersistAnnotationsCommand,
    CreateTestCaseFromAudioCommand,
)
from audio_service.application.commands.audio_upload_commands import (
    PresignUploadCommand,
    PresignPartCommand,
    CompleteDirectUploadCommand,
    InitUploadTaskCommand,
    RegisterUploadFileCommand,
    UploadChunkCommand,
    MergeChunksCommand,
    GetUploadProgressQuery as GetUploadProgressCommand,
    UrlImportCommand,
)

__all__ = [
    # 音频 CRUD 命令
    "UpdateAudioMetadataCommand",
    "BatchUpdateAnnotationsCommand",
    "BatchActionAudiosCommand",
    "DeleteAudioCommand",
    "UpdateAudioAlgorithmsCommand",
    "BatchUpdateAudioAlgorithmsCommand",
    "ConvertAudioCommand",
    "PreviewAudioCommand",
    "StopPreviewAudioCommand",
    "PersistAnnotationsCommand",
    "CreateTestCaseFromAudioCommand",
    # 上传命令
    "PresignUploadCommand",
    "PresignPartCommand",
    "CompleteDirectUploadCommand",
    "InitUploadTaskCommand",
    "RegisterUploadFileCommand",
    "UploadChunkCommand",
    "MergeChunksCommand",
    "GetUploadProgressCommand",
    "UrlImportCommand",
]
