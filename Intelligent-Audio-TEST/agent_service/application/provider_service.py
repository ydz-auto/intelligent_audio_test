# -*- coding: utf-8 -*-
"""用户模型供应商应用服务（§6.4 / §11 provider API）。

- 所有操作先按 owner_id + tenant_id 归属校验（不符 / 不存在 / 已删统一 404）；
- 响应只回掩码与有效窗口，永不返回密文或明文；
- 保存时按「用户覆盖 → 目录默认 → 128k 兜底」解析窗口并落
  ``context_window_source``；非法覆盖值（越界 / 未对齐）抛
  ``InvalidContextWindow``，由接口层映射 400；
- 删除为逻辑删除：清空密文与掩码，若删的是默认项则把最早的可用项提升为
  默认，避免 run 因「无默认」直接失效。
"""
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from agent_service.domain.enums import LlmProtocol, ProviderStatus
from agent_service.domain.exceptions import (
    InvalidProviderConfiguration, ProviderNotFound,
)
from agent_service.domain.model.entities import AgentLlmProvider
from agent_service.domain.ports.llm_provider import ProviderVerifier
from agent_service.domain.repositories import LlmProviderRepository
from agent_service.domain.services.context_window_resolver import (
    ContextWindowResolver,
)
from agent_service.infrastructure.llm.credential_store import CredentialStore
from shared.utils.time_utils import utcnow

logger = logging.getLogger(__name__)

API_KEY_MAX_LEN = 512
BASE_URL_MAX_LEN = 500
MODEL_MAX_LEN = 100
NAME_MAX_LEN = 100


@dataclass(frozen=True)
class ProviderView:
    """对外可见的供应商快照（无密文 / 无明文）。"""

    id: str
    owner_id: int
    tenant_id: str
    name: str
    protocol: str
    base_url: str
    model: str
    api_key_mask: str
    context_window: Optional[int]
    context_window_source: str
    effective_context_window: int
    catalog_context_window: Optional[int]
    catalog_max_output_tokens: Optional[int]
    context_window_warning: Optional[str]
    context_window_warning_message: Optional[str]
    is_default: bool
    status: str
    last_verified_at: Optional[str]
    created_at: Optional[str]
    updated_at: Optional[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.id, 'owner_id': self.owner_id,
            'tenant_id': self.tenant_id, 'name': self.name,
            'protocol': self.protocol, 'base_url': self.base_url,
            'model': self.model, 'api_key_mask': self.api_key_mask,
            'context_window': self.context_window,
            'context_window_source': self.context_window_source,
            'effective_context_window': self.effective_context_window,
            'catalog_context_window': self.catalog_context_window,
            'catalog_max_output_tokens': self.catalog_max_output_tokens,
            'context_window_warning': self.context_window_warning,
            'context_window_warning_message':
                self.context_window_warning_message,
            'is_default': self.is_default, 'status': self.status,
            'last_verified_at': self.last_verified_at,
            'created_at': self.created_at, 'updated_at': self.updated_at,
        }


def _iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value else None


