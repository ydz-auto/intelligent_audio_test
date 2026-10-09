# -*- coding: utf-8 -*-
"""TransferPackage 聚合根 — 跨区传输包领域实体。

归属：transfer_agent（跨区传输上下文）
本文件为纯领域对象，不依赖 SQLAlchemy / db.Model。
PO 映射在 infrastructure/persistence/models.py。

传输包协议字段对齐设计文档 09_跨区网络传输方案 §4.2.1；
PkgType / TransferStatus 枚举为跨服务共享语义，定义在 shared.models.common_enums。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

from shared.models.common_enums import PkgType, TransferStatus

from transfer_agent.domain.errors import (
    FileHashMismatchError,
    InvalidPackageFieldError,
    InvalidTransferStateError,
)
from transfer_agent.domain.services.zone_category import TransferCategory


# 东八区时间源（对齐 shared.models.database.utc8now）
def utc8now() -> datetime:
    return datetime.now(timezone(timedelta(hours=8)))


def _utc8(dt: Optional[datetime]) -> datetime:
    """将 naive datetime 视为东八区，aware datetime 转东八区。"""
    if dt is None:
        return utc8now()
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone(timedelta(hours=8)))
    return dt.astimezone(timezone(timedelta(hours=8)))


# transfer_id 进入存储路径（transit/{transfer_id}/chunks/...），白名单防路径穿越
_TRANSFER_ID_RE = re.compile(r'^[A-Za-z0-9_-]{1,64}$')


def validate_transfer_id(transfer_id: str) -> str:
    if not _TRANSFER_ID_RE.match(transfer_id or ''):
        raise InvalidPackageFieldError(
            f'transfer_id 非法（仅允许字母/数字/下划线/连字符，长度 1~64）: {transfer_id!r}'
        )
    return transfer_id


def validate_storage_key(key: str) -> str:
    """key 落盘时拼接为 {root}/{category}/{key}，拒绝一切可逃逸存储根的形态。"""
    if not key:
        raise InvalidPackageFieldError('key 为必填')
    if '\\' in key or ':' in key:
        raise InvalidPackageFieldError(f'key 不允许反斜杠/冒号: {key!r}')
    if key.startswith('/'):
        raise InvalidPackageFieldError(f'key 不允许绝对路径: {key!r}')
    if '..' in key.split('/'):
        raise InvalidPackageFieldError(f'key 不允许相对上跳段（..）: {key!r}')
    return key


@dataclass
class TransferChunkRecord:
    """已收分片值对象 — 断点续传/幂等去重的领域表示。"""
    transfer_id: str
    chunk_index: int
    checksum: str
    size: int
    received_at: datetime = field(default_factory=utc8now)


@dataclass
class TransferPackage:
    """传输包聚合根。

    封装传输包协议字段、分片元数据与状态机迁移；持有 TTL 判定与完整性校验行为。
    """
    transfer_id: str
    pkg_type: str
    src_zone: str
    dst_zone: str
    category: str
    key: str
    file_hash: str          # sha256:<hex>
    file_size: int
    ttl_seconds: int
    ephemeral: bool
    timestamp: str          # 发起方 ISO8601 时间，参与签名
    signature: str
    meta: dict = field(default_factory=dict)
    chunk_size: int = 4 * 1024 * 1024
    status: str = TransferStatus.CREATED.value
    created_at: datetime = field(default_factory=utc8now)
    expires_at: Optional[datetime] = None
    final_path: Optional[str] = None   # 合并完成后的存储路径（带 scheme）

    def __post_init__(self):
        # 路径安全不变量（5 层基座 · 内容校验层的落盘前置）：transfer_id / key
        # 均进入存储路径，实体层强制校验，任何构造路径（含 PO 重建）都不可绕过
        validate_transfer_id(self.transfer_id)
        validate_storage_key(self.key)
        try:
            self.pkg_type = PkgType(self.pkg_type).value
            self.category = TransferCategory(self.category).value
            self.status = TransferStatus(self.status).value
        except ValueError as e:
            raise InvalidPackageFieldError(f'传输包枚举字段非法: {e}') from e
        if self.expires_at is None:
            self.expires_at = _utc8(self.created_at) + timedelta(seconds=self.ttl_seconds)

    # ---- 分片元数据 ----
    @staticmethod
    def compute_total_chunks(file_size: int, chunk_size: int) -> int:
        if file_size <= 0 or chunk_size <= 0:
            return 0
        return (file_size + chunk_size - 1) // chunk_size

    @property
    def total_chunks(self) -> int:
        return self.compute_total_chunks(self.file_size, self.chunk_size)

    @property
    def chunk_bytes(self) -> int:
        return self.chunk_size

    # ---- TTL ----
    def is_expired(self, now: Optional[datetime] = None) -> bool:
        if self.expires_at is None:
            return False
        return _utc8(now or utc8now()) > self.expires_at

    # ---- 状态机 ----
    def _require(self, *statuses: TransferStatus) -> None:
        if self.status not in [s.value for s in statuses]:
            raise InvalidTransferStateError(
                f'transfer {self.transfer_id} 状态为 {self.status}，'
                f'不允许该操作（允许：{"/".join(s.value for s in statuses)}）'
            )

    def mark_transferring(self) -> None:
        self._require(TransferStatus.CREATED)
        self.status = TransferStatus.TRANSFERRING.value

    def mark_completed(self, final_path: str) -> None:
        self._require(TransferStatus.CREATED, TransferStatus.TRANSFERRING)
        self.status = TransferStatus.COMPLETED.value
        self.final_path = final_path

    def mark_delivered(self) -> None:
        """出站交付完成（B→C 第三方 API 同步响应已收到）；重复交付幂等。"""
        self._require(TransferStatus.COMPLETED, TransferStatus.DELIVERED)
        self.status = TransferStatus.DELIVERED.value

    def mark_failed(self) -> None:
        self._require(TransferStatus.CREATED, TransferStatus.TRANSFERRING)
        self.status = TransferStatus.FAILED.value

    def mark_expired(self) -> None:
        """过期回收：未完成包与 ephemeral 完成包均可置 EXPIRED（幂等）。"""
        if self.status == TransferStatus.EXPIRED.value:
            return
        self.status = TransferStatus.EXPIRED.value

    # ---- 内容校验层 ----
    def validate_file_hash(self, actual_sha256_hex: str) -> None:
        expected = self.file_hash
        if expected.startswith('sha256:'):
            expected = expected.split(':', 1)[1]
        if expected.lower() != (actual_sha256_hex or '').lower():
            raise FileHashMismatchError(
                f'transfer {self.transfer_id} 合并后 sha256={actual_sha256_hex} '
                f'与声明 file_hash={self.file_hash} 不一致'
            )

    # ---- 协议视图 ----
    def to_dict(self, received_indexes: Optional[list] = None) -> dict:
        return {
            'transfer_id': self.transfer_id,
            'pkg_type': self.pkg_type,
            'src_zone': self.src_zone,
            'dst_zone': self.dst_zone,
            'category': self.category,
            'key': self.key,
            'file_hash': self.file_hash,
            'file_size': self.file_size,
            'chunk_size': self.chunk_size,
            'total_chunks': self.total_chunks,
            'meta': self.meta,
            'ttl_seconds': self.ttl_seconds,
            'ephemeral': self.ephemeral,
            'timestamp': self.timestamp,
            'status': self.status,
            'created_at': _utc8(self.created_at).isoformat(),
            'expires_at': _utc8(self.expires_at).isoformat() if self.expires_at else None,
            'final_path': self.final_path,
            'received_chunks': sorted(received_indexes or []),
        }
