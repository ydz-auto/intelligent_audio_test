# -*- coding: utf-8 -*-
"""tool_search 关键词 + 轻量语义索引与检索（INT-2453 / INT-2465，方案 §6.1）。

索引对象：205 个外部 MCP 工具（宿主语境专用工具除外，见
``intent_tools.AGENT_UNEXPOSED_MCP_TOOLS``）+ 31 个意图工具。

检索分三层，全部本地、确定性、无外部向量库：

1. **关键词**：工具名（含 ``_`` 分段）与描述的子串匹配；
2. **轻量语义**：中文按二元组（bigram）切分、英文按词切分，做词袋覆盖率
   打分；中文意图词表（``_SYNONYMS``）把「报告 / 音频」等口语扩成英文工具名
   片段，解决中文查询命中英文工具名的问题；同族词（``_CONCEPTS``）把
   「收录 / 回收」这类近义说法收敛到同一概念；
3. **归属**：每条结果带 ``intent``（归属的意图工具）与 ``external_only``
   （仅外部 MCP，不内部暴露），与 ``coverage.py`` 的矩阵同源。

命中后返回可直接调用的 Schema 子集；执行时仍走 ToolGateway 权限校验与
M1 只读门禁，检索结果本身不授予任何权限。
"""
from __future__ import annotations

import re
from typing import Dict, List, Sequence, Set, Tuple

from shared.agent_tools import coverage
from shared.agent_tools.intent_tools import TOOL_INDEX

DEFAULT_LIMIT = 10
MAX_LIMIT = 30

# 名称 / 描述匹配权重（显式常量，避免魔法值散落）
_NAME_EXACT = 100
_NAME_SEGMENT = 60
_NAME_TERM = 45
_NAME_SUBSTRING = 35
_DESC_TERM = 10
_NAME_BIGRAM = 8
_DESC_BIGRAM = 3
_COVERAGE_BONUS = 15

_CJK_RE = re.compile(r'[一-鿿]+')
_SPLIT_RE = re.compile(r'[^0-9a-z一-鿿]+')

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
    '诊断': ('diagnose', 'diagnosis'),
    '报错': ('error', 'log'),
    '错误': ('error',),
    '异常': ('error', 'exception'),
    '失败': ('failed', 'fail', 'error'),
    '重测': ('retest', 'retry'),
    '首页': ('home', 'dashboard'),
    '基准': ('benchmark',),
    '收藏': ('favorite',),
    '回收站': ('trash',),
    '导出': ('export',),
    '导入': ('import',),
    '生成': ('generate', 'create'),
    '对比': ('compare',),
    '统计': ('stat', 'statistics'),
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
    '回收': ('trash', 'restore'),
    '工具': ('tool',),
    '批量': ('batch',),
    '标注': ('annotation', 'annotate'),
    '上传': ('upload',),
    '分片': ('chunk', 'upload'),
    '转码': ('convert',),
    '下载': ('download',),
    '树': ('tree',),
    '目录': ('folder', 'tree'),
    '分享': ('share',),
    '发布': ('publish',),
    '恢复': ('restore', 'recover'),
    '删除': ('delete', 'purge'),
    '彻底': ('purge',),
    '可见性': ('visibility', 'share'),
    '健康检查': ('health', 'check'),
    '序列号': ('serial',),
    '摘要': ('summary',),
    '页签': ('tab',),
    '趋势': ('trend',),
    '二次': ('secondary',),
    '环比': ('trend',),
    '同比': ('trend',),
    '模板': ('template',),
    '表单': ('form', 'schema'),
    '选项': ('option',),
    '热重载': ('reload',),
    '分类': ('category',),
    '排行': ('ranking',),
    '基线': ('baseline',),
}

# 同族词：把口语近义说法收敛到同一个检索概念（比词表更强的轻量语义）
_CONCEPTS: Dict[str, Sequence[str]] = {
    '收录': ('导入',),
    '回收站': ('恢复', '彻底', '删除'),
    '声压级': ('spl', '校准'),
    '数字域': ('digital_spl', 'spl'),
    '物理域': ('spl',),
    '文件夹': ('目录',),
    '草稿': ('draft',),
    '统计报表': ('统计', '报告'),
    '个人收藏': ('收藏',),
}


