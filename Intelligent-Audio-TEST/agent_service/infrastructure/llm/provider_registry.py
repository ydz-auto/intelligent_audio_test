# -*- coding: utf-8 -*-
"""用户模型供应商解析（§6.4-3 / §6.4-5 / §12.1）。

- 按 ``run.owner_id``（+ tenant）取默认供应商；没有 / 已删 / 密文为空一律
  抛 LlmProviderNotConfigured，run 以 LLM_PROVIDER_NOT_CONFIGURED 失败，
  **不发起任何模型请求**，也不回退平台 Key；
- 只把非敏感元数据（协议 / base_url / model / 有效窗口）交给 application；
- Key 在 ``build_client`` 里从仓储读取并按版本解密，直接交给协议适配器，
  用后即弃：不进入上下文、事件、日志、审计与沙箱。
"""
import logging
from agent_service.domain.enums import LlmProtocol
from agent_service.domain.exceptions import (
    LlmConfigurationError, LlmProviderNotConfigured,
)
from agent_service.domain.model.entities import AgentRun
from agent_service.domain.ports.llm import LlmClient
from agent_service.domain.ports.llm_provider import (
    LlmProviderResolver, ResolvedProvider,
)
from agent_service.domain.repositories import LlmProviderRepository
from agent_service.domain.services.context_window_resolver import (
    ContextWindowResolver,
)
from agent_service.infrastructure.llm.anthropic import AnthropicLlmClient
from agent_service.infrastructure.llm.credential_store import CredentialStore
from agent_service.infrastructure.llm.openai_compatible import (
    OpenAICompatibleLlmClient,
)

logger = logging.getLogger(__name__)


class ProviderRegistry(LlmProviderResolver):
    """默认供应商解析 + 协议适配器构造。"""

    def __init__(self, *, providers: LlmProviderRepository,
                 credentials: CredentialStore,
                 windows: ContextWindowResolver,
                 timeout_seconds: float = 60.0,
                 temperature: float = 0.2,
                 include_usage: bool = True,
                 output_token_cap: int = 8192,
                 output_token_ratio: float = 0.10,
                 http_transport=None):
        self._providers = providers
        self._credentials = credentials
        self._windows = windows
        self._timeout = float(timeout_seconds or 60.0)
        self._temperature = float(temperature)
        self._include_usage = bool(include_usage)
        self._output_cap = int(output_token_cap)
        self._output_ratio = float(output_token_ratio)
        self._http_transport = http_transport

    # ------------------------------------------------------------ resolve

    def resolve_for_run(self, run: AgentRun) -> ResolvedProvider:
        record = self._providers.get_default(run.owner_id, run.tenant_id)
        if record is None or not record.api_key_ciphertext:
            # 只报事实，不提示平台 Key（平台 Key 分支未实现）
            raise LlmProviderNotConfigured(
                f'用户 {run.owner_id} 未配置可用的模型供应商')
        resolution = self._windows.resolve(
            record.protocol, record.model, record.context_window)
        output_limit = self._windows.output_token_limit(
            resolution.effective_context_window,
            cap=self._output_cap, ratio=self._output_ratio,
            protocol=record.protocol, model=record.model)
        return ResolvedProvider(
            provider_id=record.id,
            owner_id=record.owner_id,
            tenant_id=record.tenant_id,
            protocol=record.protocol,
            base_url=record.base_url,
            model=record.model,
            key_version=record.key_version,
            effective_context_window=resolution.effective_context_window,
            context_window_source=resolution.source,
            catalog_context_window=resolution.catalog_context_window or 0,
            max_output_tokens=output_limit,
        )

    def resolve_record(self, provider: ResolvedProvider):
        """再次按 owner + tenant 取供应商（防止解析后被删/被换）。"""
        return self._providers.get_for_owner(
            provider.provider_id, provider.owner_id, provider.tenant_id)

    # ------------------------------------------------------------ client

    def build_client(self, provider: ResolvedProvider) -> LlmClient:
        record = self.resolve_record(provider)
        if record is None or not record.api_key_ciphertext:
            raise LlmProviderNotConfigured('模型供应商已不存在或已删除')
        api_key = self._credentials.decrypt(
            record.api_key_ciphertext, key_version=record.key_version,
            owner_id=record.owner_id, provider_id=record.id)
        if provider.protocol is LlmProtocol.OPENAI_COMPATIBLE:
            return OpenAICompatibleLlmClient(
                base_url=provider.base_url, api_key=api_key,
                model=provider.model, timeout_seconds=self._timeout,
                temperature=self._temperature,
                max_output_tokens=provider.max_output_tokens,
                include_usage=self._include_usage,
                http_transport=self._http_transport)
        if provider.protocol is LlmProtocol.ANTHROPIC:
            return AnthropicLlmClient(
                base_url=provider.base_url, api_key=api_key,
                model=provider.model, timeout_seconds=self._timeout,
                temperature=self._temperature,
                max_output_tokens=provider.max_output_tokens,
                http_transport=self._http_transport)
        raise LlmConfigurationError(
            f'不支持的模型供应商协议: {provider.protocol}')


__all__ = ['ProviderRegistry']
