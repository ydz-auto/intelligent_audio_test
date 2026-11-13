# -*- coding: utf-8 -*-
"""INT-2462 Skill `evaluation-config`：L1/L2、只读 allowed-tools、触发准确率。

验收锚点（卡面可测标准 3、4）：
3. Skill 触发准确率 ≥ 90%；allowed-tools 只含只读工具；
4. 评分口径解释必须引用维度配置原文（Skill 正文硬规则）。
"""
import pytest

from agent_service.domain.enums import (
    SkillIssueCode, SkillIssueSeverity, ToolRisk,
)
from shared.agent_tools import intent_tools
from tests.agent_eval.domains.evaluation import fixtures
from tests.agent_eval.domains.evaluation.skill_support import (
    get_skill, load_skills, route, skill_body, skill_meta, trigger_terms,
)


def test_skill_loads_without_errors_or_unknown_tools():
    registry = load_skills()
    skill = registry.get('evaluation-config')
    assert skill is not None, 'skills/evaluation-config/SKILL.md 未被装载'
    fatal = [i for i in registry.issues_for('evaluation-config')
             if i.severity is SkillIssueSeverity.ERROR]
    assert fatal == []
    unknown = [i for i in registry.issues
               if i.code is SkillIssueCode.UNKNOWN_TOOL]
    assert unknown == []
    assert skill.body_line_count <= 500


def test_required_sections_and_frontmatter():
    meta = skill_meta()
    assert meta.name == 'evaluation-config'
    assert meta.description.strip()
    assert meta.version and meta.owner
    assert meta.permissions == ('evaluation:read',)
    assert 0 < meta.max_tool_calls <= 40
    assert meta.max_tokens and meta.max_tokens <= 60000
    body = skill_body()
    assert '## Gotchas' in body
    assert '## 验收' in body


def test_allowed_tools_exist_and_are_declared_read_or_m2_write():
    """M1 只挂只读工具；INT-2469 起写入口 `evaluation_manage` 也在白名单内。"""
    meta = skill_meta()
    assert meta.allowed_tools, 'allowed-tools 不能为空'
    for name in meta.allowed_tools:
        tool = intent_tools.INTENT_TOOL_BY_NAME.get(name)
        assert tool is not None, f'未注册工具：{name}'
        assert tool.enabled is True, f'工具未启用：{name}'
        if name == 'evaluation_manage':
            assert ToolRisk(tool.risk) is ToolRisk.WRITE
            continue
        assert ToolRisk(tool.risk) is ToolRisk.READ, f'非只读工具：{name}'
    assert 'evaluation_query' in meta.allowed_tools
    assert 'evaluation_manage' in meta.allowed_tools


def test_skill_explains_scoring_by_quoting_fields():
    body = skill_body()
    for field in ('score_unit', 'result_min', 'result_max', 'decimal_places',
                  'weight', 'statistic_method', 'agg_denominator',
                  'exclude_rounds', 'rule', 'output_fields'):
        assert field in body, f'评分口径未覆盖字段 {field}'
    # 硬规则：引用接口原文、不做二次计算
    assert '引用' in body and '原文' in body
    assert '不' in body and ('二次计算' in body or '自己算' in body)
    assert 'output_fields' in body and 'agg_role' in body


def test_skill_documents_scope_topics():
    body = skill_body()
    for topic in ('导入导出', '健康检查', '重评估前置条件', '可见性',
                  '失败处置', '修改影响面'):
        assert topic in body, topic
    # 写动作边界必须写明：提案 → 审批 → 执行，且不得把提案说成已执行
    assert 'evaluation_manage' in body
    assert '提案' in body and '审批' in body
    assert 'APPROVAL_REQUIRED' in body
    assert '软删' in body


def test_trigger_accuracy_at_least_90_percent():
    positives = fixtures.TRIGGER_POSITIVE
    assert len(positives) >= 10
    hits = [q for q in positives if route(q)[0] == 'evaluation-config']
    accuracy = len(hits) / len(positives)
    assert accuracy >= 0.9, (
        f'触发准确率 {accuracy:.0%} < 90%；未命中：'
        f'{[q for q in positives if q not in hits]}')


@pytest.mark.parametrize('skill_name', [
    'algorithm-config', 'audio-import', 'platform-reference',
])
def test_off_domain_skill_does_not_borrow_evaluation_core_terms(skill_name):
    """INT-2511：评估核心词只属于本域。

    这些通用词若对每个 Skill 都计分，口语化问题会跨域同分，route() 平局取
    目录序第一个（algorithm-config 排在最前），评估域就永远拿不到命中。
    """
    skills = {s.name: s for s in load_skills().skills}
    assert skill_name in skills
    probe = '维度 121 的详细配置是什么？'
    assert route(probe, [skills[skill_name]]) == (None, 0)


@pytest.mark.parametrize('query', fixtures.TRIGGER_NEGATIVE)
def test_off_domain_queries_not_routed_to_evaluation(query):
    assert route(query)[0] != 'evaluation-config', query


def test_trigger_terms_are_present_in_description():
    meta = skill_meta()
    terms = trigger_terms(meta.description)
    assert '评估维度' in terms
    assert '评分口径' in terms
    assert '重评估' in terms
