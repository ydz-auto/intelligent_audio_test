# -*- coding: utf-8 -*-
"""INT-2465 汇总评测：12 个 M1 Skill × 10 条 golden tasks 触发准确率 ≥ 90%。

口径是**确定性词面代理**（见 ``skill_trigger.py``）：只读 L1 ``description``
的触发词段 + 本域词汇表，不调用模型。真实模型级评测需要供应商 Key，本 run
不跑，结论在交付评论注明。

同时校验词汇表有 L1 依据（描述里能查到这些词），防止代理替 Skill 兜底。
"""
import io
import json
import os
from collections import Counter

import pytest

from tests.agent_eval.coverage import skill_trigger as trigger

DATASET = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       'datasets', 'skill_trigger_tasks.json')
THRESHOLD = 0.9


def _load():
    with io.open(DATASET, encoding='utf-8') as handle:
        return json.load(handle)


def _tasks_by_skill():
    grouped = {}
    for task in _load()['tasks']:
        grouped.setdefault(task['skill'], []).append(task)
    return grouped


def test_dataset_covers_12_m1_skills_with_10_tasks_each():
    doc = _load()
    grouped = _tasks_by_skill()
    assert set(grouped) == set(trigger.M1_SKILLS) | set(trigger.EXTRA_SKILLS)
    for name in trigger.M1_SKILLS:
        assert len(grouped[name]) == 10, f'{name} 任务数 {len(grouped[name])}'
        assert len({t['query'] for t in grouped[name]}) == 10
    assert len(grouped['platform-reference']) == 10
    assert len(doc['tasks']) == 130
    assert set(doc['tiers']['m1']) == set(trigger.M1_SKILLS)


def test_domain_terms_have_l1_basis():
    """域词汇表里的每个词都必须出现在该 Skill 的 L1 描述中。"""
    registry = trigger.load_skills()
    for skill in registry.skills:
        if skill.name not in trigger.DOMAIN_TERMS:
            continue
        description = skill.description.lower()
        missing = [term for term in trigger.DOMAIN_TERMS[skill.name]
                   if term.lower() not in description]
        assert not missing, f'{skill.name} 的词汇表缺 L1 依据：{missing}'


def test_m1_trigger_accuracy_at_least_90_percent():
    registry = trigger.load_skills()
    grouped = _tasks_by_skill()
    failures = []
    per_skill = {}
    for name in trigger.M1_SKILLS:
        tasks = grouped[name]
        hits = 0
        for task in tasks:
            got, score, longest = trigger.route(task['query'], registry)
            if got == name:
                hits += 1
            else:
                failures.append({
                    'skill': name, 'query': task['query'],
                    'got': got, 'score': score, 'longest': longest,
                })
        per_skill[name] = hits / len(tasks)
        assert per_skill[name] >= THRESHOLD, (
            f'{name} 触发准确率 {per_skill[name]:.0%} < 90%；'
            f'失败项：{[f["query"] for f in failures if f["skill"] == name]}')
    overall = sum(per_skill.values()) / len(per_skill)
    assert overall >= THRESHOLD, f'12 Skill 平均触发准确率 {overall:.0%}'
    assert not failures, failures


def test_platform_reference_regression_still_triggers():
    """M0 的 platform-reference 不在 12 Skill 口径内，单独回归。"""
    registry = trigger.load_skills()
    tasks = _tasks_by_skill()['platform-reference']
    hits = sum(1 for task in tasks
               if trigger.route(task['query'], registry)[0]
               == 'platform-reference')
    assert hits / len(tasks) >= THRESHOLD, f'platform-reference {hits}/10'


def test_no_cross_domain_false_positive():
    """其它域的 query 不应被本域 Skill 抢走（跨域误命中率 ≤ 5%）。"""
    registry = trigger.load_skills()
    tasks = _load()['tasks']
    wrong = [
        (task['skill'], task['query'], trigger.route(task['query'], registry)[0])
        for task in tasks
        if trigger.route(task['query'], registry)[0] != task['skill']
    ]
    assert len(wrong) / len(tasks) <= 0.05, f'跨域误命中：{wrong}'
    assert not wrong


def test_skill_registry_loads_without_errors():
    registry = trigger.load_skills()
    assert len(registry.skills) == 13
    assert registry.issues == ()


def test_trigger_terms_are_non_empty_and_unique():
    registry = trigger.load_skills()
    for name in trigger.ALL_SKILLS:
        skill = registry.get(name)
        assert skill is not None, name
        terms = trigger.skill_terms(name, skill.description)
        assert len(terms) >= 5, f'{name} 触发词过少'
        assert len(terms) == len(set(terms)), f'{name} 触发词重复'