def _split(text: str) -> List[str]:
    return [token for token in _SPLIT_RE.split((text or '').lower()) if token]


def _cjk_bigrams(text: str) -> List[str]:
    grams: List[str] = []
    for run in _CJK_RE.findall((text or '').lower()):
        if len(run) == 1:
            grams.append(run)
        for index in range(len(run) - 1):
            grams.append(run[index:index + 2])
    return grams


def _terms(query: str) -> List[str]:
    """把查询拆成检索词：英文 token + 中文二元组 + 词表扩展 + 同族词。"""
    lowered = (query or '').strip().lower()
    terms: List[str] = []
    terms.extend(_split(lowered))
    terms.extend(_cjk_bigrams(lowered))
    # 中文整串本身也保留（工具描述里可能直接包含中文短语）
    for run in _CJK_RE.findall(lowered):
        terms.append(run)
    for word, expansions in _SYNONYMS.items():
        if word.lower() in lowered:
            terms.extend(x.lower() for x in expansions)
    for word, expansions in _CONCEPTS.items():
        if word in lowered:
            for expansion in expansions:
                terms.append(expansion)
                terms.extend(_SYNONYMS.get(expansion, ()))
    seen: Set[str] = set()
    ordered: List[str] = []
    for term in terms:
        if term and term not in seen:
            seen.add(term)
            ordered.append(term)
    return ordered


def _name_segments(name: str) -> Set[str]:
    return {part for part in name.split('_') if part}


def _score(tool: dict, terms: Sequence[str], lowered_query: str) -> Tuple[int, int]:
    """返回 (总分, 命中的检索词数)。"""
    name = (tool.get('name') or '').lower()
    description = (tool.get('description') or '').lower()
    segments = _name_segments(name)
    cjk_terms = set(_cjk_bigrams(lowered_query))
    score = 0
    matched = 0
    for term in terms:
        hit = 0
        if name == term:
            hit += _NAME_EXACT
        elif term in segments:
            hit += _NAME_SEGMENT
        elif len(term) >= 3 and term in name:
            hit += _NAME_SUBSTRING
        if term in description:
            hit += _DESC_TERM
        if term in cjk_terms:
            if term in name:
                hit += _NAME_BIGRAM
            elif term in description:
                hit += _DESC_BIGRAM
        if hit:
            matched += 1
            score += hit
    if lowered_query and lowered_query in name:
        score += _NAME_TERM
    if terms and matched:
        score += (_COVERAGE_BONUS * matched) // len(terms)
    return score, matched


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
      明示当前不可调用；
    - 每条结果带 ``intent`` / ``external_only``，与覆盖矩阵同源。
    """
    limit = max(1, min(int(limit or DEFAULT_LIMIT), MAX_LIMIT))
    lowered = (query or '').strip().lower()
    terms = _terms(query)
    scored: List[Tuple[int, int, dict]] = []
    for tool in TOOL_INDEX:
        if not _granted(permissions, tool.get('permissions') or ()):
            continue
        if not include_reserved and tool.get('enabled') is False:
            continue
        score, matched = _score(tool, terms, lowered)
        if score > 0:
            scored.append((score, matched, tool))
    scored.sort(key=lambda item: (-item[0], -item[1], item[2]['name']))
    tools = []
    for _, _, tool in scored[:limit]:
        intent, category = coverage.intent_of(tool['name'])
        tools.append({
            'name': tool['name'],
            'description': tool['description'],
            'inputSchema': tool['inputSchema'],
            'permissions': list(tool.get('permissions') or []),
            'risk': tool.get('risk', 'READ'),
            'kind': tool.get('kind', 'mcp'),
            'enabled': tool.get('enabled', True),
            'intent': intent,
            'external_only': category == coverage.EXTERNAL,
        })
    return {'query': query, 'total': len(tools), 'tools': tools}


__all__ = ['DEFAULT_LIMIT', 'MAX_LIMIT', 'search']
