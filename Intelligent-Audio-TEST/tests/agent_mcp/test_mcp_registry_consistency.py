# -*- coding: utf-8 -*-
"""MCP ``tools/list`` ↔ ``shared/agent_tools`` 一致性（INT-2476 验收 2）。

锚点：
- 网关 ``POST /api/v1/mcp`` 的 ``tools/list`` 与 ``shared/agent_tools``
  **逐项一致**（数量 / 顺序 / name / description / inputSchema），对外 1:1
  契约不漂移；
- 权限声明三处同源（注册表 / ``tool_search`` 索引 / COVERAGE 归属矩阵），
  且都是合法的 ``资源:操作`` 码，没有通配或空转；
- 工具路由形（method / path / path_params）与 Schema 自洽。
"""
import json
import re
from types import SimpleNamespace

from api_gateway.application.services.mcp import mcp_handler, tools_registry
from shared.agent_tools import coverage, intent_tools, mcp_registry

# 对外 MCP 工具总数（INT-2453 谱 205 + INT-2461 首页只读 2）
MCP_TOTAL = 207
# 权限码形态：资源:操作（可多级，如 report:studio:export）
PERMISSION_PATTERN = re.compile(r'^[a-z][a-z0-9_]*:[a-z][a-z0-9_]*(:[a-z][a-z0-9_]*)*$')


def _request(permissions=('*',)):
    state = SimpleNamespace(user_id=7, permissions=list(permissions))
    return SimpleNamespace(
        state=state, headers={'Authorization': 'Bearer fake'},
        query_params={})


def _tools_list():
    payload, status = mcp_handler.handle_mcp_request(
        _request(), json.dumps({'jsonrpc': '2.0', 'id': 1,
                                'method': 'tools/list'}))
    assert status == 200
    return payload['result']['tools']


# ---------------------------------------------------------------- 逐项一致

def test_gateway_tools_list_is_the_shared_single_source():
    listed = _tools_list()
    expected = mcp_registry.list_tools()
    assert len(listed) == MCP_TOTAL == len(expected)
    # 顺序与内容逐项一致（不是集合相等：外部客户端按列表顺序展示）
    assert listed == expected
    assert [tool['name'] for tool in listed] == [
        tool['name'] for tool in mcp_registry.TOOLS]
    assert tools_registry.TOOLS is mcp_registry.TOOLS
    assert tools_registry.list_tools() == expected


def test_tools_list_item_schema_shape():
    for tool in _tools_list():
        assert set(tool) == {'name', 'description', 'inputSchema'}
        assert tool['name'] and isinstance(tool['name'], str)
        assert tool['description'] and isinstance(tool['description'], str)
        schema = tool['inputSchema']
        assert schema['type'] == 'object'
        assert schema['additionalProperties'] is True
        assert isinstance(schema['properties'], dict)


def test_registry_names_unique_and_routable():
    names = [tool['name'] for tool in mcp_registry.TOOLS]
    assert len(names) == len(set(names)), 'MCP 注册表存在重复工具名'
    for tool in mcp_registry.TOOLS:
        assert tool['method'] in {'GET', 'POST', 'PUT', 'PATCH', 'DELETE'}
        assert tool['path'].startswith('/api/v1/')
        placeholders = set(re.findall(r'\{(\w+)\}', tool['path']))
        assert placeholders == set(tool['path_params']), tool['name']
        assert set(tool['query_params']) <= set(
            tool['inputSchema']['properties']), tool['name']


# ---------------------------------------------------------------- 权限

def test_every_declared_permission_is_a_valid_code():
    for tool in mcp_registry.TOOLS:
        permissions = tool['permissions']
        assert isinstance(permissions, list), tool['name']
        assert len(permissions) == len(set(permissions)), tool['name']
        for permission in permissions:
            assert permission != '*', (
                f'{tool["name"]} 不能用通配权限：MCP 工具必须声明具体权限码')
            assert PERMISSION_PATTERN.match(permission), (
                f'{tool["name"]} 权限码非法：{permission!r}')


def test_permissions_match_search_index_and_coverage_matrix():
    """权限三处同源：注册表 = tool_search 索引 = COVERAGE 归属矩阵。"""
    index = {entry['name']: entry for entry in intent_tools.TOOL_INDEX
             if entry.get('kind') == 'mcp'}
    rows = {row.name: row for row in coverage.coverage_rows()}
    for tool in mcp_registry.TOOLS:
        name = tool['name']
        if name in index:
            assert index[name]['permissions'] == list(tool['permissions']), name
            assert index[name]['inputSchema'] == tool['inputSchema'], name
        row = rows[name]
        assert row.permissions == tuple(tool['permissions']), name
        assert row.method == tool['method'], name


def test_no_hidden_tool_outside_coverage_matrix():
    """对外每个工具都有归属结论；仅外部集合有显式理由（无暗能力）。"""
    names = {tool['name'] for tool in mcp_registry.TOOLS}
    rows = coverage.coverage_rows()
    assert {row.name for row in rows} == names
    assert set(coverage.EXTERNAL_ONLY) <= names
    for name in coverage.EXTERNAL_ONLY:
        assert any(row.name == name and row.category == coverage.EXTERNAL
                   for row in rows), name
