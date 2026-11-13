# -*- coding: utf-8 -*-
"""INT-2459 Skill `device-operations` / `spl-calibration` / `driver-proposal`。

验收锚点（卡面可测标准 3、4）：
3. 3 个 Skill 触发准确率 ≥ 90%，``allowed-tools`` 只含只读工具；
4. 不编造设备在线状态或校准数值（Skill 正文硬规则 + 只读工具边界）。

另外锁定卡面口径说明：§6.1 没有独立的 SPL 只读意图工具，SPL 只读走
``device_query`` 的 SPL 子集 + ``tool_search`` 长尾，正文必须写明，避免执行者
自造工具名。
"""
import pytest

from agent_service.domain.enums import (
    SkillIssueCode, SkillIssueSeverity, ToolRisk,
)
from shared.agent_tools import device_tools, intent_tools
from tests.agent_eval.domains.device import fixtures
from tests.agent_eval.domains.device.skill_support import (
    SKILL_NAMES, get_skill, load_skills, route, skill_body, skill_meta,
    trigger_accuracy, trigger_terms,
)

READ_ONLY_TOOLS = {'device_query', 'tool_search'}


# ---------------------------------------------------------------- 装载与契约

def test_three_skills_load_without_errors_or_unknown_tools():
    registry = load_skills()
    for name in SKILL_NAMES:
        skill = registry.get(name)
        assert skill is not None, f'skills/{name}/SKILL.md 未被装载'
        fatal = [issue for issue in registry.issues_for(name)
                 if issue.severity is SkillIssueSeverity.ERROR]
        assert fatal == [], (name, [i.message for i in fatal])
        assert skill.body_line_count <= 500, name
    unknown = [issue for issue in registry.issues
               if issue.code is SkillIssueCode.UNKNOWN_TOOL]
    assert unknown == []


@pytest.mark.parametrize('name', SKILL_NAMES)
def test_required_sections_and_frontmatter(name):
    meta = skill_meta(name)
    assert meta.name == name
    assert meta.description.strip()
    assert meta.version and meta.owner
    assert 0 < meta.max_tool_calls <= 40
    assert meta.max_tokens and meta.max_tokens <= 60000
    body = skill_body(name)
    assert '## Gotchas' in body
    assert '## 验收' in body


@pytest.mark.parametrize('name', SKILL_NAMES)
def test_allowed_tools_are_readonly_and_enabled(name):
    meta = skill_meta(name)
    assert meta.allowed_tools, f'{name} allowed-tools 不能为空'
    assert set(meta.allowed_tools) <= READ_ONLY_TOOLS, meta.allowed_tools
    assert 'device_query' in meta.allowed_tools
    for tool_name in meta.allowed_tools:
        tool = intent_tools.INTENT_TOOL_BY_NAME.get(tool_name)
        assert tool is not None, f'未注册工具：{tool_name}'
        assert tool.enabled is True, f'工具未启用：{tool_name}'
        assert ToolRisk(tool.risk) is ToolRisk.READ, f'非只读工具：{tool_name}'
    # M1 只读：禁止把写工具（含 M2 的 driver_propose）放进 allowed-tools
    assert 'device_control' not in meta.allowed_tools
    assert 'spl_calibrate' not in meta.allowed_tools
    assert 'driver_propose' not in meta.allowed_tools


def test_skill_permissions_match_domain_scope():
    assert set(skill_meta('device-operations').permissions) == {'device:read'}
    assert set(skill_meta('spl-calibration').permissions) == {
        'spl:read', 'digital_spl:read'}
    assert set(skill_meta('driver-proposal').permissions) == {'device:read'}


# ---------------------------------------------------------------- L2 正文口径

def test_device_operations_documents_every_device_action():
    body = skill_body('device-operations')
    for action in device_tools.DEVICE_QUERY_ACTIONS:
        assert f'`{action}`' in body, f'L2 正文没有覆盖动作 {action}'
    # SPL 动作属于 spl-calibration，不在本 Skill 混写
    for action in device_tools.DEVICE_SPL_TARGETS:
        assert f'`{action}`' not in body, f'device-operations 混入了 {action}'


