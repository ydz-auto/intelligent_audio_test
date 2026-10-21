# -*- coding: utf-8 -*-
"""skill 下载 + MCP 适配端点单测（INT-1150 / INT-1140 分道 A）。

覆盖：
- tools 注册表覆盖/除外边界（INT-1140 覆盖能力清单）
- _user_has_permission 越权预检
- MCP JSON-RPC：initialize / tools/list / tools/call（转发打桩）/ 越权拒绝 /
  未知方法 / 通知
- skill 包：build_skill_zip 含 SKILL.md + mcp.json 且 base_url 注入；
  resolve_base_url ?base_url= → Origin → Host 兜底
- 路由：skill 下载 / MCP 端点需登录（无 user_id → 401）
"""
import io
import json
import os
import zipfile
from types import SimpleNamespace
from unittest import mock

import pytest

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from api_gateway.application.services.mcp import (  # noqa: E402
    mcp_handler,
    skill_package,
    tools_registry,
)
from api_gateway.routes import agent_bp  # noqa: E402


def _req(user_id=7, permissions=None, headers=None, query=None, base_url=None):
    """构造测试用伪 FastAPI Request。"""
    state = SimpleNamespace(
        user_id=user_id,
        permissions=permissions or ['task:read', 'testcase:read'],
        _json_body=None,
    )
    hdrs = dict(headers or {})
    hdrs.setdefault('Authorization', 'Bearer fake-token')
    return SimpleNamespace(
        state=state,
        headers=hdrs,
        query_params=query or {},
        base_url=base_url or 'http://testserver/',
    )


# ========================================================================
# tools 注册表：覆盖 / 除外边界
# ========================================================================

class TestToolsRegistry:

    def test_core_business_domains_covered(self):
        names = {t['name'] for t in tools_registry.TOOLS}
        for tool in ('task_list', 'task_get', 'task_create',
                     'testcase_list', 'testcase_get',
                     'audio_list', 'audio_get',
                     'device_list', 'device_get',
                     'evaluation_dimension_list', 'evaluation_category_list',
                     'report_list', 'report_get',
                     'algorithm_definition_list', 'algorithm_group_list',
                     'tag_list', 'tag_create',
                     'group_list', 'group_create'):
            assert tool in names, f'{tool} 应覆盖'

    def test_share_and_favorites_covered(self):
        names = {t['name'] for t in tools_registry.TOOLS}
        for tool in ('task_set_visibility', 'testcase_set_visibility',
                     'report_set_visibility', 'tag_set_visibility',
                     'group_set_visibility', 'evaluation_dimension_set_visibility',
                     'favorites_list', 'task_favorite', 'task_restore',
                     'data_transfer_export', 'data_transfer_import',
                     'benchmark_ranking', 'report_studio_create_document'):
            assert tool in names, f'{tool} 应覆盖'

    def test_personal_and_system_settings_excluded(self):
        names = {t['name'] for t in tools_registry.TOOLS}
        for prefix in ('auth_', 'option_', 'system_', 'status_', 'user_',
                       'role_', 'permission_', 'oauth_'):
            for name in names:
                assert not name.startswith(prefix), \
                    f'{name} 属个人信息/系统设置，不应暴露'
        # 日志只暴露只读，管理/websocket 排除
        log_tools = [t for t in tools_registry.TOOLS if t['name'].startswith('log_')]
        assert all(t['permissions'] == ['log:read'] for t in log_tools)
        # SSE 长连接推送排除
        assert not any(t['name'].startswith('sse_') for t in tools_registry.TOOLS)

    def test_tool_schema_shape(self):
        tool = tools_registry.get_tool('task_get')
        assert tool is not None
        assert tool['method'] == 'GET'
        assert tool['path'] == '/api/v1/tasks/{task_id}'
        assert tool['path_params'] == ['task_id']
        assert tool['inputSchema']['type'] == 'object'
        assert tool['inputSchema']['properties']['task_id']['required'] is True

    def test_unknown_tool_returns_none(self):
        assert tools_registry.get_tool('no_such_tool') is None


