# -*- coding: utf-8 -*-
"""传输存储适配器 — TransferStorageABC 实现，复用 shared.infrastructure.storage。

- 分片暂存：transit 域，key = {transfer_id}/chunks/{index:06d}.chunk
- 合并暂存：transit 域，key = {transfer_id}/merged.pkg（file_hash 校验通过前不触碰终桶）
- 提升落桶：校验通过后 promote_file 将暂存文件移动到 category 对应桶（ephemeral → transit）
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
_MERGED_KEY_FMT = '{transfer_id}/merged.pkg'
_PATH_SCHEMES = ('oss://', 'local://')


class TransferStorageAdapter(TransferStorageABC):
    """基于统一存储抽象（OSS/本地降级）的传输存储实现。"""

    def __init__(self, transit_category: str = TransferCategory.TRANSIT.value):
        self._transit = transit_category

    @staticmethod
    def _chunk_key(transfer_id: str, chunk_index: int) -> str:
        return _CHUNK_KEY_FMT.format(transfer_id=transfer_id, index=chunk_index)

    def _transit_path(self, key: str) -> str:
        return shared_storage.build_path(self._transit, key)

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

    def merge_chunks(self, transfer_id: str, total_chunks: int) -> Tuple[str, str]:
        """按序合并分片 → transit 暂存区，返回 (staged_path, sha256_hex)。

        逐片流式写入本地临时文件并增量计算 sha256，避免百 MB 级文件整体进内存。
        终桶在 file_hash 校验通过前不写入（防同 key 原有对象被损坏内容覆盖）。
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
            staged_path = shared_storage.save_file(
                tmp_path, self._transit,
                _MERGED_KEY_FMT.format(transfer_id=transfer_id),
            )
        finally:
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        return staged_path, sha.hexdigest()

    def promote_file(self, staged_path: str, dest_category: str, dest_key: str) -> str:
        """transit 暂存文件 → 目标桶（移动语义），返回 final_path。

        下载到本地临时文件后走统一存储写入，避免整文件进内存；
        提升完成后回收暂存文件。
        """
        local_tmp = shared_storage.load_file(staged_path)
        try:
            final_path = shared_storage.save_file(local_tmp, dest_category, dest_key)
        finally:
            try:
                os.remove(local_tmp)
            except OSError:
                pass
        self.delete_transit_file(staged_path)
        return final_path

    def read_file(self, path: str) -> bytes:
        return shared_storage.load_bytes(path)

    def delete_transit_file(self, path: str) -> None:
        """删除中转暂存文件。严格比对 scheme 后的 category 段，持久桶路径拒绝删除。"""
        if not path:
            return
        if not self._is_transit_path(path):
            logger.warning('拒绝删除非 transit 域文件: %s', path)
            return
        try:
            shared_storage.delete(path)
        except FileNotFoundError:
            pass

    def _is_transit_path(self, path: str) -> bool:
        """仅接受 oss://transit/... 或 local://transit/... 形态（category 段全等比较）。"""
        for scheme in _PATH_SCHEMES:
            if path.startswith(scheme):
                category = path[len(scheme):].split('/', 1)[0]
                return category == self._transit
        return False


# 模块级单例
transfer_storage = TransferStorageAdapter()