def test_device_operations_covers_status_alarm_and_write_boundary():
    body = skill_body('device-operations')
    for field in ('status', 'last_online_at', 'occupied_status',
                  'event_type', 'health_check', 'threshold_value',
                  'metric_type', 'severity'):
        assert field in body, field
    assert 'device:control' in body and 'APPROVAL_REQUIRED' in body
    assert 'M1' in body and '审批' in body
    # 不编造：状态以接口为准
    assert '以接口返回为准' in body
    assert '编造' in body


def test_spl_skill_documents_every_spl_action():
    body = skill_body('spl-calibration')
    for action in device_tools.DEVICE_SPL_TARGETS:
        assert f'`{action}`' in body, f'L2 正文没有覆盖动作 {action}'
    for field in ('target_spl', 'calibration_status', 'calibration_data',
                  'gainOffset', 'baseLevel', 'finalLevel', 'test_frequency',
                  'calibration_points', 'target_spl', 'gain_linear',
                  'rms_dbfs', 'reference_spl'):
        assert field in body, field
    assert 'calibrated' in body and 'uncalibrated' in body


def test_spl_skill_states_no_dedicated_read_tool():
    """卡面口径：没有独立 SPL 只读意图工具，正文必须写明、禁止自造工具名。"""
    body = skill_body('spl-calibration')
    assert '没有独立的 SPL 只读意图工具' in body
    assert 'device_query' in body
    assert 'tool_search' in body
    assert '不要自造' in body or '不要臆造' in body
    # 写侧工具名只作为 M2 边界说明出现
    assert 'spl_calibrate' in body
    assert 'M2' in body


def test_driver_proposal_skill_is_proposal_only():
    body = skill_body('driver-proposal')
    assert 'driver_propose' in body
    for target_kind in ('DEVICE_DRIVER', 'API_ADAPTER', 'PAIR'):
        assert target_kind in body, target_kind
    # 内部步骤不是对外工具
    assert 'generate_driver_from_elements' in body
    assert 'publish_driver_proposal' in body
    assert '不是对外工具' in body or '不是工具' in body
    # 只提案不执行不发布
    assert '不执行' in body and '不注册' in body and '不发布' in body
    assert '只提案' in body
    # 不把未启用工具当可用
    assert 'TOOL_NOT_ENABLED' in body
    assert 'M2' in body and 'INT-2467' in body


# ---------------------------------------------------------------- 触发准确率

@pytest.mark.parametrize('name,positives,negatives', [
    ('device-operations', fixtures.DEVICE_TRIGGER_POSITIVE,
     fixtures.TRIGGER_NEGATIVE['device-operations']),
    ('spl-calibration', fixtures.SPL_TRIGGER_POSITIVE,
     fixtures.TRIGGER_NEGATIVE['spl-calibration']),
    ('driver-proposal', fixtures.DRIVER_TRIGGER_POSITIVE,
     fixtures.TRIGGER_NEGATIVE['driver-proposal']),
])
def test_trigger_accuracy_at_least_90_percent(name, positives, negatives):
    accuracy, misses, false_positives = trigger_accuracy(
        positives, negatives, name)
    assert accuracy >= 0.9, (
        f'{name} 触发准确率 {accuracy:.0%} < 90%；'
        f'未命中={misses}；误命中={false_positives}')


def test_trigger_words_are_declared_in_each_description():
    expectations = {
        'device-operations': ('设备列表', '设备告警', '可用序列号', '驱动关键词'),
        'spl-calibration': ('SPL', '映射', '校准历史', '测试音', '声压级'),
        'driver-proposal': ('驱动提案', 'AppDriver', 'UiAutoDev', '适配器提案'),
    }
    for name, words in expectations.items():
        terms = trigger_terms(skill_meta(name).description)
        for word in words:
            assert word in terms, (name, word)


@pytest.mark.parametrize('query', fixtures.OFF_DOMAIN)
def test_off_domain_queries_do_not_route_to_device_skills(query):
    assert route(query)[0] not in SKILL_NAMES, query
