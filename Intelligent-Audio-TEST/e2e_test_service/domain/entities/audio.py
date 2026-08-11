# -*- coding: utf-8 -*-
"""音频聚合 - Audio 聚合根 + 标注/标签/算法关联实体。

Audio 是 e2e 测试上下文中的音频素材聚合根，统一管理音频元数据及其
边界内的标注（AudioAnnotationEntity）、标签（AudioTagEntity）与
算法关联（AudioAlgorithmRelationEntity）。本模块为纯领域模型，不依赖
SQLAlchemy/db.Model，亦不包含任何 IO 调用。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class AudioAnnotationEntity:
    """音频标注实体 - 归属于 Audio 聚合内"""
    id: Optional[int] = None
    audio_id: Optional[int] = None
    content: str = ""
    start_time: float = 0.0
    end_time: float = 0.0
    # 扩展属性（与 PO 同名字段，供上层直接访问，避免感知 PO）
    format: str = "json"
    code: str = ""
    data: Any = None
    source_language: str = ""
    target_language: str = ""
    deleted: bool = False


@dataclass
class AudioTagEntity:
    """音频标签实体 - 归属于 Audio 聚合内"""
    id: Optional[int] = None
    audio_id: Optional[int] = None
    tag_name: str = ""


@dataclass
class AudioAlgorithmRelationEntity:
    """音频与算法关联实体 - 归属于 Audio 聚合内"""
    id: Optional[int] = None
    audio_id: Optional[int] = None
    algorithm_type: str = ""
    params: Dict[str, Any] = field(default_factory=dict)
    # 扩展属性（与 PO 同名字段，供上层直接访问，避免感知 PO）
    is_primary: bool = False
    weight: float = 1.0


@dataclass
class AudioAggregate:
    """音频聚合根

    持有音频唯一标识及物理/元数据属性，并通过 annotations / tags /
    algorithm_relations 维护其边界内的关联实体集合。
    """
    id: Optional[int] = None
    filename: str = ""
    duration: float = 0.0
    sample_rate: int = 0
    channels: int = 0
    file_path: str = ""
    file_size: int = 0
    audio_format: str = ""
    # 扩展属性（与 PO 同名字段，供上层直接访问，避免感知 PO）
    deleted: bool = False
    original_filename: str = ""
    md5: str = ""
    audio_type: str = "dry"
    asr_text: str = ""
    description: str = ""
    source_language: str = ""
    bitrate: int = 0
    created_at: Any = None
    updated_at: Any = None
    annotations: List[AudioAnnotationEntity] = field(default_factory=list)
    tags: List[AudioTagEntity] = field(default_factory=list)
    algorithm_relations: List[AudioAlgorithmRelationEntity] = field(default_factory=list)

    # --- PO 字段名兼容属性（供上层以 PO 字段名访问，不感知 entity 命名差异）---

    @property
    def name(self) -> str:
        """PO.name 的兼容访问，映射到 entity.filename"""
        return self.filename

    @property
    def size(self) -> int:
        """PO.size 的兼容访问，映射到 entity.file_size"""
        return self.file_size

    @property
    def format(self) -> str:
        """PO.format 的兼容访问，映射到 entity.audio_format"""
        return self.audio_format

    def add_annotation(self, annotation: AudioAnnotationEntity) -> None:
        """追加标注并回填 audio_id"""
        annotation.audio_id = self.id
        self.annotations.append(annotation)

    def add_tag(self, tag: AudioTagEntity) -> None:
        """追加标签并回填 audio_id"""
        tag.audio_id = self.id
        self.tags.append(tag)

    def add_algorithm_relation(self, relation: AudioAlgorithmRelationEntity) -> None:
        """追加算法关联并回填 audio_id"""
        relation.audio_id = self.id
        self.algorithm_relations.append(relation)

    def to_snapshot(self) -> "AudioSnapshot":
        """生成不可变快照"""
        return AudioSnapshot(
            id=self.id,
            filename=self.filename,
            duration=self.duration,
            sample_rate=self.sample_rate,
            channels=self.channels,
            file_path=self.file_path,
            file_size=self.file_size,
            audio_format=self.audio_format,
            tag_names=[t.tag_name for t in self.tags],
            algorithm_types=[r.algorithm_type for r in self.algorithm_relations],
            annotation_count=len(self.annotations),
        )


@dataclass(frozen=True)
class AudioSnapshot:
    """音频不可变快照值对象

    用于跨层传递音频当前状态；关联集合以摘要形式快照，不暴露内部实体引用。
    """
    id: Optional[int]
    filename: str
    duration: float
    sample_rate: int
    channels: int
    file_path: str
    file_size: int
    audio_format: str
    tag_names: List[str] = field(default_factory=list)
    algorithm_types: List[str] = field(default_factory=list)
    annotation_count: int = 0
