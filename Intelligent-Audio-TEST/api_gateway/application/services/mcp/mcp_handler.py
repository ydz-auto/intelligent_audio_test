# -*- coding: utf-8 -*-
"""MCP 协议适配处理器（INT-1150 / INT-1140 分道 A）。

网关内实现 JSON-RPC 2.0 MCP 端点（/api/v1/mcp）：
  - initialize / notifications/initialized / ping / tools/list / tools/call
  - 工具调用映射到网关既有 REST 能力（tools_registry），转发带原 Authorization
    头，目标端点自身 require_permission 二次校验生效权限；MCP 层先按工具
    required permissions 预检（越权 → isError 403 语义）。

传输：POST JSON-RPC；Accept 含 text/event-stream 时按 streamable HTTP
SSE 帧包裹（参考 sse_bp.py StreamingResponse 先例）。无 id 的 JSON-RPC
通知返回 202 空响应。
"""
from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)

# MCP 协议版本（2025-06-18 稳定版；negotiation 兼容客户端声明的新版本）
MCP_PROTOCOL_VERSION = '2025-06-18'
MCP_SERVER_NAME = 'intelligent-audio-test'
MCP_SERVER_VERSION = '1.0.0'

# JSON-RPC 错误码
_PARSE_ERROR = -32700
_INVALID_REQUEST = -32600
_METHOD_NOT_FOUND = -32601
_INVALID_PARAMS = -32602
_INTERNAL_ERROR = -32603

# 网关自转发超时（秒）：MCP tools/call → 目标 REST 能力
_MCP_FORWARD_TIMEOUT_SECONDS = 60


def _rpc_error(rpc_id, code: int, message: str, data=None) -> dict:
    err = {'code': code, 'message': message}
    if data is not None:
        err['data'] = data
    return {'jsonrpc': '2.0', 'id': rpc_id, 'error': err}


def _rpc_result(rpc_id, result) -> dict:
    return {'jsonrpc': '2.0', 'id': rpc_id, 'result': result}


# ========================================================================
# MCP 方法实现
# ========================================================================

def _handle_initialize(params) -> dict:
    """initialize：协议握手（clientInfo/能力协商，tools 能力声明）。"""
    requested = (params or {}).get('protocolVersion', '')
    version = MCP_PROTOCOL_VERSION
    # 客户端声明更新版本时返回服务端支持版本（MCP 规范降级语义）
    if requested and requested != MCP_PROTOCOL_VERSION:
        version = MCP_PROTOCOL_VERSION
    return {
        'protocolVersion': version,
        'capabilities': {'tools': {'listChanged': False}},
        'serverInfo': {'name': MCP_SERVER_NAME, 'version': MCP_SERVER_VERSION},
    }


def _handle_ping() -> dict:
    return {}


# ========================================================================
# tools/list & tools/call
# ========================================================================

def _handle_tools_list() -> dict:
    from api_gateway.application.services.mcp.tools_registry import list_tools
    return {'tools': list_tools()}


def _user_has_permission(user_permissions: list, required: list) -> bool:
    """越权预检：生效权限含所需任一码或 '*' 通配 → 放行。"""
    if not required:
        return True
    perms = set(user_permissions or [])
    if '*' in perms:
        return True
    return bool(perms & set(required))


def _build_target_url(request, tool: dict, args: dict) -> str:
    """按工具定义拼目标网关 URL：base_url（取当前请求）+ path 占位符替换 + 查询串。"""
    base = str(request.base_url).rstrip('/')
    path = tool['path']
    path_params = set(tool['path_params'])
    for name in path_params:
        if name in args and args[name] is not None:
            path = path.replace('{%s}' % name, str(args[name]))
    query_args = {}
    if tool['method'] == 'GET':
        # GET/DELETE：剩余参数全部进查询串
        for name, value in args.items():
            if name not in path_params and value is not None:
                query_args[name] = value
    else:
        for name in tool['query_params']:
            if name in args and args[name] is not None:
                query_args[name] = args[name]
    url = f'{base}{path}'
    if query_args:
        import urllib.parse
        qs = urllib.parse.urlencode(
            {k: (str(v) if not isinstance(v, (list, tuple)) else v)
             for k, v in query_args.items()}, doseq=True)
        url = f'{url}?{qs}'
    return url


def _build_target_body(tool: dict, args: dict) -> dict | None:
    """POST/PUT/PATCH body：剩余参数（非路径、非显式查询）进 JSON body。

    arguments 里显式 ``body`` 字段直接作为整个 body（覆盖其余参数），
    便于透传复杂嵌套结构。
    """
    if tool['method'] == 'GET':
        return None
    if 'body' in args and isinstance(args['body'], dict):
        return args['body']
    path_params = set(tool['path_params'])
    query_params = set(tool['query_params'])
    body = {k: v for k, v in args.items()
            if k not in path_params and k not in query_params and v is not None}
    return body or None


