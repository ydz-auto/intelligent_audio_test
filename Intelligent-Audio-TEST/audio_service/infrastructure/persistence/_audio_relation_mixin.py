# -*- coding: utf-8 -*-
"""音频关联集合仓储 Mixin（从 audio_repository.py 拆分，P4-4）。

提取 AudioRepository 中 Tag / Annotation / AlgorithmRelation 三类关联
集合的读写方法，遵循项目既有的 Mixin 组合模式（参考 _param_mixin 拆分），
使主仓储文件聚焦音频聚合根本身的 CRUD。
"""
from typing import Dict, List, Optional

from shared.models.database import get_db_session
from audio_service.infrastructure.persistence.models import (
    AudioAnnotation,
    AudioTag,
    AudioAlgorithmRelation,
)
from audio_service.domain.entities import (
    AudioAnnotationEntity,
    AudioTagEntity,
    AudioAlgorithmRelationEntity,
)
from audio_service.infrastructure.persistence._audio_converters import (
    _audio_annotation_po_to_entity,
    _audio_tag_po_to_entity,
    _audio_algorithm_relation_po_to_entity,
)


class AudioRelationMixin:
    """音频关联集合仓储：标签 / 标注 / 算法关联的读写（供 AudioRepository 组合）"""

    # ========== Tag 相关 ==========

    def _get_tag_name_to_id_map(self, tag_names: List[str]) -> Dict[str, int]:
        """通过 gRPC 查询标签名 → ID 映射（Tag 属于 task_service 域）"""
        from audio_service.infrastructure.acl.tag_acl_repository import tag_acl_repository
        return tag_acl_repository.get_tag_name_to_id_map(tag_names)

    def _get_all_tag_name_to_id_map(self) -> Dict[str, int]:
        """通过 gRPC 查询所有标签名 → ID 映射"""
        from audio_service.infrastructure.acl.tag_acl_repository import tag_acl_repository
        return tag_acl_repository.get_all_tag_name_to_id_map()

    def get_all_tag_names(self) -> List[str]:
        """查询所有不重复的标签名"""
        from audio_service.infrastructure.acl.tag_acl_repository import tag_acl_repository
        return tag_acl_repository.get_all_tag_names()

    def get_or_create_tag(self, tag_name: str):
        """查找或创建标签，返回含 id 和 name 的对象（供 add_audio_tag 使用 tag.id）"""
        from audio_service.infrastructure.acl.tag_acl_repository import tag_acl_repository
        return tag_acl_repository.get_or_create_tag(tag_name)

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
        from audio_service.infrastructure.acl.tag_acl_repository import tag_acl_repository
        return tag_acl_repository.get_tag_id_to_name_map(tag_ids)

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
