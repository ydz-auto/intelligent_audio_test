# -*- coding: utf-8 -*-
"""Skill 装载与触发评测辅助（INT-2462）。

触发评测是一个**确定性代理**：用 Skill L1 description 里的「触发词」做词面
匹配，验证描述能让评估域问题稳定命中 `evaluation-config`、域外问题不误命中。
真实模型级的触发准确率评测归 INT-2465，本卡只保证 L1 描述可用。
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


def skills_root() -> str:
    return os.path.join(_PROJECT_ROOT, 'skills')


def load_skills() -> SkillRegistry:
    return SkillRegistry(
        FsSkillRepository(skills_root()),
        known_tools=lambda: [t.name for t in INTENT_TOOLS]).load()


def get_skill(name: str = 'evaluation-config'):
    return load_skills().get(name)


def skill_body(name: str = 'evaluation-config') -> str:
    skill = get_skill(name)
    assert skill is not None, name
    return skill.body


def skill_meta(name: str = 'evaluation-config'):
    skill = get_skill(name)
    assert skill is not None, name
    return skill.meta


# ---------------------------------------------------------------- 触发评测

# 描述里「触发词：」之后到句号/换行为止的一段
_TRIGGER_SECTION = re.compile(r'触发词[：:]\s*(.+?)(?:。|不适用|$)', re.S)
_SPLIT = re.compile(r'[、，,；;\s]+')

# 领域核心词也参与匹配（描述里的短语常被口语拆开，如「维度 121 的配置」）
_CORE_TERMS = ('评估', '维度', '评分', '分类', '权重', '重评估')


def trigger_terms(description: str) -> List[str]:
    section = _TRIGGER_SECTION.search(description or '')
    raw = section.group(1) if section else (description or '')
    terms = [t.strip() for t in _SPLIT.split(raw) if len(t.strip()) >= 2]
    terms.extend(_CORE_TERMS)
    seen, ordered = set(), []
    for term in terms:
        if term not in seen:
            seen.add(term)
            ordered.append(term)
    return ordered


def score_skill(description: str, query: str) -> int:
    return sum(1 for term in trigger_terms(description) if term in query)


def route(query: str, skills: Optional[Iterable] = None
          ) -> Tuple[Optional[str], int]:
    """返回 (命中的 Skill 名, 命中分数)；0 分视为未命中。"""
    skills = list(skills if skills is not None else load_skills().skills)
    best_name: Optional[str] = None
    best_score = 0
    for skill in skills:
        score = score_skill(skill.description, query)
        if score > best_score:
            best_name, best_score = skill.name, score
    return best_name, best_score
