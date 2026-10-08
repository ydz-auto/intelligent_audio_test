# -*- coding: utf-8 -*-
"""发送侧传输编排 — 打包、分片、断点续传、重试。

依赖 RemoteTransferClientABC（ACL 防腐层实现），不感知远端是 HTTP 还是 gRPC；
重试采用指数退避（默认 3 次），重试前先查询远端已收分片避免重复传输。
"""
from __future__ import annotations

import hashlib
import logging
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

from transfer_agent.domain.entities.transfer_package import TransferPackage
from transfer_agent.domain.errors import TransferError
from transfer_agent.domain.repositories.transfer_repository_abc import (
    RemoteTransferClientABC,
)
from transfer_agent.domain.services.signature_service import SignatureService

logger = logging.getLogger(__name__)


class ChunkedUploadService:
    """分片上传编排服务（发送侧）。"""

    def __init__(
        self,
        client: RemoteTransferClientABC,
        signature_service: SignatureService,
        chunk_size: Optional[int] = None,
        max_retries: int = 3,
        backoff_seconds: float = 1.0,
        default_ttl: int = 3600,
    ):
        self._client = client
        self._signature_service = signature_service
        if chunk_size is None:
            from transfer_agent.config.config import Config
            chunk_size = Config.TRANSFER_CHUNK_SIZE
        self._chunk_size = chunk_size
        self._max_retries = max_retries
        self._backoff_seconds = backoff_seconds
        self._default_ttl = default_ttl

    def send_file(
        self,
        local_path: str,
        pkg_type: str,
        src_zone: str,
        dst_zone: str,
        category: str,
        key: str,
        ephemeral: bool = False,
        meta: Optional[Dict] = None,
        ttl_seconds: Optional[int] = None,
        transfer_id: Optional[str] = None,
    ) -> Dict:
        """将本地文件按传输包协议发送到远端 transfer_agent。

        全链路：打包(算 hash/size) → create → 断点续传(跳过已收片) → 分片重试 → complete。
        返回远端完成视图（含 transfer_id / final 信息）。
        """
        secret = self._signature_service.get_token(src_zone, dst_zone)
        if not secret:
            from transfer_agent.domain.errors import AccessTokenInvalidError
            raise AccessTokenInvalidError(
                f'路由 {src_zone}->{dst_zone} 未配置预共享 token，无法签名'
            )

        file_hash, file_size = self._hash_file(local_path)
        ttl = ttl_seconds if ttl_seconds is not None else self._default_ttl
        timestamp = datetime.now(timezone(timedelta(hours=8))).isoformat()
        fields = {
            'transfer_id': transfer_id or uuid.uuid4().hex,
            'pkg_type': pkg_type,
            'src_zone': src_zone,
            'dst_zone': dst_zone,
            'category': category,
            'key': key,
            'file_hash': file_hash,
            'file_size': file_size,
            'ttl_seconds': int(ttl),
            'timestamp': timestamp,
        }
        fields['signature'] = SignatureService.compute_signature(secret, **fields)

        self._client.create_transfer({**fields, 'meta': meta or {}, 'ephemeral': ephemeral})

        total = TransferPackage.compute_total_chunks(file_size, self._chunk_size)
        received = self._fetch_received(fields['transfer_id'])

        with open(local_path, 'rb') as f:
            for index in range(total):
                if index in received:
                    continue
                f.seek(index * self._chunk_size)
                data = f.read(self._chunk_size)
                checksum = hashlib.sha256(data).hexdigest()
                self._upload_with_retry(fields['transfer_id'], index, data, checksum)

        result = self._client.complete_transfer(fields['transfer_id'])
        logger.info('分片传输完成: transfer_id=%s file_size=%s chunks=%s',
                    fields['transfer_id'], file_size, total)
        return result

    def _fetch_received(self, transfer_id: str) -> set:
        """断点续传：查询远端已收分片集合。"""
        try:
            status = self._client.get_transfer_status(transfer_id)
            return set(status.get('received_chunks') or [])
        except TransferError:
            return set()

    def _upload_with_retry(self, transfer_id: str, index: int,
                           data: bytes, checksum: str) -> None:
        """单分片指数退避重试（3 次）；重试前查询远端去重状态。"""
        attempt = 0
        while True:
            try:
                self._client.upload_chunk(transfer_id, index, data, checksum)
                return
            except TransferError as e:
                attempt += 1
                if attempt > self._max_retries:
                    raise
                sleep_s = self._backoff_seconds * (2 ** (attempt - 1))
                logger.warning('分片上传失败将重试: transfer_id=%s index=%s attempt=%s/%s err=%s',
                               transfer_id, index, attempt, self._max_retries, e)
                time.sleep(sleep_s)
                # 重传前校验远端是否已收（幂等去重兜底）
                if index in self._fetch_received(transfer_id):
                    return

    @staticmethod
    def _hash_file(local_path: str) -> tuple:
        """流式计算文件 sha256 与大小。"""
        sha = hashlib.sha256()
        size = 0
        with open(local_path, 'rb') as f:
            while True:
                block = f.read(1024 * 1024)
                if not block:
                    break
                sha.update(block)
                size += len(block)
        return f'sha256:{sha.hexdigest()}', size
