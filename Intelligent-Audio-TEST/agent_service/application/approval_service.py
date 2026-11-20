# -*- coding: utf-8 -*-
"""写操作审批服务（INT-2466 / INT-2571，方案 §5.2 / §9 / §10 / §9.4）。

职责：

1. **提案**：WRITE / DESTRUCTIVE 工具调用先落 ``agent_approval``（一次
   tool call 1..N 张单，``(run_id, tool_call_id, batch_index)`` 唯一），审批
   前不产生任何副作用；同一次调用重复提交只复用已有提案（重启 / 重复投递
   幂等）。单次影响 > 阈值（默认 20）个显式枚举对象时按 §9.4.1 拆单：同批
   共享 ``batch_id``，逐张决策、**全批批准后一次执行**；``DESTRUCTIVE`` 恒
   一张单。超过对象上限（默认 100）在提案前拒绝
   （``APPROVAL_OBJECT_LIMIT_EXCEEDED``：不建单、无副作用）。
2. **决策**：只有 run 归属者本人能审批（越权一律 404，不泄漏存在性）；
   决策 / 过期都是 ``WHERE status='PENDING'`` 的条件更新，并发审批只有一个
   请求生效；过期单不再允许决策（``ApprovalExpired``，调用方据此唤醒 run）。
   拒绝 / 过期按**批**收口：同一次调用剩余的 PENDING 单一起转 REJECTED /
   EXPIRED，不留半批状态。
3. **执行前复核**：决策时把审批人的实时权限快照写入 ``decision_permissions``；
   真正执行前用它重新校验权限，并重新校验工具注册状态与参数 Schema ——
   「审批后权限被收回」或注册表变化都让执行失败，而不是照旧执行。拆单批次
   逐张复核，任一不再授权即整批不执行。
4. **过期**：``expires_at`` 到点即不可执行（决策路径 / 命令侧结算 /
   周期扫描三处判定，幂等）。查询侧只读，不落库（§3.1 CQRS）。
5. **取消**：run 被取消时未决提案转 REJECTED（不执行、留决策人）。

审批本身不代表授权：审批人可以是本人，但**执行**仍要求其权限仍在。
"""
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Sequence, Tuple

from agent_service.domain.enums import (
    ApprovalDecision, ApprovalStatus, EventType, ToolRisk,
)
from agent_service.domain.exceptions import (
    ApprovalConflict, ApprovalConfirmationRequired, ApprovalExpired,
    ApprovalNotFound, ApprovalObjectLimitExceeded,
)
from agent_service.domain.model.entities import (
    AgentApproval, AgentRun, AgentToolCall, ToolCallRequest,
)
from agent_service.domain.ports.tool_gateway import ToolGateway
from agent_service.domain.repositories import (
    ApprovalRepository, EventRepository, RunRepository,
)
from shared.agent_tools import approval_split
from shared.agent_tools.intent_tools import redact_for_audit
from shared.utils.time_utils import utcnow

@dataclass(frozen=True)
class ApprovalSettings:
    """审批行为参数（全部来自配置）。

    ``split_threshold`` / ``split_chunk_size`` / ``max_objects`` 是 §9.4.1
    拆单口径：阈值只允许收紧（收敛在配置层，见 ``Config``）；粒度默认 1
    （每对象一张单）；单次调用对象上限默认 100，超过提案前拒绝。
    """

    ttl_seconds: int = 900
    expiry_scan_limit: int = 200
    split_threshold: int = 20
    split_chunk_size: int = 1
    max_objects: int = 100


def _granted(granted: Sequence[str], required: Sequence[str]) -> bool:
    """权限 OR 语义；``*`` 通配；required 为空表示仅需登录。"""
    if not required:
        return True
    perms = set(granted or ())
    if '*' in perms:
        return True
    return bool(perms & set(required))


