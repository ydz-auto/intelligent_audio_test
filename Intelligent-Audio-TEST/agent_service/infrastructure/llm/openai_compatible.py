# -*- coding: utf-8 -*-
"""OpenAI 兼容 LLM 流式适配器（§12.1）。

约束（卡面）：base_url / api_key / model 来自用户默认供应商（INT-2488，
§6.4），timeout / temperature / include_usage 来自 config；不读服务端统一
LLM Key。未配置时抛 LlmConfigurationError（服务本身仍可启动）。

流式解析口径（OpenAI ``/chat/completions`` SSE）：
- ``choices[0].delta.content`` → LlmTextDelta
- ``choices[0].delta.tool_calls``（按 index 累积，id 与 function.arguments
  分片到达）→ 轮末汇总为 LlmToolCalls
- ``usage`` → LlmUsage（provider 支持时）
- ``[DONE]`` 结束 → LlmFinished
"""
import json
import logging
from typing import Dict, Iterator, List, Optional

import httpx

from agent_service.domain.enums import LlmMessageRole
from agent_service.domain.exceptions import (
    LlmConfigurationError, LlmInvocationError, RunCancelled,
)
from agent_service.domain.model.entities import LlmMessage, ToolCallRequest
from agent_service.domain.ports.llm import (
    CancelCheck, LlmClient, LlmFinished, LlmRequest, LlmTextDelta,
    LlmToolCalls, LlmUsage,
)
from agent_service.infrastructure.llm.sanitize import sanitize_upstream_body

logger = logging.getLogger(__name__)


