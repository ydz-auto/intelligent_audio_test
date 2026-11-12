# -*- coding: utf-8 -*-
"""断点恢复（§9.2）。

Worker 重启后：
1. 把上次中断时仍 RUNNING 的 step 标记 FAILED（该轮模型调用已不可续）；
2. 对中断时仍 RUNNING 的 tool call 做副作用判定：
   - READ：安全，重置为 PENDING，由 Loop 按新上下文重新执行；
   - WRITE / DESTRUCTIVE：禁止自动重放，标记 FAILED 并把 run 收口为 FAILED
     （M2 接入真实副作用查询后改走审批）；
3. 其余活跃 run（QUEUED / RUNNING / WAITING_APPROVAL）重新投递。

已 COMPLETED 的 tool call 不会再次进入执行路径（Loop 按 tool_call_id 复用
落库结果），因此重启前后 tool_call 不重复执行。
"""
import logging
from typing import List

from agent_service.domain.enums import EventType, RunStatus, ToolCallStatus
from agent_service.domain.ports.side_effects import SideEffectChecker
from agent_service.domain.ports.run_wakeup import RunWakeup
from agent_service.domain.repositories import (
    EventRepository, RunRepository, StepRepository, ToolCallRepository,
)
from agent_service.domain.services.state_machine import RunStateMachine
from shared.utils.time_utils import utcnow

logger = logging.getLogger(__name__)


class RecoveryService:
    def __init__(self, *, runs: RunRepository, steps: StepRepository,
                 tool_calls: ToolCallRepository, events: EventRepository,
                 side_effects: SideEffectChecker, wakeup: RunWakeup):
        self._runs = runs
        self._steps = steps
        self._tool_calls = tool_calls
        self._events = events
        self._side_effects = side_effects
        self._wakeup = wakeup

    def recover(self) -> List[str]:
        """返回需要重新投递的 run_id 列表。幂等，可重复调用。"""
        resumable: List[str] = []
        for run in self._runs.list_active():
            try:
                self._steps.fail_running(
                    run.id, 'worker restarted before step finished')
                if self._has_unverified_write(run):
                    self._fail(run.id, 'RESTART_WRITE_UNVERIFIED')
                    continue
                for call in self._tool_calls.list_running(run.id):
                    if self._side_effects.can_replay(call):
                        self._tool_calls.update(
                            call.tool_call_id, run.id,
                            status=ToolCallStatus.PENDING)
                resumable.append(run.id)
            except Exception:  # noqa: BLE001 - 单个 run 恢复失败不阻断其余
                logger.exception('Run 恢复失败 run=%s', run.id)
        return resumable

    def _has_unverified_write(self, run) -> bool:
        for call in self._tool_calls.list_running(run.id):
            if not self._side_effects.can_replay(call):
                message = ('进程重启前的中断写操作需人工确认，'
                           '禁止自动重放')
                self._tool_calls.update(
                    call.tool_call_id, run.id,
                    status=ToolCallStatus.FAILED,
                    permission_decision='restart_write_unverified',
                    result={'ok': False, 'content': message,
                            'error_code': 'RESTART_WRITE_UNVERIFIED'},
                    error=message)
                self._events.append(run.id, EventType.ERROR, {
                    'code': 'RESTART_WRITE_UNVERIFIED',
                    'message': message,
                })
                return True
        return False

    def _fail(self, run_id: str, error: str) -> None:
        current = self._runs.get(run_id)
        if current is None or current.status.is_terminal:
            return
        try:
            RunStateMachine.assert_transition(current.status, RunStatus.FAILED)
        except Exception:  # noqa: BLE001 - 状态机拒绝说明已被其它路径收口
            return
        hit = self._runs.transition_if(
            run_id, {current.status}, RunStatus.FAILED, error=error,
            finished_at=utcnow())
        if hit:
            self._events.append(run_id, EventType.RUN_FINISHED, {
                'status': RunStatus.FAILED.value,
                'reason': 'restart_recovery',
                'error': error,
            })
            self._wakeup.notify(run_id)
