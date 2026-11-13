# -*- coding: utf-8 -*-
"""写操作审批服务（INT-2466，方案 §5.2 / §9 / §10 / §9.4）。

职责：

1. **提案**：WRITE / DESTRUCTIVE 工具调用先落 ``agent_approval``（一次
   tool call 一张单，``(run_id, tool_call_id)`` 唯一），审批前不产生任何
   副作用；同一次调用重复提交只复用已有提案（重启 / 重复投递幂等）。
2. **决策**：只有 run 归属者本人能审批（越权一律 404，不泄漏存在性）；
   决策 / 过期都是 ``WHERE status='PENDING'`` 的条件更新，并发审批只有一个
   请求生效；过期单不再允许决策。
3. **执行前复核**：决策时把审批人的实时权限快照写入 ``decision_permissions``；
   真正执行前用它重新校验权限，并重新校验工具注册状态与参数 Schema ——
   「审批后权限被收回」或注册表变化都让执行失败，而不是照旧执行。
4. **过期**：``expires_at`` 到点即不可执行（决策路径 / Loop 恢复路径 /
   启动扫描三处判定，幂等）。
5. **取消**：run 被取消时未决提案转 REJECTED（不执行、留决策人）。

审批本身不代表授权：审批人可以是本人，但**执行**仍要求其权限仍在。
"""
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Optional, Sequence, Tuple

from agent_service.domain.enums import (
    ApprovalDecision, ApprovalStatus, EventType, ToolRisk,
)
from agent_service.domain.exceptions import (
    ApprovalConflict, ApprovalExpired, ApprovalNotFound,
)
from agent_service.domain.model.entities import (
    AgentApproval, AgentRun, AgentToolCall, ToolCallRequest,
)
from agent_service.domain.ports.tool_gateway import ToolGateway
from agent_service.domain.repositories import (
    ApprovalRepository, EventRepository, RunRepository,
)
from shared.agent_tools.intent_tools import redact_for_audit
from shared.utils.time_utils import utcnow

@dataclass(frozen=True)
class ApprovalSettings:
    """审批行为参数（全部来自配置）。"""

    ttl_seconds: int = 900
    expiry_scan_limit: int = 200


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
                args_hash: str) -> Tuple[AgentApproval, bool]:
        """生成待审批提案；同一 tool call 已提案时复用（不重复建单）。

        返回 ``(审批单, 是否新建)``。新建时额外落一条 ``approval_required``
        事件（SSE 的审批入口），重复提案不再重复发事件。
        """
        existing = self._approvals.find_for_tool_call(
            run.id, call.tool_call_id)
        if existing is not None:
            return existing, False

        now = utcnow()
        approval_id = uuid.uuid4().hex
        approval = AgentApproval(
            id=approval_id,
            run_id=run.id,
            tool_call_id=call.tool_call_id,
            status=ApprovalStatus.PENDING,
            proposal={
                'tool': call.name,
                'risk': risk.value,
                # 审计 / 审批视图都不落正文（memory_write 内容已被脱敏）
                'arguments': redact_for_audit(call.name, call.arguments),
                'args_hash': args_hash,
                'idempotency_key': idempotency_key,
                'step_id': step_id,
                'turn': int(turn),
                'requested_by': run.owner_id,
                'session_id': run.session_id,
            },
            # 变更预览：REST 写工具给「方法 + 路径 + 参数」，域写工具可覆盖成
            # 字段级 diff；拿不到预览就留 None，不伪造。
            diff=self._gateway.proposal_diff(call.name, call.arguments),
            expires_at=now + timedelta(
                seconds=max(1, int(self._settings.ttl_seconds))),
            created_at=now, updated_at=now,
        )
        approval = self._approvals.add(approval)
        # 并发唯一键冲突时 add 返回已存在的行：只有本次真正建出的才发事件
        if approval.id != approval_id:
            return approval, False
        self._events.append(run.id, EventType.APPROVAL_REQUIRED, {
            'approval_id': approval.id,
            'tool_call_id': call.tool_call_id,
            'tool': call.name,
            'risk': risk.value,
            'proposal': approval.proposal,
            'expires_at': (approval.expires_at.isoformat()
                           if approval.expires_at else None),
        })
        return approval, True

    # ------------------------------------------------------------ 决策

    def decide(self, approval_id: str, *, owner_id: int, tenant_id: str,
               decision: ApprovalDecision,
               permissions: Sequence[str]
               ) -> Tuple[AgentApproval, AgentRun]:
        """审批决策（幂等键是审批单状态本身）。

        - 审批单不存在 / 不属于当前用户/租户的 run → ``ApprovalNotFound``（404）；
        - 已决 → ``ApprovalConflict``（409）；
        - 已过期 → 先落 EXPIRED 再 ``ApprovalExpired``（409），不执行；
        - 并发审批只有一个请求命中条件更新，其余按「已决」返回。
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
        if approval.status is not ApprovalStatus.PENDING:
            raise ApprovalConflict(approval_id)
        if self._is_due(approval, now):
            self._approvals.expire(approval.id, now)
            raise ApprovalExpired(approval.id, approval.run_id)

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

    def expire_due(self) -> int:
        """启动 / 恢复时的过期扫描：把到点的待审批单统一判过期。"""
        now = utcnow()
        expired = 0
        for approval in self._approvals.list_due(
                now, self._settings.expiry_scan_limit):
            if self._approvals.expire(approval.id, now):
                expired += 1
        return expired

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
        risk = self._gateway.risk_of(call.tool)
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
        return [self.settle(item)
                for item in self._approvals.list_by_run(run_id)]

    # ------------------------------------------------------------ internals

    @staticmethod
    def _is_due(approval: AgentApproval, now: datetime) -> bool:
        expires = approval.expires_at
        return expires is not None and expires <= now


__all__ = ['ApprovalService', 'ApprovalSettings']
