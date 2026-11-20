# -*- coding: utf-8 -*-
"""Skill 触发评测代理（INT-2465 汇总；INT-2475 纳入 M2 的 app-api-onboarding）。

口径：**确定性词面代理**，不是真实模型调用。评分只用 Skill 的 L1
``description``（「触发词：」段）+ 本域词汇表；同域近义说法靠词汇表收敛，
避免「描述没写、代理替它兜底」。真实模型级触发评测需要供应商 Key / 计费
通道，五层门禁（``tests/agent_eval/gate.py``）默认跑本代理，结论按代理口径
表述，不冒充模型实测。

评分 = Σ(命中词长度²)，域词汇表与触发词同权；平局先比最长命中词，再比
Skill 名（与 SkillRegistry 目录序一致）。0 分视为未命中。
"""
from __future__ import annotations

import os
from typing import Dict, Iterable, List, Tuple

from agent_service.application.skill_registry import SkillRegistry
from agent_service.infrastructure.skill.fs_skill_repository import (
    FsSkillRepository,
)
from shared.agent_tools.intent_tools import INTENT_TOOLS

# 方案 §4.3 的 12 个 M1 Skill（platform-reference 是 M0，单独作回归）
M1_SKILLS: Tuple[str, ...] = (
    'algorithm-config', 'audio-import', 'device-operations', 'driver-proposal',
    'evaluation-config', 'log-diagnostics', 'report-compare', 'report-studio',
    'spl-calibration', 'tag-group', 'task-operations', 'testcase-authoring',
)
# M2 追加的 Skill（§4.3 / §6.6）：INT-2475 起纳入「每 Skill ≥10 条」口径
M2_SKILLS: Tuple[str, ...] = ('app-api-onboarding',)
EXTRA_SKILLS: Tuple[str, ...] = ('platform-reference',)
ALL_SKILLS: Tuple[str, ...] = M1_SKILLS + M2_SKILLS + EXTRA_SKILLS

# 域词汇表：每个 Skill 的口语核心词（与 L1 触发词同域，不跨域借词）。
# 词汇表只做「同义收敛」，不替代 description —— 测试同时校验这些词能在
# L1 描述里找到依据（见 test_skill_trigger_accuracy）。
DOMAIN_TERMS: Dict[str, Tuple[str, ...]] = {
    'algorithm-config': (
        '算法定义', '算法参数', '参考参数', '参数映射', '表单', '算法选项',
        '算法分组', '热重载', '算法维度'),
    'audio-import': (
        '音频', '音频列表', 'md5', '目录树', '采样率', '音频质量',
        '播放历史', '导入前'),
    'device-operations': (
        '设备', '告警', '序列号', '状态历史', '健康检查', '连接', '重启',
        '扫描', '驱动关键词'),
    'driver-proposal': (
        '驱动', 'appdriver', 'apivendoradapter', '适配器', 'uiautodev',
        '元素树', '操作轨迹', '能力画像', '驱动模板'),
    'evaluation-config': (
        '评估维度', '维度配置', '评分', '权重', '评估分类', '重评估',
        '聚合分母'),
    'log-diagnostics': ('日志', '报错', '异常日志', '日志级别', '日志来源'),
    'report-compare': (
        '报告对比', '对比报告', '二次对比', '并排', '报告差异', '指标差异',
        '通过率对比', '报告趋势', '异常报告', '环比', '同比'),
    'report-studio': (
        '报告列表', '报告详情', '报告指标', '报告统计', '报告进度', '页签',
        '通过率', '平均分', '报告起草', '报告版本'),
    'spl-calibration': (
        'spl', '声压级', '校准', '测试音', '增益', '数字域', 'rms',
        '播放设备'),
    'tag-group': ('标签', '打标', '用例分组', '分组可见性', '分组用例数'),
    'task-operations': (
        '任务列表', '任务详情', '执行进度', '任务统计', '通过率', '失败用例',
        '失败原因', '任务诊断', '重测', '用例执行', '任务实验室'),
    'testcase-authoring': (
        '用例', '轮次', '参考参数', '用例导出', '用例统计', '分组下的用例',
        '标注生成用例', '用例变体'),
    'app-api-onboarding': (
        '接入 app', '接入 api', '接入包', 'onboarding', '测量路径',
        '冒烟用例', 'ui_trace', 'capabilities', '接入计划', '缺口清单'),
    'platform-reference': (
        '接口', '字段', '枚举', '权限码', 'schema', 'tool_search', '平台',
        '状态枚举', '返回的是什么类型'),
}

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))


def skills_root() -> str:
    return os.path.join(_PROJECT_ROOT, 'skills')


def load_skills(root: str = None) -> SkillRegistry:
    return SkillRegistry(
        FsSkillRepository(root or skills_root()),
        known_tools=lambda: [t.name for t in INTENT_TOOLS]).load()


def trigger_terms(description: str) -> List[str]:
    """L1 描述的「触发词：」段 → 小写词列表（去重保序）。

    INT-2549：实现迁到 ``agent_service.application.skill_trigger``（发布门槛
    与评测共用同一份），这里只做转出，不再各写一套。
    """
    from agent_service.application.skill_trigger import (
        trigger_terms as _trigger_terms,
    )
    return _trigger_terms(description)


def skill_terms(skill_name: str, description: str) -> List[str]:
    terms = trigger_terms(description)
    seen, ordered = set(terms), list(terms)
    for term in DOMAIN_TERMS.get(skill_name, ()):
        token = term.lower()
        if token not in seen:
            seen.add(token)
            ordered.append(token)
    return ordered


def score_skill(terms: Iterable[str], query: str) -> Tuple[int, int]:
    """返回 (分数, 最长命中词长度)。命中词按长度平方加权（生产侧同一实现）。"""
    from agent_service.application.skill_trigger import (
        score_skill as _score_skill,
    )
    return _score_skill(terms, query)


def route(query: str, registry: SkillRegistry = None) -> Tuple:
    """返回 (命中的 Skill 名或 None, 分数, 最长命中词长)。"""
    registry = registry or load_skills()
    best = (0, 0, '')
    for skill in registry.skills:
        if skill.name not in ALL_SKILLS:
            continue
        score, longest = score_skill(
            skill_terms(skill.name, skill.description), query)
        candidate = (score, longest, skill.name)
        if candidate > best:
            best = candidate
    return (best[2] or None), best[0], best[1]


def describe(registry: SkillRegistry = None) -> Dict[str, List[str]]:
    registry = registry or load_skills()
    return {skill.name: skill_terms(skill.name, skill.description)
            for skill in registry.skills if skill.name in ALL_SKILLS}


__all__ = [
    'ALL_SKILLS', 'DOMAIN_TERMS', 'EXTRA_SKILLS', 'M1_SKILLS', 'M2_SKILLS',
    'describe', 'load_skills', 'route', 'score_skill', 'skill_terms',
    'skills_root',
]