class ApprovalService:
    def __init__(self, *, approvals: ApprovalRepository,
                 events: EventRepository, runs: RunRepository,
                 tool_gateway: ToolGateway,
                 settings: Optional[ApprovalSettings] = None):
        self._approvals = approvals
        self._events = events
        self._runs = runs
        self._gateway = tool_gateway
        self._settings = settings or ApprovalSettings()

    # ------------------------------------------------------------ 提案

    def propose(self, run: AgentRun, *, step_id: Optional[str],
                call: ToolCallRequest, risk: ToolRisk, turn: int,
                idempotency_key: str,
                args_hash: str) -> Tuple[List[AgentApproval], bool]:
        """生成待审批提案（§9.4.1：1..N 张单，同批共享 ``batch_id``）。

        返回 ``(审批单列表, 是否新建)``，列表按 ``batch_index`` 升序。新建时
        每张单各落一条 ``approval_required`` 事件（SSE 的审批入口，载荷带
        批次字段），重复提案不再重复发事件。

        幂等：同一 tool call 已存在**任一**单时整批复用（不按新配置重建）；
        ``(run_id, tool_call_id, batch_index)`` 唯一键兜底并发插入。

        超过对象上限抛 ``ApprovalObjectLimitExceeded``（提案前拒绝，不建单、
        无副作用）。
        """
        existing = self._approvals.list_for_tool_call(
            run.id, call.tool_call_id)
        if existing:
            return existing, False

        try:
            plan = approval_split.plan_approvals(
                call.name, call.arguments, risk=risk.value,
                threshold=self._settings.split_threshold,
                chunk_size=self._settings.split_chunk_size,
                max_objects=self._settings.max_objects)
        except approval_split.ObjectLimitExceeded as exc:
            raise ApprovalObjectLimitExceeded(exc.count, exc.limit) from exc

        now = utcnow()
        batch_id = (approval_split.new_batch_id()
                    if plan.total > 1 else None)
        approvals: List[AgentApproval] = []
        created_any = False
        for chunk in plan.chunks:
            approval_id = uuid.uuid4().hex
            approval = AgentApproval(
                id=approval_id,
                run_id=run.id,
                tool_call_id=call.tool_call_id,
                status=ApprovalStatus.PENDING,
                proposal={
                    'tool': call.name,
                    'risk': risk.value,
                    # 审计 / 审批视图都不落正文（memory_write 内容已被脱敏）；
                    # 拆单时参数收窄到本单对象，完整参数留在 agent_tool_call
                    'arguments': redact_for_audit(call.name, chunk.arguments),
                    'args_hash': args_hash,
                    'idempotency_key': idempotency_key,
                    'step_id': step_id,
                    'turn': int(turn),
                    'requested_by': run.owner_id,
                    'session_id': run.session_id,
                    # §9.4.1：本批总对象数（非枚举范围计 1）
                    'object_count': int(plan.object_count),
                },
                # 变更预览同样收窄到本单对象；拿不到就留 None，不伪造。
                diff=self._gateway.proposal_diff(call.name, chunk.arguments),
                expires_at=now + timedelta(
                    seconds=max(1, int(self._settings.ttl_seconds))),
                batch_id=batch_id,
                batch_index=chunk.index,
                batch_total=chunk.total,
                object_ref=chunk.object_ref,
                created_at=now, updated_at=now,
            )
            approval = self._approvals.add(approval)
            approvals.append(approval)
            # 并发唯一键冲突时 add 返回已存在的行：只有本次真正建出的才发事件
            if approval.id != approval_id:
                continue
            created_any = True
            self._events.append(run.id, EventType.APPROVAL_REQUIRED, {
                'approval_id': approval.id,
                'tool_call_id': call.tool_call_id,
                'tool': call.name,
                'risk': risk.value,
                'proposal': approval.proposal,
                'expires_at': (approval.expires_at.isoformat()
                               if approval.expires_at else None),
                # §9.4.1 第 10 条：每张单一条事件，同批 tool_call_id 相同
                'batch_id': approval.batch_id,
                'batch_index': approval.batch_index,
                'batch_total': approval.batch_total,
                'object_count': int(plan.object_count),
            })
        approvals.sort(key=lambda item: item.batch_index)
        return approvals, created_any

    # ------------------------------------------------------------ 决策

    def decide(self, approval_id: str, *, owner_id: int, tenant_id: str,
               decision: ApprovalDecision,
               permissions: Sequence[str],
               confirm: bool = False
               ) -> Tuple[AgentApproval, AgentRun]:
        """审批决策（幂等键是审批单状态本身）。

        - 审批单不存在 / 不属于当前用户/租户的 run → ``ApprovalNotFound``（404）；
        - 已决 → ``ApprovalConflict``（409）；
        - 已过期 → 先落 EXPIRED 再 ``ApprovalExpired``（409），不执行；
        - 并发审批只有一个请求命中条件更新，其余按「已决」返回；
        - **破坏性操作二次确认**（INT-2467）：``DESTRUCTIVE`` 工具批准时必须
          同时带 ``confirm=true``，否则 ``ApprovalConfirmationRequired``（不落决策）。
          拒绝（REJECT）不需要二次确认。

        ``ApprovalExpired`` 是「让 run 收下过期结果」的唤醒信号：调用方必须
        提交 run（``executor.submit``），否则 run 会一直停在 WAITING_APPROVAL。
        """
        approval = self._approvals.get(approval_id)
        if approval is None:
            raise ApprovalNotFound(approval_id)
        run = self._runs.get_for_owner(
            approval.run_id, owner_id, tenant_id)
        if run is None:
            # 非本人 / 不存在统一 404：不泄漏审批单或 run 是否存在
            raise ApprovalNotFound(approval_id)

        now = utcnow()
        if run.status.is_terminal:
            # run 已收口（取消 / 失败 / 超预算）：审批不再产生任何副作用
            self.cancel_pending(approval.run_id, owner_id)
            raise ApprovalConflict(approval_id)
        if approval.status is ApprovalStatus.EXPIRED:
            # 已被命令侧 / 周期扫描结算成 EXPIRED：仍按「过期」语义返回，
            # 调用方据此唤醒 run 把 APPROVAL_EXPIRED 回灌模型（不是 409 挂死）。
            # 同批兄弟单一起收盘，不留半批 PENDING（§9.4.1 第 5 条）。
            self._close_batch(approval, ApprovalStatus.EXPIRED, now)
            raise ApprovalExpired(approval.id, approval.run_id)
        if approval.status is not ApprovalStatus.PENDING:
            raise ApprovalConflict(approval_id)
        if self._is_due(approval, now):
            self._approvals.expire(approval.id, now)
            self._close_batch(approval, ApprovalStatus.EXPIRED, now)
            raise ApprovalExpired(approval.id, approval.run_id)

        if decision is ApprovalDecision.APPROVE and not confirm:
            # DESTRUCTIVE 工具（设备控制等不可回滚动作）必须二次确认：
            # 风险按当前注册表实时解析，审批单记录的 risk 只作兜底。
            tool = str((approval.proposal or {}).get('tool') or '')
            risk = self._gateway.risk_of(tool) if tool else None
            if risk is None:
                recorded = str((approval.proposal or {}).get('risk') or '')
                risk = ToolRisk(recorded) if recorded in ToolRisk.__members__ \
                    else None
            if risk is ToolRisk.DESTRUCTIVE:
                raise ApprovalConfirmationRequired(approval.id, tool)

        hit = self._approvals.decide(
            approval.id, decision.target, decided_by=owner_id,
            decided_at=now, permissions=tuple(permissions or ()), now=now)
        if not hit:
            # 并发：另一请求先决策，或刚好过期（同一 UPDATE 的条件）
            latest = self._approvals.get(approval.id)
            if latest is not None and latest.status is ApprovalStatus.EXPIRED:
                raise ApprovalExpired(approval.id, approval.run_id)
            raise ApprovalConflict(approval.id)
        latest = self._approvals.get(approval.id)
        if latest is None:  # pragma: no cover - 条件更新刚命中过
            raise ApprovalConflict(approval.id)
        if decision is ApprovalDecision.REJECT:
            # §9.4.1 第 5 条：任一单被拒 → 整批拒绝，其余 PENDING 自动转
            # REJECTED（不执行、留决策人），不留半批状态。
            self._close_batch(latest, ApprovalStatus.REJECTED, now,
                              actor=owner_id)
            latest = self._approvals.get(approval.id) or latest
        return latest, run

    # ------------------------------------------------------------ 状态处置

    def settle(self, approval: AgentApproval) -> AgentApproval:
        """把到期的 PENDING 单落成 EXPIRED，返回最新状态（幂等）。"""
        if approval.status is not ApprovalStatus.PENDING:
            return approval
        now = utcnow()
        if not self._is_due(approval, now):
            return approval
        self._approvals.expire(approval.id, now)
        return self._approvals.get(approval.id) or approval

    def expire_due(self) -> List[str]:
        """过期扫描（命令侧）：把到点的待审批单统一判过期。

        返回**受影响的 run id**（去重、保序）：调用方据此提交 run，让 Loop
        把 ``APPROVAL_EXPIRED`` 作为工具结果回灌模型并继续收口 —— 否则
        「TTL 到点且无人决策」只能等重启。

        拆单批次按批收口：一张到点即整批（同一次调用的其余 PENDING）转
        EXPIRED，不留半批状态（§9.4.1 第 5 条）。
        """
        now = utcnow()
        expired_runs: List[str] = []
        for approval in self._approvals.list_due(
                now, self._settings.expiry_scan_limit):
            if self._approvals.expire(approval.id, now):
                self._close_batch(approval, ApprovalStatus.EXPIRED, now)
                if approval.run_id not in expired_runs:
                    expired_runs.append(approval.run_id)
        return expired_runs

    def cancel_pending(self, run_id: str, actor_id: int) -> int:
        """run 取消：未决提案转 REJECTED（不执行；已完成写不回滚，§9.2-4）。"""
        now = utcnow()
        cancelled = 0
        for approval in self._approvals.list_open_by_run(run_id):
            if self._approvals.decide(
                    approval.id, ApprovalStatus.REJECTED,
                    decided_by=actor_id, decided_at=now,
                    permissions=(), now=now):
                cancelled += 1
        return cancelled

    # ------------------------------------------------------------ 执行前复核

    def check_execution(self, approval: AgentApproval,
                        call: AgentToolCall) -> Optional[Tuple[str, str]]:
        """审批 → 执行之间的实时复核：``(错误码, 文案)``，``None`` 表示可执行。

        1. 权限：用**决策时**的权限快照重新校验（审批后权限被收回 → 拒绝）；
        2. 实时状态：工具仍在注册表、仍是写工具、参数仍合法；
        3. 审批单必须仍是 APPROVED（过期 / 拒绝 / 并发变更都不执行）。
        """
        if approval.status is not ApprovalStatus.APPROVED:
            code = ('APPROVAL_EXPIRED'
                    if approval.status is ApprovalStatus.EXPIRED
                    else 'APPROVAL_REJECTED')
            return code, '审批单未批准，写操作不执行'
        arguments = call.arguments or {}
        required = self._gateway.required_permissions(call.tool, arguments)
        if required is None:
            return ('TOOL_NOT_REGISTERED', '工具已不存在，审批作废，写操作未执行')
        risk = (self._gateway.risk_for(call.tool, arguments)
                or self._gateway.risk_of(call.tool))
        if risk is None or not risk.requires_approval:
            return ('TOOL_NOT_REGISTERED', '工具已不可用，审批作废，写操作未执行')
        validation = self._gateway.validate_call(call.tool, arguments)
        if validation:
            return ('INVALID_ARGUMENTS', f'参数已不合法，写操作未执行：{validation}')
        if not _granted(approval.decision_permissions or (), required):
            return ('PERMISSION_DENIED', '审批后权限已收回，写操作未执行')
        return None

    # ------------------------------------------------------------ 查询

    def list_for_run(self, run_id: str) -> List[AgentApproval]:
        """本 run 的审批单（**只读**，查询侧不落库）。

        §3.1 CQRS：列表接口不得把到点的 PENDING 单写成 EXPIRED —— 那会让
        「先查列表再决策」拿到 409 且 run 无人唤醒。过期结算只在命令侧
        （决策 / Loop 结算 / 周期扫描）发生，查询如实返回库内状态。
        """
        return self._approvals.list_by_run(run_id)

    # ------------------------------------------------------------ internals

    def close_remaining(self, approval: AgentApproval,
                        target: ApprovalStatus, *,
                        actor: Optional[int] = None) -> int:
        """命令侧整批收口：把同一次调用剩余的 PENDING 单一起关掉。

        Loop 结算（拒绝 / 过期）用它保证不留半批 PENDING；只动
        ``status='PENDING'`` 的行，已决单不受影响。
        """
        return self._close_batch(approval, target, utcnow(), actor=actor)

    def check_batch_execution(self, approvals: Sequence[AgentApproval],
                              call: AgentToolCall) -> Optional[Tuple[str, str]]:
        """拆单批次的执行前复核：逐张校验，任一不通过则整批不执行。

        用**完整原始参数**（``agent_tool_call.arguments``）校验，不是收窄后的
        单对象参数 —— 真正执行的就是这一份（§9.4.1 第 5 条）。
        """
        for approval in approvals:
            failure = self.check_execution(approval, call)
            if failure is not None:
                return failure
        return None

    def _close_batch(self, approval: AgentApproval,
                     target: ApprovalStatus, now: datetime, *,
                     actor: Optional[int] = None) -> int:
        """把同一次调用剩余的 PENDING 单整批收口（拒绝 / 过期）。"""
        return self._approvals.settle_batch(
            approval.run_id, approval.tool_call_id, target,
            decided_by=actor,
            decided_at=(now if actor is not None else None),
            now=now)

    @staticmethod
    def _is_due(approval: AgentApproval, now: datetime) -> bool:
        expires = approval.expires_at
        return expires is not None and expires <= now


__all__ = ['ApprovalService', 'ApprovalSettings']
