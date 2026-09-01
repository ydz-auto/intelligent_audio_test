# -*- coding: utf-8 -*-
"""音频仓储 PO ↔ Entity 转换器（从 audio_repository.py 拆分，P4-4）。

P5+DOMAIN：仓储方法返回 domain entities（AudioAggregate 等）而非 PO，
本模块集中维护所有 PO ↔ Entity 的显式映射，字段命名差异在此处统一处理。

字段映射速查（PO → Entity）：
    Audio:        name→filename, size→file_size, format→audio_format
    UploadFile:   task_id→upload_task_id, size→file_size
    UploadChunk:  file_id→upload_file_id, status=='completed'→uploaded
"""
import logging
from typing import Any, List

from audio_service.infrastructure.persistence.models import (
    Audio,
    AudioAnnotation,
    AudioTag,
    AudioAlgorithmRelation,
    UploadTask,
    UploadFile,
    UploadChunk,
)
from audio_service.domain.entities import (
    AudioAggregate,
    AudioAnnotationEntity,
    AudioTagEntity,
    AudioAlgorithmRelationEntity,
    UploadTaskAggregate,
    UploadFileEntity,
    UploadChunkEntity,
    UploadStatus,
)

logger = logging.getLogger(__name__)


def _now():
    """当前时间（中国时区）"""
    from shared.utils.query_utils import now_cst
    return now_cst()


# ========== Audio PO ↔ Entity 转换 ==========

def _audio_po_to_entity(po: Audio,
                         tags: List[str] = None,
                         annotations: List[AudioAnnotationEntity] = None,
                         algorithm_relations: List[AudioAlgorithmRelationEntity] = None,
                         ) -> AudioAggregate:
    """Audio PO → AudioAggregate 聚合根。

    关联集合（标签/标注/算法关联）按需传入，避免每次查询都做联表。
    PO 字段映射说明：
        - PO.name        → entity.filename
        - PO.size        → entity.file_size
        - PO.format      → entity.audio_format
        - 其余同名字段直接映射
    """
    return AudioAggregate(
        id=po.id,
        filename=po.name or "",
        duration=po.duration or 0.0,
        sample_rate=po.sample_rate or 0,
        channels=po.channels or 0,
        file_path=po.file_path or "",
        file_size=po.size or 0,
        audio_format=po.format or "",
        deleted=po.deleted or False,
        original_filename=po.original_filename or "",
        md5=po.md5 or "",
        audio_type=po.audio_type or "dry",
        asr_text=po.asr_text or "",
        description=po.description or "",
        source_language=po.source_language or "",
        bitrate=po.bitrate or 0,
        created_at=po.created_at,
        updated_at=po.updated_at,
        tags=[AudioTagEntity(id=t.id, audio_id=t.audio_id, tag_name=name)
              for t, name in _pair_audio_tags(po.id, tags or [])] if tags is not None else [],
        annotations=annotations or [],
        algorithm_relations=algorithm_relations or [],
    )


def _apply_aggregate_to_po(aggregate: AudioAggregate, po: Audio) -> None:
    """将 AudioAggregate 聚合根的可写字段映射回 PO（不含 id/created_at 等元数据）。

    PO 与 entity 字段命名差异在此处显式映射：
        - entity.filename      → PO.name
        - entity.file_size    → PO.size
        - entity.audio_format → PO.format
    """
    po.name = aggregate.filename
    po.duration = aggregate.duration
    po.sample_rate = aggregate.sample_rate
    po.channels = aggregate.channels
    po.file_path = aggregate.file_path
    po.size = aggregate.file_size
    po.format = aggregate.audio_format


def _audio_annotation_po_to_entity(po: AudioAnnotation) -> AudioAnnotationEntity:
    """AudioAnnotation PO → AudioAnnotationEntity 实体"""
    return AudioAnnotationEntity(
        id=po.id,
        audio_id=po.audio_id,
        format=po.format or "json",
        code=po.code or "",
        data=po.data,
        source_language=po.source_language or "",
        target_language=po.target_language or "",
        deleted=po.deleted or False,
    )


def _audio_tag_po_to_entity(po: AudioTag, tag_name: str = "") -> AudioTagEntity:
    """AudioTag PO → AudioTagEntity 实体（tag_name 由调用方提供，避免额外联表）"""
    return AudioTagEntity(
        id=po.id,
        audio_id=po.audio_id,
        tag_name=tag_name,
    )


