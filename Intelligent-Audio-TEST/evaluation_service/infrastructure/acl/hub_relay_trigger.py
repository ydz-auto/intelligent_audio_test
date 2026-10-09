# -*- coding: utf-8 -*-
"""中枢侧中转执行生产触发器（F2.3/INT-53，设计文档 §4.2.2 步骤④生产化）。

生产形态下 A→B 传输到位的 EVAL_REQUEST 由本触发器自动发现并执行（此前无生产
调用方，集成测试以后台线程模拟 — INT-50 提测范围说明/INT-29 审计已知项）：

轮询式（方案一，二选一取其一）：守护线程按 relay_trigger_poll_interval_seconds
周期调 transfer_agent /internal/transfer/relay/claim 原子认领待执行中转包
（幂等去重：transfer_agent 仓储行锁 CAS，同一中转包不重复执行），认领成功即
execute_incoming（④⑤⑥⑦：解包→T-B 出站投递 C→校验→EVAL_RESULT 回同步，
F2.1/F2.2 已交付），完成后 /relay/{id}/finish 收敛终态（executed/failed；
失败不悬挂 — A 侧按 relay_result_timeout_seconds 超时进既有 __error__ 收敛
路径并发 Failed 审计）。

事件式（方案二）不采用：需 A 侧接线改动（明确不做，F2.2 已交付），且传输域
事件按五通道契约不进跨服务事件通道（transfer_events 模块契约）。

仅中枢（self_zone == hub_zone）且 relay_trigger_enabled 时启动；边缘区（A）
不启动（start() 自门控）。
"""
from __future__ import annotations

import logging
import threading
from typing import Optional

logger = logging.getLogger(__name__)


class HubRelayTrigger:
    """中枢侧中转执行触发器（轮询 claim → execute_incoming → finish 收敛）。"""

    def __init__(self, acl, poll_interval_seconds: Optional[float] = None,
                 claim_stale_seconds: Optional[int] = None):
        self._acl = acl
        self._poll_interval = poll_interval_seconds
        self._claim_stale_seconds = claim_stale_seconds
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # ---- 配置（延迟取 ACL settings，进既有 third_party 配置框架）----
    @property
    def poll_interval_seconds(self) -> float:
        if self._poll_interval is None:
            return float(getattr(self._acl.settings,
                                 'relay_trigger_poll_interval_seconds', 2.0))
        return float(self._poll_interval)

    @property
    def claim_stale_seconds(self) -> int:
        if self._claim_stale_seconds is None:
            return int(getattr(self._acl.settings,
                               'relay_trigger_claim_stale_seconds', 1800))
        return int(self._claim_stale_seconds)

    @property
    def enabled(self) -> bool:
        settings = self._acl.settings
        return bool(settings.is_hub
                    and getattr(settings, 'relay_trigger_enabled', True))

    # ---- 生命周期 ----
    def start(self) -> None:
        if not self.enabled:
            logger.info('中枢侧中转执行触发器未启用（is_hub=%s relay_trigger_enabled=%s）',
                        self._acl.settings.is_hub,
                        getattr(self._acl.settings, 'relay_trigger_enabled', None))
            return
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run, name='HubRelayTrigger', daemon=True)
        self._thread.start()
        logger.info('中枢侧中转执行触发器已启动（poll_interval=%ss claim_stale=%ss）',
                    self.poll_interval_seconds, self.claim_stale_seconds)

    def stop(self, timeout: float = 5.0) -> None:
        self._stop_event.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=timeout)
        self._thread = None

    # ---- 轮询主循环 ----
    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                claimed = self._claim_next()
            except Exception as e:
                # 触发链路失败收敛：记录日志，下一轮询重试（任务不悬挂 —
                # A 侧按 relay_result_timeout_seconds 超时进既有收敛路径）
                logger.warning('中转执行认领失败（下一轮重试）: %s', e)
                claimed = None
            if claimed is None:
                self._stop_event.wait(self.poll_interval_seconds)
                continue
            self._execute_claimed(claimed)

    def _claim_next(self) -> Optional[str]:
        token = self._inbound_token()
        return self._acl.client.claim_relay(
            token=token, stale_seconds=self.claim_stale_seconds)

    def _inbound_token(self) -> str:
        settings = self._acl.settings
        token = self._acl.client.get_token(settings.sync_back_zone, settings.self_zone)
        if not token:
            raise RuntimeError(
                f'未配置边缘区 {settings.sync_back_zone}->{settings.self_zone} '
                f'预共享 token，中转执行触发器无法认领（fail-closed）')
        return token

    def _execute_claimed(self, transfer_id: str) -> None:
        try:
            self._acl.execute_incoming(transfer_id)
        except Exception as e:
            # execute_incoming 内部已按 stage 发 Failed 审计（unpack/
            # third_party_call/result_sync_back/transfer）；此处仅收敛 relay
            # 终态，不重复发事件
            logger.exception('中转包执行失败 transfer_id=%s', transfer_id)
            state, error = 'failed', str(e)
        else:
            state, error = 'executed', None
        try:
            self._acl.client.finish_relay(
                transfer_id, state=state, error=error,
                token=self._inbound_token())
        except Exception:
            logger.exception('中转执行终态收敛失败 transfer_id=%s state=%s',
                             transfer_id, state)
