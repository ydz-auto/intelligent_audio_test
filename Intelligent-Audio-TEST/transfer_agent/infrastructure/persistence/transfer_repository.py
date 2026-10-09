# -*- coding: utf-8 -*-
"""transfer_agent 仓储实现（PO ↔ 聚合映射，SQLAlchemy）。

实现 domain/repositories/transfer_repository_abc.py 定义的接口；
Repository 提交时机：本服务为独立微服务，操作粒度小，采用逐操作 commit。
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from shared.models.common_enums import TransferStatus
from shared.models.database import get_db_session

from transfer_agent.domain.entities.transfer_package import (
    TransferChunkRecord,
    TransferPackage,
)
from transfer_agent.domain.errors import InvalidPackageFieldError
from transfer_agent.domain.repositories.transfer_repository_abc import (
    TransferChunkRepositoryABC,
    TransferRecordRepositoryABC,
)
from transfer_agent.infrastructure.persistence.models import TransferChunk, TransferRecord

logger = logging.getLogger(__name__)

_E8 = timezone(timedelta(hours=8))


def _as_e8(dt: Optional[datetime]) -> Optional[datetime]:
    """DB 中的 naive datetime 视为东八区；aware 转东八区。"""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=_E8)
    return dt.astimezone(_E8)


def _record_to_aggregate(po: TransferRecord) -> TransferPackage:
    try:
        meta = json.loads(po.meta) if po.meta else {}
    except (TypeError, ValueError):
        meta = {}
    return TransferPackage(
        transfer_id=po.transfer_id,
        pkg_type=po.pkg_type,
        src_zone=po.src_zone,
        dst_zone=po.dst_zone,
        category=po.category,
        key=po.key,
        file_hash=po.file_hash,
        file_size=int(po.file_size or 0),
        ttl_seconds=int(po.ttl_seconds or 0),
        ephemeral=bool(po.ephemeral),
        timestamp=po.timestamp or '',
        signature=po.signature or '',
        meta=meta,
        chunk_size=int(po.chunk_size or 0),
        status=po.status,
        created_at=_as_e8(po.created_at) or datetime.now(_E8),
        expires_at=_as_e8(po.created_at) + timedelta(seconds=po.ttl_seconds or 0)
        if po.created_at else None,
        final_path=po.final_path,
    )


class TransferRecordRepository(TransferRecordRepositoryABC):
    """传输流水仓储实现。"""

    def find_by_transfer_id(self, transfer_id: str) -> Optional[TransferPackage]:
        session = get_db_session()
        po = session.query(TransferRecord).filter(
            TransferRecord.transfer_id == transfer_id,
        ).first()
        return _record_to_aggregate(po) if po else None

    def add(self, package: TransferPackage) -> None:
        session = get_db_session()
        session.add(TransferRecord(
            transfer_id=package.transfer_id,
            pkg_type=package.pkg_type,
            src_zone=package.src_zone,
            dst_zone=package.dst_zone,
            category=package.category,
            key=package.key,
            file_hash=package.file_hash,
            file_size=package.file_size,
            chunk_size=package.chunk_size,
            meta=json.dumps(package.meta, ensure_ascii=False) if package.meta else None,
            ttl_seconds=package.ttl_seconds,
            ephemeral=package.ephemeral,
            timestamp=package.timestamp,
            signature=package.signature,
            status=package.status,
        ))
        session.commit()

    def save(self, package: TransferPackage) -> None:
        session = get_db_session()
        po = session.query(TransferRecord).filter(
            TransferRecord.transfer_id == package.transfer_id,
        ).first()
        if po is None:
            raise InvalidPackageFieldError(
                f'传输流水不存在: transfer_id={package.transfer_id}'
            )
        po.status = package.status
        po.final_path = package.final_path
        po.meta = json.dumps(package.meta, ensure_ascii=False) if package.meta else None
        session.commit()

    def list_expired(self, now: datetime, limit: int = 100) -> List[TransferPackage]:
        """过期回收清单：未完成包超时 / FAILED 包残留 / COMPLETED·DELIVERED 且 ephemeral 到期。

        COMPLETED/DELIVERED 且非 ephemeral 的包永不回收（目的区持久数据）；
        DELIVERED 包的 transit 暂存同样按 TTL 回收（交付事实保留于 meta）。
        """
        session = get_db_session()
        now_naive = now.astimezone(_E8).replace(tzinfo=None)
        unfinished = ['CREATED', 'TRANSFERRING', 'FAILED']
        rows = session.query(TransferRecord).filter(
            TransferRecord.status.in_(unfinished)
            | (
                (TransferRecord.status.in_([
                    TransferStatus.COMPLETED.value, TransferStatus.DELIVERED.value,
                ]))
                & (TransferRecord.ephemeral == True)  # noqa: E712
            ),
        ).all()
        expired = []
        for po in rows:
            if po.created_at is None:
                continue
            deadline = po.created_at + timedelta(seconds=po.ttl_seconds or 0)
            if now_naive > deadline:
                expired.append(_record_to_aggregate(po))
            if len(expired) >= limit:
                break
        return expired


class TransferChunkRepository(TransferChunkRepositoryABC):
    """已收分片仓储实现。"""

    def list_records(self, transfer_id: str) -> List[TransferChunkRecord]:
        session = get_db_session()
        rows = session.query(TransferChunk).filter(
            TransferChunk.transfer_id == transfer_id,
        ).order_by(TransferChunk.chunk_index).all()
        return [
            TransferChunkRecord(
                transfer_id=row.transfer_id,
                chunk_index=row.chunk_index,
                checksum=row.checksum,
                size=int(row.size or 0),
                received_at=_as_e8(row.received_at) or datetime.now(_E8),
            )
            for row in rows
        ]

    def find(self, transfer_id: str, chunk_index: int) -> Optional[TransferChunkRecord]:
        session = get_db_session()
        row = session.query(TransferChunk).filter(
            TransferChunk.transfer_id == transfer_id,
            TransferChunk.chunk_index == chunk_index,
        ).first()
        if row is None:
            return None
        return TransferChunkRecord(
            transfer_id=row.transfer_id,
            chunk_index=row.chunk_index,
            checksum=row.checksum,
            size=int(row.size or 0),
            received_at=_as_e8(row.received_at) or datetime.now(_E8),
        )

    def add(self, record: TransferChunkRecord) -> None:
        session = get_db_session()
        session.add(TransferChunk(
            transfer_id=record.transfer_id,
            chunk_index=record.chunk_index,
            checksum=record.checksum,
            size=record.size,
        ))
        session.commit()

    def delete_all(self, transfer_id: str) -> None:
        session = get_db_session()
        session.query(TransferChunk).filter(
            TransferChunk.transfer_id == transfer_id,
        ).delete()
        session.commit()


# 模块级单例（与 task_service 仓储单例风格一致）
transfer_record_repository = TransferRecordRepository()
transfer_chunk_repository = TransferChunkRepository()
