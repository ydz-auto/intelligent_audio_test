# -*- coding: utf-8 -*-
"""音频配置仓储 — 聚合导出模块（P4-4 大文件拆分）。

原单文件 1060 行，已按职责拆分为 4 个内部模块，本文件保持
`from audio_service.infrastructure.persistence.audio_repository import ...`
的全部导入路径不变：

- _audio_converters.py：PO ↔ Entity 显式转换函数（Audio/Upload 系列实体）
- _audio_query_filters.py：公共查询过滤器（list/folder_tree 共用，消除重复）
- _audio_relation_mixin.py：Tag/标注/算法关联读写 Mixin
- upload_repository.py：UploadRepository（UploadTask/File/Chunk CRUD）

AudioRepository（音频聚合根仓储，实现 AudioRepositoryInterface + UploadRepositoryInterface）
保留在本文件，通过 Mixin 组合保持原单例 audio_repository 的全部方法可用。
"""
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import func

from shared.models.database import get_db_session
from audio_service.infrastructure.persistence.models import Audio
from audio_service.domain.entities import AudioAggregate
from audio_service.domain.repositories.audio_repository_abc import (
    AudioRepositoryInterface,
)
from audio_service.infrastructure.persistence._audio_converters import (
    _now,
    _audio_po_to_entity,
)
from audio_service.infrastructure.persistence._audio_query_filters import (
    apply_audio_list_filters,
    apply_folder_tree_filters,
)
from audio_service.infrastructure.persistence._audio_relation_mixin import (
    AudioRelationMixin,
)
from audio_service.infrastructure.persistence.upload_repository import UploadRepository

logger = logging.getLogger(__name__)


class AudioRepository(AudioRelationMixin, AudioRepositoryInterface, UploadRepository):
    """音频聚合根仓储

    P5+DOMAIN: 通过 PO ↔ Entity 显式转换，仓储方法返回 domain entities，
    聚合根不再持有 ORM 引用，领域层与 SQLAlchemy 完全隔离。

    组合结构（MRO：AudioRelationMixin → AudioRepositoryInterface → UploadRepository）：
    - AudioRelationMixin：Tag / 标注 / 算法关联读写
    - AudioRepositoryInterface：音频聚合根 CRUD 契约（本文件实现）
    - UploadRepository：上传任务/文件/分片 CRUD（原 AudioRepository 内联实现，拆出复用）

    查询过滤逻辑复用 _audio_query_filters（list_audios / get_all_audio_ids /
    collect_folder_files 三处共用，消除重复代码）。
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
        query = apply_audio_list_filters(query, session, params, self._get_tag_name_to_id_map)

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
        query = apply_audio_list_filters(query, session, params, self._get_tag_name_to_id_map)
        return [a.id for a in query.with_entities(Audio.id).all()]

    def collect_folder_files(self, params: dict) -> List[Any]:
        """按条件查询用于构建文件夹树的音频记录（仅选择必要列）。

        返回的是轻量元组列表（非聚合根），用于文件夹树构建。
        """
        session = get_db_session()
        query = session.query(Audio).filter_by(deleted=False)
        query = apply_folder_tree_filters(query, session, params, self._get_tag_name_to_id_map)

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
        """按文件名查音频（用于补全 rounds_config 中的 audio_id），返回 AudioAggregate。

        先按 name 查，未命中再按 original_filename 查（兼容统一标注文件格式）。
        """
        session = get_db_session()
        po = session.query(Audio).filter_by(name=name, deleted=False).first()
        if po is None:
            po = session.query(Audio).filter_by(
                original_filename=name, deleted=False
            ).first()
        if po is None:
            return None
        return _audio_po_to_entity(po)


# ==================== 转换函数与辅助对象再导出（保持模块内部符号可见）====================

from audio_service.infrastructure.persistence._audio_converters import (  # noqa: E402
    _apply_aggregate_to_po,
    _audio_annotation_po_to_entity,
    _audio_tag_po_to_entity,
    _audio_algorithm_relation_po_to_entity,
    _apply_algorithm_relation_entity_to_po,
    _upload_task_po_to_entity,
    _apply_upload_task_entity_to_po,
    _upload_file_po_to_entity,
    _apply_upload_file_entity_to_po,
    _upload_chunk_po_to_entity,
    _parse_upload_status,
    _pair_audio_tags,
)
from audio_service.infrastructure.persistence.upload_repository import (  # noqa: E402
    UploadRepository as _UploadRepository,
)

__all__ = [
    # 仓储类与单例
    "AudioRepository",
    "UploadRepository",
    "audio_repository",
    "upload_repository",
    # PO ↔ Entity 转换函数（保持原模块符号可见）
    "_audio_po_to_entity",
    "_apply_aggregate_to_po",
    "_audio_annotation_po_to_entity",
    "_audio_tag_po_to_entity",
    "_audio_algorithm_relation_po_to_entity",
    "_apply_algorithm_relation_entity_to_po",
    "_upload_task_po_to_entity",
    "_apply_upload_task_entity_to_po",
    "_upload_file_po_to_entity",
    "_apply_upload_file_entity_to_po",
    "_upload_chunk_po_to_entity",
    "_parse_upload_status",
    "_pair_audio_tags",
    "_now",
]


# 模块级单例
audio_repository = AudioRepository()
upload_repository = _UploadRepository()
