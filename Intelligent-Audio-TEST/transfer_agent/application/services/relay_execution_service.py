# -*- coding: utf-8 -*-
"""中转执行应用服务 — 中枢侧触发器的认领/终态编排（F2.3/INT-53）。

背景：A 区 dispatch 到位的 EVAL_REQUEST 此前无生产调用方（execute_incoming
仅集成测试以后台线程模拟触发，INT-50 提测范围说明/INT-29 审计已知项）。
本服务为中枢触发链路的 transfer_agent 侧契约：
- claim_next：原子认领一个待执行 EVAL_REQUEST 中转包（仓储行锁 CAS，
  幂等去重前提：同一中转包不重复执行）；
- finish：执行终态收敛（executed/failed），终态后不再认领（重复触发幂等）。

失败收敛：finish(failed) 记流水终态并发 TransferRelayFailed 审计事件；
A 侧按既有 relay_result_timeout_seconds 超时进既有 __error__ 收敛路径，
任务不悬挂（触发链路失败不产生悬挂中转包）。
"""
from __future__ import annotations

import logging
from typing import Callable, Optional

from transfer_agent.domain.entities.transfer_package import (
    RelayExecutionState,
    TransferPackage,
)
from transfer_agent.domain.errors import (
    InvalidPackageFieldError,
    PackageNotFoundError,
)
from transfer_agent.domain.events.transfer_events import (
    TransferEvent,
    TransferRelayClaimed,
    TransferRelayCompleted,
    TransferRelayFailed,
)
from transfer_agent.domain.repositories.transfer_repository_abc import (
    TransferRecordRepositoryABC,
)
from transfer_agent.domain.services.signature_service import SignatureService

logger = logging.getLogger(__name__)


def _default_event_sink(event: TransferEvent) -> None:
    logger.info('transfer_event=%s transfer_id=%s detail=%s',
                type(event).__name__, event.transfer_id, event)


class RelayExecutionService:
    """中转执行应用服务（触发器契约：原子认领 → 执行 → 终态收敛）。"""

    def __init__(
        self,
        record_repo: Optional[TransferRecordRepositoryABC] = None,
        signature_service: Optional[SignatureService] = None,
        event_sink: Optional[Callable[[TransferEvent], None]] = None,
        self_zone: Optional[str] = None,
    ):
        self._record_repo = record_repo
        self._signature_service = signature_service
        self._event_sink = event_sink or _default_event_sink
        self._self_zone = self_zone

    # ---- 依赖延迟装配（避免导入期触发 DB 连接）----
    @property
    def record_repo(self) -> TransferRecordRepositoryABC:
        if self._record_repo is None:
            from transfer_agent.infrastructure.persistence.transfer_repository import (
                transfer_record_repository,
            )
            self._record_repo = transfer_record_repository
        return self._record_repo

    @property
    def signature_service(self) -> SignatureService:
        if self._signature_service is None:
            from transfer_agent.config.config import Config
            self._signature_service = SignatureService(Config.transfer_tokens())
        return self._signature_service

    @property
    def self_zone(self) -> str:
        """本实例所在区（认领 dst_zone=本区 的待执行中转包）。"""
        if self._self_zone is None:
            from transfer_agent.config.config import Config
            self._self_zone = Config.TRANSFER_ZONE
        return self._self_zone

    def _emit(self, event: TransferEvent) -> None:
        try:
            self._event_sink(event)
        except Exception:
            logger.warning('传输事件发布失败（不阻塞主流程）: %s', event, exc_info=True)

    # ================= 命令 =================
    def claim_next(self, *, token: str, stale_seconds: int) -> Optional[TransferPackage]:
        """原子认领一个待执行中转包（触发器轮询入口；无候选返回 None）。

        访问控制：token 须为任一指向本区的预共享路由 token（入站路由成员资格，
        fail-closed）；stale_seconds 为认领失效窗（认领方死亡后的崩溃恢复阈值，
        由触发器按自身最坏执行时长配置）。
        """
        if stale_seconds <= 0:
            raise InvalidPackageFieldError(f'stale_seconds 须为正整数: {stale_seconds}')
        self.signature_service.verify_inbound_token(self.self_zone, token)
        package = self.record_repo.claim_relay_execution(
            dst_zone=self.self_zone, stale_seconds=stale_seconds)
        if package is None:
            return None
        relay = dict((package.meta or {}).get('relay') or {})
        self._emit(TransferRelayClaimed(
            transfer_id=package.transfer_id, pkg_type=package.pkg_type,
            src_zone=package.src_zone, dst_zone=package.dst_zone,
            attempts=int(relay.get('attempts') or 1)))
        return package

    def finish(self, *, transfer_id: str, token: str, state: str,
               error: Optional[str] = None) -> bool:
        """中转执行终态收敛（executed/failed；重复收敛/未认领幂等拒绝返回 False）。

        访问控制：按包路由预共享 token 验签（与其他 /internal/transfer/* 端点
        一致 — 收敛方持有发起侧路由 token）。
        """
        try:
            state_value = RelayExecutionState(state).value
        except ValueError:
            raise InvalidPackageFieldError(
                f'relay 终态非法（允许 executed/failed）: {state}') from None
        if state_value == RelayExecutionState.EXECUTING.value:
            raise InvalidPackageFieldError('relay 终态不允许为 executing')
        package = self.record_repo.find_by_transfer_id(transfer_id)
        if package is None:
            raise PackageNotFoundError(f'传输包不存在: transfer_id={transfer_id}')
        self.signature_service.verify_token(package.src_zone, package.dst_zone, token)
        finished = self.record_repo.finish_relay_execution(
            transfer_id=transfer_id, state=state_value, error=error)
        if not finished:
            return False
        if state_value == RelayExecutionState.EXECUTED.value:
            self._emit(TransferRelayCompleted(transfer_id=transfer_id))
        else:
            self._emit(TransferRelayFailed(transfer_id=transfer_id,
                                           reason=error or '中转执行失败'))
        return True
