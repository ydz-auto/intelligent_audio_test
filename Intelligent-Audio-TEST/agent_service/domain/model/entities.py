# -*- coding: utf-8 -*-
"""运行底座实体（对应落地方案 §10 前七张表）。

字段口径与 infrastructure/persistence/models/agent_models.py 的 PO 一一对应；
时间统一 UTC naive（与 shared.utils.time_utils.utcnow 写库口径一致）。
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from agent_service.domain.enums import (
    CompactionLevel, EventType, RunStatus, StepStatus, ToolCallStatus, ToolRisk,
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
