# -*- coding: utf-8 -*-
"""用户模型供应商端口（§6.4）。

application/run_orchestrator.py 只依赖本端口；具体取默认供应商、解密 Key、
按协议构造适配器都在 infrastructure/llm/provider_registry.py。

``ResolvedProvider`` 只承载非敏感元数据（不含 api_key）：预算按
``effective_context_window`` 计算，Key 只在 ``build_client`` 里内存解密、
用后即弃，不进入上下文、事件、日志、审计与沙箱。
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass

from agent_service.domain.enums import ContextWindowSource, LlmProtocol
from agent_service.domain.model.entities import AgentRun
from agent_service.domain.ports.llm import LlmClient


@dataclass(frozen=True)
class ResolvedProvider:
    """一次 run 解析出的供应商参数（不含密钥）。"""

    provider_id: str
    owner_id: int
    tenant_id: str
    protocol: LlmProtocol
    base_url: str
    model: str
    key_version: int
    effective_context_window: int
    context_window_source: ContextWindowSource
    catalog_context_window: int = 0
    max_output_tokens: int = 0


class LlmProviderResolver(ABC):
    """按 ``run.owner_id`` 解析默认供应商并构造模型客户端。"""

    @abstractmethod
    def resolve_for_run(self, run: AgentRun) -> ResolvedProvider:
        """取默认供应商并解析有效窗口；无可用 Key 抛 LlmProviderNotConfigured。"""

    @abstractmethod
    def build_client(self, provider: ResolvedProvider) -> LlmClient:
        """在发起模型调用时内存解密 Key，按协议构造客户端（用后即弃）。"""


@dataclass(frozen=True)
class VerifyOutcome:
    """供应商连通性验证结果（响应只含状态与错误码，不含 Key）。"""

    ok: bool
    code: str
    message: str = ''
    auth_failed: bool = False


class ProviderVerifier(ABC):
    """轻量连通性验证端口（infrastructure/llm/verifier.py 实现）。"""

    @abstractmethod
    def verify(self, *, protocol: LlmProtocol, base_url: str, model: str,
               api_key: str) -> VerifyOutcome: ...


__all__ = [
    'LlmProviderResolver', 'ProviderVerifier', 'ResolvedProvider',
    'VerifyOutcome',
]
