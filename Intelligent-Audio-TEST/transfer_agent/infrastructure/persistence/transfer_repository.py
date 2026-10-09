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

from shared.models.common_enums import PkgType, TransferStatus
from shared.models.database import get_db_session

from transfer_agent.domain.entities.transfer_package import (
    RelayExecutionState,
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


def _parse_e8(value) -> Optional[datetime]:
    """解析 meta 中的 ISO 时间串（naive 东八区），非法/缺失返回 None。"""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    return _as_e8(parsed).replace(tzinfo=None)


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


    def claim_relay_execution(self, *, dst_zone: str, stale_seconds: int,
                              now: Optional[datetime] = None) -> Optional[TransferPackage]:
        """原子认领一个待执行中转包（F2.3 中枢触发器，幂等去重前提）。

        行锁（FOR UPDATE；SQLite 由写串行化兜底）内做资格判定与 meta.relay
        认领写入，并发认领方仅一方成功：
        - 资格：pkg_type=EVAL_REQUEST、dst_zone=本区、status=COMPLETED、未过期，
          且 meta.relay 缺失，或 relay.state=executing 且 claimed_at 已超过
          stale_seconds（认领方死亡后的崩溃恢复；重复执行安全：C 按 transfer_id
          幂等去重，EVAL_RESULT 同 id 回写传输层幂等去重）；
        - 认领成功回写 relay.state=executing + claimed_at + attempts 并返回聚合；
        - 无候选包返回 None（已终态 executed/failed 的包不再认领）。
        """
        session = get_db_session()
        now_e8 = _as_e8(now or datetime.now(_E8)).replace(tzinfo=None)
        rows = session.query(TransferRecord).filter(
            TransferRecord.pkg_type == PkgType.EVAL_REQUEST.value,
            TransferRecord.dst_zone == dst_zone,
            TransferRecord.status == TransferStatus.COMPLETED.value,
        ).order_by(TransferRecord.created_at).with_for_update().all()
        for po in rows:
            if po.created_at is not None:
                deadline = po.created_at + timedelta(seconds=po.ttl_seconds or 0)
                if now_e8 > deadline:
                    continue  # 已过期：交由既有过期清理收敛，不认领
            try:
                meta = json.loads(po.meta) if po.meta else {}
            except (TypeError, ValueError):
                meta = {}
            if not isinstance(meta, dict):
                meta = {}
            relay = dict(meta.get('relay') or {})
            state = str(relay.get('state') or '')
            if state in (RelayExecutionState.EXECUTED.value,
                         RelayExecutionState.FAILED.value):
                continue
            if state == RelayExecutionState.EXECUTING.value:
                claimed_at = _parse_e8(relay.get('claimed_at'))
                if claimed_at is not None and (now_e8 - claimed_at).total_seconds() < stale_seconds:
                    continue  # 认领方执行中（未失效），跳过
            relay.update({
                'state': RelayExecutionState.EXECUTING.value,
                'claimed_at': now_e8.isoformat(),
                'attempts': int(relay.get('attempts') or 0) + 1,
            })
            meta['relay'] = relay
            po.meta = json.dumps(meta, ensure_ascii=False)
            session.commit()
            return _record_to_aggregate(po)
        session.rollback()  # 无候选：释放行锁
        return None

    def finish_relay_execution(self, *, transfer_id: str, state: str,
                               error: Optional[str] = None,
                               now: Optional[datetime] = None) -> bool:
        """中转执行终态收敛（仅认领方调用；executing→executed/failed）。

        幂等守卫：仅 relay.state=executing 允许收敛，重复收敛/未认领返回 False；
        终态后触发器轮询不再认领（同一中转包不重复执行）。
        """
        if state not in (RelayExecutionState.EXECUTED.value,
                         RelayExecutionState.FAILED.value):
            raise InvalidPackageFieldError(f'relay 终态非法: {state}')
        session = get_db_session()
        po = session.query(TransferRecord).filter(
            TransferRecord.transfer_id == transfer_id,
        ).with_for_update().first()
        if po is None:
            session.rollback()
            return False
        try:
            meta = json.loads(po.meta) if po.meta else {}
        except (TypeError, ValueError):
            meta = {}
        if not isinstance(meta, dict):
            meta = {}
        relay = dict(meta.get('relay') or {})
        if relay.get('state') != RelayExecutionState.EXECUTING.value:
            session.rollback()
            return False
        now_e8 = _as_e8(now or datetime.now(_E8)).replace(tzinfo=None)
        relay.update({
            'state': state,
            'finished_at': now_e8.isoformat(),
            'error': error or '',
        })
        meta['relay'] = relay
        po.meta = json.dumps(meta, ensure_ascii=False)
        session.commit()
        return True


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