# ========================================================================
# 越权预检
# ========================================================================

class TestUserHasPermission:

    def test_admin_wildcard_passes(self):
        assert mcp_handler._user_has_permission(['*'], ['task:read']) is True

    def test_matching_permission_passes(self):
        assert mcp_handler._user_has_permission(['task:read'], ['task:read']) is True

    def test_any_of_required_passes(self):
        assert mcp_handler._user_has_permission(
            ['audio:read'], ['task:read', 'audio:read']) is True

    def test_missing_permission_denied(self):
        assert mcp_handler._user_has_permission(
            ['task:read'], ['audio:delete']) is False

    def test_empty_required_allows(self):
        assert mcp_handler._user_has_permission([], []) is True


# ========================================================================
# MCP JSON-RPC 协议
# ========================================================================

class TestMcpProtocol:

    def test_initialize(self):
        payload, status = mcp_handler.handle_mcp_request(
            _req(), json.dumps({'jsonrpc': '2.0', 'id': 1,
                                'method': 'initialize',
                                'params': {'protocolVersion': '2025-06-18',
                                           'clientInfo': {'name': 'test'}}}))
        assert status == 200
        assert payload['id'] == 1
        result = payload['result']
        assert result['protocolVersion'] == mcp_handler.MCP_PROTOCOL_VERSION
        assert result['serverInfo']['name'] == mcp_handler.MCP_SERVER_NAME
        assert result['capabilities']['tools'] == {'listChanged': False}

    def test_tools_list(self):
        payload, status = mcp_handler.handle_mcp_request(
            _req(), json.dumps({'jsonrpc': '2.0', 'id': 2,
                                'method': 'tools/list'}))
        assert status == 200
        tools = payload['result']['tools']
        assert len(tools) == len(tools_registry.TOOLS)
        assert all({'name', 'description', 'inputSchema'} <= set(t.keys())
                   for t in tools)

    def test_ping(self):
        payload, status = mcp_handler.handle_mcp_request(
            _req(), json.dumps({'jsonrpc': '2.0', 'id': 3, 'method': 'ping'}))
        assert status == 200
        assert payload['result'] == {}

    def test_unknown_method(self):
        payload, status = mcp_handler.handle_mcp_request(
            _req(), json.dumps({'jsonrpc': '2.0', 'id': 4,
                                'method': 'no/such/method'}))
        assert status == 200
        assert payload['error']['code'] == -32601

    def test_notification_returns_202_no_body(self):
        payload, status = mcp_handler.handle_mcp_request(
            _req(), json.dumps({'jsonrpc': '2.0',
                                'method': 'notifications/initialized'}))
        assert status == 202
        assert payload is None

    def test_invalid_jsonrpc(self):
        payload, status = mcp_handler.handle_mcp_request(
            _req(), json.dumps({'jsonrpc': '1.0', 'id': 1, 'method': 'ping'}))
        assert status == 400
        assert payload['error']['code'] == -32600


