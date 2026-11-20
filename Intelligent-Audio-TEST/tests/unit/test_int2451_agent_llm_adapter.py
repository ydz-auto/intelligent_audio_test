# -*- coding: utf-8 -*-
"""INT-2451 LLM 适配器：配置驱动 / 流式解析 / 工具分片合并 / 取消。"""
import json
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import httpx
import pytest

from agent_service.domain.exceptions import (
    LlmConfigurationError, LlmInvocationError, RunCancelled,
)
from agent_service.domain.model.entities import LlmMessage
from agent_service.domain.ports.llm import (
    LlmFinished, LlmRequest, LlmTextDelta, LlmToolCalls, LlmUsage,
)
from agent_service.infrastructure.llm.openai_compatible import (
    OpenAICompatibleLlmClient,
)


def _sse(*payloads):
    lines = [f'data: {json.dumps(payload, ensure_ascii=False)}'
             for payload in payloads]
    lines.append('data: [DONE]')
    return ('\n\n'.join(lines) + '\n\n').encode('utf-8')


def _stream_response(body: bytes, status=200):
    return httpx.Response(status, content=iter([body]),
                          headers={'Content-Type': 'text/event-stream'})


def _request():
    return LlmRequest(messages=(LlmMessage(role='user', content='hi'),),
                      model='m1')


def test_missing_configuration_raises():
    client = OpenAICompatibleLlmClient(base_url='', api_key='k', model='m')
    with pytest.raises(LlmConfigurationError):
        list(client.stream(_request()))
    client = OpenAICompatibleLlmClient(base_url='http://llm/v1', api_key='k',
                                       model='')
    with pytest.raises(LlmConfigurationError):
        list(client.stream(_request()))


def test_streaming_text_tools_usage_are_parsed():
    seen = {}

    def handler(request):
        seen['url'] = str(request.url)
        seen['auth'] = request.headers.get('Authorization')
        seen['body'] = json.loads(request.content.decode('utf-8'))
        body = _sse(
            {'choices': [{'delta': {'content': '你'}}]},
            {'choices': [{'delta': {'content': '好'}}]},
            {'choices': [{'delta': {'tool_calls': [{
                'index': 0, 'id': 'c1',
                'function': {'name': 'task_query', 'arguments': '{"a":'}}]}}]},
            {'choices': [{'delta': {'tool_calls': [{
                'index': 0, 'function': {'arguments': '1}'}}]}}]},
            {'choices': [], 'usage': {'prompt_tokens': 10,
                                      'completion_tokens': 5}},
        )
        return _stream_response(body)

    client = OpenAICompatibleLlmClient(
        base_url='http://llm/v1', api_key='secret', model='m1',
        timeout_seconds=5, http_transport=httpx.MockTransport(handler))
    chunks = list(client.stream(_request()))

    texts = ''.join(c.text for c in chunks if isinstance(c, LlmTextDelta))
    assert texts == '你好'
    tool_chunks = [c for c in chunks if isinstance(c, LlmToolCalls)]
    assert len(tool_chunks) == 1
    call = tool_chunks[0].calls[0]
    assert (call.tool_call_id, call.name, call.arguments) == (
        'c1', 'task_query', {'a': 1})
    usage = [c for c in chunks if isinstance(c, LlmUsage)][0]
    assert (usage.prompt_tokens, usage.completion_tokens) == (10, 5)
    assert isinstance(chunks[-1], LlmFinished)
    assert seen['url'] == 'http://llm/v1/chat/completions'
    assert seen['auth'] == 'Bearer secret'
    assert seen['body']['model'] == 'm1'
    assert seen['body']['stream'] is True


def test_http_error_is_wrapped():
    def handler(request):
        return httpx.Response(401, json={'error': 'bad key'})

    client = OpenAICompatibleLlmClient(
        base_url='http://llm/v1', api_key='k', model='m',
        http_transport=httpx.MockTransport(handler))
    with pytest.raises(LlmInvocationError) as exc_info:
        list(client.stream(_request()))
    assert exc_info.value.code == 'LLM_HTTP_401'


def test_cancel_check_aborts_stream():
    def handler(request):
        return _stream_response(_sse(
            {'choices': [{'delta': {'content': 'a'}}]},
            {'choices': [{'delta': {'content': 'b'}}]},
        ))

    client = OpenAICompatibleLlmClient(
        base_url='http://llm/v1', api_key='k', model='m',
        http_transport=httpx.MockTransport(handler))
    with pytest.raises(RunCancelled):
        list(client.stream(_request(), cancel_check=lambda: True))