class ProviderService:
    def __init__(self, *, providers: LlmProviderRepository,
                 credentials: CredentialStore,
                 windows: ContextWindowResolver,
                 verifier: ProviderVerifier):
        self._providers = providers
        self._credentials = credentials
        self._windows = windows
        self._verifier = verifier

    # ------------------------------------------------------------ queries

    def list(self, owner_id: int, tenant_id: str) -> List[ProviderView]:
        return [self._view(row) for row in
                self._providers.list_for_owner(owner_id, tenant_id)]

    def get(self, provider_id: str, owner_id: int,
            tenant_id: str) -> ProviderView:
        return self._view(self._require(provider_id, owner_id, tenant_id))

    def catalog(self) -> Dict[str, Any]:
        return self._windows.as_catalog_dict()

    # ------------------------------------------------------------ commands

    def create(self, *, owner_id: int, tenant_id: str, name: str,
               protocol: LlmProtocol, base_url: str, model: str,
               api_key: str, context_window: Optional[int]) -> ProviderView:
        protocol = self._normalize_protocol(protocol)
        base_url = self._normalize_base_url(base_url)
        model = self._normalize_model(model)
        api_key = self._normalize_key(api_key, required=True)
        resolution = self._windows.resolve(protocol, model, context_window)
        provider_id = str(uuid.uuid4())
        secret = self._credentials.encrypt(
            api_key, owner_id=owner_id, provider_id=provider_id)
        # 默认项口径与 get_default 一致：只有「存在 ACTIVE 默认」时才另起默认，
        # 旧默认已失效（INVALID）时新建的可用供应商直接顶上，否则 run 会一直
        # 报 LLM_PROVIDER_NOT_CONFIGURED。
        is_default = self._providers.get_default(owner_id, tenant_id) is None
        if is_default:
            # 失效（INVALID）的旧默认项仍占着 is_default=True，部分唯一索引
            # (owner_id, tenant_id) WHERE is_default 会挡住新默认，先收回。
            self._providers.clear_default(owner_id, tenant_id)
        now = utcnow()
        provider = AgentLlmProvider(
            id=provider_id, owner_id=owner_id, tenant_id=tenant_id,
            name=self._normalize_name(name, model), protocol=protocol,
            base_url=base_url, model=model,
            api_key_ciphertext=secret.ciphertext,
            api_key_mask=CredentialStore.mask(api_key),
            key_version=secret.key_version,
            context_window=context_window,
            context_window_source=resolution.source,
            is_default=is_default, status=ProviderStatus.ACTIVE,
            created_at=now, updated_at=now,
        )
        created = self._providers.add(provider)
        if is_default:
            # 同 owner/tenant 唯一默认的数据库兜底之外，显式收口一次
            self._providers.set_default(created.id, owner_id, tenant_id)
            created = self._providers.get_for_owner(
                created.id, owner_id, tenant_id) or created
        return self._view(created)

    def update(self, provider_id: str, owner_id: int, tenant_id: str,
               fields: Dict[str, Any]) -> ProviderView:
        provider = self._require(provider_id, owner_id, tenant_id)
        changes: Dict[str, Any] = {}
        if 'name' in fields and fields['name'] is not None:
            changes['name'] = self._normalize_name(
                fields['name'], provider.model)
        if 'protocol' in fields and fields['protocol'] is not None:
            changes['protocol'] = self._normalize_protocol(fields['protocol'])
        if 'base_url' in fields and fields['base_url'] is not None:
            changes['base_url'] = self._normalize_base_url(fields['base_url'])
        if 'model' in fields and fields['model'] is not None:
            changes['model'] = self._normalize_model(fields['model'])

        connection_changed = any(
            name in changes for name in ('protocol', 'base_url', 'model'))

        api_key = fields.get('api_key')
        if api_key:
            plaintext = self._normalize_key(api_key, required=True)
            secret = self._credentials.encrypt(
                plaintext, owner_id=owner_id, provider_id=provider_id)
            changes.update({
                'api_key_ciphertext': secret.ciphertext,
                'api_key_mask': CredentialStore.mask(plaintext),
                'key_version': secret.key_version,
            })
            connection_changed = True

        if 'context_window' in fields:
            changes['context_window'] = fields['context_window']

        if connection_changed:
            changes['status'] = ProviderStatus.ACTIVE
            changes['last_verified_at'] = None

        protocol = changes.get('protocol', provider.protocol)
        model = changes.get('model', provider.model)
        override = (changes['context_window']
                    if 'context_window' in changes else provider.context_window)
        resolution = self._windows.resolve(protocol, model, override)
        changes['context_window_source'] = resolution.source

        self._providers.update(provider_id, owner_id, tenant_id, **changes)
        return self.get(provider_id, owner_id, tenant_id)

    def delete(self, provider_id: str, owner_id: int, tenant_id: str) -> None:
        provider = self._require(provider_id, owner_id, tenant_id)
        self._providers.update(
            provider_id, owner_id, tenant_id,
            api_key_ciphertext='', api_key_mask='',
            is_default=False, status=ProviderStatus.DELETED)
        if provider.is_default:
            candidate = self._providers.find_first_active(
                owner_id, tenant_id, exclude_id=provider_id)
            if candidate is not None:
                self._providers.set_default(candidate.id, owner_id, tenant_id)

    def set_default(self, provider_id: str, owner_id: int,
                    tenant_id: str) -> ProviderView:
        self._require(provider_id, owner_id, tenant_id)
        if not self._providers.set_default(provider_id, owner_id, tenant_id):
            raise ProviderNotFound(provider_id)
        return self.get(provider_id, owner_id, tenant_id)

    def verify(self, provider_id: str, owner_id: int,
               tenant_id: str) -> Dict[str, Any]:
        provider = self._require(provider_id, owner_id, tenant_id)
        if not provider.api_key_ciphertext:
            outcome_ok, code, message = False, 'PROVIDER_KEY_MISSING', '密钥缺失'
        else:
            api_key = self._credentials.decrypt(
                provider.api_key_ciphertext,
                key_version=provider.key_version, owner_id=owner_id,
                provider_id=provider_id)
            outcome = self._verifier.verify(
                protocol=provider.protocol, base_url=provider.base_url,
                model=provider.model, api_key=api_key)
            outcome_ok, code, message = outcome.ok, outcome.code, outcome.message
            if outcome.ok:
                # 一次瞬时 401 之后 verify 明确成功必须恢复 ACTIVE，
                # 否则 get_default 永远取不到它、run 一直报未配置。
                self._providers.update(
                    provider_id, owner_id, tenant_id,
                    status=ProviderStatus.ACTIVE)
            elif outcome.auth_failed:
                self._providers.update(
                    provider_id, owner_id, tenant_id,
                    status=ProviderStatus.INVALID)
        self._providers.update(provider_id, owner_id, tenant_id,
                               last_verified_at=utcnow())
        current = self._require(provider_id, owner_id, tenant_id)
        return {
            'provider_id': provider_id,
            'ok': outcome_ok,
            'code': code,
            'message': message,
            'status': current.status.value,
            'last_verified_at': _iso(current.last_verified_at),
        }

    # ------------------------------------------------------------ helpers

    def _require(self, provider_id: str, owner_id: int,
                 tenant_id: str) -> AgentLlmProvider:
        provider = self._providers.get_for_owner(
            provider_id, owner_id, tenant_id)
        if provider is None:
            raise ProviderNotFound(provider_id)
        return provider

    def _view(self, provider: AgentLlmProvider) -> ProviderView:
        resolution = self._windows.resolve(
            provider.protocol, provider.model, provider.context_window)
        return ProviderView(
            id=provider.id, owner_id=provider.owner_id,
            tenant_id=provider.tenant_id, name=provider.name,
            protocol=provider.protocol.value, base_url=provider.base_url,
            model=provider.model, api_key_mask=provider.api_key_mask,
            context_window=provider.context_window,
            context_window_source=resolution.source.value,
            effective_context_window=resolution.effective_context_window,
            catalog_context_window=resolution.catalog_context_window,
            catalog_max_output_tokens=resolution.catalog_max_output_tokens,
            context_window_warning=resolution.warning,
            context_window_warning_message=resolution.warning_message,
            is_default=provider.is_default,
            status=provider.status.value,
            last_verified_at=_iso(provider.last_verified_at),
            created_at=_iso(provider.created_at),
            updated_at=_iso(provider.updated_at),
        )

    @staticmethod
    def _normalize_protocol(protocol) -> LlmProtocol:
        try:
            return protocol if isinstance(protocol, LlmProtocol) \
                else LlmProtocol(str(protocol))
        except ValueError as exc:
            raise InvalidProviderConfiguration(
                f'不支持的协议: {protocol}') from exc

    @staticmethod
    def _normalize_base_url(base_url: str) -> str:
        value = (base_url or '').strip()
        if not value:
            raise InvalidProviderConfiguration('base_url 不能为空')
        parsed = urlparse(value)
        if parsed.scheme not in ('http', 'https') or not parsed.netloc:
            raise InvalidProviderConfiguration('base_url 必须是 http(s) 地址')
        if len(value) > BASE_URL_MAX_LEN:
            raise InvalidProviderConfiguration(
                f'base_url 不能超过 {BASE_URL_MAX_LEN} 字符')
        return value.rstrip('/')

    @staticmethod
    def _normalize_model(model: str) -> str:
        value = (model or '').strip()
        if not value:
            raise InvalidProviderConfiguration('model 不能为空')
        if len(value) > MODEL_MAX_LEN:
            raise InvalidProviderConfiguration(
                f'model 不能超过 {MODEL_MAX_LEN} 字符')
        return value

    @staticmethod
    def _normalize_name(name: Optional[str], model: str) -> str:
        value = (name or '').strip() or model
        if len(value) > NAME_MAX_LEN:
            raise InvalidProviderConfiguration(
                f'name 不能超过 {NAME_MAX_LEN} 字符')
        return value

    @staticmethod
    def _normalize_key(api_key: str, *, required: bool) -> str:
        value = (api_key or '').strip()
        if required and not value:
            raise InvalidProviderConfiguration('api_key 不能为空')
        if len(value) > API_KEY_MAX_LEN:
            raise InvalidProviderConfiguration(
                f'api_key 不能超过 {API_KEY_MAX_LEN} 字符')
        return value


__all__ = ['ProviderService', 'ProviderView']