class OpenAICompatibleLlmClient(LlmClient):
    """同步流式客户端（在 worker 线程内消费）。"""

    def __init__(self, *, base_url: str, api_key: str, model: str,
                 timeout_seconds: float = 60.0, temperature: float = 0.2,
                 max_output_tokens: int = 0,
                 include_usage: bool = True,
                 http_transport=None):
        self._base_url = (base_url or '').strip()
        self._api_key = (api_key or '').strip()
        self._model = (model or '').strip()
        self._timeout = float(timeout_seconds or 60.0)
        self._temperature = float(temperature)
        self._max_output_tokens = int(max_output_tokens or 0)
        self._include_usage = bool(include_usage)
        self._http_transport = http_transport

    @property
    def model(self) -> str:
        return self._model

    # ------------------------------------------------------------ helpers

    def _validate(self) -> None:
        if not self._base_url:
            raise LlmConfigurationError('供应商 base_url 未配置')
        if not self._model:
            raise LlmConfigurationError('供应商 model 未配置')

    def _endpoint(self) -> str:
        if self._base_url.rstrip('/').endswith('/chat/completions'):
            return self._base_url.rstrip('/')
        return self._base_url.rstrip('/') + '/chat/completions'

    def _headers(self) -> Dict[str, str]:
        headers = {'Content-Type': 'application/json', 'Accept': 'text/event-stream'}
        if self._api_key:
            headers['Authorization'] = f'Bearer {self._api_key}'
        return headers

    def _payload(self, request: LlmRequest) -> Dict:
        payload = {
            'model': request.model or self._model,
            'messages': [self._serialize_message(m) for m in request.messages],
            'stream': True,
            'temperature': request.temperature if request.temperature is not None
            else self._temperature,
        }
        if request.tools:
            payload['tools'] = list(request.tools)
        tokens = request.max_output_tokens or self._max_output_tokens
        if tokens:
            payload['max_tokens'] = tokens
        if self._include_usage:
            payload['stream_options'] = {'include_usage': True}
        return payload

    @staticmethod
    def _serialize_message(message: LlmMessage) -> Dict:
        data = {'role': message.role}
        if message.content is not None:
            data['content'] = message.content
        if message.tool_call_id:
            data['tool_call_id'] = message.tool_call_id
        if message.tool_calls:
            data['tool_calls'] = list(message.tool_calls)
        return data

    # ------------------------------------------------------------ stream

    def stream(self, request: LlmRequest,
               cancel_check: Optional[CancelCheck] = None) -> Iterator:
        self._validate()
        timeout = httpx.Timeout(self._timeout, connect=min(10.0, self._timeout))
        kwargs = {'timeout': timeout, 'headers': self._headers()}
        if self._http_transport is not None:
            kwargs['transport'] = self._http_transport

        tool_buffers: Dict[int, Dict] = {}
        finish_reason = 'stop'
        try:
            with httpx.Client(**kwargs) as client:
                with client.stream('POST', self._endpoint(),
                                   json=self._payload(request)) as response:
                    if response.status_code >= 400:
                        body = sanitize_upstream_body(
                            response.read().decode('utf-8', errors='replace'))
                        raise LlmInvocationError(
                            f'模型上游返回 {response.status_code}: {body}',
                            code=f'LLM_HTTP_{response.status_code}',
                        )
                    for line in response.iter_lines():
                        if cancel_check is not None and cancel_check():
                            raise RunCancelled()
                        if not line:
                            continue
                        if isinstance(line, bytes):
                            line = line.decode('utf-8', errors='replace')
                        if not line.startswith('data:'):
                            continue
                        data = line[5:].strip()
                        if data == '[DONE]':
                            break
                        try:
                            chunk = json.loads(data)
                        except ValueError:
                            logger.debug('忽略无法解析的模型流片段: %s', data[:120])
                            continue
                        if cancel_check is not None and cancel_check():
                            raise RunCancelled()
                        yield from self._consume_chunk(chunk, tool_buffers)
                        choice_finish = self._finish_reason(chunk)
                        if choice_finish:
                            finish_reason = choice_finish
        except httpx.HTTPError as exc:
            raise LlmInvocationError(f'模型调用网络错误: {exc}') from exc

        if tool_buffers:
            calls: List[ToolCallRequest] = []
            for index in sorted(tool_buffers):
                buffered = tool_buffers[index]
                if not buffered.get('name'):
                    continue
                calls.append(ToolCallRequest(
                    tool_call_id=buffered.get('id') or f'call_{index}',
                    name=buffered['name'],
                    arguments=self._parse_arguments(buffered.get('arguments')),
                ))
            if calls:
                yield LlmToolCalls(calls=tuple(calls))
        yield LlmFinished(finish_reason=finish_reason)

    @staticmethod
    def _finish_reason(chunk: Dict) -> str:
        choices = chunk.get('choices') or []
        if not choices:
            return ''
        return choices[0].get('finish_reason') or ''

    def _consume_chunk(self, chunk: Dict, tool_buffers: Dict[int, Dict]) -> Iterator:
        usage = chunk.get('usage')
        if usage:
            yield LlmUsage(
                prompt_tokens=int(usage.get('prompt_tokens') or 0),
                completion_tokens=int(usage.get('completion_tokens') or 0),
            )
        choices = chunk.get('choices') or []
        if not choices:
            return
        delta = choices[0].get('delta') or {}
        content = delta.get('content')
        if content:
            yield LlmTextDelta(text=content)
        for raw in delta.get('tool_calls') or []:
            index = int(raw.get('index') or 0)
            buffered = tool_buffers.setdefault(
                index, {'id': '', 'name': '', 'arguments': ''})
            if raw.get('id'):
                buffered['id'] = raw['id']
            function = raw.get('function') or {}
            if function.get('name'):
                buffered['name'] = function['name']
            if function.get('arguments'):
                buffered['arguments'] += function['arguments']

    @staticmethod
    def _parse_arguments(raw: Optional[str]) -> Dict:
        if not raw:
            return {}
        try:
            parsed = json.loads(raw)
        except ValueError:
            logger.warning('模型返回的工具参数不是合法 JSON：%s', str(raw)[:200])
            return {}
        return parsed if isinstance(parsed, dict) else {}


__all__ = ['OpenAICompatibleLlmClient', 'LlmMessageRole']
