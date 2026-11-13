# -*- coding: utf-8 -*-
"""tool_search 关键词索引与检索（INT-2453，方案 §6.1）。

索引对象：205 个外部 MCP 工具（宿主语境专用工具除外，见
``intent_tools.AGENT_UNEXPOSED_MCP_TOOLS``）+ 31 个意图工具（含 5 个预留名称）。
中文关键词通过双语词表扩展为英文工具名片段，命中后返回**子集 Schema**，
模型可直接照 Schema 调用；命中工具在真正执行时仍走 ToolGateway 权限校验。
"""
from __future__ import annotations

from typing import Dict, List, Sequence

from shared.agent_tools.intent_tools import TOOL_INDEX

DEFAULT_LIMIT = 10
MAX_LIMIT = 30

# 中文意图词 → 工具名 / 描述里的英文片段（只做召回扩展，不做语义推理）
_SYNONYMS: Dict[str, Sequence[str]] = {
    '任务': ('task',),
    '列表': ('list',),
    '详情': ('get', 'detail'),
    '报告': ('report',),
    '音频': ('audio',),
    '用例': ('testcase', 'case'),
    '标签': ('tag',),
    '分组': ('group',),
    '评估': ('evaluation',),
    '评分': ('evaluation', 'score'),
    '维度': ('dimension', 'evaluation'),
    '算法': ('algorithm',),
    '参数': ('param',),
    '映射': ('mapping', 'map'),
    '设备': ('device',),
    '播放': ('playback',),
    '实验室': ('laborator', 'lab'),
    '日志': ('log',),
    '首页': ('home', 'dashboard'),
    '基准': ('benchmark',),
    '收藏': ('favorite',),
    '回收站': ('trash',),
    '导出': ('export',),
    '导入': ('import',),
    '生成': ('generate', 'create'),
    '对比': ('compare',),
    '统计': ('stat',),
    '进度': ('progress',),
    '校验': ('validate', 'check'),
    '启动': ('start',),
    '停止': ('stop',),
    '重试': ('retry',),
    '合并': ('merge',),
    '校准': ('calibrate', 'spl'),
    '标定': ('calibrate',),
    'JSON': ('json',),
    'PPT': ('pptx', 'ppt'),
    'PDF': ('pdf',),
    'HTML': ('html',),
    'Markdown': ('md', 'markdown'),
    '记忆': ('memory',),
    '界面': ('ui',),
    '探索': ('ui', 'explore'),
    '接口': ('api',),
    '契约': ('spec', 'contract', 'api'),
    '驱动': ('driver', 'propose'),
    '审批': ('approval',),
    '权限': ('permission', 'role'),
    '用户': ('user',),
    '角色': ('role',),
    '状态': ('status',),
    '告警': ('alarm',),
    '复核': ('review',),
    '挑选': ('cherry', 'pick'),
    '回收': ('trash',),
    '工具': ('tool',),
}


def _terms(query: str) -> List[str]:
    """把查询拆成英文检索词：原文 token + 中文词表扩展。"""
    lowered = (query or '').strip().lower()
    terms: List[str] = []
    for token in lowered.replace('，', ' ').replace(',', ' ').split():
        if token:
            terms.append(token)
    for word, expansions in _SYNONYMS.items():
        if word.lower() in lowered:
            terms.extend(x.lower() for x in expansions)
    # 中文整串本身也保留（描述里可能直接包含中文）
    if lowered:
        terms.append(lowered)
    seen = set()
    ordered = []
    for term in terms:
        if term and term not in seen:
            seen.add(term)
            ordered.append(term)
    return ordered


def _score(tool: dict, terms: Sequence[str], lowered_query: str) -> int:
    name = (tool.get('name') or '').lower()
    description = (tool.get('description') or '').lower()
    score = 0
    for term in terms:
        if name == term:
            score += 100
        elif term in name:
            score += 50
        if term in description:
            score += 10
    if lowered_query and lowered_query in name:
        score += 30
    return score


def _granted(granted: Sequence[str], required: Sequence[str]) -> bool:
    """权限为 OR 语义；`*` 通配；required 为空表示仅需登录。"""
    if not required:
        return True
    perms = set(granted or ())
    if '*' in perms:
        return True
    return bool(perms & set(required))


def search(query: str, permissions: Sequence[str], *, limit: int = DEFAULT_LIMIT,
           include_reserved: bool = True) -> dict:
    """检索工具索引，返回 ``{query, total, tools[]}``。

    - 权限不满足的工具不返回（与 Agent 可见工具口径一致）；
    - reserved 工具默认返回（用于发现「以后支持」的能力），``enabled=False``
      明示当前不可调用。
    """
    limit = max(1, min(int(limit or DEFAULT_LIMIT), MAX_LIMIT))
    lowered = (query or '').strip().lower()
    terms = _terms(query)
    scored = []
    for tool in TOOL_INDEX:
        if not _granted(permissions, tool.get('permissions') or ()):
            continue
        if not include_reserved and tool.get('enabled') is False:
            continue
        score = _score(tool, terms, lowered)
        if score > 0:
            scored.append((score, tool))
    scored.sort(key=lambda item: (-item[0], item[1]['name']))
    tools = []
    for _, tool in scored[:limit]:
        tools.append({
            'name': tool['name'],
            'description': tool['description'],
            'inputSchema': tool['inputSchema'],
            'permissions': list(tool.get('permissions') or []),
            'risk': tool.get('risk', 'READ'),
            'kind': tool.get('kind', 'mcp'),
            'enabled': tool.get('enabled', True),
        })
    return {'query': query, 'total': len(tools), 'tools': tools}


__all__ = ['DEFAULT_LIMIT', 'MAX_LIMIT', 'search']
