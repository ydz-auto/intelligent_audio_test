# -*- coding: utf-8 -*-
"""供应商轻量连通性验证（§6.4 / §11 verify 端点）。

只使用「列模型 / 最小请求」判定能否连通，不生成可计费的长回复：
- OPENAI_COMPATIBLE：``GET {base_url}/models``（Bearer）；
- ANTHROPIC：``POST {base_url}/v1/messages``，max_tokens=1（x-api-key）。

返回明确失败码（``PROVIDER_UNREACHABLE`` / ``PROVIDER_AUTH_FAILED`` /
``PROVIDER_HTTP_ERROR``），message 只带状态码等非敏感信息，绝不回显 Key
或上游响应正文。
"""
import logging
from typing import Dict

import httpx

from agent_service.domain.enums import LlmProtocol
from agent_service.domain.ports.llm_provider import ProviderVerifier, VerifyOutcome
from agent_service.infrastructure.llm.anthropic import ANTHROPIC_VERSION

logger = logging.getLogger(__name__)

VERIFIED = 'PROVIDER_VERIFIED'
UNREACHABLE = 'PROVIDER_UNREACHABLE'
AUTH_FAILED = 'PROVIDER_AUTH_FAILED'
HTTP_ERROR = 'PROVIDER_HTTP_ERROR'
UNSUPPORTED_PROTOCOL = 'PROVIDER_PROTOCOL_UNSUPPORTED'


class HttpProviderVerifier(ProviderVerifier):
    def __init__(self, *, timeout_seconds: float = 10.0,
                 http_transport=None):
        self._timeout = float(timeout_seconds or 10.0)
        self._http_transport = http_transport

    def verify(self, *, protocol: LlmProtocol, base_url: str, model: str,
               api_key: str) -> VerifyOutcome:
        base = (base_url or '').strip().rstrip('/')
        if not base:
            return VerifyOutcome(
                ok=False, code=UNREACHABLE, message='供应商地址为空')
        kwargs = {'timeout': httpx.Timeout(self._timeout,
                                           connect=min(5.0, self._timeout))}
        if self._http_transport is not None:
            kwargs['transport'] = self._http_transport
        try:
            with httpx.Client(**kwargs) as client:
                if protocol is LlmProtocol.OPENAI_COMPATIBLE:
                    response = client.get(
                        self._openai_models_url(base),
                        headers=self._openai_headers(api_key))
                elif protocol is LlmProtocol.ANTHROPIC:
                    response = client.post(
                        self._anthropic_url(base),
                        headers=self._anthropic_headers(api_key),
                        json=self._anthropic_payload(model))
                else:
                    return VerifyOutcome(
                        ok=False, code=UNSUPPORTED_PROTOCOL,
                        message=f'不支持的协议: {protocol}')
        except httpx.HTTPError as exc:
            logger.info('供应商连通性验证失败 provider_url=%s: %s', base,
                        type(exc).__name__)
            return VerifyOutcome(
                ok=False, code=UNREACHABLE,
                message=f'无法连接供应商: {type(exc).__name__}')
        if response.status_code < 400:
            return VerifyOutcome(ok=True, code=VERIFIED)
        if response.status_code in (401, 403):
            return VerifyOutcome(
                ok=False, code=AUTH_FAILED,
                message=f'鉴权失败（HTTP {response.status_code}）',
                auth_failed=True)
        return VerifyOutcome(
            ok=False, code=HTTP_ERROR,
            message=f'上游返回 HTTP {response.status_code}')

    # ------------------------------------------------------------ helpers

    @staticmethod
    def _openai_models_url(base: str) -> str:
        if base.endswith('/chat/completions'):
            base = base[: -len('/chat/completions')]
        if base.endswith('/models'):
            return base
        if base.endswith('/v1'):
            return base + '/models'
        return base + '/v1/models'

    @staticmethod
    def _openai_headers(api_key: str) -> Dict[str, str]:
        headers = {'Accept': 'application/json'}
        if api_key:
            headers['Authorization'] = f'Bearer {api_key}'
        return headers

    @staticmethod
    def _anthropic_url(base: str) -> str:
        if base.endswith('/messages'):
            return base
        if base.endswith('/v1'):
            return base + '/messages'
        return base + '/v1/messages'

    @staticmethod
    def _anthropic_headers(api_key: str) -> Dict[str, str]:
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'anthropic-version': ANTHROPIC_VERSION,
        }
        if api_key:
            headers['x-api-key'] = api_key
        return headers

    @staticmethod
    def _anthropic_payload(model: str) -> Dict:
        return {
            'model': model or '',
            'max_tokens': 1,
            'messages': [{'role': 'user', 'content': 'ping'}],
        }


__all__ = [
    'AUTH_FAILED', 'HTTP_ERROR', 'HttpProviderVerifier', 'UNREACHABLE',
    'UNSUPPORTED_PROTOCOL', 'VERIFIED',
]