class TestMcpToolsCall:

    def test_tools_call_forwards_and_returns_content(self):
        fake_resp = mock.Mock()
        fake_resp.status_code = 200
        fake_resp.json.return_value = {'success': True, 'data': [{'id': 1}]}
        with mock.patch('httpx.request', return_value=fake_resp) as m:
            payload, status = mcp_handler.handle_mcp_request(
                _req(), json.dumps({'jsonrpc': '2.0', 'id': 5,
                                    'method': 'tools/call',
                                    'params': {'name': 'task_list',
                                               'arguments': {'page': 1}}}))
        assert status == 200
        assert payload['id'] == 5
        result = payload['result']
        assert result['isError'] is False
        body = json.loads(result['content'][0]['text'])
        assert body['success'] is True
        # 转发到任务列表端点，带原 Authorization 头
        call_args = m.call_args
        assert call_args[0][0] == 'GET'
        assert call_args[0][1].endswith('/api/v1/tasks?page=1')
        assert call_args[1]['headers']['Authorization'] == 'Bearer fake-token'

    def test_tools_call_forwards_path_params(self):
        fake_resp = mock.Mock()
        fake_resp.status_code = 200
        fake_resp.json.return_value = {'id': 42}
        with mock.patch('httpx.request', return_value=fake_resp) as m:
            payload, _ = mcp_handler.handle_mcp_request(
                _req(), json.dumps({'jsonrpc': '2.0', 'id': 6,
                                    'method': 'tools/call',
                                    'params': {'name': 'task_get',
                                               'arguments': {'task_id': 42}}}))
        assert payload['result']['isError'] is False
        assert m.call_args[0][1].endswith('/api/v1/tasks/42')

    def test_tools_call_permission_denied(self):
        # 用户只有 task:read，工具要求 audio:delete → 越权拒绝（不转发）
        req = _req(permissions=['task:read'], headers={'Authorization': 'Bearer t'})
        payload, status = mcp_handler.handle_mcp_request(
            req, json.dumps({'jsonrpc': '2.0', 'id': 7,
                             'method': 'tools/call',
                             'params': {'name': 'audio_delete',
                                        'arguments': {'audio_id': 1}}}))
        assert status == 200
        assert payload['result']['isError'] is True
        text = json.loads(payload['result']['content'][0]['text'])
        assert '越权' in text['error']

    def test_tools_call_unknown_tool(self):
        payload, status = mcp_handler.handle_mcp_request(
            _req(), json.dumps({'jsonrpc': '2.0', 'id': 8,
                                'method': 'tools/call',
                                'params': {'name': 'nope', 'arguments': {}}}))
        assert payload['error']['code'] == -32601

    def test_tools_call_forward_error_passthrough(self):
        fake_resp = mock.Mock()
        fake_resp.status_code = 403
        fake_resp.json.return_value = {'detail': '缺少权限'}
        req = _req(permissions=['tag:create'])
        with mock.patch('httpx.request', return_value=fake_resp):
            payload, _ = mcp_handler.handle_mcp_request(
                req, json.dumps({'jsonrpc': '2.0', 'id': 9,
                                 'method': 'tools/call',
                                 'params': {'name': 'tag_create',
                                            'arguments': {'name': 'x'}}}))
        assert payload['result']['isError'] is True
        assert json.loads(payload['result']['content'][0]['text'])['detail'] == '缺少权限'

    def test_tools_call_post_body(self):
        fake_resp = mock.Mock()
        fake_resp.status_code = 200
        fake_resp.json.return_value = {'success': True}
        req = _req(permissions=['tag:create'])
        with mock.patch('httpx.request', return_value=fake_resp) as m:
            payload, _ = mcp_handler.handle_mcp_request(
                req, json.dumps({'jsonrpc': '2.0', 'id': 10,
                                 'method': 'tools/call',
                                 'params': {'name': 'tag_create',
                                            'arguments': {'name': '新标签'}}}))
        assert payload['result']['isError'] is False
        assert m.call_args[1]['json'] == {'name': '新标签'}


# ========================================================================
# skill 包
# ========================================================================

