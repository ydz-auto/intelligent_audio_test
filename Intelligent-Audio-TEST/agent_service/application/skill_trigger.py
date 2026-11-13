# -*- coding: utf-8 -*-
"""Skill 触发的确定性词面代理（INT-2549 发布门槛，复用 INT-2465 口径）。

发布门槛需要「触发判定通过」：本模块把 INT-2465 的确定性触发代理抽成
**生产侧唯一实现**（评测代码直接复用，不新建第二套）。

口径：只读 L1 ``description`` 的「触发词：」段；评分 = Σ(命中词长度²)。
平局先比最长命中词，再比 Skill 名。0 分视为未命中。不做模型判定。
"""
from __future__ import annotations

import re
from typing import Iterable, List, Sequence, Tuple

_TRIGGER_SECTION = re.compile(r'触发词[：:]\s*(.+?)(?:。|不适用|$)', re.S)
_SPLIT = re.compile(r'[、，,；;。\s]+')


def trigger_terms(description: str) -> List[str]:
    """L1 描述的「触发词：」段 → 小写词列表（去重保序）。"""
    text = ' '.join((description or '').split())
    match = _TRIGGER_SECTION.search(text)
    raw = match.group(1) if match else ''
    seen, ordered = set(), []
    for term in _SPLIT.split(raw):
        token = term.strip().lower()
        if len(token) >= 2 and token not in seen:
            seen.add(token)
            ordered.append(token)
    return ordered


def score_skill(terms: Iterable[str], query: str) -> Tuple[int, int]:
    """返回 (分数, 最长命中词长度)。命中词按长度平方加权。"""
    lowered = (query or '').lower()
    hits = [term for term in terms if term in lowered]
    score = sum(len(term) ** 2 for term in hits)
    longest = max((len(term) for term in hits), default=0)
    return score, longest


def matches(description: str, queries: Sequence[str]) -> Tuple[bool, List[str]]:
    """≥1 条 query 命中该 Skill 的触发词 → 通过。

    返回 ``(是否通过, 命中明细)``；命中明细用于发布回执的 ``failures``。
    """
    terms = trigger_terms(description)
    hits: List[str] = []
    for query in queries:
        score, longest = score_skill(terms, query)
        if score > 0:
            hits.append(query)
    return bool(hits), hits


__all__ = ['matches', 'score_skill', 'trigger_terms']
