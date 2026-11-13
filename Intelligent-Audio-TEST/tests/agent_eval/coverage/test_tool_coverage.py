# -*- coding: utf-8 -*-
"""INT-2465 覆盖率报告：207 个外部 MCP 工具 100% 有归属结论。

验收锚点（卡面 1 / 拍板增补 2）：
- ``shared/agent_tools/COVERAGE.md`` 与 ``coverage.py`` 同源，207 项逐行有结论；
- 每项结论是「内部归属（某意图工具）」或「仅外部 MCP（不内部暴露）」；
- 归属的意图工具必须在 31 个注册表内，且结论不随注册表漂移。
"""
import io
import os

import pytest

from shared.agent_tools import coverage, intent_tools, mcp_registry

COVERAGE_FILE = coverage.coverage_path()

MCP_TOTAL = 207          # INT-2453 谱 205 + INT-2461 首页只读 2
# tool_search 的 MCP 索引视图：去掉宿主语境通道（audio_get_by_ids）与已被
# 已启用意图工具顶替的同名 MCP 项（report_compare、INT-2471 的 report_export）
LONG_TAIL_INDEX = 204
OWNED_TOTAL = 198
EXTERNAL_TOTAL = 9


def _read_coverage_md() -> str:
    assert os.path.exists(COVERAGE_FILE), 'COVERAGE.md 未生成'
    with io.open(COVERAGE_FILE, encoding='utf-8') as handle:
        return handle.read()


def test_coverage_file_is_generated_from_code():
    """表格不能手写：文件必须与 render_markdown() 逐字节一致。"""
    assert _read_coverage_md() == coverage.render_markdown()
    assert coverage.write_markdown  # 生成入口存在


def test_every_mcp_tool_has_exactly_one_conclusion():
    rows = coverage.coverage_rows()
    assert len(rows) == MCP_TOTAL
    names = [row.name for row in rows]
    assert len(names) == len(set(names))
    assert set(names) == {tool['name'] for tool in mcp_registry.TOOLS}
    for row in rows:
        assert row.category in (coverage.OWNED, coverage.EXTERNAL)
        assert row.reason.strip()
        if row.category == coverage.OWNED:
            assert row.intent in intent_tools.INTENT_TOOL_BY_NAME
        else:
            assert row.intent is None


def test_coverage_summary_matches_matrix():
    stats = coverage.summary()
    assert stats['mcp_total'] == MCP_TOTAL
    assert stats['owned'] == OWNED_TOTAL
    assert stats['external'] == EXTERNAL_TOTAL
    assert stats['owned'] + stats['external'] == stats['mcp_total']
    assert stats['intent_total'] == 31
    assert set(stats['by_intent']) | set(stats['intent_none']) == {
        tool.name for tool in intent_tools.INTENT_TOOLS}
    assert not (set(stats['by_intent']) & set(stats['intent_none']))


def test_coverage_md_lists_every_tool_and_conclusion():
    text = _read_coverage_md()
    for tool in mcp_registry.TOOLS:
        assert f'`{tool["name"]}`' in text, f'COVERAGE.md 漏了 {tool["name"]}'
    for row in coverage.coverage_rows():
        if row.category == coverage.OWNED:
            assert f'内部归属（`{row.intent}`）' in text
        else:
            assert '仅外部 MCP（不内部暴露）' in text


def test_external_only_tools_have_explicit_reasons():
    stats = coverage.summary()
    assert set(stats['external_names']) == set(coverage.EXTERNAL_ONLY)
    for name, reason in coverage.EXTERNAL_ONLY.items():
        assert reason.strip(), name
        assert mcp_registry.get_tool(name) is not None, name
    # 宿主语境通道固定不可内部暴露（INT-2530）
    assert 'audio_get_by_ids' in coverage.EXTERNAL_ONLY
    assert 'audio_get_by_ids' in intent_tools.AGENT_UNEXPOSED_MCP_TOOLS


def test_long_tail_index_view_counts():
    """tool_search 的 MCP 视图 204 项 + 31 个意图名称（含顶替项）。"""
    mcp_entries = [e for e in intent_tools.TOOL_INDEX if e.get('kind') == 'mcp']
    assert len(mcp_entries) == LONG_TAIL_INDEX
    names = [entry['name'] for entry in intent_tools.TOOL_INDEX]
    assert len(names) == len(set(names))
    assert set(names) == {t.name for t in intent_tools.INTENT_TOOLS} | {
        entry['name'] for entry in mcp_entries}


@pytest.mark.parametrize('row', coverage.coverage_rows(),
                         ids=lambda row: row.name)
def test_row_metadata_contains_required_fields(row):
    """每行带 name / method / permissions / risk，供审计逐项核对。"""
    tool = mcp_registry.get_tool(row.name)
    assert tool is not None
    assert row.method == tool['method']
    assert row.permissions == tuple(tool['permissions'])
    assert row.risk == ('READ' if tool['method'] == 'GET' else 'WRITE')
    assert isinstance(tool['description'], str) and tool['description']
    assert isinstance(tool['permissions'], list)
    assert row.indexed in ('mcp', 'intent', 'excluded')


def test_external_only_flags_visible_in_search_results():
    """仅外部 MCP 的工具在 tool_search 结果里标 external_only=True。"""
    for name in coverage.EXTERNAL_ONLY:
        if name in intent_tools.AGENT_UNEXPOSED_MCP_TOOLS:
            continue
        result = intent_tools.tool_search(name, ('*',), limit=30)
        hits = {tool['name']: tool for tool in result['tools']}
        assert name in hits, f'{name} 未被 tool_search 检索到'
        assert hits[name]['external_only'] is True
        if hits[name]['intent'] is not None:
            pytest.fail(f'{name} 标为仅外部 MCP，却带归属 {hits[name]["intent"]}')
