# -*- coding: utf-8 -*-
"""Skill 装载与触发评测辅助（INT-2463 报告域）。

触发评测是一个**确定性代理**：用「域标记词」判定一条口语 query 应该命中
`report-studio`（取数 / 指标解释 / 起草）还是 `report-compare`（对比 / 趋势 /
异常），并回查这些标记词确实出现在对应 Skill 的 L1 触发词段里——描述没写到的
词不能让代理替它兜底。真实模型级触发准确率归 INT-2465，本卡只保证 L1 描述
可用且两个 Skill 不互相抢词。
"""
import os
import re
from typing import Iterable, List, Optional, Tuple

from agent_service.application.skill_registry import SkillRegistry
from agent_service.infrastructure.skill.fs_skill_repository import (
    FsSkillRepository,
)
from shared.agent_tools.intent_tools import INTENT_TOOLS

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

SKILL_STUDIO = 'report-studio'
SKILL_COMPARE = 'report-compare'
REPORT_SKILLS = (SKILL_STUDIO, SKILL_COMPARE)

# 对比 / 趋势 / 异常：只要有这些词就归 report-compare。
COMPARE_MARKERS: Tuple[str, ...] = (
    '对比', '二次对比', '并排', '差异', '趋势', '异常', '环比', '同比')

# 取数 / 指标解释 / 起草：没有对比标记时归 report-studio。
STUDIO_MARKERS: Tuple[str, ...] = (
    '报告', '指标', '用例', '统计', '进度', '页签', '起草', '版本',
    '平均值', '详情')

# 触发词段：描述里「触发词：」到「不适用：」之间
_TRIGGER_SECTION = re.compile(r'触发词[：:]\s*(.+?)(?:。不适用|不适用|$)', re.S)


def skills_root() -> str:
    return os.path.join(_PROJECT_ROOT, 'skills')


def load_skills() -> SkillRegistry:
    return SkillRegistry(
        FsSkillRepository(skills_root()),
        known_tools=lambda: [t.name for t in INTENT_TOOLS]).load()


def get_skill(name: str = SKILL_STUDIO):
    return load_skills().get(name)


def skill_body(name: str = SKILL_STUDIO) -> str:
    skill = get_skill(name)
    assert skill is not None, name
    return skill.body


def skill_meta(name: str = SKILL_STUDIO):
    skill = get_skill(name)
    assert skill is not None, name
    return skill.meta


def trigger_section(description: str) -> str:
    """取 L1 description 的「触发词：…」整段（折叠换行）。"""
    text = ' '.join((description or '').split())
    match = _TRIGGER_SECTION.search(text)
    return match.group(1) if match else ''


def route(query: str) -> Optional[str]:
    """返回应命中的报告 Skill 名；都不命中返回 None。"""
    for marker in COMPARE_MARKERS:
        if marker in query:
            return SKILL_COMPARE
    for marker in STUDIO_MARKERS:
        if marker in query:
            return SKILL_STUDIO
    return None


def accuracy(queries: Iterable[Tuple[str, Optional[str]]]) -> float:
    """按 (query, 期望 Skill) 计算命中率。"""
    pairs: List[Tuple[str, Optional[str]]] = list(queries)
    if not pairs:
        return 0.0
    hits = sum(1 for query, expected in pairs if route(query) == expected)
    return hits / len(pairs)
