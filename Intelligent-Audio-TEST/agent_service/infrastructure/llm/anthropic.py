# -*- coding: utf-8 -*-
"""Anthropic Messages 流式适配器（§6.4-5 / §12.1）。

与 OpenAI 兼容适配器同端口（``LlmClient``），只负责协议差异；Key 解密与
供应商选择在 ``provider_registry.py``，两者解耦。

- 端点：``{base_url}/v1/messages``（base_url 已带 /v1 或 /messages 时不再重复）；
- 鉴权：``x-api-key`` + ``anthropic-version``（不再用 Bearer）；
- system 消息提升为顶层 ``system`` 字段；tool 结果转为 ``tool_result`` 块；
- SSE：``content_block_delta.text_delta`` → 文本增量，
  ``input_json_delta.partial_json`` 按 index 累积 → 工具调用，
  ``message_start / message_delta`` 的 usage → LlmUsage，
  ``message_stop`` → LlmFinished。
"""
import json
import logging
from typing import Dict, Iterator, List, Optional

import httpx

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

ANTHROPIC_VERSION = '2023-06-01'


class AnthropicLlmClient(LlmClient):
    """Anthropic Messages API 同步流式客户端。"""

    def __init__(self, *, base_url: str, api_key: str, model: str,
                 timeout_seconds: float = 60.0, temperature: float = 0.2,
                 max_output_tokens: int = 1024,
                 anthropic_version: str = ANTHROPIC_VERSION,
                 http_transport=None):
        self._base_url = (base_url or '').strip()
        self._api_key = (api_key or '').strip()
        self._model = (model or '').strip()
        self._timeout = float(timeout_seconds or 60.0)
        self._temperature = float(temperature)
        self._max_output_tokens = int(max_output_tokens or 0)
        self._anthropic_version = anthropic_version
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
        base = self._base_url.rstrip('/')
        if base.endswith('/messages'):
            return base
        if base.endswith('/v1'):
            return base + '/messages'
        return base + '/v1/messages'

    def _headers(self) -> Dict[str, str]:
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'text/event-stream',
            'anthropic-version': self._anthropic_version,
        }
        if self._api_key:
            headers['x-api-key'] = self._api_key
        return headers

    def _payload(self, request: LlmRequest) -> Dict:
        system_parts: List[str] = []
        converted: List[Dict] = []
        for message in request.messages:
            if message.role == 'system':
                if message.content:
                    system_parts.append(message.content)
                continue
            if message.role == 'tool':
                converted.append({
                    'role': 'user',
                    'content': [{
                        'type': 'tool_result',
                        'tool_use_id': message.tool_call_id or '',
                        'content': message.content or '',
                    }],
                })
                continue
            if message.role == 'assistant' and message.tool_calls:
                blocks: List[Dict] = []
                if message.content:
                    blocks.append({'type': 'text', 'text': message.content})
                for raw in message.tool_calls:
                    function = raw.get('function') or {}
                    blocks.append({
                        'type': 'tool_use',
                        'id': raw.get('id') or '',
                        'name': function.get('name') or '',
                        'input': self._parse_arguments(function.get('arguments')),
                    })
                converted.append({'role': 'assistant', 'content': blocks})
                continue
            converted.append({
                'role': message.role,
                'content': message.content or '',
            })

        payload: Dict = {
            'model': request.model or self._model,
            'messages': self._merge_adjacent(converted),
            'max_tokens': max(1, int(request.max_output_tokens
                                     or self._max_output_tokens or 1)),
            'stream': True,
        }
        if system_parts:
            payload['system'] = '\n\n'.join(system_parts)
        temperature = (request.temperature if request.temperature is not None
                       else self._temperature)
        if temperature is not None:
            payload['temperature'] = float(temperature)
        if request.tools:
            payload['tools'] = [self._tool_spec(tool) for tool in request.tools]
        return payload

    @staticmethod
    def _tool_spec(tool: Dict) -> Dict:
        function = tool.get('function') or {}
        parameters = function.get('parameters') or {}
        return {
            'name': function.get('name') or '',
            'description': function.get('description') or '',
            'input_schema': parameters if isinstance(parameters, dict)
            else {'type': 'object', 'properties': {}},
        }

    @staticmethod
    def _merge_adjacent(messages: List[Dict]) -> List[Dict]:
        """Anthropic 要求 user/assistant 交替：相邻同角色合并为内容块列表。"""
        merged: List[Dict] = []
        for message in messages:
            if merged and merged[-1]['role'] == message['role']:
                left = merged[-1]['content']
                right = message['content']
                left_blocks = (left if isinstance(left, list)
                               else [{'type': 'text', 'text': left}])
                right_blocks = (right if isinstance(right, list)
                                else [{'type': 'text', 'text': right}])
                merged[-1]['content'] = left_blocks + right_blocks
                continue
            merged.append(dict(message))
        return merged

    @staticmethod
    def _parse_arguments(raw) -> Dict:
        if isinstance(raw, dict):
            return raw
        if not raw:
            return {}
        try:
            parsed = json.loads(raw)
        except (TypeError, ValueError):
            logger.warning('模型返回的工具参数不是合法 JSON：%s', str(raw)[:200])
            return {}
        return parsed if isinstance(parsed, dict) else {}

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
                        if not data or data == '[DONE]':
                            continue
                        try:
                            chunk = json.loads(data)
                        except ValueError:
                            logger.debug('忽略无法解析的模型流片段: %s', data[:120])
                            continue
                        for item in self._consume_chunk(chunk, tool_buffers):
                            yield item
                        if chunk.get('type') == 'message_delta':
                            stop_reason = ((chunk.get('delta') or {})
                                           .get('stop_reason'))
                            if stop_reason:
                                finish_reason = stop_reason
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

    def _consume_chunk(self, chunk: Dict,
                       tool_buffers: Dict[int, Dict]) -> Iterator:
        chunk_type = chunk.get('type')
        if chunk_type == 'message_start':
            usage = ((chunk.get('message') or {}).get('usage') or {})
            if usage:
                yield LlmUsage(prompt_tokens=int(usage.get('input_tokens') or 0),
                               completion_tokens=0)
            return
        if chunk_type == 'content_block_start':
            block = chunk.get('content_block') or {}
            if block.get('type') == 'tool_use':
                index = int(chunk.get('index') or 0)
                tool_buffers[index] = {
                    'id': block.get('id') or '',
                    'name': block.get('name') or '',
                    'arguments': '',
                }
            return
        if chunk_type == 'content_block_delta':
            delta = chunk.get('delta') or {}
            if delta.get('type') == 'text_delta' and delta.get('text'):
                yield LlmTextDelta(text=delta['text'])
            elif delta.get('type') == 'input_json_delta':
                index = int(chunk.get('index') or 0)
                buffered = tool_buffers.setdefault(
                    index, {'id': '', 'name': '', 'arguments': ''})
                buffered['arguments'] += delta.get('partial_json') or ''
            return
        if chunk_type == 'message_delta':
            usage = chunk.get('usage') or {}
            if usage:
                yield LlmUsage(
                    prompt_tokens=0,
                    completion_tokens=int(usage.get('output_tokens') or 0))
            return
        if chunk_type == 'error':
            error = chunk.get('error') or {}
            raise LlmInvocationError(
                f"模型上游错误: {error.get('type') or 'unknown'}",
                code='LLM_ANTHROPIC_ERROR')


__all__ = ['AnthropicLlmClient', 'ANTHROPIC_VERSION']
