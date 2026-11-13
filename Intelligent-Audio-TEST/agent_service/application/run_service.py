# -*- coding: utf-8 -*-
"""会话 / Run 应用服务（命令侧）。

- 建会话、发起 run（支持 Idempotency-Key）、取消、查询；
- 发起 run 时先落 run_started 事件，保证 SSE 从任意时刻连上都能回放到首事件；
- 状态推进一律过 RunStateMachine + 条件更新，终态不可覆盖。
"""
import logging
import uuid
from typing import Dict, Iterable, Optional, Tuple

from agent_service.application.cancel_registry import CancelRegistry
from agent_service.application.skill_registry import SkillRegistry
from agent_service.domain.enums import EventType, RunStatus
from agent_service.domain.exceptions import (
    InvalidRunTransition, RunNotFound, SessionNotFound, SkillNotAvailable,
)
from agent_service.domain.model.budget import RunBudget
from agent_service.domain.model.entities import AgentRun, AgentSession
from agent_service.domain.repositories import (
    EventRepository, RunRepository, SessionRepository,
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
                 skills: Optional[SkillRegistry] = None):
        self._sessions = sessions
        self._runs = runs
        self._events = events
        self._wakeup = wakeup
        self._cancel_registry = cancel_registry
        self._budget_defaults = dict(budget_defaults)
        self._default_model = default_model
        self._skills = skills

    # ------------------------------------------------------------ sessions

    def create_session(self, *, owner_id: int, tenant_id: str,
                       title: str = '', active_skill: Optional[str] = None,
                       model: str = '',
                       permissions: Iterable[str] = ()) -> AgentSession:
        now = utcnow()
        session = AgentSession(
            id=str(uuid.uuid4()), owner_id=owner_id, tenant_id=tenant_id,
            title=(title or '')[:200],
            active_skill=self._resolve_skill(active_skill, permissions),
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
            session.active_skill = self._resolve_skill(active_skill, permissions)
            updated = self._sessions.update_active_skill(
                session.id, session.active_skill)
            if updated is not None:
                session = updated
        effective_skill = session.active_skill
        if effective_skill and self._skills is not None and \
                self._skills.get_visible(effective_skill, permissions) is None:
            # 权限变化后原 Skill 不再可见：本轮不注入 L2，也不改动会话记录
            logger.info('会话激活 Skill 当前不可见，本轮跳过 L2 session=%s skill=%s',
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
            self._events.append(run.id, EventType.RUN_FINISHED, {
                'status': RunStatus.CANCELLED.value,
                'reason': 'user_cancelled',
                'error': None,
            })
            self._wakeup.notify(run.id)
        return self._runs.get(run.id) or run

    def list_approvals(self, run_id: str, *, owner_id: int,
                       tenant_id: str) -> list:
        """M0 占位：审批表由 M2 建立，恒返回空列表（仍校验 run 归属）。"""
        self.get_run(run_id, owner_id=owner_id, tenant_id=tenant_id)
        return []

    # ------------------------------------------------------------ internals

    def _resolve_skill(self, name: Optional[str],
                       permissions: Iterable[str]) -> Optional[str]:
        """校验 Skill 存在且当前用户可见（§4.2 规则 7）；不可用直接拒绝。"""
        if not name:
            return None
        if self._skills is None:
            return name
        skill = self._skills.get_visible(name, permissions)
        if skill is None:
            raise SkillNotAvailable(name)
        return skill.name

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
