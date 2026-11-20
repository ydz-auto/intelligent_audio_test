# -*- coding: utf-8 -*-
"""Access Token 权限 = 用户权限 ∩ token scopes（INT-2476 验收 3）。

单测部分不依赖环境：
- ``_intersect_permissions`` 的四种组合（空 scopes / 通配 token / 通配用户 /
  逐码交集）；
- MCP ``tools/call`` 的越权预检（scope 不足 → isError，足够 → 转发）。

``test_live_*`` 只在 ``AGENT_LIVE_GATEWAY`` 指向 docker 栈时运行（实测口径）：
真登录 → 建 scoped access token → MCP ``tools/call`` 一个够权工具成功、
一个越权工具被拒 → 删除 token。
"""
import json
import os
import urllib.error
import urllib.request
from types import SimpleNamespace
from unittest import mock

import pytest

from api_gateway.application.services.auth.access_token_service import (
    _intersect_permissions,
)
from api_gateway.application.services.mcp import mcp_handler
from shared.agent_tools import mcp_registry
from tests.agent_eval import live_support


def _req(permissions):
    return SimpleNamespace(
        state=SimpleNamespace(user_id=7, permissions=list(permissions)),
        headers={'Authorization': 'Bearer fake'},
        query_params={})


def _call(name, arguments, permissions):
    payload, status = mcp_handler.handle_mcp_request(
        _req(permissions),
        json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
                    'params': {'name': name, 'arguments': arguments}}))
    assert status == 200
    return payload['result']


# ---------------------------------------------------------------- 交集口径

def test_empty_scopes_inherit_all_user_permissions():
    assert _intersect_permissions(['task:read', 'audio:read'], []) == [
        'task:read', 'audio:read']


def test_wildcard_scope_inherits_all_user_permissions():
    assert _intersect_permissions(['task:read'], ['*']) == ['task:read']


def test_admin_user_is_narrowed_by_token_scopes():
    assert _intersect_permissions(['*'], ['task:read']) == ['task:read']


def test_intersection_keeps_only_scopes_the_user_still_has():
    assert _intersect_permissions(
        ['task:read', 'audio:read'], ['task:read', 'audio:delete']) == [
        'task:read']


# ---------------------------------------------------------------- MCP 预检

def test_mcp_call_denied_when_scope_is_insufficient():
    result = _call('audio_delete', {'audio_id': 1}, ['task:read'])
    assert result['isError'] is True
    body = json.loads(result['content'][0]['text'])
    assert '越权' in body['error']
    assert body['required_permissions'] == ['audio:delete']


def test_mcp_call_allowed_when_scope_covers_tool():
    fake = mock.Mock()
    fake.status_code = 200
    fake.json.return_value = {'success': True, 'data': {'items': []}}
    with mock.patch('httpx.request', return_value=fake) as forwarded:
        result = _call('task_list', {'page': 1}, ['task:read'])
    assert result['isError'] is False
    assert forwarded.call_args[0][1].endswith('/api/v1/tasks?page=1')


# ---------------------------------------------------------------- 实测（docker）

def _post_mcp(gateway: str, token: str, payload: dict) -> dict:
    request = urllib.request.Request(
        f'{gateway}/api/v1/mcp',
        data=json.dumps(payload).encode('utf-8'),
        headers={'Authorization': f'Bearer {token}',
                 'Content-Type': 'application/json'},
        method='POST')
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode('utf-8'))


@pytest.mark.skipif(not live_support.available(),
                    reason='需要 AGENT_LIVE_GATEWAY 指向 docker 网关栈')
def test_live_tools_list_matches_shared_registry():
    gateway = live_support.GATEWAY
    payload = _post_mcp(gateway, live_support.login(),
                        {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'})
    tools = payload['result']['tools']
    assert tools == mcp_registry.list_tools()
    assert len(tools) == len(mcp_registry.TOOLS) == 207


@pytest.mark.skipif(not live_support.available(),
                    reason='需要 AGENT_LIVE_GATEWAY 指向 docker 网关栈')
def test_live_access_token_scope_is_enforced():
    gateway = live_support.GATEWAY
    jwt = live_support.login()
    try:
        status, created = live_support.raw(
            'POST', '/api/v1/auth/access-tokens', jwt,
            {'name': '接线测试_MCP_scope', 'scopes': ['task:read']})
        assert status == 200, created
        token_id = created['data']['id']
        at_token = created['data']['token']
        assert at_token.startswith('at_')
        try:
            # scope 足够：task_list 需要 task:read → 成功
            ok = _post_mcp(gateway, at_token, {
                'jsonrpc': '2.0', 'id': 2, 'method': 'tools/call',
                'params': {'name': 'task_list', 'arguments': {'page': 1,
                                                              'per_page': 1}}})
            assert ok['result']['isError'] is False, ok
            # scope 不足：audio_delete 需要 audio:delete → 越权拒绝
            denied = _post_mcp(gateway, at_token, {
                'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call',
                'params': {'name': 'audio_delete',
                           'arguments': {'audio_id': 1}}})
            assert denied['result']['isError'] is True, denied
            body = json.loads(denied['result']['content'][0]['text'])
            assert '越权' in body['error']
        finally:
            live_support.raw('DELETE',
                             f'/api/v1/auth/access-tokens/{token_id}', jwt)
    except urllib.error.HTTPError as exc:  # pragma: no cover - 环境不可用
        pytest.skip(f'实测网关不可用：{exc}')
