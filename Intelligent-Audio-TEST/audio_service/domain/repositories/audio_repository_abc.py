# -*- coding: utf-8 -*-
"""音频仓储接口（ABC）— 依赖倒置契约。

domain 层定义接口，infrastructure/persistence/audio_repository.py 做实现。
application/handlers 层依赖此 ABC，不直接 import 具体仓储类。

遵循 DDD 分层原则：domain 不依赖 SQLAlchemy/db.session 等基础设施。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from audio_service.domain.entities import (
    AudioAggregate,
    AudioAlgorithmRelationEntity,
    AudioAnnotationEntity,
    AudioTagEntity,
    UploadChunkEntity,
    UploadFileEntity,
    UploadStatus,
    UploadTaskAggregate,
)


class AudioRepositoryInterface(ABC):
    """音频聚合根仓储接口。

    所有方法返回领域实体（AudioAggregate 等）或基础类型，
    绝不返回 ORM/PO 对象。
    """

    # ========== Audio 基础 CRUD ==========

    @abstractmethod
    def create_audio(self, data: dict) -> AudioAggregate: ...



    @abstractmethod
    def update_audio(self, audio_id: int, update_fields: dict) -> Optional[AudioAggregate]: ...

    @abstractmethod
    def get_audio(self, audio_id: int) -> Optional[AudioAggregate]: ...

    @abstractmethod
    def get_audio_with_deleted(self, audio_id: int) -> Optional[AudioAggregate]: ...

    @abstractmethod
    def delete_audio(self, audio_id: int) -> bool: ...

    @abstractmethod
    def batch_soft_delete_audios(self, audio_ids: List[int]) -> int: ...

    @abstractmethod
    def list_audios(self, params: dict) -> Any: ...

    @abstractmethod
    def get_audios_by_ids(self, audio_ids: List[int]) -> List[AudioAggregate]: ...

    @abstractmethod
    def get_audio_by_md5(self, md5: str) -> Optional[AudioAggregate]: ...

    @abstractmethod
    def get_audios_by_md5_list(self, md5_list: List[str]) -> List[AudioAggregate]: ...

    @abstractmethod
    def get_all_audio_ids(self, params: dict) -> List[int]: ...

    @abstractmethod
    def collect_folder_files(self, params: dict) -> List[Any]: ...

    @abstractmethod
    def get_audio_stats(self) -> dict: ...

    @abstractmethod
    def find_audio_by_name(self, name: str) -> Optional[AudioAggregate]: ...

    # ========== Tag 相关 ==========

    @abstractmethod
    def get_all_tag_names(self) -> List[str]: ...

    @abstractmethod
    def get_or_create_tag(self, tag_name: str) -> Any: ...

    @abstractmethod
    def delete_audio_tags(self, audio_id: int) -> int: ...

    @abstractmethod
    def add_audio_tag(self, audio_id: int, tag_id: int) -> AudioTagEntity: ...

    @abstractmethod
    def get_audio_tag_names(self, audio_id: int) -> List[str]: ...

    @abstractmethod
    def get_audio_tags_map(self, audio_ids: List[int]) -> Dict[int, List[str]]: ...

    # ========== Annotation 相关 ==========

    @abstractmethod
    def delete_audio_annotations(self, audio_id: int) -> int: ...

    @abstractmethod
    def soft_delete_annotation_by_code(self, audio_id: int, code: str) -> Optional[AudioAnnotationEntity]: ...

    @abstractmethod
    def create_audio_annotation(self, audio_id: int, ann: dict) -> AudioAnnotationEntity: ...

    @abstractmethod
    def get_annotations_by_audio(self, audio_id: int, include_deleted: bool = False) -> List[AudioAnnotationEntity]: ...

    @abstractmethod
    def get_annotations_map(self, audio_ids: List[int]) -> Dict[int, List[dict]]: ...

    # ========== Algorithm Relation 相关 ==========

    @abstractmethod
    def get_audio_algorithm_relations(self, audio_id: int) -> List[AudioAlgorithmRelationEntity]: ...

    @abstractmethod
    def soft_delete_audio_algorithm_relations(self, audio_id: int) -> int: ...

    @abstractmethod
    def create_audio_algorithm_relation(self, audio_id: int, item: dict) -> AudioAlgorithmRelationEntity: ...

    # ========== Session 管理 ==========

    @abstractmethod
    def commit(self): ...

    @abstractmethod
    def rollback(self): ...

    @abstractmethod
    def flush(self): ...

    @property
    @abstractmethod
    def no_autoflush(self): ...


class UploadRepositoryInterface(ABC):
    """上传任务仓储接口。"""

    @abstractmethod
    def create_upload_task(self, task_id: str, total_files: int = 0, total_size: int = 0,
                           status: str = 'preparing', expired_at=None) -> UploadTaskAggregate: ...

    @abstractmethod
    def get_upload_task(self, task_id: str) -> Optional[UploadTaskAggregate]: ...

    @abstractmethod
    def update_upload_task(self, task_id: str, **fields) -> Optional[UploadTaskAggregate]: ...

    @abstractmethod
    def create_upload_file(self, file_id: str, task_id: str, filename: str,
                           original_filename: str, relative_path: str,
                           size: int, md5: str, status: str,
                           uploaded_size: int, completed_chunks: int,
                           total_chunks: int) -> UploadFileEntity: ...

    @abstractmethod
    def get_upload_file(self, file_id: str) -> Optional[UploadFileEntity]: ...

    @abstractmethod
    def update_upload_file(self, file_id: str, **fields) -> Optional[UploadFileEntity]: ...

    @abstractmethod
    def list_upload_files(self, task_id: str) -> List[UploadFileEntity]: ...

    @abstractmethod
    def create_upload_chunk(self, file_id: str, chunk_index: int, chunk_size: int,
                            stored_path: str, status: str = 'completed') -> UploadChunkEntity: ...

    @abstractmethod
    def get_upload_chunk(self, file_id: str, chunk_index: int) -> Optional[UploadChunkEntity]: ...

    @abstractmethod
    def update_upload_task_progress(self, task_id: str, **fields) -> Optional[UploadTaskAggregate]: ...

    @abstractmethod
    def update_upload_file_progress(self, file_id: str, **fields) -> Optional[UploadFileEntity]: ...