def _forward_tool_call(request, tool: dict, args: dict, token: str):
    """把 tools/call 转发到目标 REST 能力（带原 Authorization，双鉴权）。"""
    import httpx
    url = _build_target_url(request, tool, args)
    body = _build_target_body(tool, args)
    headers = {'Authorization': f'Bearer {token}'}
    user_id = getattr(request.state, 'user_id', None)
    if user_id:
        headers['X-User-Id'] = str(user_id)
    try:
        resp = httpx.request(tool['method'], url, json=body, headers=headers,
                             timeout=_MCP_FORWARD_TIMEOUT_SECONDS)
    except httpx.HTTPError as e:
        logger.warning('MCP tools/call 转发失败 tool=%s url=%s: %s',
                       tool['name'], url, e)
        return {'isError': True, 'content': [
            {'type': 'text', 'text': json.dumps(
                {'error': f'目标服务不可用: {e}', 'tool': tool['name']},
                ensure_ascii=False)}]}
    except Exception as e:  # noqa: BLE001 —— 转发构造/参数异常收敛为工具失败，不抛 500
        logger.warning('MCP tools/call 转发异常 tool=%s url=%s: %s',
                       tool['name'], url, e, exc_info=True)
        return {'isError': True, 'content': [
            {'type': 'text', 'text': json.dumps(
                {'error': f'目标调用异常: {e}', 'tool': tool['name']},
                ensure_ascii=False)}]}
    try:
        payload = resp.json()
    except ValueError:
        payload = {'detail': resp.text[:2000]}
    text = json.dumps(payload, ensure_ascii=False, default=_json_default)
    # 目标端点 4xx/5xx 透传为 MCP 调用失败（含 403 越权语义）
    is_error = resp.status_code >= 400
    return {'isError': is_error, 'content': [
        {'type': 'text', 'text': text}]}


def _json_default(obj):
    from datetime import datetime, date
    from decimal import Decimal
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    return str(obj)


def _handle_tools_call(request, rpc_id, params) -> dict:
    """tools/call：越权预检 + 目标能力转发（返回完整 JSON-RPC 信封）。"""
    if not isinstance(params, dict):
        return _rpc_error(rpc_id, _INVALID_PARAMS, 'params 必须是对象')
    name = params.get('name') or ''
    args = params.get('arguments') or {}
    if not isinstance(args, dict):
        args = {}
    from api_gateway.application.services.mcp.tools_registry import get_tool
    tool = get_tool(name)
    if tool is None:
        return _rpc_error(rpc_id, _METHOD_NOT_FOUND,
                          f'未知工具: {name}', {'tool': name})

    # 越权预检：生效权限（request.state.permissions，JWT 快照或
    # access token 用户权限 ∩ scopes）不含工具所需权限 → 拒绝
    user_permissions = list(getattr(request.state, 'permissions', None) or [])
    if not _user_has_permission(user_permissions, tool['permissions']):
        return _rpc_result(rpc_id, {'isError': True, 'content': [
            {'type': 'text', 'text': json.dumps(
                {'error': '越权：当前 token 权限不含该工具所需权限',
                 'required_permissions': tool['permissions'],
                 'tool': name}, ensure_ascii=False)}]})

    auth_header = request.headers.get('Authorization', '')
    token = auth_header[7:] if auth_header.startswith('Bearer ') else ''
    result = _forward_tool_call(request, tool, args, token)
    return _rpc_result(rpc_id, result)


# ========================================================================
# JSON-RPC 2.0 分发入口
# ========================================================================

def handle_mcp_request(request, raw_body: bytes | None = None) -> dict:
    """解析并分发一个 MCP JSON-RPC 请求。

    Returns: (response_payload, http_status)。无 id 的通知返回 (None, 202)。
    """
    if raw_body is None:
        raw_body = getattr(getattr(request, 'state', None), '_json_body', None)
    if raw_body is None:
        return _rpc_error(None, _INVALID_REQUEST, '请求体为空'), 400
    try:
        if isinstance(raw_body, (bytes, bytearray)):
            req = json.loads(raw_body.decode('utf-8'))
        elif isinstance(raw_body, str):
            req = json.loads(raw_body)
        else:
            req = raw_body
    except (json.JSONDecodeError, UnicodeDecodeError):
        return _rpc_error(None, _PARSE_ERROR, 'JSON 解析失败'), 400

    if not isinstance(req, dict) or req.get('jsonrpc') != '2.0':
        return _rpc_error(None, _INVALID_REQUEST, '非法 JSON-RPC 2.0 请求'), 400

    rpc_id = req.get('id')
    method = req.get('method') or ''
    params = req.get('params')

    # 通知（无 id）：按 JSON-RPC/MCP 规范静默忽略，返回 202 空响应
    if rpc_id is None:
        return None, 202

    try:
        if method == 'initialize':
            result = _handle_initialize(params)
        elif method == 'tools/list':
            result = _handle_tools_list()
        elif method == 'tools/call':
            return _handle_tools_call(request, rpc_id, params), 200
        elif method == 'ping':
            result = _handle_ping()
        elif method == 'resources/list':
            # 本端点不实现资源能力：空列表
            result = {'resources': []}
        else:
            return _rpc_error(rpc_id, _METHOD_NOT_FOUND,
                              f'不支持的方法: {method}'), 200
        return _rpc_result(rpc_id, result), 200
    except Exception as e:  # noqa: BLE001
        logger.warning('MCP 方法处理异常 method=%s: %s', method, e,
                       exc_info=True)
        return _rpc_error(rpc_id, _INTERNAL_ERROR, '内部错误'), 200
