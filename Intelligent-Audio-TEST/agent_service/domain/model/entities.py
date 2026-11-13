# -*- coding: utf-8 -*-
"""运行底座与模型供应商实体（对应落地方案 §10 前七张表 + agent_llm_provider）。

字段口径与 infrastructure/persistence/models/agent_models.py 的 PO 一一对应；
时间统一 UTC naive（与 shared.utils.time_utils.utcnow 写库口径一致）。
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from agent_service.domain.enums import (
    ApprovalStatus, CompactionLevel, ContextWindowSource, EventType,
    LlmProtocol, ProviderStatus, RunStatus, StepStatus, ToolCallStatus,
    ToolRisk,
)


@dataclass
class AgentSession:
    id: str
    owner_id: int
    tenant_id: str
    title: str
    active_skill: Optional[str]
    model: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class AgentRun:
    id: str
    session_id: str
    owner_id: int
    tenant_id: str
    status: RunStatus
    model: str
    budget: Dict[str, Any] = field(default_factory=dict)
    token_in: int = 0
    token_out: int = 0
    idempotency_key: Optional[str] = None
    cancel_requested: bool = False
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class AgentRunEvent:
    id: str
    run_id: str
    sequence: int
    type: EventType
    payload: Dict[str, Any]
    created_at: Optional[datetime] = None


@dataclass
class AgentStep:
    id: str
    run_id: str
    index: int
    status: StepStatus
    plan_snapshot: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class AgentToolCall:
    id: str
    run_id: str
    tool_call_id: str
    tool: str
    args_hash: str
    risk: ToolRisk
    status: ToolCallStatus
    step_id: Optional[str] = None
    arguments: Optional[Dict[str, Any]] = None
    result: Optional[Dict[str, Any]] = None
    result_ref: Optional[str] = None
    latency_ms: Optional[int] = None
    permission_decision: Optional[str] = None
    result_code: Optional[str] = None
    error: Optional[str] = None
    idempotency_key: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class AgentApproval:
    """写调用审批单（§10 agent_approval，INT-2466 / INT-2571）。

    一次 tool call 对应 1..N 张单（``(run_id, tool_call_id, batch_index)``
    唯一）：单次影响 > 20 个对象时按 §9.4.1 拆成多张，同批共享 ``batch_id``，
    ``batch_index`` 1..N、``batch_total`` 相同；未拆单时 ``batch_index`` 与
    ``batch_total`` 都按 1（历史口径）。``object_ref = {kind, ids}`` 是本单
    负责的对象（完整参数留在 ``agent_tool_call.arguments``）。

    审批前不产生任何副作用；``decision_permissions`` 是审批人**决策时**的
    实时权限快照 —— 执行前用它重新校验权限（审批后权限被收回 → 执行失败），
    因此不再回读「发起 run 时」的旧权限。
    """

    id: str
    run_id: str
    tool_call_id: str
    status: ApprovalStatus
    proposal: Dict[str, Any]
    diff: Optional[Dict[str, Any]] = None
    expires_at: Optional[datetime] = None
    decided_by: Optional[int] = None
    decided_at: Optional[datetime] = None
    decision_permissions: Optional[List[str]] = None
    # INT-2571 §9.4.1：批次字段（未拆单时 batch_id 为空、index/total 为 1）
    batch_id: Optional[str] = None
    batch_index: int = 1
    batch_total: int = 1
    object_ref: Optional[Dict[str, Any]] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class AgentArtifact:
    id: str
    run_id: str
    kind: str
    uri: str
    size: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: Optional[datetime] = None


@dataclass
class AgentContextSnapshot:
    id: str
    run_id: str
    version: int
    token_count: int
    level: CompactionLevel
    dropped_ids: List[str] = field(default_factory=list)
    memo: Dict[str, Any] = field(default_factory=dict)
    created_at: Optional[datetime] = None


@dataclass
class AgentLlmProvider:
    """用户模型供应商（§10 agent_llm_provider）。

    ``api_key_ciphertext`` 只存 AES-256-GCM 密文；``api_key_mask`` 是为响应
    回显准备的脱敏串（``sk-****abcd``），读取列表时不需要解密。两者都
    不得进入事件、日志、审计与沙箱。
    """

    id: str
    owner_id: int
    tenant_id: str
    name: str
    protocol: LlmProtocol
    base_url: str
    model: str
    api_key_ciphertext: str
    api_key_mask: str
    key_version: int
    context_window: Optional[int] = None
    context_window_source: ContextWindowSource = ContextWindowSource.MODEL_DEFAULT
    is_default: bool = False
    status: ProviderStatus = ProviderStatus.ACTIVE
    last_verified_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass(frozen=True)
class LlmMessage:
    """模型消息（assembler 输出；OpenAI 兼容结构）。"""

    role: str
    content: Optional[str] = None
    tool_call_id: Optional[str] = None
    tool_calls: Tuple[Dict[str, Any], ...] = ()


@dataclass(frozen=True)
class ToolCallRequest:
    """模型返回的一次工具调用。"""

    tool_call_id: str
    name: str
    arguments: Dict[str, Any]


@dataclass(frozen=True)
class ToolResult:
    """工具执行结果（按 tool_call_id 原样回灌模型）。"""

    tool_call_id: str
    tool: str
    ok: bool
    content: str
    error_code: Optional[str] = None
