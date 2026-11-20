# -*- coding: utf-8 -*-
"""INT-2463 两个报告 Skill：L1/L2、只读 allowed-tools、触发准确率。

验收锚点（卡面可测标准 3、4）：
3. `report-studio` / `report-compare` 触发准确率 ≥ 90%，allowed-tools 只含只读工具；
4. 指标解释必须引用接口原文（Skill 正文硬规则），对比不派生数值。
"""
import pytest

from agent_service.domain.enums import (
    SkillIssueCode, SkillIssueSeverity, ToolRisk,
)
from shared.agent_tools import intent_tools
from shared.agent_tools.intent_tools import (
    REPORT_COMPARE_ACTIONS, REPORT_QUERY_ACTIONS,
)
from tests.agent_eval.domains.report import fixtures
from tests.agent_eval.domains.report.skill_support import (
    COMPARE_MARKERS, SKILL_COMPARE, SKILL_STUDIO, STUDIO_MARKERS,
    get_skill, load_skills, route, skill_body, skill_meta, trigger_section,
)


def test_both_skills_load_without_errors_or_unknown_tools():
    registry = load_skills()
    for name in (SKILL_STUDIO, SKILL_COMPARE):
        skill = registry.get(name)
        assert skill is not None, f'skills/{name}/SKILL.md 未被装载'
        fatal = [i for i in registry.issues_for(name)
                 if i.severity is SkillIssueSeverity.ERROR]
        assert fatal == [], fatal
        assert skill.body_line_count <= 500, name
    unknown = [i for i in registry.issues
               if i.code is SkillIssueCode.UNKNOWN_TOOL]
    assert unknown == []


@pytest.mark.parametrize('name,permissions', [
    (SKILL_STUDIO, {'report:read', 'report:create', 'report:studio:create',
                    'report:studio:edit', 'report:studio:undo',
                    'report:studio:export'}),
    (SKILL_COMPARE, {'report:read', 'report:compare'}),
])
def test_upstream_contracts(name, permissions):
    meta = skill_meta(name)
    assert meta.name == name
    assert meta.description.strip()
    assert meta.version and meta.owner
    assert set(meta.permissions) == permissions
    assert 0 < meta.max_tool_calls <= 40
    assert meta.max_tokens and meta.max_tokens <= 60000
    body = skill_body(name)
    assert '## Gotchas' in body
    assert '## 验收' in body


# M2 起 report-studio 声明写工具（INT-2471）；report-compare 仍只声明只读工具。
STUDIO_WRITE_TOOLS = frozenset({'report_generate', 'report_export'})


@pytest.mark.parametrize('name,tool', [
    (SKILL_STUDIO, 'report_query'),
    (SKILL_COMPARE, 'report_compare'),
])
def test_allowed_tools_exist_enabled_and_scoped(name, tool):
    """M1 只挂只读工具；INT-2471 起 Studio 写工具也在白名单内（README 口径）。"""
    meta = skill_meta(name)
    assert meta.allowed_tools, 'allowed-tools 不能为空'
    for tool_name in meta.allowed_tools:
        registered = intent_tools.INTENT_TOOL_BY_NAME.get(tool_name)
        assert registered is not None, f'未注册工具：{tool_name}'
        assert registered.enabled is True, f'工具未启用：{tool_name}'
        if tool_name in STUDIO_WRITE_TOOLS:
            assert name == SKILL_STUDIO, f'{name} 不应声明写工具 {tool_name}'
            assert ToolRisk(registered.risk) is ToolRisk.WRITE
            continue
        assert ToolRisk(registered.risk) is ToolRisk.READ, f'非只读工具：{tool_name}'
    assert tool in meta.allowed_tools
    assert metadata_has_write_tools(name, meta)


def metadata_has_write_tools(name, meta):
    """Studio 必须声明两个写工具；compare 不得声明任何写工具。"""
    if name == SKILL_STUDIO:
        assert STUDIO_WRITE_TOOLS <= set(meta.allowed_tools)
    else:
        assert not (STUDIO_WRITE_TOOLS & set(meta.allowed_tools))
    return True


def test_studio_skill_documents_every_query_action():
    body = skill_body(SKILL_STUDIO)
    for action in REPORT_QUERY_ACTIONS:
        assert f'`{action}`' in body, f'L2 正文没有覆盖动作 {action}'
    # 写链路必须写明：提案 / 审批 / 执行，且不得把提案说成已执行
    assert 'report_generate' in body and 'report_export' in body
    assert '提案' in body and '审批' in body
    assert 'APPROVAL_REQUIRED' in body
    assert '已提交审批' in body or '批准后' in body


