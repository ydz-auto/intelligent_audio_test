# -*- coding: utf-8 -*-
"""工具网关端口（§6.3 权限 / 审计留在网关与 harness）。

M0 不实现具体工具（m0-03），但 Loop 必须能按 tool_call_id 回灌结果，
因此这里先固定执行契约：风险等级、沙箱层级、权限决策、结果结构。
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Optional, Sequence

from agent_service.domain.enums import SandboxTier, ToolRisk
from agent_service.domain.model.entities import ToolCallRequest, ToolResult


@dataclass(frozen=True)
class ToolDescriptor:
    """工具注册表条目（意图级工具，§6.1）。"""

    name: str
    description: str
    parameters: Dict[str, Any]
    # 风险等级必填：不允许缺省成 READ（INT-2487：缺省会变成写操作 fail-open）
    risk: ToolRisk
    sandbox_tier: SandboxTier = SandboxTier.T0_NONE
    permissions: tuple = ()


@dataclass(frozen=True)
class ToolInvocationContext:
    """一次工具调用上下文：用户 / 租户 / run / 权限 / 幂等键。"""

    run_id: str
    session_id: str
    owner_id: int
    tenant_id: str
    step_id: Optional[str]
    permissions: tuple
    idempotency_key: str


class ToolGateway(ABC):
    """工具执行端口。"""

    @abstractmethod
    def all_tools(self) -> Sequence[ToolDescriptor]:
        """当前用户可见的意图级工具全集（供本轮 LLM tools 定义）。"""

    @abstractmethod
    def describe(self, names: Sequence[str]) -> Sequence[ToolDescriptor]:
        """返回本轮需要的工具描述（供 LLM tools 定义与风险判定）。"""

    @abstractmethod
    def execute(self, call: ToolCallRequest,
                context: ToolInvocationContext) -> ToolResult:
        """执行一次工具调用。权限不足 / 未注册必须返回普通失败结果，不抛内部异常。"""


class NoopToolGateway(ToolGateway):
    """M0 默认实现：没有已注册工具（工具层由 m0-03 落地）。"""

    def all_tools(self) -> Sequence[ToolDescriptor]:
        return ()

    def describe(self, names: Sequence[str]) -> Sequence[ToolDescriptor]:
        return ()

    def execute(self, call: ToolCallRequest,
                context: ToolInvocationContext) -> ToolResult:
        return ToolResult(
            tool_call_id=call.tool_call_id,
            tool=call.name,
            ok=False,
            content=f'工具 {call.name} 尚未注册（M0 工具层未落地）',
            error_code='TOOL_NOT_REGISTERED',
        )
