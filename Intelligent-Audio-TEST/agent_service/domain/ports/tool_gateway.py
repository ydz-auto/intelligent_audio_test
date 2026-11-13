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
    enabled: bool = True


@dataclass(frozen=True)
class ToolApproval:
    """一次**已批准**的写调用凭据（由服务端按审批表构造，模型无法伪造）。

    ``approval_id`` 只作为「已审批」的事实标记：网关据此放行写路径；拒绝的
    提案永远不会被构造成本对象。
    """

    approval_id: str
    risk: ToolRisk
    proposal: Dict[str, Any]
    diff: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class ToolInvocationContext:
    """一次工具调用上下文：用户 / 租户 / run / 权限 / 幂等键。

    ``approval`` 非空表示本次调用是「审批通过后的执行」；写工具只有在
    这个凭据存在时才允许产生副作用（§5.2 硬规则 5）。
    """

    run_id: str
    session_id: str
    owner_id: int
    tenant_id: str
    step_id: Optional[str]
    permissions: tuple
    idempotency_key: str
    approval: Optional[ToolApproval] = None


class ToolGateway(ABC):
    """工具执行端口。"""

    @abstractmethod
    def all_tools(self) -> Sequence[ToolDescriptor]:
        """当前用户可见的意图级工具全集（供本轮 LLM tools 定义）。"""

    @abstractmethod
    def describe(self, names: Sequence[str]) -> Sequence[ToolDescriptor]:
        """返回本轮需要的工具描述（供 LLM tools 定义与风险判定）。"""

    def risk_of(self, name: str) -> Optional[ToolRisk]:
        """已注册工具的风险等级（含 tool_search 命中的长尾 MCP 工具）。

        两份注册表（意图工具 / MCP）都查不到时返回 ``None``，由调用方按
        「未注册」拒绝执行（fail-closed）。默认实现返回 ``None``：不认识长尾
        工具的网关不会把它们当成只读放行。
        """
        return None

    def proposal_capable(self, name: str) -> bool:
        """工具是否自带提案原语（不经通用 ``agent_approval`` 审批表）。

        当前只有 ``memory_write``（INT-2490 的文件式提案：正文不落库、审批时
        按文件摘要防覆盖）。返回 ``True`` 的工具由网关自己生成「待审批提案」，
        Loop 不为其建 ``agent_approval``；其余 WRITE / DESTRUCTIVE 工具一律
        走通用审批表（提案 → 审批 → 执行）。
        """
        return False

    def required_permissions(self, name: str,
                             arguments: Optional[Dict[str, Any]] = None
                             ) -> Optional[Sequence[str]]:
        """工具（按参数收窄后）所需权限码；``None`` 表示未注册。

        默认返回空元组：测试替身里的工具不声明权限域。
        """
        return ()

    def validate_call(self, name: str,
                      arguments: Optional[Dict[str, Any]]) -> Optional[str]:
        """执行前的实时校验（注册状态 / 参数 Schema）；返回错误文本或 ``None``。

        审批通过到真正执行之间隔了人工决策，注册表与参数校验必须重新做一遍
        （§9.4：审批后执行前重新校验权限与实时状态）。
        """
        return None

    def proposal_diff(self, name: str,
                      arguments: Optional[Dict[str, Any]]
                      ) -> Optional[Dict[str, Any]]:
        """审批人可见的变更预览（``agent_approval.diff``）；无预览返回 ``None``。

        默认无预览：具体工具在域写卡里给出字段级 diff。REST 写工具至少能
        给出「方法 + 路径 + 参数」的请求预览。
        """
        return None

    @abstractmethod
    def execute(self, call: ToolCallRequest,
                context: ToolInvocationContext) -> ToolResult:
        """执行一次工具调用。权限不足 / 未注册必须返回普通失败结果，不抛内部异常。

        写工具只有在 ``context.approval`` 非空时才允许产生副作用。
        """


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
