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

from agent_service.domain.enums import (
    ApprovalStatus, RunStatus, SkillScope, SkillStatus,
)
from agent_service.domain.model.agent_skill import (
    AgentRunSkill, AgentSkill, AgentSkillReview, AgentSkillVersion,
)
from agent_service.domain.model.entities import (
    AgentApproval, AgentArtifact, AgentContextSnapshot, AgentLlmProvider,
    AgentRun, AgentRunEvent, AgentSession, AgentStep, AgentToolCall,
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

    @abstractmethod
    def update_active_skill(self, session_id: str,
                            active_skill: Optional[str]
                            ) -> Optional[AgentSession]:
        """落库会话当前激活的 Skill（§10 agent_session.active_skill）。

        返回更新后的会话；会话不存在时返回 None。
        """


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
    def list_by_run(self, run_id: str) -> List[AgentToolCall]: ...

    @abstractmethod
    def list_running(self, run_id: str) -> List[AgentToolCall]: ...

    @abstractmethod
    def claim(self, run_id: str, tool_call_id: str,
              from_statuses: Sequence, target) -> bool:
        """条件迁移工具调用状态（并发下只有一个执行者能抢到）。

        返回是否命中；用于审批通过后「只执行一次」的 DB 级互斥。
        """


class ApprovalRepository(ABC):
    """写调用审批单仓储（§10 agent_approval，INT-2466 / INT-2571）。

    决策 / 过期一律走条件更新（``WHERE status='PENDING'``），把并发审批的
    唯一性交给数据库，不依赖进程内锁。一次 tool call 可以有 1..N 张单
    （§9.4.1 拆单），按 ``batch_index`` 排序读取。
    """

    @abstractmethod
    def add(self, approval: AgentApproval) -> AgentApproval:
        """插入审批单；(run_id, tool_call_id, batch_index) 已存在时返回已有行。"""

    @abstractmethod
    def get(self, approval_id: str) -> Optional[AgentApproval]: ...

    @abstractmethod
    def list_for_tool_call(self, run_id: str,
                           tool_call_id: str) -> List[AgentApproval]:
        """一次 tool call 的全部审批单（按 ``batch_index`` 升序）。"""

    @abstractmethod
    def list_by_run(self, run_id: str) -> List[AgentApproval]: ...

    @abstractmethod
    def list_open_by_run(self, run_id: str) -> List[AgentApproval]: ...

    @abstractmethod
    def decide(self, approval_id: str, target: ApprovalStatus, *,
               decided_by: int, decided_at: datetime,
               permissions: Sequence[str],
               now: datetime) -> bool:
        """PENDING → target；已过期（expires_at ≤ now）时不算命中。"""

    @abstractmethod
    def expire(self, approval_id: str, now: datetime) -> bool:
        """PENDING 且已过期 → EXPIRED；返回是否命中。"""

    @abstractmethod
    def settle_batch(self, run_id: str, tool_call_id: str,
                     target: ApprovalStatus, *,
                     decided_by: Optional[int] = None,
                     decided_at: Optional[datetime] = None,
                     now: datetime) -> int:
        """把同一次调用剩余的 PENDING 单整批收口（拒绝 / 过期，§9.4.1）。

        返回命中的单数。``REJECTED`` 记 ``decided_by`` / ``decided_at``；
        ``EXPIRED`` 不记决策人（系统结算）。
        """

    @abstractmethod
    def list_due(self, now: datetime, limit: int) -> List[AgentApproval]:
        """所有已过期的 PENDING 审批单（启动 / 恢复时的兜底扫描）。"""


class ArtifactRepository(ABC):
    @abstractmethod
    def add(self, artifact: AgentArtifact) -> AgentArtifact: ...

    @abstractmethod
    def update(self, artifact_id: str, *, size: Optional[int] = None,
               metadata: Optional[Dict[str, Any]] = None,
               uri: Optional[str] = None) -> bool:
        """更新已登记产物的体积 / 元数据（不新增行）。

        同一 URI 被覆盖写时（例如每一步都重写的 ``ui_trace.json``），登记
        必须跟着最终内容走，否则 ``agent_artifact`` 描述的是首版而不是落盘
        的内容。返回是否命中该产物。
        """

    @abstractmethod
    def list_by_run(self, run_id: str) -> List[AgentArtifact]: ...


class ContextSnapshotRepository(ABC):
    @abstractmethod
    def add(self, snapshot: AgentContextSnapshot) -> AgentContextSnapshot: ...

    @abstractmethod
    def list_by_run(self, run_id: str) -> List[AgentContextSnapshot]: ...


class LlmProviderRepository(ABC):
    """用户模型供应商仓储：所有查询强制带 owner_id（+ tenant_id）。"""

    @abstractmethod
    def add(self, provider: AgentLlmProvider) -> AgentLlmProvider: ...

    @abstractmethod
    def get_for_owner(self, provider_id: str, owner_id: int,
                      tenant_id: str) -> Optional[AgentLlmProvider]:
        """返回未删除的供应商；不存在 / 非本人 / 已删除一律 None。"""

    @abstractmethod
    def list_for_owner(self, owner_id: int,
                       tenant_id: str) -> List[AgentLlmProvider]: ...

    @abstractmethod
    def get_default(self, owner_id: int,
                    tenant_id: str) -> Optional[AgentLlmProvider]:
        """取默认供应商（ACTIVE 且 is_default），没有则 None。"""

    @abstractmethod
    def update(self, provider_id: str, owner_id: int, tenant_id: str,
               **fields) -> bool: ...

    @abstractmethod
    def clear_default(self, owner_id: int, tenant_id: str,
                      keep_id: Optional[str] = None) -> None: ...

    @abstractmethod
    def set_default(self, provider_id: str, owner_id: int,
                    tenant_id: str) -> bool:
        """把指定供应商置为默认（同一用户/租户唯一默认）。"""

    @abstractmethod
    def find_first_active(self, owner_id: int, tenant_id: str,
                          exclude_id: Optional[str] = None
                          ) -> Optional[AgentLlmProvider]: ...


class AgentSkillRepository(ABC):
    """自定义 Skill（TENANT / USER 层）仓储（INT-2549 §4.4 / §10）。

    唯一性由数据库局部唯一索引兜底（``(scope, owner_id, name)`` /
    ``(scope, tenant_id, name)``）；仓储层不静默覆盖，冲突由应用层判定。
    正文只在版本表，当前版本用 ``agent_skill.version`` 指针引用。
    """

    @abstractmethod
    def add(self, skill: AgentSkill) -> AgentSkill: ...

    @abstractmethod
    def get(self, skill_id: str) -> Optional[AgentSkill]: ...

    @abstractmethod
    def find_by_name(self, scope: SkillScope, name: str, *,
                     owner_id: Optional[int] = None,
                     tenant_id: Optional[str] = None
                     ) -> Optional[AgentSkill]:
        """同作用域同名查找（冲突判定用；含 DISABLED 行，删除后不占名）。"""

    @abstractmethod
    def list_visible(self, *, tenant_id: str, owner_id: int,
                     scopes: Optional[Sequence[SkillScope]] = None,
                     statuses: Optional[Sequence[SkillStatus]] = None
                     ) -> List[AgentSkill]:
        """本人可见：``USER.owner_id=本人`` + ``TENANT.tenant_id=本租户``。"""

    @abstractmethod
    def list_active(self) -> List[AgentSkill]:
        """全部 ``ACTIVE`` 自定义行（供 CompositeSkillRepository 合并去重）。"""

    @abstractmethod
    def update(self, skill_id: str, **fields) -> bool:
        """条件更新（含 ``version`` 指针 +1）；返回是否命中。"""

    @abstractmethod
    def transition_if(self, skill_id: str,
                      from_statuses: Iterable[SkillStatus],
                      target: SkillStatus) -> bool:
        """仅当当前状态 ∈ ``from_statuses`` 时迁移到 ``target``（INT-2551）。

        审核流的状态推进一律走条件更新：两个管理员同时批准同一版本时，
        数据库层只有一次命中，另一次拿到 ``False`` 按状态冲突处理，不依赖
        进程内锁。
        """

    @abstractmethod
    def apply_edit(self, skill_id: str, *, from_status: SkillStatus,
                   row_fields: Dict[str, Any],
                   version: AgentSkillVersion,
                   review: AgentSkillReview) -> bool:
        """一个事务内完成编辑提交：迁移 + 版本行 + 当前行 + 审计（INT-2594）。

        ``row_fields`` 是当前行的新值（含 ``status``）；仓储以
        ``WHERE id=? AND status=from_status`` 做条件更新，未命中（状态已被
        并发请求改走）时返回 ``False`` 且一条都不写。命中后写入版本快照与
        ``EDIT`` 审计行，三步同生同灭 —— 任一步失败整体回滚，不会留下
        「已发布版本被改成 DRAFT 却没有版本 / 审计」的中间态，也不会留下
        孤儿版本号挡住后续重试。
        """

    @abstractmethod
    def delete(self, skill_id: str) -> bool:
        """删除当前行；版本行保留（历史 run 依赖其回放）。"""

    @abstractmethod
    def add_version(self, version: AgentSkillVersion) -> AgentSkillVersion: ...

    @abstractmethod
    def list_versions(self, skill_id: str) -> List[AgentSkillVersion]: ...

    @abstractmethod
    def get_version(self, skill_id: str,
                    version: str) -> Optional[AgentSkillVersion]: ...


class AgentRunSkillRepository(ABC):
    """run 激活快照仓储（INT-2549）：一次激活 / 切换追加一行，不覆盖。"""

    @abstractmethod
    def add(self, snapshot: AgentRunSkill) -> AgentRunSkill: ...

    @abstractmethod
    def list_by_run(self, run_id: str) -> List[AgentRunSkill]: ...


class SkillReviewRepository(ABC):
    """``agent_skill_review`` 审计仓储（INT-2551）。

    只追加、不更新、不删除：审批链是审计事实，任何「改历史」的写入口都
    不允许存在。``(skill_id, version)`` 索引服务单版本追溯，
    ``(tenant_id, status_to)`` 索引服务管理员待审队列。
    """

    @abstractmethod
    def add(self, review: AgentSkillReview) -> AgentSkillReview: ...

    @abstractmethod
    def list_for_skill(self, skill_id: str) -> List[AgentSkillReview]:
        """单个 Skill 的完整审批链（``created_at`` 升序）。"""

    @abstractmethod
    def list_current(self, status: SkillStatus, *, tenant_id: str,
                     limit: int = 100) -> List[AgentSkillReview]:
        """本租户「当前处在 ``status``」的 Skill 最近一条迁移记录。

        队列口径 =「Skill 此刻的状态」+「把它带到该状态的那条记录」：
        仓储按 ``tenant_id`` + ``skill.status`` join 过滤，再按
        ``created_at`` 降序返回；同一条 Skill 的多条历史记录由调用方去重。
        """
