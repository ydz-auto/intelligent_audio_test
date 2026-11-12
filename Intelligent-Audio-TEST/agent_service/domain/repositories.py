# -*- coding: utf-8 -*-
"""领域仓储端口（domain 定义，infrastructure/persistence 实现）。

约束：
- 返回领域实体，不返回 ORM 对象；上层不感知 SQLAlchemy。
- 状态推进走 ``transition_if``（条件更新），调用方必须先过 RunStateMachine；
  仓储层保证「终态不可被覆盖」在并发下也成立。
"""
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence

from agent_service.domain.enums import RunStatus
from agent_service.domain.model.entities import (
    AgentArtifact, AgentContextSnapshot, AgentRun, AgentRunEvent, AgentSession,
    AgentStep, AgentToolCall,
)


class SessionRepository(ABC):
    @abstractmethod
    def add(self, session: AgentSession) -> AgentSession: ...

    @abstractmethod
    def get(self, session_id: str) -> Optional[AgentSession]: ...

    @abstractmethod
    def get_for_owner(self, session_id: str, owner_id: int,
                      tenant_id: str) -> Optional[AgentSession]: ...

    @abstractmethod
    def touch(self, session_id: str) -> None: ...


class RunRepository(ABC):
    @abstractmethod
    def add(self, run: AgentRun) -> AgentRun: ...

    @abstractmethod
    def add_if_absent(self, run: AgentRun) -> tuple:
        """幂等创建：idempotency_key 已存在时返回 (已有 run, False)。"""

    @abstractmethod
    def get(self, run_id: str) -> Optional[AgentRun]: ...

    @abstractmethod
    def get_for_owner(self, run_id: str, owner_id: int,
                      tenant_id: str) -> Optional[AgentRun]: ...

    @abstractmethod
    def get_by_idempotency_key(self, idempotency_key: str) -> Optional[AgentRun]: ...

    @abstractmethod
    def list_session_runs(self, session_id: str, limit: int) -> List[AgentRun]: ...

    @abstractmethod
    def list_active(self) -> List[AgentRun]: ...

    @abstractmethod
    def count_for_session(self, session_id: str) -> int: ...

    @abstractmethod
    def transition_if(self, run_id: str, from_statuses: Iterable[RunStatus],
                      target: RunStatus, *, error: Optional[str] = None,
                      started_at: Optional[datetime] = None,
                      finished_at: Optional[datetime] = None) -> bool:
        """仅当当前状态 ∈ from_statuses 时更新为 target；返回是否命中。"""

    @abstractmethod
    def update_tokens(self, run_id: str, token_in_delta: int,
                      token_out_delta: int) -> None: ...

    @abstractmethod
    def request_cancel(self, run_id: str) -> bool:
        """置 cancel_requested=true（不改状态）；返回 run 是否存在且未终态。"""


class EventRepository(ABC):
    @abstractmethod
    def append(self, run_id: str, event_type, payload: Dict[str, Any]) -> AgentRunEvent:
        """分配严格递增 sequence 并落库（并发下由唯一约束兜底）。"""

    @abstractmethod
    def list_after(self, run_id: str, sequence_exclusive: int,
                   limit: int) -> List[AgentRunEvent]: ...

    @abstractmethod
    def list_by_types(self, run_id: str, event_types: Sequence,
                      limit: int) -> List[AgentRunEvent]:
        """按事件类型定向查询，sequence 升序。"""

    @abstractmethod
    def max_sequence(self, run_id: str) -> int: ...

    @abstractmethod
    def has_type(self, run_id: str, event_type) -> bool: ...


class StepRepository(ABC):
    @abstractmethod
    def create(self, run_id: str, index: int,
               plan_snapshot: Optional[Dict[str, Any]] = None) -> AgentStep: ...

    @abstractmethod
    def finish(self, step_id: str, status, error: Optional[str] = None) -> None: ...

    @abstractmethod
    def next_index(self, run_id: str) -> int: ...

    @abstractmethod
    def fail_running(self, run_id: str, error: str) -> int: ...


class ToolCallRepository(ABC):
    @abstractmethod
    def find(self, run_id: str, tool_call_id: str) -> Optional[AgentToolCall]: ...

    @abstractmethod
    def find_by_idempotency_key(self, key: str) -> Optional[AgentToolCall]: ...

    @abstractmethod
    def create(self, tool_call: AgentToolCall) -> AgentToolCall: ...

    @abstractmethod
    def update(self, tool_call_id: str, run_id: str, **fields) -> None: ...

    @abstractmethod
    def count_for_run(self, run_id: str) -> int: ...

    @abstractmethod
    def recent(self, run_id: str, limit: int) -> List[AgentToolCall]: ...

    @abstractmethod
    def list_running(self, run_id: str) -> List[AgentToolCall]: ...


class ArtifactRepository(ABC):
    @abstractmethod
    def add(self, artifact: AgentArtifact) -> AgentArtifact: ...

    @abstractmethod
    def list_by_run(self, run_id: str) -> List[AgentArtifact]: ...


class ContextSnapshotRepository(ABC):
    @abstractmethod
    def add(self, snapshot: AgentContextSnapshot) -> AgentContextSnapshot: ...

    @abstractmethod
    def list_by_run(self, run_id: str) -> List[AgentContextSnapshot]: ...