def _audio_algorithm_relation_po_to_entity(po: AudioAlgorithmRelation) -> AudioAlgorithmRelationEntity:
    """AudioAlgorithmRelation PO → AudioAlgorithmRelationEntity 实体"""
    return AudioAlgorithmRelationEntity(
        id=po.id,
        audio_id=po.audio_id,
        algorithm_type=po.algorithm_type or "",
        params=po.params or {},
        is_primary=po.is_primary if po.is_primary is not None else False,
        weight=po.weight if po.weight is not None else 1.0,
    )


def _apply_algorithm_relation_entity_to_po(entity: AudioAlgorithmRelationEntity,
                                            po: AudioAlgorithmRelation) -> None:
    """将 AudioAlgorithmRelationEntity 可写字段映射回 PO"""
    po.algorithm_type = entity.algorithm_type
    po.params = entity.params


def _pair_audio_tags(audio_id: int, tag_names: List[str]):
    """辅助：将标签名列表与 audio_id 配对为占位 AudioTag 记录（用于 entity 构造）。

    返回 (占位 AudioTagEntity, tag_name) 元组序列，供 _audio_po_to_entity 内部使用。
    """
    for name in tag_names:
        yield AudioTagEntity(audio_id=audio_id, tag_name=name), name


# ========== Upload PO ↔ Entity 转换 ==========

def _parse_upload_status(value: Any) -> UploadStatus:
    """将字符串/枚举状态解析为 UploadStatus 枚举"""
    if isinstance(value, UploadStatus):
        return value
    if not value:
        return UploadStatus.pending
    try:
        return UploadStatus(value)
    except (ValueError, KeyError):
        return UploadStatus.pending


def _upload_task_po_to_entity(po: UploadTask) -> UploadTaskAggregate:
    """UploadTask PO → UploadTaskAggregate 聚合根"""
    status = _parse_upload_status(po.status)
    return UploadTaskAggregate(
        id=po.id,
        total_files=po.total_files or 0,
        total_size=po.total_size or 0,
        uploaded_size=po.uploaded_size or 0,
        status=status,
        completed_files=po.completed_files or 0,
        failed_files=po.failed_files or 0,
        created_at=po.created_at,
    )


def _apply_upload_task_entity_to_po(entity: UploadTaskAggregate, po: UploadTask) -> None:
    """将 UploadTaskAggregate 可写字段映射回 PO"""
    po.total_files = entity.total_files
    po.total_size = entity.total_size
    po.uploaded_size = entity.uploaded_size
    po.completed_files = entity.completed_files
    po.failed_files = entity.failed_files
    po.status = entity.status.value if isinstance(entity.status, UploadStatus) else entity.status


def _upload_file_po_to_entity(po: UploadFile) -> UploadFileEntity:
    """UploadFile PO → UploadFileEntity 实体"""
    return UploadFileEntity(
        id=po.id,
        upload_task_id=po.task_id,
        filename=po.filename or "",
        file_size=po.size or 0,
        uploaded_size=po.uploaded_size or 0,
        status=_parse_upload_status(po.status),
        original_filename=po.original_filename or "",
        relative_path=po.relative_path or "",
        md5=po.md5 or "",
        completed_chunks=po.completed_chunks or 0,
        total_chunks=po.total_chunks or 0,
        created_at=po.created_at,
    )


def _apply_upload_file_entity_to_po(entity: UploadFileEntity, po: UploadFile) -> None:
    """将 UploadFileEntity 可写字段映射回 PO"""
    po.filename = entity.filename
    po.original_filename = entity.original_filename
    po.relative_path = entity.relative_path
    po.size = entity.file_size
    po.uploaded_size = entity.uploaded_size
    po.md5 = entity.md5
    po.completed_chunks = entity.completed_chunks
    po.total_chunks = entity.total_chunks
    po.status = entity.status.value if isinstance(entity.status, UploadStatus) else entity.status


def _upload_chunk_po_to_entity(po: UploadChunk) -> UploadChunkEntity:
    """UploadChunk PO → UploadChunkEntity 实体"""
    return UploadChunkEntity(
        id=po.id,
        upload_file_id=po.file_id,
        chunk_index=po.chunk_index or 0,
        chunk_size=po.chunk_size or 0,
        uploaded=(po.status == UploadStatus.completed.value),
    )
