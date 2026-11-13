# -*- coding: utf-8 -*-
"""INT-2488 协议适配与连通性验证（§6.4-5 / §11 verify）。"""
import json
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import httpx
import pytest

from agent_service.domain.enums import LlmProtocol
from agent_service.domain.exceptions import (
    LlmConfigurationError, LlmInvocationError,
)
from agent_service.domain.model.entities import LlmMessage
from agent_service.domain.ports.llm import (
    LlmFinished, LlmRequest, LlmTextDelta, LlmToolCalls, LlmUsage,
)
from agent_service.infrastructure.llm.anthropic import AnthropicLlmClient
from agent_service.infrastructure.llm.verifier import (
    AUTH_FAILED, HTTP_ERROR, HttpProviderVerifier, UNREACHABLE, VERIFIED,
)


def _sse(*payloads):
    return ''.join(
        f'event: {payload.get("type", "message")}\n'
        f'data: {json.dumps(payload, ensure_ascii=False)}\n\n'
        for payload in payloads).encode('utf-8')


def _stream(body):
    return httpx.Response(200, content=iter([body]),
                          headers={'Content-Type': 'text/event-stream'})


def _request():
    return LlmRequest(
        messages=(
            LlmMessage(role='system', content='你是测试助手'),
            LlmMessage(role='user', content='hi'),
        ),
        model='claude-sonnet-4-5',
        max_output_tokens=321,
        tools=({'type': 'function', 'function': {
            'name': 'task_query', 'description': '查任务',
            'parameters': {'type': 'object', 'properties': {}}}},),
    )


def test_anthropic_stream_parses_text_tools_and_usage():
    seen = {}

    def handler(request):
        seen['url'] = str(request.url)
        seen['key'] = request.headers.get('x-api-key')
        seen['version'] = request.headers.get('anthropic-version')
        seen['body'] = json.loads(request.content.decode('utf-8'))
        return _stream(_sse(
            {'type': 'message_start', 'message': {
                'usage': {'input_tokens': 12, 'output_tokens': 0}}},
            {'type': 'content_block_start', 'index': 0,
             'content_block': {'type': 'text', 'text': ''}},
            {'type': 'content_block_delta', 'index': 0,
             'delta': {'type': 'text_delta', 'text': '你'}},
            {'type': 'content_block_delta', 'index': 0,
             'delta': {'type': 'text_delta', 'text': '好'}},
            {'type': 'content_block_start', 'index': 1, 'content_block': {
                'type': 'tool_use', 'id': 'toolu_1', 'name': 'task_query'}},
            {'type': 'content_block_delta', 'index': 1,
             'delta': {'type': 'input_json_delta',
                       'partial_json': '{"task_id":'}},
            {'type': 'content_block_delta', 'index': 1,
             'delta': {'type': 'input_json_delta', 'partial_json': ' 7}'}},
            {'type': 'message_delta',
             'delta': {'stop_reason': 'tool_use'},
             'usage': {'output_tokens': 7}},
            {'type': 'message_stop'},
        ))

    client = AnthropicLlmClient(
        base_url='https://api.anthropic.com', api_key='secret',
        model='claude-sonnet-4-5', max_output_tokens=1024,
        http_transport=httpx.MockTransport(handler))
    chunks = list(client.stream(_request()))

    texts = ''.join(c.text for c in chunks if isinstance(c, LlmTextDelta))
    assert texts == '你好'
    calls = [c for c in chunks if isinstance(c, LlmToolCalls)][0].calls
    assert calls[0].tool_call_id == 'toolu_1'
    assert calls[0].name == 'task_query'
    assert calls[0].arguments == {'task_id': 7}
    usages = [c for c in chunks if isinstance(c, LlmUsage)]
    assert (usages[0].prompt_tokens, usages[0].completion_tokens) == (12, 0)
    assert (usages[1].prompt_tokens, usages[1].completion_tokens) == (0, 7)
    assert isinstance(chunks[-1], LlmFinished)

    assert seen['url'] == 'https://api.anthropic.com/v1/messages'
    assert seen['key'] == 'secret'
    assert seen['version']
    body = seen['body']
    assert body['system'] == '你是测试助手'
    assert body['max_tokens'] == 321
    assert body['messages'] == [{'role': 'user', 'content': 'hi'}]
    assert body['tools'][0]['input_schema'] == {'type': 'object',
                                                'properties': {}}
    assert 'Authorization' not in body


def test_anthropic_base_url_with_v1_not_duplicated():
    seen = {}

    def handler(request):
        seen['url'] = str(request.url)
        return _stream(_sse({'type': 'message_stop'}))

    client = AnthropicLlmClient(
        base_url='http://gw.local/v1', api_key='k', model='m',
        http_transport=httpx.MockTransport(handler))
    list(client.stream(_request()))
    assert seen['url'] == 'http://gw.local/v1/messages'


def test_anthropic_http_error_wrapped():
    def handler(request):
        return httpx.Response(429, json={'error': 'slow down'})

    client = AnthropicLlmClient(
        base_url='http://gw.local', api_key='k', model='m',
        http_transport=httpx.MockTransport(handler))
    with pytest.raises(LlmInvocationError) as exc_info:
        list(client.stream(_request()))
    assert exc_info.value.code == 'LLM_HTTP_429'


def test_anthropic_stream_error_event():
    def handler(request):
        return _stream(_sse({'type': 'error',
                             'error': {'type': 'overloaded_error'}}))

    client = AnthropicLlmClient(
        base_url='http://gw.local', api_key='k', model='m',
        http_transport=httpx.MockTransport(handler))
    with pytest.raises(LlmInvocationError) as exc_info:
        list(client.stream(_request()))
    assert exc_info.value.code == 'LLM_ANTHROPIC_ERROR'


def test_anthropic_missing_configuration():
    client = AnthropicLlmClient(base_url='', api_key='k', model='m')
    with pytest.raises(LlmConfigurationError):
        list(client.stream(_request()))


# ---------------------------------------------------------------- verifier

@pytest.mark.parametrize('protocol,status,expected', [
    (LlmProtocol.OPENAI_COMPATIBLE, 200, VERIFIED),
    (LlmProtocol.OPENAI_COMPATIBLE, 401, AUTH_FAILED),
    (LlmProtocol.OPENAI_COMPATIBLE, 500, HTTP_ERROR),
    (LlmProtocol.ANTHROPIC, 200, VERIFIED),
    (LlmProtocol.ANTHROPIC, 403, AUTH_FAILED),
])
def test_verifier_codes(protocol, status, expected):
    def handler(request):
        return httpx.Response(status, json={'ok': status < 400})

    verifier = HttpProviderVerifier(
        timeout_seconds=1, http_transport=httpx.MockTransport(handler))
    outcome = verifier.verify(protocol=protocol, base_url='http://x.local/v1',
                              model='m', api_key='sk-secret-key-123456')
    assert outcome.code == expected
    assert 'sk-secret-key-123456' not in outcome.message


def test_verifier_unreachable():
    def handler(request):
        raise httpx.ConnectError('connection refused', request=request)

    verifier = HttpProviderVerifier(
        timeout_seconds=1, http_transport=httpx.MockTransport(handler))
    outcome = verifier.verify(
        protocol=LlmProtocol.OPENAI_COMPATIBLE, base_url='http://127.0.0.1:1',
        model='m', api_key='sk-secret-key-123456')
    assert outcome.ok is False
    assert outcome.code == UNREACHABLE
    assert 'sk-secret-key-123456' not in outcome.message
