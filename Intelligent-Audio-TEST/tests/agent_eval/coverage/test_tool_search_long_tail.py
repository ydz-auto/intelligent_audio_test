# -*- coding: utf-8 -*-
"""INT-2465 tool_search 长尾索引：20 个长尾关键词命中正确工具且可调用。

验收锚点（卡面 2）：每个关键词命中可执行的工具 Schema；写工具在 M1 仍
``risk=WRITE``（执行由只读门禁拦），读工具可直接走 ``resolve_rest_call``。
"""
import pytest

from agent_service.domain.enums import ToolRisk
from agent_service.infrastructure.tools.registry_bridge import (
    SharedToolRegistryBridge,
)
from shared.agent_tools import coverage, intent_tools, mcp_registry
from shared.agent_tools.search import search

# 20 个长尾关键词：覆盖任务回收站 / 数据搬运 / Benchmark / 收藏 / 音频上传 /
# 设备 / 算法表单 / 报告分享 / Studio / 日志 / 首页 / 导入导出 / 标签可见性。
LONG_TAIL = [
    ('回收站恢复任务', 'task_restore'),
    ('彻底删除任务', 'task_purge'),
    ('任务数据 ZIP 导出', 'data_transfer_export'),
    ('Benchmark 排行', 'benchmark_ranking'),
    ('个人收藏列表', 'favorites_list'),
    ('OSS 直传预签名', 'audio_upload_presign'),
    ('分片上传合并', 'audio_upload_merge'),
    ('音频目录树', 'audio_folder_tree'),
    ('设备健康检查', 'device_health_check'),
    ('设备序列号列表', 'device_serials'),
    ('算法表单 Schema', 'algorithm_form_schema'),
    ('算法热重载', 'algorithm_reload'),
    ('用例算法参数', 'algorithm_case_param_list'),
    ('报告页签计数', 'report_tab_counts'),
    ('报告分享链接', 'report_share_list'),
    ('Studio 文档草稿', 'report_studio_create_document'),
    ('日志级别统计', 'log_stats'),
    ('首页统计摘要', 'home_stats_summary'),
    ('用例导入导出', 'testcase_export'),
    ('标签可见性', 'tag_set_visibility'),
]


def _hits(query, permissions=('*',), limit=10):
    return search(query, list(permissions), limit=limit)['tools']


@pytest.mark.parametrize('query,expected', LONG_TAIL,
                         ids=[name for _, name in LONG_TAIL])
def test_long_tail_keyword_hits_expected_tool(query, expected):
    tools = _hits(query)
    names = [tool['name'] for tool in tools]
    assert expected in names, f'{query} -> {names}'
    rank = names.index(expected) + 1
    assert rank <= 10, f'{query} 命中 {expected} 排名 {rank}'


@pytest.mark.parametrize('query,expected', LONG_TAIL,
                         ids=[name for _, name in LONG_TAIL])
def test_hit_returns_callable_schema(query, expected):
    hit = next(tool for tool in _hits(query) if tool['name'] == expected)
    assert hit['inputSchema']['type'] == 'object'
    assert hit['description']
    assert isinstance(hit['permissions'], list)
    tool, merged, error = intent_tools.resolve_rest_call(expected, {})
    assert error is None, f'{expected} 无法解析为可调用工具：{error}'
    assert tool is not None and tool['name'] == expected
    assert merged == {}
    # 风险等级由共享注册表推导，未知工具不得降级成 READ
    assert hit['risk'] in (ToolRisk.READ.value, ToolRisk.WRITE.value)
    assert hit['risk'] == ('READ' if tool['method'] == 'GET' else 'WRITE')


@pytest.mark.parametrize('query,expected', LONG_TAIL,
                         ids=[name for _, name in LONG_TAIL])
def test_search_result_carries_coverage_metadata(query, expected):
    hit = next(tool for tool in _hits(query) if tool['name'] == expected)
    intent, category = coverage.intent_of(expected)
    assert hit['intent'] == intent
    assert hit['external_only'] is (category == coverage.EXTERNAL)
    assert hit['enabled'] is True  # 长尾 MCP 条目默认可用（写工具另由门禁拦）


def test_write_long_tail_is_blocked_by_readonly_gate():
    """长尾写工具可检索，但风险是 WRITE —— M1 网关会返回 APPROVAL_REQUIRED。"""
    bridge = SharedToolRegistryBridge()
    for name in ('task_restore', 'task_purge', 'data_transfer_export',
                 'benchmark_ranking_compute', 'report_share_create'):
        tool = mcp_registry.get_tool(name)
        assert tool is not None
        assert bridge.risk_of(name) is ToolRisk.WRITE
        assert bridge.permissions_of(name) == tuple(tool['permissions'])


def test_long_tail_search_respects_permissions():
    names = [t['name'] for t in _hits('报告 导出', permissions=('task:read',),
                                      limit=30)]
    assert all(not name.startswith('report') for name in names)
    names = [t['name'] for t in _hits('报告 导出', permissions=('report:read',),
                                      limit=30)]
    assert any(name.startswith('report') for name in names)


def test_search_returns_at_most_limit_and_schema_subset():
    result = search('任务', ['*'], limit=3)
    assert result['total'] == 3
    assert len(result['tools']) == 3
    for tool in result['tools']:
        assert tool['inputSchema']['type'] == 'object'
