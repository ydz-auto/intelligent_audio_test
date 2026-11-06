# -*- coding: utf-8 -*-
"""出站投递应用服务 — T-B 出站投递腿编排（设计文档 §4.2.2 步骤⑤，F2.1/INT-49）。

读取 COMPLETED 的 EVAL_REQUEST transit 暂存包（④），按第三方契约（§4.3 三形态）
经 GW-2 投递 C 第三方 API，同步响应回传调用方（evaluation_service）。
交付语义与传输流水对齐：
- 成功：包状态 COMPLETED → DELIVERED（transfer_records dst=C 流水对应真实传输），
  发 TransferDelivered 事件；transit 暂存文件按 TTL 由过期清理回收；
- 失败：流水保持原状态（可重投），meta.delivery 记录最近一次投递结果，
  发 TransferDeliveryFailed 事件；
- 幂等重投：DELIVERED 包允许再次投递（重发场景），C 按 transfer_id 幂等去重。
"""
from __future__ import annotations

import logging
from typing import Callable, Optional

from shared.models.common_enums import PkgType, TransferStatus

from transfer_agent.domain.entities.transfer_package import utc8now
from transfer_agent.domain.errors import (
    InvalidPackageFieldError,
    InvalidTransferStateError,
    PackageExpiredError,
    PackageNotFoundError,
)
from transfer_agent.domain.events.transfer_events import (
    TransferDeliveryFailed,
    TransferDelivered,
    TransferEvent,
)
from transfer_agent.domain.repositories.transfer_repository_abc import (
    TransferRecordRepositoryABC,
    TransferStorageABC,
)
from transfer_agent.domain.services.eval_request_bundle import parse_eval_request_bundle
from transfer_agent.domain.services.signature_service import SignatureService
from transfer_agent.domain.services.zone_route_policy import ZoneRoutePolicy

logger = logging.getLogger(__name__)


def _default_event_sink(event: TransferEvent) -> None:
    logger.info('transfer_event=%s transfer_id=%s detail=%s',
                type(event).__name__, event.transfer_id, event)


