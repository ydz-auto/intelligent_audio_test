# -*- coding: utf-8 -*-
"""传输存储适配器 — TransferStorageABC 实现，复用 shared.infrastructure.storage。

- 分片暂存：transit 域，key = {transfer_id}/chunks/{index:06d}.chunk
- 合并落桶：ephemeral → transit（目的区不持久化）；普通包 → 按 category 落对应桶
- 流式合并并同步计算整体 sha256（内容校验层）
"""
from __future__ import annotations

import hashlib
import logging
import os
import tempfile
from typing import Tuple

from shared.infrastructure.storage import storage as shared_storage

from transfer_agent.domain.errors import InvalidPackageFieldError
from transfer_agent.domain.repositories.transfer_repository_abc import TransferStorageABC
from transfer_agent.domain.services.zone_category import TransferCategory

logger = logging.getLogger(__name__)

_CHUNK_KEY_FMT = '{transfer_id}/chunks/{index:06d}.chunk'


class TransferStorageAdapter(TransferStorageABC):
    """基于统一存储抽象（OSS/本地降级）的传输存储实现。"""

    def __init__(self, transit_category: str = TransferCategory.TRANSIT.value):
        self._transit = transit_category

    @staticmethod
    def _chunk_key(transfer_id: str, chunk_index: int) -> str:
        return _CHUNK_KEY_FMT.format(transfer_id=transfer_id, index=chunk_index)

    def save_chunk(self, transfer_id: str, chunk_index: int, data: bytes) -> None:
        shared_storage.save_bytes(
            data, self._transit, self._chunk_key(transfer_id, chunk_index),
        )

    def chunk_exists(self, transfer_id: str, chunk_index: int) -> bool:
        path = shared_storage.build_path(self._transit, self._chunk_key(transfer_id, chunk_index))
        return shared_storage.exists(path)

    def delete_chunks(self, transfer_id: str, total_chunks: int) -> None:
        for index in range(total_chunks):
            path = shared_storage.build_path(
                self._transit, self._chunk_key(transfer_id, index),
            )
            try:
                shared_storage.delete(path)
            except FileNotFoundError:
                continue

    def merge_chunks(self, transfer_id: str, total_chunks: int,
                     dest_category: str, dest_key: str) -> Tuple[str, str]:
        """按序合并分片 → 目标桶，返回 (final_path, sha256_hex)。

        逐片流式写入本地临时文件并增量计算 sha256，避免百 MB 级文件整体进内存。
        """
        if total_chunks <= 0:
            raise InvalidPackageFieldError(f'total_chunks={total_chunks} 非法')
        sha = hashlib.sha256()
        fd, tmp_path = tempfile.mkstemp(prefix=f'transfer_{transfer_id}_')
        try:
            with os.fdopen(fd, 'wb') as out:
                for index in range(total_chunks):
                    data = shared_storage.load_bytes(
                        shared_storage.build_path(
                            self._transit, self._chunk_key(transfer_id, index),
                        ),
                    )
                    sha.update(data)
                    out.write(data)
            final_path = shared_storage.save_file(tmp_path, dest_category, dest_key)
        finally:
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        return final_path, sha.hexdigest()

    def delete_transit_file(self, path: str) -> None:
        """删除中转暂存文件。仅允许 transit 域路径，持久桶路径拒绝删除。"""
        if not path:
            return
        if self._transit not in path:
            logger.warning('拒绝删除非 transit 域文件: %s', path)
            return
        try:
            shared_storage.delete(path)
        except FileNotFoundError:
            pass


# 模块级单例
transfer_storage = TransferStorageAdapter()
