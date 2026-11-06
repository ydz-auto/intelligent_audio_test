# -*- coding: utf-8 -*-
"""上传聚合 - UploadTask 聚合根 + UploadFile/UploadChunk 实体。

UploadTask 是 e2e 测试上下文中的文件上传任务聚合根，统一管理其边界内的
上传文件（UploadFileEntity）与分片（UploadChunkEntity）。本模块为纯领域
模型，不依赖 SQLAlchemy/db.Model，亦不包含任何 IO 调用。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, List, Optional


class UploadStatus(Enum):
    """上传状态枚举"""
    pending = "pending"
    uploading = "uploading"
    completed = "completed"
    failed = "failed"


@dataclass
class UploadChunkEntity:
    """上传分片实体 - 归属于 UploadFile 聚合内"""
    id: Optional[int] = None
    upload_file_id: Optional[str] = None
    chunk_index: int = 0
    chunk_size: int = 0
    uploaded: bool = False

    def mark_uploaded(self) -> None:
        """标记分片已上传完成"""
        self.uploaded = True


@dataclass
class UploadFileEntity:
    """上传文件实体 - 归属于 UploadTask 聚合内"""
    id: Optional[str] = None
    upload_task_id: Optional[str] = None
    filename: str = ""
    file_size: int = 0
    uploaded_size: int = 0
    status: Any = UploadStatus.pending
    # 扩展属性（与 PO 同名字段，供上层直接访问，避免感知 PO）
    original_filename: str = ""
    relative_path: str = ""
    md5: str = ""
    completed_chunks: int = 0
    total_chunks: int = 0
    created_at: Any = None

    # --- PO 字段名兼容属性 ---

    @property
    def size(self) -> int:
        """PO.size 的兼容访问，映射到 entity.file_size"""
        return self.file_size

    def mark_uploading(self) -> None:
        """标记文件为上传中"""
        self.status = UploadStatus.uploading

    def mark_completed(self) -> None:
        """标记文件上传完成"""
        self.status = UploadStatus.completed
        self.uploaded_size = self.file_size

    def mark_failed(self) -> None:
        """标记文件上传失败"""
        self.status = UploadStatus.failed

    @property
    def is_completed(self) -> bool:
        """是否已完成"""
        return self.status is UploadStatus.completed

    @property
    def progress(self) -> float:
        """上传进度（0.0 - 1.0）"""
        if self.file_size <= 0:
            return 0.0
        return min(1.0, self.uploaded_size / self.file_size)


@dataclass
class UploadTaskAggregate:
    """上传任务聚合根

    持有任务唯一标识及总体进度，并通过 chunks 维护其边界内的文件集合
    （UploadFileEntity，其内部再持有 UploadChunkEntity）。
    """
    id: Optional[str] = None
    total_files: int = 0
    total_size: int = 0
    uploaded_size: int = 0
    status: Any = UploadStatus.pending
    chunks: List[UploadFileEntity] = field(default_factory=list)
    # 扩展属性（与 PO 同名字段，供上层直接访问，避免感知 PO）
    completed_files: int = 0
    failed_files: int = 0
    created_at: Any = None

    def add_file(self, file: UploadFileEntity) -> None:
        """追加一个上传文件并回填 upload_task_id"""
        file.upload_task_id = self.id
        self.chunks.append(file)

    def mark_uploading(self) -> None:
        """标记任务为上传中"""
        self.status = UploadStatus.uploading

    def mark_completed(self) -> None:
        """标记任务上传完成"""
        self.status = UploadStatus.completed

    def mark_failed(self) -> None:
        """标记任务上传失败"""
        self.status = UploadStatus.failed

    @property
    def progress(self) -> float:
        """整体上传进度（0.0 - 1.0）"""
        if self.total_size <= 0:
            return 0.0
        return min(1.0, self.uploaded_size / self.total_size)

    @property
    def is_terminal(self) -> bool:
        """是否处于终态"""
        return self.status in (UploadStatus.completed, UploadStatus.failed)