class OutboundDeliveryService:
    """出站投递服务（出站腿 worker：读包 → 契约投递 → 流水对齐 → 响应回传）。"""

    def __init__(
        self,
        record_repo: Optional[TransferRecordRepositoryABC] = None,
        storage: Optional[TransferStorageABC] = None,
        route_policy: Optional[ZoneRoutePolicy] = None,
        c_client=None,
        signature_service: Optional[SignatureService] = None,
        event_sink: Optional[Callable[[TransferEvent], None]] = None,
        outbound_zone: Optional[str] = None,
    ):
        self._record_repo = record_repo
        self._storage = storage
        self._route_policy = route_policy
        self._c_client = c_client
        self._signature_service = signature_service
        self._event_sink = event_sink or _default_event_sink
        self._outbound_zone = outbound_zone

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
    def storage(self) -> TransferStorageABC:
        if self._storage is None:
            from transfer_agent.infrastructure.storage.transfer_storage import (
                transfer_storage,
            )
            self._storage = transfer_storage
        return self._storage

    @property
    def route_policy(self) -> ZoneRoutePolicy:
        if self._route_policy is None:
            from transfer_agent.config.config import Config
            self._route_policy = Config.route_policy()
        return self._route_policy

    @property
    def c_client(self):
        if self._c_client is None:
            from transfer_agent.config.config import Config
            from transfer_agent.infrastructure.acl.c_api_client import ThirdPartyCAPIClient
            self._c_client = ThirdPartyCAPIClient(
                base_url=Config.THIRD_PARTY_C_API_BASE_URL,
                timeout_seconds=Config.THIRD_PARTY_C_TIMEOUT_SECONDS,
                max_retries=Config.THIRD_PARTY_C_MAX_RETRIES,
                backoff_seconds=Config.THIRD_PARTY_C_BACKOFF_SECONDS,
            )
        return self._c_client

    @property
    def signature_service(self) -> SignatureService:
        if self._signature_service is None:
            from transfer_agent.config.config import Config
            self._signature_service = SignatureService(Config.transfer_tokens())
        return self._signature_service

    @property
    def outbound_zone(self) -> str:
        """本实例所在区（出站腿源区；仅白名单允许 →C 的区可投递）。"""
        if self._outbound_zone is None:
            from transfer_agent.config.config import Config
            self._outbound_zone = Config.TRANSFER_ZONE
        return self._outbound_zone

    def _emit(self, event: TransferEvent) -> None:
        try:
            self._event_sink(event)
        except Exception:
            logger.warning('传输事件发布失败（不阻塞主流程）: %s', event, exc_info=True)

    # ================= 命令 =================
    def dispatch(self, cmd) -> dict:
        """出站投递：读包 → 契约投递 C → 流水对齐 → 同步响应回传。

        返回投递视图 {'delivered', 'dst_status', 'dst_body', 'dst_text',
        'attempts', 'delivered_at'|'error'}；投递失败不抛错（交付语义由
        delivered=False 表达，评估语义由 evaluation_service 侧解析）。
        """
        package = self.record_repo.find_by_transfer_id(cmd.transfer_id)
        if package is None:
            raise PackageNotFoundError(f'传输包不存在: transfer_id={cmd.transfer_id}')
        self.signature_service.verify_token(package.src_zone, package.dst_zone, cmd.token)
        if package.pkg_type != PkgType.EVAL_REQUEST.value:
            raise InvalidPackageFieldError(
                f'仅 EVAL_REQUEST 包支持出站投递，当前包类型: {package.pkg_type}')
        if package.status not in (TransferStatus.COMPLETED.value,
                                  TransferStatus.DELIVERED.value):
            raise InvalidTransferStateError(
                f'transfer {package.transfer_id} 状态为 {package.status}，'
                f'仅 COMPLETED/DELIVERED 暂存包可出站投递'
                f'（DELIVERED 重投为幂等重投，C 按 transfer_id 去重）')
        self._require_not_expired(package)
        # 网络隔离点：本实例所在区 → C 的 EVAL_REQUEST 出站腿须在路由白名单
        # （A 区实例无 B→C 出站权限，route policy fail-closed 拒绝）
        self.route_policy.check(self.outbound_zone, 'C', package.pkg_type)

        bundle = parse_eval_request_bundle(self.storage.read_file(package.final_path))
        outcome = self.c_client.deliver(cmd.adapter_kind, bundle)
        delivery = self._record_delivery(package, cmd.adapter_kind, outcome)
        if not outcome.delivered:
            self._emit(TransferDeliveryFailed(
                transfer_id=package.transfer_id, adapter_kind=cmd.adapter_kind,
                reason=outcome.error or '出站投递失败', attempts=outcome.attempts))
            return {
                'delivered': False,
                'dst_status': outcome.dst_status,
                'dst_body': outcome.body,
                'dst_text': outcome.text,
                'attempts': outcome.attempts,
                'error': outcome.error,
                'delivery': delivery,
            }
        package.mark_delivered()
        self.record_repo.save(package)
        self._emit(TransferDelivered(
            transfer_id=package.transfer_id, adapter_kind=cmd.adapter_kind,
            dst_status=outcome.dst_status or 0, attempts=outcome.attempts))
        return {
            'delivered': True,
            'dst_status': outcome.dst_status,
            'dst_body': outcome.body,
            'dst_text': outcome.text,
            'attempts': outcome.attempts,
            'delivered_at': delivery.get('delivered_at'),
            'delivery': delivery,
        }

    # ---- 内部 ----
    def _require_not_expired(self, package) -> None:
        if package.is_expired():
            raise PackageExpiredError(
                f'transfer {package.transfer_id} 已超过 TTL={package.ttl_seconds}s，'
                f'expires_at={package.expires_at.isoformat()}'
            )

    def _record_delivery(self, package, adapter_kind, outcome) -> dict:
        """投递结果落 transfer_records.meta（审计层：流水与真实数据路径对齐）。"""
        delivery = {
            'adapter_kind': str(adapter_kind),
            'status': 'delivered' if outcome.delivered else 'failed',
            'attempts': outcome.attempts,
            'dst_status': outcome.dst_status,
            'error': outcome.error,
            'delivered_at': utc8now().isoformat() if outcome.delivered else None,
        }
        package.meta = {**(package.meta or {}), 'delivery': delivery}
        self.record_repo.save(package)
        return delivery