def test_studio_skill_documents_write_chain_topics():
    """卡面要求：生成 vs 重生成、OTS 版本口径、导出格式与失败处置。"""
    body = skill_body(SKILL_STUDIO)
    for action in ('generate', 'regenerate', 'studio_draft', 'studio_edit',
                   'studio_restore'):
        assert f'`{action}`' in body, f'L2 正文没有覆盖写动作 {action}'
    # 生成 vs 重生成
    assert 'exists' in body and 'generating' in body
    assert '软删' in body and '回收站' in body
    # 版本（乐观锁 / 恢复产生新版本）
    assert 'expected_version' in body and '乐观锁' in body
    assert '409' in body and 'restore' in body
    # 导出格式与失败处置
    for fmt in ('pdf', 'pptx', 'html', 'md'):
        assert f'`{fmt}`' in body, fmt
    assert 'download_ref' in body and 'pending' in body and 'failed' in body
    assert '403' in body and '404' in body


def test_compare_skill_documents_every_compare_action():
    body = skill_body(SKILL_COMPARE)
    for action in REPORT_COMPARE_ACTIONS:
        assert f'`{action}`' in body, f'L2 正文没有覆盖动作 {action}'
    for field in ('report_ids', 'trend_type', 'metric', 'start_time', 'end_time'):
        assert field in body, field
    assert 'M2' in body and '审批' in body


def test_studio_skill_documents_metric_explanation_fields():
    """指标解释依赖的字段与量纲口径必须在正文里（否则模型会自己算）。"""
    body = skill_body(SKILL_STUDIO)
    for field in ('all_metrics', 'unit', 'decimal_places', 'statistic_method',
                  'agg_denominator', 'dimension_type', 'parent_dimension_id',
                  'metric_data', 'tag_metric_data', 'case_type_stats',
                  'device_stats', 'api_stats', 'resources', 'resource_headers',
                  'summary', 'pass_rate', 'total_cases', 'completed_cases',
                  'failed_cases', 'raw_data'):
        assert field in body, f'缺字段说明：{field}'
    assert '引用' in body and '原文' in body
    assert '不' in body and ('二次计算' in body or '重算' in body)


def test_studio_skill_documents_response_shapes_and_boundaries():
    body = skill_body(SKILL_STUDIO)
    # 列表信封 / 进度响应态 / 页签计数 / 统计维度
    for token in ('items', 'total', 'pages', 'progress', 'report_status',
                  'tab_counts', 'anomaly', 'dimension'):
        assert token in body, token
    # 生成中不是 status；private 404 防探测；导出二进制通道
    assert 'generating' in body and 'published' in body
    assert 'private' in body and '404' in body
    assert '二进制' in body


def test_compare_skill_documents_matrix_and_gotchas():
    body = skill_body(SKILL_COMPARE)
    for token in ('reports', 'missing', 'source_task_ids', 'time_trend',
                  'dimension_trend', 'secondary_comparison', 'anomaly',
                  'artifact'):
        assert token in body, token
    # 不派生数值 / 一次最多 10 份 / 不落报告
    assert '差值' in body and '增长率' in body
    assert '10' in body
    assert '不落' in body or '不会出现在报告列表' in body


def test_trigger_markers_are_declared_in_descriptions():
    """离线触发代理用的标记词必须真的写进 L1 触发词段，不能靠测试替它兜底。"""
    studio = trigger_section(skill_meta(SKILL_STUDIO).description)
    compare = trigger_section(skill_meta(SKILL_COMPARE).description)
    assert studio and compare
    missing_studio = [m for m in STUDIO_MARKERS if m not in studio]
    missing_compare = [m for m in COMPARE_MARKERS if m not in compare]
    assert missing_studio == [], missing_studio
    assert missing_compare == [], missing_compare
    # 两个 Skill 的「不适用」边界要互相指向对方
    assert SKILL_COMPARE in skill_meta(SKILL_STUDIO).description
    assert SKILL_STUDIO in skill_meta(SKILL_COMPARE).description


def test_trigger_accuracy_at_least_90_percent():
    cases = [(query, SKILL_STUDIO) for query in fixtures.STUDIO_POSITIVE]
    cases += [(query, SKILL_COMPARE) for query in fixtures.COMPARE_POSITIVE]
    cases += [(query, None) for query in fixtures.TRIGGER_NEGATIVE]
    hits = [query for query, expected in cases if route(query) == expected]
    accuracy = len(hits) / len(cases)
    misses = [(q, e, route(q)) for q, e in cases if route(q) != e]
    assert accuracy >= 0.9, f'触发准确率 {accuracy:.0%} < 90%；未命中：{misses}'


def test_compare_queries_do_not_route_to_studio_and_vice_versa():
    for query in fixtures.COMPARE_POSITIVE:
        assert route(query) == SKILL_COMPARE, query
    for query in fixtures.STUDIO_POSITIVE:
        assert route(query) == SKILL_STUDIO, query


def test_off_domain_queries_hit_no_report_skill():
    for query in fixtures.TRIGGER_NEGATIVE:
        assert route(query) is None, query
