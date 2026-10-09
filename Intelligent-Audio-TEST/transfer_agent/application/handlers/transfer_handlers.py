# -*- coding: utf-8 -*-
"""transfer_agent 应用层命令/查询处理器（CQRS）。

命令侧：只写（流水表 + 分片表 + 存储）并产生领域事件，不承担查询职责；
查询侧：只读，不产生副作用。

5 层安全基座在命令入口按序执行：
  ① 网络隔离点/内容层  ZoneRoutePolicy.check(src, dst, pkg_type)
  ② 访问控制层        SignatureService.verify_token
  ③ 签名层            SignatureService.verify_signature（HMAC-SHA256 规范串）
  ④ 内容校验层        分片 checksum + 完成 file_hash 整体校验
  ⑤ 审计层            transfer_records 流水 + 领域事件日志
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime
from typing import Callable, List, Optional

from shared.models.common_enums import TransferStatus
from transfer_agent.application.commands.transfer_commands import (
    CompleteTransferCommand,
    CreateTransferCommand,
    ExpirePackagesCommand,
    UploadChunkCommand,
)
from transfer_agent.application.queries.transfer_queries import (
    GetTransferQuery,
    GetTransferStatusQuery,
)
from transfer_agent.domain.entities.transfer_package import (
    TransferChunkRecord,
    TransferPackage,
    utc8now,
    validate_storage_key,
    validate_transfer_id,
)
from transfer_agent.domain.errors import (
    ChunkChecksumMismatchError,
    ChunkIndexOutOfRangeError,
    ChunkSizeInvalidError,
    DuplicateTransferConflictError,
    InvalidPackageFieldError,
    MissingChunksError,
    PackageExpiredError,
    PackageNotFoundError,
)
from transfer_agent.domain.events.transfer_events import (
    TransferChunkReceived,
    TransferCompleted,
    TransferCreated,
    TransferEvent,
    TransferExpired,
    TransferFailed,
)
from transfer_agent.domain.repositories.transfer_repository_abc import (
    TransferChunkRepositoryABC,
    TransferRecordRepositoryABC,
    TransferStorageABC,
)
from transfer_agent.domain.services.signature_service import SignatureService
from transfer_agent.domain.services.zone_category import TransferCategory
from transfer_agent.domain.services.zone_route_policy import ZoneRoutePolicy

logger = logging.getLogger(__name__)


def _default_event_sink(event: TransferEvent) -> None:
    logger.info('transfer_event=%s transfer_id=%s detail=%s',
                type(event).__name__, event.transfer_id, event)


class TransferCommandHandler:
    """传输命令处理器（接收侧：收包、分片、合并、清理）。"""

    def __init__(
        self,
        record_repo: Optional[TransferRecordRepositoryABC] = None,
        chunk_repo: Optional[TransferChunkRepositoryABC] = None,
        storage: Optional[TransferStorageABC] = None,
        signature_service: Optional[SignatureService] = None,
        route_policy: Optional[ZoneRoutePolicy] = None,
        event_sink: Optional[Callable[[TransferEvent], None]] = None,
        ttl_bounds: Optional[tuple] = None,
        default_chunk_size: Optional[int] = None,
        max_chunk_bytes: Optional[int] = None,
    ):
        self._record_repo = record_repo
        self._chunk_repo = chunk_repo
        self._storage = storage
        self._signature_service = signature_service
        self._route_policy = route_policy
        self._event_sink = event_sink or _default_event_sink
        self._ttl_bounds = ttl_bounds
        self._default_chunk_size = default_chunk_size
        self._max_chunk_bytes = max_chunk_bytes

    # ---- 依赖延迟装配（避免导入期触发 DB/OSS 连接）----
    @property
    def record_repo(self) -> TransferRecordRepositoryABC:
        if self._record_repo is None:
            from transfer_agent.infrastructure.persistence.transfer_repository import (
                transfer_record_repository,
            )
            self._record_repo = transfer_record_repository
        return self._record_repo

    @property
    def chunk_repo(self) -> TransferChunkRepositoryABC:
        if self._chunk_repo is None:
            from transfer_agent.infrastructure.persistence.transfer_repository import (
                transfer_chunk_repository,
            )
            self._chunk_repo = transfer_chunk_repository
        return self._chunk_repo

    @property
    def storage(self) -> TransferStorageABC:
        if self._storage is None:
            from transfer_agent.infrastructure.storage.transfer_storage import (
                transfer_storage,
            )
            self._storage = transfer_storage
        return self._storage

    @property
    def signature_service(self) -> SignatureService:
        if self._signature_service is None:
            from transfer_agent.config.config import Config
            self._signature_service = SignatureService(Config.transfer_tokens())
        return self._signature_service

    @property
    def route_policy(self) -> ZoneRoutePolicy:
        if self._route_policy is None:
            from transfer_agent.config.config import Config
            self._route_policy = Config.route_policy()
        return self._route_policy

    @property
    def ttl_bounds(self) -> tuple:
        if self._ttl_bounds is None:
            from transfer_agent.config.config import Config
            self._ttl_bounds = (Config.TRANSFER_MIN_TTL_SECONDS, Config.TRANSFER_MAX_TTL_SECONDS)
        return self._ttl_bounds

    @property
    def default_chunk_size(self) -> int:
        if self._default_chunk_size is None:
            from transfer_agent.config.config import Config
            return Config.TRANSFER_CHUNK_SIZE
        return self._default_chunk_size

    @property
    def max_chunk_bytes(self) -> int:
        if self._max_chunk_bytes is None:
            from transfer_agent.config.config import Config
            return Config.TRANSFER_CHUNK_SIZE
        return self._max_chunk_bytes

    def _emit(self, event: TransferEvent) -> None:
        try:
            self._event_sink(event)
        except Exception:
            logger.warning('传输事件发布失败（不阻塞主流程）: %s', event, exc_info=True)

    # ---- 安全链（命令公共前置）----
    def _load_package(self, transfer_id: str, token: str) -> TransferPackage:
        package = self.record_repo.find_by_transfer_id(transfer_id)
        if package is None:
            raise PackageNotFoundError(f'传输包不存在: transfer_id={transfer_id}')
        self.signature_service.verify_token(package.src_zone, package.dst_zone, token)
        return package

    def _require_not_expired(self, package: TransferPackage,
                             now: Optional[datetime] = None) -> None:
        if package.is_expired(now):
            raise PackageExpiredError(
                f'transfer {package.transfer_id} 已超过 TTL={package.ttl_seconds}s，'
                f'expires_at={package.expires_at.isoformat()}'
            )

    def _require_transferring(self, package: TransferPackage) -> None:
        package._require(TransferStatus.CREATED, TransferStatus.TRANSFERRING)

    # ================= 命令 =================
    def create_transfer(self, cmd: CreateTransferCommand) -> dict:
        """创建传输会话（幂等：同 transfer_id 同 file_hash 直接返回已存在）。"""
        # ① 网络隔离点/内容层：路由 + 枚举合法性
        self.route_policy.check(cmd.src_zone, cmd.dst_zone, cmd.pkg_type)
        try:
            TransferCategory(str(cmd.category))
        except ValueError:
            raise InvalidPackageFieldError(f'非法传输类别 category: {cmd.category}')
        # ② 访问控制层
        self.signature_service.verify_token(cmd.src_zone, cmd.dst_zone, cmd.token)
        # TTL 边界（配置化，拒绝越界）
        min_ttl, max_ttl = self.ttl_bounds
        if not (min_ttl <= cmd.ttl_seconds <= max_ttl):
            raise InvalidPackageFieldError(
                f'ttl_seconds={cmd.ttl_seconds} 越界（允许 {min_ttl}~{max_ttl}）'
            )
        if not cmd.transfer_id or not cmd.key or not cmd.file_hash:
            raise InvalidPackageFieldError('transfer_id / key / file_hash 均为必填')
        # 路径安全：transfer_id / key 均进入存储路径，入口即拒绝穿越形态
        validate_transfer_id(cmd.transfer_id)
        validate_storage_key(cmd.key)
        # ③ 签名层：HMAC-SHA256 规范串验签
        self.signature_service.verify_signature({
            'transfer_id': cmd.transfer_id, 'pkg_type': cmd.pkg_type,
            'src_zone': cmd.src_zone, 'dst_zone': cmd.dst_zone,
            'category': cmd.category, 'key': cmd.key,
            'file_hash': cmd.file_hash, 'file_size': cmd.file_size,
            'ttl_seconds': cmd.ttl_seconds, 'timestamp': cmd.timestamp,
            'signature': cmd.signature,
        })
        # 幂等去重：同 ID 已存在
        existing = self.record_repo.find_by_transfer_id(cmd.transfer_id)
        if existing is not None:
            if existing.file_hash.lower() != cmd.file_hash.lower():
                raise DuplicateTransferConflictError(
                    f'transfer_id={cmd.transfer_id} 已存在且 file_hash 不一致'
                    f'（{existing.file_hash} != {cmd.file_hash}），请更换 transfer_id 重传'
                )
            self._emit(TransferCreated(
                transfer_id=cmd.transfer_id, pkg_type=existing.pkg_type,
                src_zone=existing.src_zone, dst_zone=existing.dst_zone, dedup=True,
            ))
            return {**existing.to_dict(), 'dedup': True}

        chunk_size = cmd.chunk_size or self.default_chunk_size
        if chunk_size <= 0:
            raise InvalidPackageFieldError(f'chunk_size={chunk_size} 非法')
        if chunk_size > self.max_chunk_bytes:
            raise InvalidPackageFieldError(
                f'chunk_size={chunk_size} 超过接收端分片上限 {self.max_chunk_bytes}'
            )
        package = TransferPackage(
            transfer_id=cmd.transfer_id,
            pkg_type=cmd.pkg_type,
            src_zone=cmd.src_zone.upper(),
            dst_zone=cmd.dst_zone.upper(),
            category=cmd.category,
            key=cmd.key,
            file_hash=cmd.file_hash,
            file_size=int(cmd.file_size),
            ttl_seconds=int(cmd.ttl_seconds),
            ephemeral=bool(cmd.ephemeral),
            timestamp=cmd.timestamp,
            signature=cmd.signature,
            meta=dict(cmd.meta or {}),
            chunk_size=chunk_size,
        )
        if package.file_size <= 0:
            raise InvalidPackageFieldError(f'file_size={package.file_size} 非法')
        self.record_repo.add(package)
        self._emit(TransferCreated(
            transfer_id=package.transfer_id, pkg_type=package.pkg_type,
            src_zone=package.src_zone, dst_zone=package.dst_zone, dedup=False,
        ))
        return {**package.to_dict(), 'dedup': False}

    def upload_chunk(self, cmd: UploadChunkCommand) -> dict:
        """接收一个分片（幂等去重：同位同 checksum 重复上传直接成功）。"""
        package = self._load_package(cmd.transfer_id, cmd.token)
        self._require_not_expired(package)
        self._require_transferring(package)

        total = package.total_chunks
        if not 0 <= cmd.chunk_index < total:
            raise ChunkIndexOutOfRangeError(
                f'chunk_index={cmd.chunk_index} 越界（total_chunks={total}）'
            )
        if len(cmd.data) > package.chunk_bytes:
            raise ChunkSizeInvalidError(
                f'分片大小 {len(cmd.data)} 超过上限 {package.chunk_bytes}'
            )
        if cmd.chunk_index < total - 1 and len(cmd.data) < package.chunk_bytes:
            raise ChunkSizeInvalidError(
                f'非末片 chunk_index={cmd.chunk_index} 必须满块 {package.chunk_bytes}'
            )
        # ④ 内容校验层：分片 checksum
        actual = hashlib.sha256(cmd.data).hexdigest()
        if (cmd.checksum or '').lower() != actual:
            raise ChunkChecksumMismatchError(
                f'chunk_index={cmd.chunk_index} checksum 不匹配'
                f'（声明 {cmd.checksum}，实际 {actual}）'
            )

        existing = self.chunk_repo.find(cmd.transfer_id, cmd.chunk_index)
        if existing is not None:
            if existing.checksum.lower() != actual:
                raise ChunkChecksumMismatchError(
                    f'chunk_index={cmd.chunk_index} 与已收分片内容不一致，'
                    f'如为重传请核对源文件'
                )
            self._emit(TransferChunkReceived(
                transfer_id=cmd.transfer_id, chunk_index=cmd.chunk_index,
                checksum=actual, dedup=True,
            ))
            return self._chunk_view(package, dedup=True)

        self.storage.save_chunk(cmd.transfer_id, cmd.chunk_index, cmd.data)
        self.chunk_repo.add(TransferChunkRecord(
            transfer_id=cmd.transfer_id,
            chunk_index=cmd.chunk_index,
            checksum=actual,
            size=len(cmd.data),
        ))
        if package.status == TransferStatus.CREATED.value:
            package.mark_transferring()
            self.record_repo.save(package)
        self._emit(TransferChunkReceived(
            transfer_id=cmd.transfer_id, chunk_index=cmd.chunk_index,
            checksum=actual, dedup=False,
        ))
        return self._chunk_view(package, dedup=False)

    def complete_transfer(self, cmd: CompleteTransferCommand) -> dict:
        """合并分片 + file_hash 完整性校验（幂等：已完成会话重复 complete 直接返回）。"""
        package = self._load_package(cmd.transfer_id, cmd.token)
        if package.status in (TransferStatus.COMPLETED.value,
                              TransferStatus.DELIVERED.value):
            # 幂等：已完成/已交付会话重复 complete 直接返回（出站重投场景依赖此分支）
            return {**package.to_dict(), 'dedup': True}
        self._require_not_expired(package)
        self._require_transferring(package)

        total = package.total_chunks
        received = self.chunk_repo.list_records(cmd.transfer_id)
        if len(received) < total:
            raise MissingChunksError(
                f'transfer {package.transfer_id} 分片不齐 '
                f'（已收 {len(received)}/{total}），请断点续传缺失分片'
            )

        # ephemeral 包提升目标仍为中转暂存（目的区不持久化）；普通包按 category 落对应桶
        if package.ephemeral:
            dest_category = TransferCategory.TRANSIT.value
            dest_key = f'{package.transfer_id}/{package.key}'
        else:
            dest_category = package.category
            dest_key = package.key

        # ② 合并到 transit 暂存区（终桶保持不动），流式计算整体 sha256
        staged_path, actual_hash = self.storage.merge_chunks(cmd.transfer_id, total)

        # ③ 内容校验层：整体 sha256 通过之前不触碰终桶，失败仅回收暂存与分片
        try:
            package.validate_file_hash(actual_hash)
        except Exception:
            package.mark_failed()
            self.record_repo.save(package)
            self.chunk_repo.delete_all(cmd.transfer_id)
            self.storage.delete_chunks(cmd.transfer_id, total)
            self.storage.delete_transit_file(staged_path)
            self._emit(TransferFailed(
                transfer_id=package.transfer_id,
                reason=f'file_hash 校验失败 actual={actual_hash}',
            ))
            raise

        # ④ 校验通过 → 暂存文件提升到终桶（移动语义，不产生未验证覆盖）
        final_path = self.storage.promote_file(staged_path, dest_category, dest_key)

        package.mark_completed(final_path)
        self.record_repo.save(package)
        self.chunk_repo.delete_all(cmd.transfer_id)
        self.storage.delete_chunks(cmd.transfer_id, total)
        self._emit(TransferCompleted(
            transfer_id=package.transfer_id, pkg_type=package.pkg_type,
            file_size=package.file_size, final_path=final_path,
        ))
        return {**package.to_dict(), 'dedup': False}

    def expire_packages(self, cmd: ExpirePackagesCommand) -> dict:
        """TTL 过期清理：未完成包与 ephemeral 已完成包的分片/临时文件回收（流水保留审计）。"""
        now = cmd.now or utc8now()
        expired = self.record_repo.list_expired(now, limit=cmd.limit)
        cleaned: List[str] = []
        for package in expired:
            total = package.total_chunks
            self.storage.delete_chunks(package.transfer_id, total)
            self.chunk_repo.delete_all(package.transfer_id)
            if package.final_path:
                self.storage.delete_transit_file(package.final_path)
            status_before = package.status
            package.mark_expired()
            self.record_repo.save(package)
            cleaned.append(package.transfer_id)
            self._emit(TransferExpired(
                transfer_id=package.transfer_id, status_before=status_before,
            ))
        return {'expired': len(cleaned), 'transfer_ids': cleaned}

    def _chunk_view(self, package: TransferPackage, dedup: bool) -> dict:
        received = self.chunk_repo.list_records(package.transfer_id)
        return {
            'transfer_id': package.transfer_id,
            'status': package.status,
            'total_chunks': package.total_chunks,
            'received_chunks': sorted(r.chunk_index for r in received),
            'dedup': dedup,
        }


class TransferQueryHandler:
    """传输查询处理器（CQRS 读侧：无副作用，不校验过期——过期是写侧语义）。"""

    def __init__(
        self,
        record_repo: Optional[TransferRecordRepositoryABC] = None,
        chunk_repo: Optional[TransferChunkRepositoryABC] = None,
        signature_service: Optional[SignatureService] = None,
    ):
        self._record_repo = record_repo
        self._chunk_repo = chunk_repo
        self._signature_service = signature_service

    @property
    def record_repo(self) -> TransferRecordRepositoryABC:
        if self._record_repo is None:
            from transfer_agent.infrastructure.persistence.transfer_repository import (
                transfer_record_repository,
            )
            self._record_repo = transfer_record_repository
        return self._record_repo

    @property
    def chunk_repo(self) -> TransferChunkRepositoryABC:
        if self._chunk_repo is None:
            from transfer_agent.infrastructure.persistence.transfer_repository import (
                transfer_chunk_repository,
            )
            self._chunk_repo = transfer_chunk_repository
        return self._chunk_repo

    @property
    def signature_service(self) -> SignatureService:
        if self._signature_service is None:
            from transfer_agent.config.config import Config
            self._signature_service = SignatureService(Config.transfer_tokens())
        return self._signature_service

    def get_transfer_status(self, query: GetTransferStatusQuery) -> dict:
        """状态 + 已收分片清单（断点续传依据）。"""
        package = self.record_repo.find_by_transfer_id(query.transfer_id)
        if package is None:
            raise PackageNotFoundError(f'传输包不存在: transfer_id={query.transfer_id}')
        self.signature_service.verify_token(package.src_zone, package.dst_zone, query.token)
        received = self.chunk_repo.list_records(query.transfer_id)
        return {**package.to_dict(
            received_indexes=[r.chunk_index for r in received],
        ), 'dedup': False}

    def get_transfer(self, query: GetTransferQuery) -> dict:
        """传输包完整元数据（审计流水视图）。"""
        package = self.record_repo.find_by_transfer_id(query.transfer_id)
        if package is None:
            raise PackageNotFoundError(f'传输包不存在: transfer_id={query.transfer_id}')
        self.signature_service.verify_token(package.src_zone, package.dst_zone, query.token)
        received = self.chunk_repo.list_records(query.transfer_id)
        return package.to_dict(received_indexes=[r.chunk_index for r in received])