class TestSkillPackage:

    def test_build_zip_contains_members_with_injected_url(self):
        data = skill_package.build_skill_zip('http://10.0.0.8:8080')
        zf = zipfile.ZipFile(io.BytesIO(data))
        assert set(zf.namelist()) == {'SKILL.md', 'mcp.json'}
        skill = zf.read('SKILL.md').decode('utf-8')
        mcp = json.loads(zf.read('mcp.json').decode('utf-8'))
        assert mcp['url'] == 'http://10.0.0.8:8080/api/v1/mcp'
        assert 'http://10.0.0.8:8080/api/v1/mcp' in skill
        assert '{{BASE_URL}}' not in skill and '{{BASE_URL}}' not in mcp['url']
        assert mcp['headers']['Authorization'] == 'Bearer 在此填入你的 Access Token'

    def test_build_zip_trailing_slash_normalized(self):
        data = skill_package.build_skill_zip('http://example.com/')
        mcp = json.loads(zipfile.ZipFile(io.BytesIO(data))
                         .read('mcp.json').decode('utf-8'))
        assert mcp['url'] == 'http://example.com/api/v1/mcp'

    def test_resolve_base_url_query_first(self):
        req = _req(query={'base_url': 'http://10.0.0.8:8080'},
                   headers={'Origin': 'http://origin.example',
                            'Host': 'host.example'})
        assert skill_package.resolve_base_url(req) == 'http://10.0.0.8:8080'

    def test_resolve_base_url_origin_fallback(self):
        req = _req(query={}, headers={'Origin': 'http://origin.example',
                                      'Host': 'host.example'})
        assert skill_package.resolve_base_url(req) == 'http://origin.example'

    def test_resolve_base_url_host_fallback(self):
        req = _req(query={}, headers={'Host': '10.0.0.8:8080'})
        assert skill_package.resolve_base_url(req) == 'http://10.0.0.8:8080'

    def test_resolve_base_url_https_forwarded(self):
        req = _req(query={}, headers={'Host': 'example.com',
                                      'X-Forwarded-Proto': 'https'})
        assert skill_package.resolve_base_url(req) == 'https://example.com'

    def test_resolve_base_url_empty_when_nothing(self):
        assert skill_package.resolve_base_url(_req(query={}, headers={})) == ''


# ========================================================================
# 路由：登录校验
# ========================================================================

class TestAgentRoutes:

    def test_skill_download_requires_login(self):
        req = _req(user_id=0)  # off 模式 dev_user
        resp = agent_bp.download_skill(req)
        assert resp.status_code == 401

    def test_skill_download_anonymous_requires_login(self):
        req = _req(user_id=None)
        resp = agent_bp.download_skill(req)
        assert resp.status_code == 401

    def test_mcp_requires_login(self):
        req = _req(user_id=0)
        resp = agent_bp.mcp_endpoint(req)
        assert resp.status_code == 401

    def test_skill_download_logged_in_builds_zip(self):
        req = _req(user_id=7, query={'base_url': 'http://10.0.0.8:8080'},
                   headers={'Host': 'host.example'})
        resp = agent_bp.download_skill(req)
        assert resp.status_code == 200
        assert resp.headers['content-type'].startswith('application/zip')
        assert 'attachment' in resp.headers['content-disposition']
        zf = zipfile.ZipFile(io.BytesIO(resp.body))
        assert 'SKILL.md' in zf.namelist()
        assert 'mcp.json' in zf.namelist()

    def test_mcp_logged_in_returns_json(self):
        req = _req(user_id=7)
        body = json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': 'ping'})
        req.state._json_body = json.loads(body)
        resp = agent_bp.mcp_endpoint(req)
        assert resp.status_code == 200
        assert json.loads(resp.body)['result'] == {}

    def test_mcp_notification_returns_202(self):
        req = _req(user_id=7)
        req.state._json_body = {'jsonrpc': '2.0',
                                'method': 'notifications/initialized'}
        resp = agent_bp.mcp_endpoint(req)
        assert resp.status_code == 202

    def test_mcp_streamable_http_sse(self):
        req = _req(user_id=7, headers={'Accept': 'text/event-stream'})
        req.state._json_body = {'jsonrpc': '2.0', 'id': 1, 'method': 'ping'}
        resp = agent_bp.mcp_endpoint(req)
        assert resp.status_code == 200
        assert resp.headers['content-type'].startswith('text/event-stream')
