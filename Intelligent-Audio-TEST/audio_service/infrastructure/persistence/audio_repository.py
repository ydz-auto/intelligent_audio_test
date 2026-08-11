# -*- coding: utf-8 -*-
"""音频配置仓储 — 持久化访问 Audio / AudioAnnotation / AudioTag / AudioAlgorithmRelation
等数据。

通过 shared.models.database.get_db_session() 的 scoped_session 访问数据库，
向上层（application/audio_crud_service 等）提供领域可读的接口。

P5+DOMAIN 改造：移除直接返回 PO 对象的 ORM 包装模式，改为 PO ↔ Entity 显式
转换。仓储方法返回 domain entities（AudioAggregate 等），而非 PO；上层不再
感知 SQLAlchemy ORM。关联集合（标注/标签/算法关联）按需加载。
"""
from typing import List, Optional, Dict, Any

from sqlalchemy import cast, String, func

from shared.models.database import get_db_session
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
from audio_service.domain.repositories.audio_repository_abc import AudioRepositoryInterface


def _now():
    from shared.utils.query_utils import now_cst
    return now_cst()


# ========== PO ↔ Entity 转换 ==========

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
        uploaded=(po.status == 'completed'),
    )


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


def _pair_audio_tags(audio_id: int, tag_names: List[str]):
    """辅助：将标签名列表与 audio_id 配对为占位 AudioTag 记录（用于 entity 构造）。

    返回 (占位 AudioTagEntity, tag_name) 元组序列，供 _audio_po_to_entity 内部使用。
    """
    for name in tag_names:
        yield AudioTagEntity(audio_id=audio_id, tag_name=name), name


class _TagProxy:
    """Tag 代理对象 — 替代原来从 task_service 导入的 Tag PO。
    仅含 id / name 两个字段，供 get_or_create_tag 返回后由 add_audio_tag 使用 tag.id。
    """
    def __init__(self, id, name):
        self.id = id
        self.name = name


def _audio_to_dict(audio: Audio, tags: List[str] = None,
                   annotations: List[dict] = None) -> dict:
    """将 Audio ORM 对象序列化为 dict（保留供上层序列化使用）"""
    return {
        'id': audio.id,
        'name': audio.name,
        'original_filename': audio.original_filename,
        'file_path': audio.file_path,
        'duration': audio.duration,
        'size': audio.size,
        'sample_rate': audio.sample_rate,
        'channels': audio.channels,
        'bitrate': audio.bitrate,
        'format': audio.format,
        'audio_type': audio.audio_type,
        'asr_text': audio.asr_text,
        'description': audio.description,
        'source_language': audio.source_language,
        'md5': audio.md5,
        'tags': tags or [],
        'annotations': annotations or [],
        'created_at': audio.created_at.isoformat() if audio.created_at else None,
        'updated_at': audio.updated_at.isoformat() if audio.updated_at else None,
    }


