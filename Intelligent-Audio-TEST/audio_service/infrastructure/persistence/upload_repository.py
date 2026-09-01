# -*- coding: utf-8 -*-
"""上传任务仓储实现（从 audio_repository.py 拆分，P4-4）。

UploadRepository：实现 domain.repositories.audio_repository_abc.UploadRepositoryInterface，
覆盖 UploadTask / UploadFile / UploadChunk 三张表的 CRUD 与进度更新。
"""
from typing import List, Optional

from shared.models.database import get_db_session
from audio_service.infrastructure.persistence.models import (
    UploadTask,
    UploadFile,
    UploadChunk,
)
from audio_service.domain.entities import (
    UploadTaskAggregate,
    UploadFileEntity,
    UploadChunkEntity,
)
from audio_service.domain.repositories.audio_repository_abc import UploadRepositoryInterface
from audio_service.infrastructure.persistence._audio_converters import (
    _upload_task_po_to_entity,
    _upload_file_po_to_entity,
    _upload_chunk_po_to_entity,
)


class UploadRepository(UploadRepositoryInterface):
    """上传任务仓储：UploadTask / UploadFile / UploadChunk CRUD"""

    # ========== UploadTask ==========

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
