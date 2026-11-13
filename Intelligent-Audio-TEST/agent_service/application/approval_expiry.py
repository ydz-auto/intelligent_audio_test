# -*- coding: utf-8 -*-
"""审批过期周期扫描（INT-2466，方案 §9.4）。

TTL 到点后必须有**命令侧**动作把 ``PENDING`` 单结算成 ``EXPIRED`` 并唤醒
run，否则「无人决策」的 run 会一直停在 ``WAITING_APPROVAL``，只能靠重启
或取消解脱。查询接口（``GET /runs/{id}/approvals``）只读，不承担结算
（§3.1 CQRS），结算由这里与决策 / Loop 恢复两处命令路径负责。

关闭态（``AGENT_ENABLED=false``）不启动本扫描：唤醒 run 属于后台执行，
与 INT-2529「关闭态不产生任何后台 run」同一条开关。
"""
import logging
import threading
from typing import Callable, List, Optional

from agent_service.application.approval_service import ApprovalService

logger = logging.getLogger(__name__)


class ApprovalExpiryScanner:
    """按固定间隔扫描到点审批单，结算后提交受影响的 run。

    ``run_once`` 与线程分离：单测直接调它即可确定性验证过期唤醒链路，
    不必等真实间隔。
    """

    def __init__(self, *, approvals: ApprovalService,
                 wake_run: Callable[[str], None], interval_seconds: float):
        self._approvals = approvals
        self._wake_run = wake_run
        self._interval = max(1.0, float(interval_seconds))
        self._stop = threading.Event()
        self._guard = threading.Lock()
        self._thread: Optional[threading.Thread] = None

    def run_once(self) -> List[str]:
        """扫一轮：返回被判过期的审批单所属 run id（去重），并逐个唤醒。"""
        run_ids = self._approvals.expire_due()
        for run_id in run_ids:
            try:
                self._wake_run(run_id)
            except Exception:  # noqa: BLE001 - 单次投递失败不中断整轮扫描
                logger.exception('审批过期唤醒 run 失败 run=%s', run_id)
        return run_ids

    def start(self) -> None:
        with self._guard:
            if self._thread is not None:
                return
            self._thread = threading.Thread(
                target=self._loop, name='agent-approval-expiry', daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        with self._guard:
            thread, self._thread = self._thread, None
        if thread is not None:
            thread.join(timeout=5.0)

    # ------------------------------------------------------------ internals

    def _loop(self) -> None:
        while not self._stop.wait(self._interval):
            try:
                self.run_once()
            except Exception:  # noqa: BLE001 - 扫描失败不终止线程
                logger.exception('审批过期扫描失败')


__all__ = ['ApprovalExpiryScanner']
