# -*- coding: utf-8 -*-
"""Skill 装载与触发评测辅助（INT-2459 设备 / SPL / 驱动提案）。

触发评测是一个**确定性代理**：用 Skill L1 description 里的「触发词」+ 本域核心词
做词面匹配，验证描述能让本域问题稳定命中对应 Skill、域外问题不误命中。
真实模型级触发准确率评测归统一评测器，本卡只保证 L1 描述可用。
"""
import os
import re
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from agent_service.application.skill_registry import SkillRegistry
from agent_service.infrastructure.skill.fs_skill_repository import (
    FsSkillRepository,
)
from shared.agent_tools.intent_tools import INTENT_TOOLS

SKILL_NAMES: Tuple[str, ...] = (
    'device-operations', 'spl-calibration', 'driver-proposal')

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))


def skills_root() -> str:
    return os.path.join(_PROJECT_ROOT, 'skills')


def load_skills() -> SkillRegistry:
    return SkillRegistry(
        FsSkillRepository(skills_root()),
        known_tools=lambda: [t.name for t in INTENT_TOOLS]).load()


def get_skill(name: str):
    return load_skills().get(name)


def skill_body(name: str) -> str:
    skill = get_skill(name)
    assert skill is not None, name
    return skill.body


def skill_meta(name: str):
    skill = get_skill(name)
    assert skill is not None, name
    return skill.meta


# ---------------------------------------------------------------- 触发评测

# 描述里「触发词：」之后到「不适用」/句号为止的一段
_TRIGGER_SECTION = re.compile(r'触发词[：:]\s*(.+?)(?:。|不适用|$)', re.S)
_SPLIT = re.compile(r'[、，,；;\s]+')

# 本域核心词：只属于该 Skill，避免口语问题跨域同分。触发词里的通用词
# （设备 / 状态 / 校准等）也按域收敛，不互相借词。
CORE_TERMS: Dict[str, Tuple[str, ...]] = {
    'device-operations': (
        '设备', '分组', '告警', '序列号', '状态历史', '健康检查', '连接',
        '重启', '扫描', '安装', '实验室', '驱动关键词', '在线', '离线', '占用'),
    'spl-calibration': (
        'SPL', '声压级', '校准', '测试音', '映射', '增益', '数字域', 'RMS',
        '播放设备', '校准点', '数字 SPL'),
    'driver-proposal': (
        '驱动提案', '驱动代码', '生成驱动', 'AppDriver', 'ApiVendorAdapter',
        '适配器', 'UiAutoDev', '元素', '能力画像', '提案', '驱动生成',
        '同类驱动', '驱动模板', '驱动覆盖率'),
}


def trigger_terms(description: str,
                  core_terms: Iterable[str] = ()) -> List[str]:
    """解析 L1 description 的触发词段，并补入本域核心词（去重保序）。"""
    text = ' '.join((description or '').split())
    section = _TRIGGER_SECTION.search(text)
    raw = section.group(1) if section else text
    terms = [t.strip() for t in _SPLIT.split(raw) if len(t.strip()) >= 2]
    terms.extend(core_terms)
    seen, ordered = set(), []
    for term in terms:
        if term not in seen:
            seen.add(term)
            ordered.append(term)
    return ordered


def score_skill(description: str, query: str,
                core_terms: Iterable[str] = ()) -> int:
    return sum(1 for term in trigger_terms(description, core_terms)
               if term in query)


def route(query: str, skills: Optional[Iterable] = None
          ) -> Tuple[Optional[str], int]:
    """返回 (命中的 Skill 名, 命中分数)；0 分视为未命中。

    平局时取目录序第一个（与 SkillRegistry 的排序一致）。
    """
    skills = list(skills if skills is not None else load_skills().skills)
    best_name: Optional[str] = None
    best_score = 0
    for skill in skills:
        score = score_skill(skill.description, query,
                            CORE_TERMS.get(skill.name, ()))
        if score > best_score:
            best_name, best_score = skill.name, score
    return best_name, best_score


def trigger_accuracy(positives: Sequence[str], negatives: Sequence[str],
                     skill_name: str) -> Tuple[float, List[str], List[str]]:
    """本 Skill 的触发准确率 = （正例命中 + 负例未误命中）/ 总数。"""
    misses = [q for q in positives if route(q)[0] != skill_name]
    false_positives = [q for q in negatives if route(q)[0] == skill_name]
    total = len(positives) + len(negatives)
    correct = (len(positives) - len(misses)) + (
        len(negatives) - len(false_positives))
    return correct / total, misses, false_positives


__all__ = [
    'CORE_TERMS', 'SKILL_NAMES', 'get_skill', 'load_skills', 'route',
    'score_skill', 'skill_body', 'skill_meta', 'skills_root',
    'trigger_accuracy', 'trigger_terms',
]
