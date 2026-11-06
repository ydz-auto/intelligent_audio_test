# -*- coding: utf-8 -*-
"""audio_service 音频领域实体 re-export。

实体拥有唯一标识（ID），其属性可变。AudioAggregate 是聚合根，
统一管理音频元数据及其边界内的标注、标签与算法关联。

re-export：本包作为各实体子模块的统一入口，便于上层以
``from audio_service.domain.entities import AudioAggregate`` 形式引用。
"""
from audio_service.domain.entities.audio import (
    AudioAggregate,
    AudioAlgorithmRelationEntity,
    AudioAnnotationEntity,
    AudioSnapshot,
    AudioTagEntity,
)
from audio_service.domain.entities.upload import (
    UploadChunkEntity,
    UploadFileEntity,
    UploadStatus,
    UploadTaskAggregate,
)

__all__ = [
    # 音频聚合
    "AudioAggregate",
    "AudioAnnotationEntity",
    "AudioTagEntity",
    "AudioAlgorithmRelationEntity",
    "AudioSnapshot",
    # 上传聚合
    "UploadTaskAggregate",
    "UploadFileEntity",
    "UploadChunkEntity",
    "UploadStatus",
]
