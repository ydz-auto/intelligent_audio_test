# -*- coding: utf-8 -*-
"""Skill 装载与触发评测辅助（INT-2460）。

触发评测是**确定性代理**：用 Skill L1 description 里的「触发词」+ 本域核心词
做词面匹配，验证两个新 Skill 的描述能让用例域 / 标签域问题稳定命中，且其它域
问题不误命中。真实模型级触发准确率评测归 INT-2465。

评分口径与 ``tests/agent_eval/domains/evaluation/skill_support.py`` 一致：
按命中词打分、核心词只给本域 Skill，跨域同分时平局取目录序第一个。
"""
import os
import re
from typing import Iterable, List, Optional, Tuple

from agent_service.application.skill_registry import SkillRegistry
from agent_service.infrastructure.skill.fs_skill_repository import (
    FsSkillRepository,
)
from shared.agent_tools.intent_tools import INTENT_TOOLS

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(os.path.join(_HERE, '..', '..', '..', '..'))

# 描述里「触发词：」之后到句号 / 「不适用」为止的一段
_TRIGGER_SECTION = re.compile(r'触发词[：:]\s*(.+?)(?:。|不适用|$)', re.S)
_SPLIT = re.compile(r'[、，,；;\s]+')

# 本域核心词：只属于本域 Skill，避免通用词对所有 Skill 都计分后被别的域抢走。
# 标签域的「分组」不单列（会被用例域口语误抢），用「用例分组」整词。
_CORE_TERMS = {
    'testcase-authoring': ('用例', '轮次', '草案', '变体'),
    'tag-group': ('标签', '打标', '用例分组'),
}


def skills_root() -> str:
    return os.path.join(_PROJECT_ROOT, 'skills')


def load_skills() -> SkillRegistry:
    return SkillRegistry(
        FsSkillRepository(skills_root()),
        known_tools=lambda: [t.name for t in INTENT_TOOLS]).load()


def get_skill(name: str = 'testcase-authoring'):
    return load_skills().get(name)


def skill_body(name: str = 'testcase-authoring') -> str:
    skill = get_skill(name)
    assert skill is not None, name
    return skill.body


def skill_meta(name: str = 'testcase-authoring'):
    skill = get_skill(name)
    assert skill is not None, name
    return skill.meta


# ---------------------------------------------------------------- 触发评测


def trigger_terms(description: str,
                  core_terms: Iterable[str] = ()) -> List[str]:
    """解析 L1 触发词段 + 追加本域核心词（去重保序）。"""
    section = _TRIGGER_SECTION.search(description or '')
    raw = section.group(1) if section else (description or '')
    terms = [t.strip() for t in _SPLIT.split(raw) if len(t.strip()) >= 2]
    terms.extend(core_terms)
    seen, ordered = set(), []
    for term in terms:
        if term and term not in seen:
            seen.add(term)
            ordered.append(term)
    return ordered


def score_skill(description: str, query: str,
                core_terms: Iterable[str] = ()) -> int:
    """命中词按长度加权：更具体的词（如「生成用例草案」）压过通用词。"""
    return sum(len(term) for term in trigger_terms(description, core_terms)
               if term in query)


def _core_terms_for(skill_name: str) -> Tuple[str, ...]:
    return _CORE_TERMS.get(skill_name, ())


def route(query: str, skills: Optional[Iterable] = None
          ) -> Tuple[Optional[str], int]:
    """返回 (命中的 Skill 名, 命中分数)；0 分视为未命中。"""
    skills = list(skills if skills is not None else load_skills().skills)
    skills.sort(key=lambda s: s.name)
    best_name: Optional[str] = None
    best_score = 0
    for skill in skills:
        score = score_skill(skill.description, query, _core_terms_for(skill.name))
        if score > best_score:
            best_name, best_score = skill.name, score
    return best_name, best_score
