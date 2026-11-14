# -*- coding: utf-8 -*-
"""会话 / Run 应用服务（命令侧）。

- 建会话、发起 run（支持 Idempotency-Key）、取消、查询；
- 发起 run 时先落 run_started 事件，保证 SSE 从任意时刻连上都能回放到首事件；
- 状态推进一律过 RunStateMachine + 条件更新，终态不可覆盖。
"""
import logging
import uuid
from typing import Dict, Iterable, Optional, Tuple

from agent_service.application.approval_service import ApprovalService
from agent_service.application.cancel_registry import CancelRegistry
from agent_service.application.skill_registry import SkillRegistry
from agent_service.domain.enums import ApprovalDecision, EventType, RunStatus
from agent_service.domain.exceptions import (
    InvalidRunTransition, RunNotFound, SessionNotFound, SkillNotAvailable,
)
from agent_service.domain.model.agent_skill import AgentRunSkill
from agent_service.domain.model.budget import RunBudget
from agent_service.domain.model.entities import AgentRun, AgentSession
from agent_service.domain.repositories import (
    AgentRunSkillRepository, EventRepository, RunRepository, SessionRepository,
)
from agent_service.domain.services.state_machine import RunStateMachine
from agent_service.domain.ports.run_wakeup import RunWakeup
from shared.utils.time_utils import utcnow

logger = logging.getLogger(__name__)


