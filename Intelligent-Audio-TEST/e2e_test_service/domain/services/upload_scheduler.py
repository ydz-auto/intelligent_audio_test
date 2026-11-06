# -*- coding: utf-8 -*-
"""上传调度领域服务 - UploadScheduler。

领域服务封装了不属于单一实体的领域逻辑。UploadScheduler 负责上传分块
策略计算（纯逻辑，不含任何 IO），保证领域层的纯粹性。
"""
from __future__ import annotations

from typing import List

from e2e_test_service.domain.entities.upload import UploadChunkEntity, UploadFileEntity

# 模块级常量：类体方法默认参数在类定义时尚未绑定类名，故置于模块级
DEFAULT_CHUNK_SIZE = 5 * 1024 * 1024  # 默认分片大小 5MB
MAX_CHUNKS = 10000  # 单文件最大分片数


class UploadScheduler:
    """上传调度领域服务

    职责：
    - 根据文件大小与目标分片大小，计算分片计划
    - 生成 UploadChunkEntity 列表，供 UploadFileEntity 持有

    本类不直接执行任何 IO，仅操作领域对象。

    常量 DEFAULT_CHUNK_SIZE / MAX_CHUNKS 亦作为类属性暴露，
    便于以 UploadScheduler.DEFAULT_CHUNK_SIZE 形式引用。
    """

    DEFAULT_CHUNK_SIZE = DEFAULT_CHUNK_SIZE  # 默认分片大小 5MB
    MAX_CHUNKS = MAX_CHUNKS  # 单文件最大分片数

    @staticmethod
    def compute_chunk_count(file_size: int, chunk_size: int = DEFAULT_CHUNK_SIZE) -> int:
        """计算给定文件大小所需的分片数量

        Args:
            file_size: 文件大小（字节）
            chunk_size: 单分片大小（字节）

        Returns:
            分片数量；file_size <= 0 时返回 0
        """
        if file_size <= 0 or chunk_size <= 0:
            return 0
        count = (file_size + chunk_size - 1) // chunk_size
        return min(count, MAX_CHUNKS)

    @staticmethod
    def plan_chunks(file: UploadFileEntity, chunk_size: int = DEFAULT_CHUNK_SIZE) -> List[UploadChunkEntity]:
        """为上传文件生成分片计划

        根据文件大小与分片大小，生成一组 UploadChunkEntity，
        并按 chunk_index 升序返回。不修改 file 实体本身的状态。
        """
        if file.file_size <= 0 or chunk_size <= 0:
            return []

        count = UploadScheduler.compute_chunk_count(file.file_size, chunk_size)
        chunks: List[UploadChunkEntity] = []
        remaining = file.file_size
        for idx in range(count):
            size = min(chunk_size, remaining)
            chunks.append(
                UploadChunkEntity(
                    upload_file_id=file.id,
                    chunk_index=idx,
                    chunk_size=size,
                    uploaded=False,
                )
            )
            remaining -= size
        return chunks
