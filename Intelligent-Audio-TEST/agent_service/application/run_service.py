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
from agent_service.application.auto_mode import (
    AutoControlState, AutoSettings, consecutive_failures,
)
from agent_service.application.cancel_registry import CancelRegistry
from agent_service.application.skill_registry import SkillRegistry
from agent_service.domain.enums import (
    ApprovalStatus, ApprovalDecision, EventType, RunMode, RunStatus,
)
from agent_service.domain.exceptions import (
    InvalidBudgetOverride, InvalidRunMode, InvalidRunTransition, RunNotPaused,
    RunNotFound, SessionNotFound, SkillNotAvailable,
)
from agent_service.domain.model.agent_skill import AgentRunSkill
from agent_service.domain.model.budget import RunBudget
from agent_service.domain.model.entities import AgentRun, AgentSession
from agent_service.domain.repositories import (
    AgentRunSkillRepository, EventRepository, RunRepository, SessionRepository,
    ToolCallRepository,
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
                 auto_budget_defaults: Optional[Dict[str, int]] = None,
                 default_model: str = '',
                 skills: Optional[SkillRegistry] = None,
                 approvals: Optional[ApprovalService] = None,
                 run_skills: Optional[AgentRunSkillRepository] = None,
                 auto_settings: Optional[AutoSettings] = None,
                 tool_calls: Optional[ToolCallRepository] = None,
                 event_scan_limit: int = 10000):
        self._sessions = sessions
        self._runs = runs
        self._events = events
        self._wakeup = wakeup
        self._cancel_registry = cancel_registry
        self._budget_defaults = dict(budget_defaults)
        # INT-2474：Auto 预算默认值（§9.4：60 / 120 / 4×W / 30min / 20MB）
        self._auto_budget_defaults = dict(
            auto_budget_defaults or budget_defaults)
        self._auto_settings = auto_settings or AutoSettings()
        # INT-2474：「继续」时要按同一口径记录连续失败数（暂停不重复触发）
        self._tool_calls = tool_calls
        self._event_scan_limit = max(1, int(event_scan_limit))
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
                   active_skill: Optional[str] = None,
                   mode: str = RunMode.CHAT.value,
                   budget_overrides: Optional[Dict[str, int]] = None
                   ) -> Tuple[AgentRun, bool]:
        session = self.get_session(session_id, owner_id=owner_id,
                                   tenant_id=tenant_id)
        permissions = tuple(permissions or ())
        normalized_key = self._normalize_key(idempotency_key, owner_id, tenant_id)
        if normalized_key:
            existing = self._runs.get_by_idempotency_key(normalized_key)
            if existing is not None:
                return existing, False
        run_mode = self._normalize_mode(mode)

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

        budget = self._build_budget(run_mode, budget_overrides)
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
            payload = {
                'user_message': message,
                'session_id': session.id,
                'model': run.model,
                'budget': run.budget,
                'permissions': list(permissions),
                'active_skill': effective_skill,
                'mode': run_mode.value,
            }
            if run_mode.is_auto:
                # 「启动 Auto 前必须展示计划与预算」：暂停规则随 run_started
                # 下发，前端（INT-2477）在开跑前即可展示；计划见首条
                # auto_step 事件。
                payload['pause_policy'] = {
                    'budget_ratio': self._auto_settings.pause_budget_ratio,
                    'consecutive_failures': (
                        self._auto_settings.pause_consecutive_failures),
                }
            self._events.append(run.id, EventType.RUN_STARTED, payload)
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

    def run_mode(self, run_id: str) -> RunMode:
        """从 run_started 取本次 run 的模式（§9.3；缺省 chat）。"""
        try:
            events = self._events.list_by_types(
                run_id, (EventType.RUN_STARTED,), 1)
        except Exception:  # noqa: BLE001 - 读取失败按默认模式
            logger.warning('读取 run_started 失败 run=%s', run_id,
                           exc_info=True)
            return RunMode.CHAT
        if not events:
            return RunMode.CHAT
        raw = str((events[0].payload or {}).get('mode') or '').strip().lower()
        try:
            return RunMode(raw)
        except ValueError:
            return RunMode.CHAT

    def resume_run(self, run_id: str, *, owner_id: int,
                   tenant_id: str) -> AgentRun:
        """Auto 暂停后「继续」（§9.4）。

        只接受**暂停态**的 Auto run，且必须没有待审批提案：
        - 有待审批提案 → 409，让用户先逐张决策（审批决策本身会唤醒 run）；
        - 已终态 / 正在执行 / 从未暂停 → 409，不制造第二条执行链。
        继续时落一条 ``run_resumed`` 事件（记录当时的连续失败数与预算确认），
        Loop 重启后按这条事实恢复，不依赖进程内标志。
        """
        run = self.get_run(run_id, owner_id=owner_id, tenant_id=tenant_id)
        if run.status.is_terminal:
            raise RunNotPaused('run 已结束，无法继续')
        if not self.run_mode(run_id).is_auto:
            raise RunNotPaused('只有 Auto 模式的任务支持继续')
        if run.status is not RunStatus.WAITING_APPROVAL:
            raise RunNotPaused('run 当前不在暂停态（可能正在执行或已继续）')
        if self._pending_approvals(run_id):
            raise RunNotPaused('仍有待审批提案：请先处理审批单，再继续')
        control = self._control_state(run_id)
        if not control.paused:
            raise RunNotPaused('run 没有暂停记录（可能已继续或正在执行）')
        if not self._runs.transition_if(
                run_id, {RunStatus.WAITING_APPROVAL}, RunStatus.RUNNING):
            raise RunNotPaused('run 状态已变化（并发继续或已收口）')
        failures = (
            consecutive_failures(
                self._tool_calls, run_id,
                max(1, int(self._auto_settings.max_consecutive_failures)))
            if self._tool_calls is not None else 0)
        self._events.append(run_id, EventType.RUN_RESUMED, {
            'resumed_by': owner_id,
            'pause_reason': control.pause_reason,
            'acked_budget_pause': True,
            'consecutive_failures': failures,
            'budget': dict(run.budget or {}),
            'token_in': run.token_in,
            'token_out': run.token_out,
        })
        self._wakeup.notify(run_id)
        return self._runs.get(run_id) or run

    def _pending_approvals(self, run_id: str) -> bool:
        if self._approvals is None:
            return False
        return any(item.status is ApprovalStatus.PENDING
                   for item in self._approvals.list_for_run(run_id))

    def _control_state(self, run_id: str) -> AutoControlState:
        try:
            events = self._events.list_after(run_id, 0, self._event_scan_limit)
        except Exception:  # noqa: BLE001 - 读取失败按未暂停
            logger.warning('读取 Auto 控制事件失败 run=%s', run_id,
                           exc_info=True)
            return AutoControlState()
        return AutoControlState.from_events(events)

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

    @staticmethod
    def _normalize_mode(raw: Optional[str]) -> RunMode:
        """运行模式归一（``chat`` / ``auto``，大小写不敏感）。"""
        value = str(raw or RunMode.CHAT.value).strip().lower()
        try:
            return RunMode(value)
        except ValueError:
            raise InvalidRunMode(str(raw))

    def _build_budget(self, mode: RunMode,
                      overrides: Optional[Dict[str, int]]) -> RunBudget:
        """按模式取服务端预算，再按请求侧值**收紧**（§9.4 不可放宽）。"""
        defaults = (self._auto_budget_defaults if mode.is_auto
                    else self._budget_defaults)
        try:
            return RunBudget.from_dict(defaults).tightened(overrides)
        except ValueError as exc:
            raise InvalidBudgetOverride(str(exc))

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