class RunService:
    def __init__(self, sessions: SessionRepository, runs: RunRepository,
                 events: EventRepository, wakeup: RunWakeup,
                 cancel_registry: CancelRegistry, *,
                 budget_defaults: Dict[str, int],
                 default_model: str = '',
                 skills: Optional[SkillRegistry] = None,
                 approvals: Optional[ApprovalService] = None,
                 run_skills: Optional[AgentRunSkillRepository] = None):
        self._sessions = sessions
        self._runs = runs
        self._events = events
        self._wakeup = wakeup
        self._cancel_registry = cancel_registry
        self._budget_defaults = dict(budget_defaults)
        self._default_model = default_model
        self._skills = skills
        self._approvals = approvals
        # INT-2549：run 激活快照（回放以本表 + 版本表为准，不随 Skill 修改变化）
        self._run_skills = run_skills

    # ------------------------------------------------------------ sessions

    def create_session(self, *, owner_id: int, tenant_id: str,
                       title: str = '', active_skill: Optional[str] = None,
                       model: str = '',
                       permissions: Iterable[str] = ()) -> AgentSession:
        now = utcnow()
        session = AgentSession(
            id=str(uuid.uuid4()), owner_id=owner_id, tenant_id=tenant_id,
            title=(title or '')[:200],
            active_skill=self._resolve_skill(
                active_skill, permissions, owner_id=owner_id,
                tenant_id=tenant_id),
            model=(model or self._default_model or '')[:100],
            created_at=now, updated_at=now,
        )
        return self._sessions.add(session)

    def get_session(self, session_id: str, *, owner_id: int,
                    tenant_id: str) -> AgentSession:
        session = self._sessions.get_for_owner(session_id, owner_id, tenant_id)
        if session is None:
            raise SessionNotFound(session_id)
        return session

    # ------------------------------------------------------------ runs

    def create_run(self, session_id: str, *, owner_id: int, tenant_id: str,
                   message: str, idempotency_key: Optional[str] = None,
                   permissions: Iterable[str] = (),
                   active_skill: Optional[str] = None
                   ) -> Tuple[AgentRun, bool]:
        session = self.get_session(session_id, owner_id=owner_id,
                                   tenant_id=tenant_id)
        permissions = tuple(permissions or ())
        normalized_key = self._normalize_key(idempotency_key, owner_id, tenant_id)
        if normalized_key:
            existing = self._runs.get_by_idempotency_key(normalized_key)
            if existing is not None:
                return existing, False

        # 切换 Skill：显式传入则落库到会话（后续 run 继续沿用），本轮只注入
        # 该 Skill 的 L2；未传且会话已有激活 Skill 时沿用会话值。
        if active_skill:
            session.active_skill = self._resolve_skill(
                active_skill, permissions, owner_id=owner_id,
                tenant_id=tenant_id)
            updated = self._sessions.update_active_skill(
                session.id, session.active_skill)
            if updated is not None:
                session = updated
        effective_skill = session.active_skill
        effective_skill_obj = None
        if effective_skill and self._skills is not None:
            effective_skill_obj = self._skills.get_visible(
                effective_skill, permissions, owner_id=owner_id,
                tenant_id=tenant_id)
            if effective_skill_obj is None:
                # 权限变化后原 Skill 不再可见：本轮不注入 L2，也不改动会话记录
                logger.info(
                    '会话激活 Skill 当前不可见，本轮跳过 L2 session=%s skill=%s',
                    session.id, effective_skill)
                effective_skill = None

        budget = RunBudget.from_dict(self._budget_defaults)
        now = utcnow()
        run = AgentRun(
            id=str(uuid.uuid4()), session_id=session.id, owner_id=owner_id,
            tenant_id=tenant_id, status=RunStatus.QUEUED,
            model=session.model or self._default_model or '',
            budget=budget.to_dict(), idempotency_key=normalized_key,
            created_at=now, updated_at=now,
        )
        run, created = self._runs.add_if_absent(run)
        if created:
            # 发起时的用户权限与激活 Skill 写入 run_started：Loop 与断点恢复
            # 都只依据这一条事件重建上下文，切换 Skill 不影响已在跑的 run。
            self._events.append(run.id, EventType.RUN_STARTED, {
                'user_message': message,
                'session_id': session.id,
                'model': run.model,
                'budget': run.budget,
                'permissions': list(permissions),
                'active_skill': effective_skill,
            })
            # INT-2549：激活即追加版本快照；之后改 Skill 不影响本 run 回放
            self._record_skill_snapshot(run.id, effective_skill_obj)
            self._sessions.touch(session.id)
            self._wakeup.notify(run.id)
        return run, created

    def get_run(self, run_id: str, *, owner_id: int,
                tenant_id: str) -> AgentRun:
        run = self._runs.get_for_owner(run_id, owner_id, tenant_id)
        if run is None:
            raise RunNotFound(run_id)
        return run

    def cancel_run(self, run_id: str, *, owner_id: int,
                   tenant_id: str) -> AgentRun:
        run = self.get_run(run_id, owner_id=owner_id, tenant_id=tenant_id)
        if run.status.is_terminal:
            return run
        RunStateMachine.assert_transition(run.status, RunStatus.CANCELLED)
        self._cancel_registry.cancel(run.id)
        if not self._runs.request_cancel(run.id):
            # 并发下已被其它路径收口：以库内最新状态为准
            return self._runs.get(run.id) or run
        hit = self._runs.transition_if(
            run.id, {run.status}, RunStatus.CANCELLED,
            finished_at=utcnow(), error=None)
        if hit:
            # §9.2-4：已完成的写不回滚，未决提案作废（后续步骤不再执行）
            if self._approvals is not None:
                self._approvals.cancel_pending(run.id, owner_id)
            self._events.append(run.id, EventType.RUN_FINISHED, {
                'status': RunStatus.CANCELLED.value,
                'reason': 'user_cancelled',
                'error': None,
            })
            self._wakeup.notify(run.id)
        return self._runs.get(run.id) or run

    def list_approvals(self, run_id: str, *, owner_id: int,
                       tenant_id: str) -> list:
        """本 run 的审批单（待审批 + 已决历史；归属校验与 GET /runs 一致）。"""
        self.get_run(run_id, owner_id=owner_id, tenant_id=tenant_id)
        if self._approvals is None:
            return []
        return [_serialize_approval(item)
                for item in self._approvals.list_for_run(run_id)]

    def decide_approval(self, approval_id: str, *, owner_id: int,
                        tenant_id: str, decision: ApprovalDecision,
                        permissions: Iterable[str] = (),
                        confirm: bool = False
                        ) -> Tuple[object, AgentRun]:
        """审批决议：只有 run 归属者本人能决策（越权一律 404）。

        ``confirm`` 是破坏性操作的二次确认（INT-2467）：DESTRUCTIVE 工具批准
        时不带即拒绝决策，避免一次点击放行不可回滚的设备动作。
        """
        if self._approvals is None:
            raise RuntimeError('审批服务未装配')
        approval, run = self._approvals.decide(
            approval_id, owner_id=owner_id, tenant_id=tenant_id,
            decision=decision, permissions=tuple(permissions or ()),
            confirm=bool(confirm))
        return _serialize_approval(approval), run

    # ------------------------------------------------------------ internals

    def _record_skill_snapshot(self, run_id: str, skill) -> None:
        """一次激活 / 切换追加一行快照（失败不阻断 run 发起）。"""
        if self._run_skills is None or skill is None:
            return
        skill_id = skill.skill_id or f'platform:{skill.name}'
        try:
            self._run_skills.add(AgentRunSkill(
                run_id=run_id, skill_id=skill_id,
                version=str(skill.meta.version or '0'),
                content_hash=skill.content_hash or '',
                activated_at=utcnow()))
        except Exception:  # noqa: BLE001 - 快照失败不阻断 run 创建
            logger.warning('写 agent_run_skill 快照失败 run=%s skill=%s',
                           run_id, skill_id, exc_info=True)

    def _resolve_skill(self, name: Optional[str],
                       permissions: Iterable[str], *,
                       owner_id: Optional[int] = None,
                       tenant_id: Optional[str] = None) -> Optional[str]:
        """校验 Skill 存在且当前用户可见（§4.2 规则 7）；不可用直接拒绝。"""
        skill = self._resolve_skill_obj(
            name, permissions, owner_id=owner_id, tenant_id=tenant_id)
        return skill.name if skill is not None else None

    def _resolve_skill_obj(self, name: Optional[str],
                           permissions: Iterable[str], *,
                           owner_id: Optional[int] = None,
                           tenant_id: Optional[str] = None):
        """解析到领域 ``Skill``（INT-2549：快照需要 id / version / hash）。"""
        if not name:
            return None
        if self._skills is None:
            return None
        skill = self._skills.get_visible(
            name, permissions, owner_id=owner_id, tenant_id=tenant_id)
        if skill is None:
            raise SkillNotAvailable(name)
        return skill

    @staticmethod
    def _normalize_key(raw: Optional[str], owner_id: int,
                       tenant_id: str) -> Optional[str]:
        if not raw:
            return None
        # 幂等键按所有者命名空间隔离并哈希：不同用户的同名字符串互不影响，
        # 也不会因截断在同前缀的长键之间误撞（唯一索引仍是数据库兜底）
        import hashlib
        scoped = f'{tenant_id}:{owner_id}:{raw}'
        return hashlib.sha256(scoped.encode('utf-8')).hexdigest()


__all__ = ['RunService', 'InvalidRunTransition', 'RunNotFound',
           'SessionNotFound', 'SkillNotAvailable']


def _iso(value) -> Optional[str]:
    return value.isoformat() if value else None


def _serialize_approval(approval) -> dict:
    """审批单的对外结构（§10 + §9.4.1 批次字段，与前端 AgentApprovalDto 一致）。"""
    return {
        'id': approval.id,
        'run_id': approval.run_id,
        'tool_call_id': approval.tool_call_id,
        'status': approval.status.value,
        'proposal': approval.proposal or {},
        'diff': approval.diff,
        'expires_at': _iso(approval.expires_at),
        'decided_by': approval.decided_by,
        'decided_at': _iso(approval.decided_at),
        'created_at': _iso(approval.created_at),
        # INT-2571：拆单批次（未拆单时 batch_id 为空、index/total 为 1）
        'batch_id': getattr(approval, 'batch_id', None),
        'batch_index': int(getattr(approval, 'batch_index', 1) or 1),
        'batch_total': int(getattr(approval, 'batch_total', 1) or 1),
        'object_ref': getattr(approval, 'object_ref', None),
    }