class AudioRepository(AudioRepositoryInterface):
    """音频配置仓储

    P5+DOMAIN: 通过 PO ↔ Entity 显式转换，仓储方法返回 domain entities，
    聚合根不再持有 ORM 引用，领域层与 SQLAlchemy 完全隔离。
    """

    # ========== Audio 基础 CRUD ==========

    def create_audio(self, data: dict) -> AudioAggregate:
        """创建音频记录，返回 AudioAggregate 聚合根。"""
        session = get_db_session()
        audio = Audio(
            name=data.get('name'),
            original_filename=data.get('original_filename'),
            file_path=data.get('file_path'),
            size=data.get('size', 0),
            duration=data.get('duration', 0.0),
            sample_rate=data.get('sample_rate'),
            channels=data.get('channels'),
            bitrate=data.get('bitrate'),
            format=data.get('format', 'wav'),
            audio_type=data.get('audio_type', 'dry'),
            asr_text=data.get('asr_text', ''),
            description=data.get('description'),
            md5=data.get('md5'),
            source_language=data.get('source_language'),
        )
        session.add(audio)
        session.flush()
        return _audio_po_to_entity(audio)

    def update_audio(self, audio_id: int, update_fields: dict) -> Optional[AudioAggregate]:
        """更新音频字段，返回更新后的 AudioAggregate。"""
        session = get_db_session()
        audio = session.query(Audio).filter_by(id=audio_id, deleted=False).first()
        if not audio:
            return None
        for key, value in update_fields.items():
            setattr(audio, key, value)
        audio.updated_at = _now()
        session.flush()
        return _audio_po_to_entity(audio)

    def get_audio(self, audio_id: int) -> Optional[AudioAggregate]:
        """按 ID 查询单个音频，返回 AudioAggregate。"""
        session = get_db_session()
        audio = session.query(Audio).filter_by(id=audio_id, deleted=False).first()
        if audio is None:
            return None
        return _audio_po_to_entity(audio)

    def get_audio_with_deleted(self, audio_id: int) -> Optional[AudioAggregate]:
        """按 ID 查询单个音频（含已删除），返回 AudioAggregate。"""
        session = get_db_session()
        audio = session.get(Audio, audio_id)
        if audio is None:
            return None
        return _audio_po_to_entity(audio)

    def delete_audio(self, audio_id: int) -> bool:
        """软删除音频"""
        session = get_db_session()
        audio = session.query(Audio).filter_by(id=audio_id, deleted=False).first()
        if not audio:
            return False
        now = _now()
        audio.deleted = True
        audio.deleted_at = now
        audio.updated_at = now
        session.flush()
        return True

    def batch_soft_delete_audios(self, audio_ids: List[int]) -> int:
        """批量软删除音频"""
        session = get_db_session()
        if not audio_ids:
            return 0
        now = _now()
        count = session.query(Audio).filter(
            Audio.id.in_(audio_ids), Audio.deleted == False
        ).update(
            {"deleted": True, "deleted_at": now, "updated_at": now},
            synchronize_session=False,
        )
        session.flush()
        return count

    def list_audios(self, params: dict) -> dict:
        """分页查询音频列表。

        返回 SQLAlchemy Pagination 对象，其中 items 已转换为 AudioAggregate。
        """
        session = get_db_session()
        query = session.query(Audio).filter_by(deleted=False)

        keyword = params.get('keyword')
        format_ = params.get('format_')
        audio_type = params.get('audio_type')
        folder = params.get('folder')
        sample_rate = params.get('sample_rate')
        duration = params.get('duration')
        tags_data = params.get('tags_data') or []
        direction = params.get('direction')

        if keyword:
            query = query.filter(
                (Audio.name.like(f"%{keyword}%")) |
                (Audio.original_filename.like(f"%{keyword}%"))
            )
        if format_:
            query = query.filter_by(format=format_)
        if audio_type:
            query = query.filter_by(audio_type=audio_type)
        if folder:
            query = query.filter(Audio.file_path.like(f"{folder}%"))
        if sample_rate and sample_rate != '':
            try:
                rate_value = float(str(sample_rate).split()[0]) * 1000
                query = query.filter_by(sample_rate=rate_value)
            except (ValueError, IndexError):
                pass
        if duration:
            if duration == 'short':
                query = query.filter(Audio.duration <= 30)
            elif duration == 'medium':
                query = query.filter(Audio.duration.between(30, 300))
            elif duration == 'long':
                query = query.filter(Audio.duration > 300)

        if direction:
            query = query.join(AudioAnnotation).filter(
                (AudioAnnotation.source_language.like(f"%{direction.split('-')[0]}%")) |
                (AudioAnnotation.target_language.like(f"%{direction.split('-')[1]}%"))
            )

        if tags_data:
            or_tags = []
            and_tags = []
            for t in tags_data:
                if isinstance(t, dict):
                    tag_name = t.get('name', '').strip()
                    tag_mode = t.get('mode', 'and')
                    if tag_name:
                        if tag_mode == 'or':
                            or_tags.append(tag_name)
                        else:
                            and_tags.append(tag_name)
                elif isinstance(t, str):
                    for part in t.split(','):
                        p = part.strip()
                        if p:
                            and_tags.append(p)

            # 通过 gRPC 查询 Tag ID（Tag 属于 task_service 域）
            tag_name_to_id = self._get_tag_name_to_id_map(or_tags + and_tags)

            if or_tags:
                or_tag_ids = [tag_name_to_id[n] for n in or_tags if n in tag_name_to_id]
                if or_tag_ids:
                    or_audio_ids = (
                        session.query(AudioTag.audio_id)
                        .filter(AudioTag.tag_id.in_(or_tag_ids))
                        .distinct()
                    )
                    query = query.filter(Audio.id.in_(or_audio_ids))

            if and_tags:
                and_tag_ids = [tag_name_to_id[n] for n in and_tags if n in tag_name_to_id]
                if and_tag_ids:
                    audio_tag_counts = (
                        session.query(AudioTag.audio_id, func.count(AudioTag.tag_id).label('tag_count'))
                        .filter(AudioTag.tag_id.in_(and_tag_ids))
                        .group_by(AudioTag.audio_id)
                        .subquery()
                    )
                    query = query.join(audio_tag_counts, audio_tag_counts.c.audio_id == Audio.id).filter(
                        audio_tag_counts.c.tag_count == len(and_tag_ids)
                    )

        page = params.get('page', 1)
        per_page = params.get('per_page', 10)
        pagination = query.order_by(Audio.created_at.desc()).paginate(
            page=page, per_page=per_page, error_out=False)
        # PO → AudioAggregate 转换
        pagination.items = [_audio_po_to_entity(po) for po in pagination.items]
        return pagination

    def get_audios_by_ids(self, audio_ids: List[int]) -> List[AudioAggregate]:
        """按 ID 列表批量查询音频，返回 AudioAggregate 列表。"""
        session = get_db_session()
        if not audio_ids:
            return []
        pos = session.query(Audio).filter(
            Audio.id.in_(audio_ids), Audio.deleted == False
        ).all()
        return [_audio_po_to_entity(po) for po in pos]

    def get_audio_by_md5(self, md5: str) -> Optional[AudioAggregate]:
        """按 MD5 查询音频，返回 AudioAggregate。"""
        session = get_db_session()
        po = session.query(Audio).filter_by(md5=md5, deleted=False).first()
        if po is None:
            return None
        return _audio_po_to_entity(po)

    def get_audios_by_md5_list(self, md5_list: List[str]) -> List[AudioAggregate]:
        """按 MD5 列表批量查询音频，返回 AudioAggregate 列表。"""
        session = get_db_session()
        if not md5_list:
            return []
        pos = session.query(Audio).filter(
            Audio.md5.in_(md5_list), Audio.deleted == False
        ).all()
        return [_audio_po_to_entity(po) for po in pos]

    def get_all_audio_ids(self, params: dict) -> List[int]:
        """按条件查询所有音频 ID（用于全选功能）"""
        session = get_db_session()
        query = session.query(Audio).filter_by(deleted=False)

        keyword = params.get('keyword')
        format_ = params.get('format_')
        audio_type = params.get('audio_type')
        sample_rate = params.get('sample_rate')
        duration = params.get('duration')
        tags_data = params.get('tags_data') or []
        direction = params.get('direction')

        if keyword:
            query = query.filter(
                (Audio.name.like(f"%{keyword}%")) |
                (Audio.original_filename.like(f"%{keyword}%"))
            )
        if format_:
            query = query.filter_by(format=format_)
        if audio_type:
            query = query.filter_by(audio_type=audio_type)
        if sample_rate and sample_rate != '':
            try:
                rate_value = float(str(sample_rate).split()[0]) * 1000
                query = query.filter_by(sample_rate=rate_value)
            except (ValueError, IndexError):
                pass
        if duration:
            if duration == 'short':
                query = query.filter(Audio.duration <= 30)
            elif duration == 'medium':
                query = query.filter(Audio.duration.between(30, 300))
            elif duration == 'long':
                query = query.filter(Audio.duration > 300)

        if direction:
            query = query.join(AudioAnnotation).filter(
                (AudioAnnotation.source_language.like(f"%{direction.split('-')[0]}%")) |
                (AudioAnnotation.target_language.like(f"%{direction.split('-')[1]}%"))
            )

        if tags_data:
            or_tags = []
            and_tags = []
            for t in tags_data:
                if isinstance(t, dict):
                    tag_name = t.get('name', '').strip()
                    tag_mode = t.get('mode', 'and')
                    if tag_name:
                        if tag_mode == 'or':
                            or_tags.append(tag_name)
                        else:
                            and_tags.append(tag_name)
                elif isinstance(t, str):
                    for part in t.split(','):
                        p = part.strip()
                        if p:
                            and_tags.append(p)

            # 通过 gRPC 查询 Tag ID（Tag 属于 task_service 域）
            tag_name_to_id = self._get_tag_name_to_id_map(or_tags + and_tags)

            if or_tags:
                or_tag_ids = [tag_name_to_id[n] for n in or_tags if n in tag_name_to_id]
                if or_tag_ids:
                    or_audio_ids = (
                        session.query(AudioTag.audio_id)
                        .filter(AudioTag.tag_id.in_(or_tag_ids))
                        .distinct()
                    )
                    query = query.filter(Audio.id.in_(or_audio_ids))

            if and_tags:
                and_tag_ids = [tag_name_to_id[n] for n in and_tags if n in tag_name_to_id]
                if and_tag_ids:
                    audio_tag_counts = (
                        session.query(AudioTag.audio_id, func.count(AudioTag.tag_id).label('tag_count'))
                        .filter(AudioTag.tag_id.in_(and_tag_ids))
                        .group_by(AudioTag.audio_id)
                        .subquery()
                    )
                    query = query.join(audio_tag_counts, audio_tag_counts.c.audio_id == Audio.id).filter(
                        audio_tag_counts.c.tag_count == len(and_tag_ids)
                    )

        return [a.id for a in query.with_entities(Audio.id).all()]

    def collect_folder_files(self, params: dict) -> List[Any]:
        """按条件查询用于构建文件夹树的音频记录（仅选择必要列）。

        返回的是轻量元组列表（非聚合根），用于文件夹树构建。
        """
        session = get_db_session()
        query = session.query(Audio).filter_by(deleted=False)

        keyword = params.get('keyword')
        audio_type = params.get('audio_type')
        format_ = params.get('format_')
        sample_rate = params.get('sample_rate')
        duration = params.get('duration')
        tags_data = params.get('tags_data') or []
        direction = params.get('direction')
        algorithm_type = params.get('algorithm_type')
        parent_path = params.get('parent_path')

        if keyword:
            query = query.filter(
                (Audio.name.like(f'%{keyword}%')) |
                (Audio.original_filename.like(f'%{keyword}%')) |
                (Audio.asr_text.like(f'%{keyword}%'))
            )

        if audio_type:
            query = query.filter_by(audio_type=audio_type)
        if format_:
            query = query.filter_by(format=format_)
        if sample_rate:
            query = query.filter(Audio.sample_rate.between(sample_rate - 100, sample_rate + 100))
        if direction:
            query = query.filter(Audio.source_language == direction)

        if duration:
            if duration == 'short':
                query = query.filter(Audio.duration <= 30)
            elif duration == 'medium':
                query = query.filter(Audio.duration > 30, Audio.duration <= 300)
            elif duration == 'long':
                query = query.filter(Audio.duration > 300)

        if tags_data:
            or_tags = []
            and_tags = []
            for t in tags_data:
                if isinstance(t, dict):
                    tag_name = t.get('name', '')
                    mode = t.get('mode', 'and')
                    if tag_name:
                        if mode == 'or':
                            or_tags.append(tag_name)
                        else:
                            and_tags.append(tag_name)
                elif isinstance(t, str):
                    and_tags.append(t)

            # 通过 gRPC 查询 Tag ID（Tag 属于 task_service 域）
            tag_name_to_id = self._get_tag_name_to_id_map(or_tags + and_tags)

            if or_tags:
                or_tag_ids = [tag_name_to_id[n] for n in or_tags if n in tag_name_to_id]
                if or_tag_ids:
                    or_audio_ids = (
                        session.query(AudioTag.audio_id)
                        .filter(AudioTag.tag_id.in_(or_tag_ids))
                        .distinct()
                    )
                    query = query.filter(Audio.id.in_(or_audio_ids))

            if and_tags:
                and_tag_ids = [tag_name_to_id[n] for n in and_tags if n in tag_name_to_id]
                if and_tag_ids:
                    audio_tag_counts = (
                        session.query(AudioTag.audio_id, func.count(AudioTag.tag_id).label('tag_count'))
                        .filter(AudioTag.tag_id.in_(and_tag_ids))
                        .group_by(AudioTag.audio_id)
                        .subquery()
                    )
                    query = query.join(audio_tag_counts, audio_tag_counts.c.audio_id == Audio.id).filter(
                        audio_tag_counts.c.tag_count == len(and_tag_ids)
                    )

        if algorithm_type:
            audio_ids_with_algo = (
                session.query(AudioAlgorithmRelation.audio_id)
                .filter(AudioAlgorithmRelation.algorithm_type == algorithm_type,
                        AudioAlgorithmRelation.deleted == False)
                .distinct()
            )
            query = query.filter(Audio.id.in_(audio_ids_with_algo))

        if parent_path:
            normalized_parent = parent_path.replace(chr(92), '/')
            escaped = normalized_parent.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
            normalized_path_expr = func.replace(Audio.file_path, chr(92), '/')
            query = query.filter(
                normalized_path_expr.like(f'%{escaped}/%', escape='\\')
            )

        audios = query.with_entities(
            Audio.id, Audio.name, Audio.original_filename, Audio.file_path,
            Audio.format, Audio.duration, Audio.size, Audio.audio_type, Audio.created_at
        ).order_by(Audio.file_path).all()

        return audios

    def get_audio_stats(self) -> dict:
        """获取音频统计信息"""
        session = get_db_session()
        stats_result = session.query(
            func.sum(Audio.size),
            func.sum(Audio.duration)
        ).filter(Audio.deleted == False).first()

        total_size = stats_result[0] or 0
        total_duration = stats_result[1] or 0

        from shared.utils.query_utils import now_cst
        today_start = now_cst().replace(hour=0, minute=0, second=0, microsecond=0)
        today_uploads = session.query(func.count(Audio.id)).filter(
            Audio.created_at >= today_start,
            Audio.deleted == False
        ).scalar() or 0

        return {
            'total_size': total_size,
            'total_duration': total_duration,
            'today_uploads': today_uploads,
        }

    def find_audio_by_name(self, name: str) -> Optional[AudioAggregate]:
        """按文件名查音频（用于补全 rounds_config 中的 audio_id），返回 AudioAggregate。"""
        session = get_db_session()
        po = session.query(Audio).filter_by(name=name, deleted=False).first()
        if po is None:
            return None
        return _audio_po_to_entity(po)

    # ========== Tag 相关 ==========

    def _get_tag_name_to_id_map(self, tag_names: List[str]) -> Dict[str, int]:
        """通过 gRPC 查询标签名 → ID 映射（Tag 属于 task_service 域）"""
        if not tag_names:
            return {}
        from shared.clients.grpc_clients import get_tag_config_service_stub
        from shared.proto import task_service_pb2 as task_pb
        from shared.utils.grpc_json import loads as _loads
        result = {}
        try:
            stub = get_tag_config_service_stub()
            page = 1
            per_page = 500
            target_names = set(tag_names)
            while target_names:
                resp = stub.ListTags(task_pb.ListTagsRequest(
                    page=page,
                    per_page=per_page,
                ))
                if not resp.success:
                    break
                data = _loads(resp.data, {})
                if not isinstance(data, dict):
                    break
                items = data.get('items', []) or []
                for item in items:
                    name = item.get('name')
                    tid = item.get('id')
                    if name and tid and name in target_names:
                        result[name] = tid
                        target_names.discard(name)
                total_pages = data.get('pages', 1)
                if page >= total_pages or not items:
                    break
                page += 1
        except Exception:
            pass
        return result

    def _get_all_tag_name_to_id_map(self) -> Dict[str, int]:
        """通过 gRPC 查询所有标签名 → ID 映射"""
        from shared.clients.grpc_clients import get_tag_config_service_stub
        from shared.proto import task_service_pb2 as task_pb
        from shared.utils.grpc_json import loads as _loads
        result = {}
        try:
            stub = get_tag_config_service_stub()
            page = 1
            per_page = 500
            while True:
                resp = stub.ListTags(task_pb.ListTagsRequest(
                    page=page,
                    per_page=per_page,
                ))
                if not resp.success:
                    break
                data = _loads(resp.data, {})
                if not isinstance(data, dict):
                    break
                items = data.get('items', []) or []
                for item in items:
                    name = item.get('name')
                    tid = item.get('id')
                    if name and tid:
                        result[name] = tid
                total_pages = data.get('pages', 1)
                if page >= total_pages or not items:
                    break
                page += 1
        except Exception:
            pass
        return result

    def get_all_tag_names(self) -> List[str]:
        """查询所有不重复的标签名"""
        from shared.clients.grpc_clients import get_tag_config_service_stub
        from shared.proto import task_service_pb2 as task_pb
        from shared.utils.grpc_json import loads as _loads
        try:
            stub = get_tag_config_service_stub()
            resp = stub.ListTagNames(task_pb.ListTagNamesRequest(
                page=1,
                per_page=500,
            ))
            if not resp.success:
                return []
            data = _loads(resp.data, {})
            if isinstance(data, dict):
                return data.get('items', []) or []
            return []
        except Exception:
            return []

    def get_or_create_tag(self, tag_name: str):
        """查找或创建标签，返回含 id 和 name 的对象（供 add_audio_tag 使用 tag.id）"""
        from shared.clients.grpc_clients import get_tag_config_service_stub
        from shared.proto import task_service_pb2 as task_pb
        from shared.utils.grpc_json import loads as _loads, dumps as _dumps
        try:
            stub = get_tag_config_service_stub()
            # 先查找
            page = 1
            per_page = 500
            while True:
                resp = stub.ListTags(task_pb.ListTagsRequest(
                    page=page,
                    per_page=per_page,
                    keyword=tag_name,
                ))
                if not resp.success:
                    break
                data = _loads(resp.data, {})
                if not isinstance(data, dict):
                    break
                items = data.get('items', []) or []
                for item in items:
                    if item.get('name') == tag_name:
                        return _TagProxy(id=item.get('id'), name=item.get('name'))
                total_pages = data.get('pages', 1)
                if page >= total_pages or not items:
                    break
                page += 1
            # 创建
            create_resp = stub.CreateTag(task_pb.CreateTagRequest(
                data=_dumps({'name': tag_name}),
            ))
            if create_resp.success:
                data = _loads(create_resp.data, {})
                if isinstance(data, dict) and data.get('id'):
                    return _TagProxy(id=data.get('id'), name=data.get('name', tag_name))
        except Exception:
            pass
        return _TagProxy(id=None, name=tag_name)

    def delete_audio_tags(self, audio_id: int) -> int:
        """删除音频的所有标签关联"""
        session = get_db_session()
        count = session.query(AudioTag).filter_by(audio_id=audio_id).delete()
        session.flush()
        return count

    def add_audio_tag(self, audio_id: int, tag_id: int) -> AudioTagEntity:
        """添加音频-标签关联，返回 AudioTagEntity 实体"""
        session = get_db_session()
        audio_tag = AudioTag(audio_id=audio_id, tag_id=tag_id)
        session.add(audio_tag)
        session.flush()
        return _audio_tag_po_to_entity(audio_tag)

    def get_audio_tag_names(self, audio_id: int) -> List[str]:
        """获取音频的标签名列表"""
        session = get_db_session()
        # 先查 AudioTag（e2e 自有），再通过 gRPC 批量查 Tag 名
        ats = session.query(AudioTag).filter(AudioTag.audio_id == audio_id).all()
        if not ats:
            return []
        tag_ids = [at.tag_id for at in ats if at.tag_id]
        if not tag_ids:
            return []
        tag_id_to_name = self._get_tag_id_to_name_map(tag_ids)
        return [tag_id_to_name.get(tid, str(tid)) for tid in tag_ids]

    def get_audio_tags_map(self, audio_ids: List[int]) -> Dict[int, List[str]]:
        """批量获取多个音频的标签映射"""
        session = get_db_session()
        if not audio_ids:
            return {}
        ats = session.query(AudioTag).filter(AudioTag.audio_id.in_(audio_ids)).all()
        if not ats:
            return {}
        tag_ids = list(set(at.tag_id for at in ats if at.tag_id))
        if not tag_ids:
            return {}
        tag_id_to_name = self._get_tag_id_to_name_map(tag_ids)
        result: Dict[int, List[str]] = {}
        for at in ats:
            name = tag_id_to_name.get(at.tag_id, str(at.tag_id))
            result.setdefault(at.audio_id, []).append(name)
        return result

    def _get_tag_id_to_name_map(self, tag_ids: List[int]) -> Dict[int, str]:
        """通过 gRPC 查询标签 ID → 名映射（Tag 属于 task_service 域）"""
        if not tag_ids:
            return {}
        from shared.clients.grpc_clients import get_tag_config_service_stub
        from shared.proto import task_service_pb2 as task_pb
        from shared.utils.grpc_json import loads as _loads
        result = {}
        try:
            stub = get_tag_config_service_stub()
            page = 1
            per_page = 500
            remaining = set(tag_ids)
            while remaining:
                resp = stub.ListTags(task_pb.ListTagsRequest(
                    page=page,
                    per_page=per_page,
                ))
                if not resp.success:
                    break
                data = _loads(resp.data, {})
                if not isinstance(data, dict):
                    break
                items = data.get('items', []) or []
                for item in items:
                    tid = item.get('id')
                    name = item.get('name')
                    if tid and name and tid in remaining:
                        result[tid] = name
                        remaining.discard(tid)
                total_pages = data.get('pages', 1)
                if page >= total_pages or not items:
                    break
                page += 1
        except Exception:
            pass
        return result

    # ========== Annotation 相关 ==========

    def delete_audio_annotations(self, audio_id: int) -> int:
        """删除音频的所有标注（物理删除，兼容原行为）"""
        session = get_db_session()
        count = session.query(AudioAnnotation).filter_by(audio_id=audio_id).delete()
        session.flush()
        return count

    def soft_delete_annotation_by_code(self, audio_id: int, code: str) -> Optional[AudioAnnotationEntity]:
        """按 code 软删除标注，返回更新后的 AudioAnnotationEntity。"""
        session = get_db_session()
        existing = session.query(AudioAnnotation).filter_by(
            audio_id=audio_id, code=code, deleted=False
        ).first()
        if existing:
            existing.deleted = True
            session.flush()
            return _audio_annotation_po_to_entity(existing)
        return None

    def create_audio_annotation(self, audio_id: int, ann: dict) -> AudioAnnotationEntity:
        """创建音频标注，返回 AudioAnnotationEntity 实体。"""
        session = get_db_session()
        annotation = AudioAnnotation(
            audio_id=audio_id,
            format=ann.get('format', 'json'),
            code=ann.get('code', ''),
            data=ann.get('data', {}) or {},
            source_language=ann.get('source_language', ''),
            target_language=ann.get('target_language', ''),
        )
        session.add(annotation)
        session.flush()
        return _audio_annotation_po_to_entity(annotation)

    def get_annotations_by_audio(self, audio_id: int, include_deleted: bool = False) -> List[AudioAnnotationEntity]:
        """获取音频的所有标注，返回 AudioAnnotationEntity 列表。"""
        session = get_db_session()
        query = session.query(AudioAnnotation).filter_by(audio_id=audio_id)
        if not include_deleted:
            query = query.filter(AudioAnnotation.deleted == False)
        return [_audio_annotation_po_to_entity(po) for po in query.all()]

    def get_annotations_map(self, audio_ids: List[int]) -> Dict[int, List[dict]]:
        """批量获取多个音频的标注映射（保留 dict 形式以便上层消费）"""
        session = get_db_session()
        if not audio_ids:
            return {}
        records = session.query(AudioAnnotation).filter(
            AudioAnnotation.audio_id.in_(audio_ids),
            AudioAnnotation.deleted == False
        ).all()
        result: Dict[int, List[dict]] = {}
        for ann in records:
            result.setdefault(ann.audio_id, []).append({
                'format': ann.format,
                'code': ann.code,
                'data': ann.data,
                'source_language': ann.source_language,
                'target_language': ann.target_language,
            })
        return result

    # ========== Algorithm Relation 相关 ==========

    def get_audio_algorithm_relations(self, audio_id: int) -> List[AudioAlgorithmRelationEntity]:
        """获取音频算法关联列表，返回 AudioAlgorithmRelationEntity 列表。"""
        session = get_db_session()
        pos = session.query(AudioAlgorithmRelation).filter_by(
            audio_id=audio_id, deleted=False
        ).all()
        return [_audio_algorithm_relation_po_to_entity(po) for po in pos]

    def soft_delete_audio_algorithm_relations(self, audio_id: int) -> int:
        """软删除音频算法关联"""
        session = get_db_session()
        count = session.query(AudioAlgorithmRelation).filter_by(
            audio_id=audio_id
        ).update({'deleted': True})
        session.flush()
        return count

    def create_audio_algorithm_relation(self, audio_id: int, item: dict) -> AudioAlgorithmRelationEntity:
        """创建音频算法关联，返回 AudioAlgorithmRelationEntity 实体。"""
        session = get_db_session()
        relation = AudioAlgorithmRelation(
            audio_id=audio_id,
            algorithm_type=item.get('algorithm_type'),
            is_primary=item.get('is_primary', False),
            weight=item.get('weight', 1.0),
            params=item.get('params'),
        )
        session.add(relation)
        session.flush()
        return _audio_algorithm_relation_po_to_entity(relation)

    # ========== Upload 相关 ==========

    def create_upload_task(self, task_id: str, total_files: int = 0, total_size: int = 0,
                          status: str = 'preparing', expired_at=None) -> UploadTaskAggregate:
        """创建上传任务，返回 UploadTaskAggregate 聚合根。"""
        session = get_db_session()
        task = UploadTask(
            id=task_id,
            total_files=total_files,
            completed_files=0,
            failed_files=0,
            total_size=total_size,
            uploaded_size=0,
            status=status,
            expired_at=expired_at,
        )
        session.add(task)
        session.flush()
        return _upload_task_po_to_entity(task)

    def get_upload_task(self, task_id: str) -> Optional[UploadTaskAggregate]:
        """获取上传任务，返回 UploadTaskAggregate。"""
        session = get_db_session()
        po = session.get(UploadTask, task_id)
        if po is None:
            return None
        return _upload_task_po_to_entity(po)

    def update_upload_task(self, task_id: str, **fields) -> Optional[UploadTaskAggregate]:
        """更新上传任务字段，返回更新后的 UploadTaskAggregate。

        P5+DOMAIN: 改为通过 PO ↔ Entity 转换，不再接收外部传入的 PO 对象。
        """
        session = get_db_session()
        po = session.get(UploadTask, task_id)
        if po is None:
            return None
        for key, value in fields.items():
            setattr(po, key, value)
        session.flush()
        return _upload_task_po_to_entity(po)

    def create_upload_file(self, file_id: str, task_id: str, filename: str,
                          original_filename: str, relative_path: str,
                          size: int, md5: str, status: str,
                          uploaded_size: int, completed_chunks: int,
                          total_chunks: int) -> UploadFileEntity:
        """创建上传文件记录，返回 UploadFileEntity 实体。"""
        session = get_db_session()
        upload_file = UploadFile(
            id=file_id,
            task_id=task_id,
            filename=filename,
            original_filename=original_filename,
            relative_path=relative_path,
            size=size,
            md5=md5,
            status=status,
            uploaded_size=uploaded_size,
            completed_chunks=completed_chunks,
            total_chunks=total_chunks,
        )
        session.add(upload_file)
        session.flush()
        return _upload_file_po_to_entity(upload_file)

    def get_upload_file(self, file_id: str) -> Optional[UploadFileEntity]:
        """获取上传文件记录，返回 UploadFileEntity。"""
        session = get_db_session()
        po = session.get(UploadFile, file_id)
        if po is None:
            return None
        return _upload_file_po_to_entity(po)

    def update_upload_file(self, file_id: str, **fields) -> Optional[UploadFileEntity]:
        """更新上传文件字段，返回更新后的 UploadFileEntity。

        P5+DOMAIN: 改为通过 PO ↔ Entity 转换，不再接收外部传入的 PO 对象。
        """
        session = get_db_session()
        po = session.get(UploadFile, file_id)
        if po is None:
            return None
        for key, value in fields.items():
            setattr(po, key, value)
        session.flush()
        return _upload_file_po_to_entity(po)

    def list_upload_files(self, task_id: str) -> List[UploadFileEntity]:
        """列出上传任务下的所有文件，返回 UploadFileEntity 列表。"""
        session = get_db_session()
        pos = session.query(UploadFile).filter_by(task_id=task_id).all()
        return [_upload_file_po_to_entity(po) for po in pos]

    def create_upload_chunk(self, file_id: str, chunk_index: int, chunk_size: int,
                           stored_path: str, status: str = 'completed') -> UploadChunkEntity:
        """创建上传分片记录，返回 UploadChunkEntity 实体。"""
        session = get_db_session()
        chunk = UploadChunk(
            file_id=file_id,
            chunk_index=chunk_index,
            chunk_size=chunk_size,
            stored_path=stored_path,
            status=status,
        )
        session.add(chunk)
        session.flush()
        return _upload_chunk_po_to_entity(chunk)

    def get_upload_chunk(self, file_id: str, chunk_index: int) -> Optional[UploadChunkEntity]:
        """获取上传分片记录，返回 UploadChunkEntity。"""
        session = get_db_session()
        po = session.query(UploadChunk).filter_by(
            file_id=file_id, chunk_index=chunk_index
        ).first()
        if po is None:
            return None
        return _upload_chunk_po_to_entity(po)

    # ========== Upload 进度更新（通过 PO 回写）==========

    def update_upload_task_progress(self, task_id: str, **fields) -> Optional[UploadTaskAggregate]:
        """更新 UploadTask 进度字段（如 total_files / completed_files / status 等）。

        直接通过 PO 字段名回写，内部走 PO ↔ Entity 转换。
        """
        session = get_db_session()
        po = session.get(UploadTask, task_id)
        if po is None:
            return None
        for key, value in fields.items():
            setattr(po, key, value)
        session.flush()
        return _upload_task_po_to_entity(po)

    def update_upload_file_progress(self, file_id: str, **fields) -> Optional[UploadFileEntity]:
        """更新 UploadFile 进度字段（如 completed_chunks / uploaded_size / status 等）。

        直接通过 PO 字段名回写，内部走 PO ↔ Entity 转换。
        """
        session = get_db_session()
        po = session.get(UploadFile, file_id)
        if po is None:
            return None
        for key, value in fields.items():
            setattr(po, key, value)
        session.flush()
        return _upload_file_po_to_entity(po)

    def commit(self):
        """提交事务"""
        get_db_session().commit()

    def rollback(self):
        """回滚事务"""
        get_db_session().rollback()

    def flush(self):
        """flush session"""
        get_db_session().flush()

    @property
    def no_autoflush(self):
        """进入 no_autoflush 上下文"""
        return get_db_session().no_autoflush


# 模块级单例
audio_repository = AudioRepository()
