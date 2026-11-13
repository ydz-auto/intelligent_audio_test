# -*- coding: utf-8 -*-
"""INT-2465 清单一致性：注册表 / Skill allowed-tools / tool_search 索引三处对齐。

验收锚点（卡面 3 + 拍板增补 2）：
- 31 个意图工具名称在注册表、Skill ``allowed-tools``、``tool_search`` 索引
  三处一致，无重复、无遗漏；
- 网关 ``POST /api/v1/mcp`` 的 ``tools/list`` 与 ``shared/agent_tools``
  逐项一致（数量 / name / inputSchema），对外契约不漂移；
- 本卡未改 ``mcp_registry``：快照 = 改造前 = 改造后，diff 为 0。
"""
import hashlib
import io
import json
import os

import pytest

from agent_service.application.skill_registry import SkillRegistry
from agent_service.domain.enums import SkillIssueCode
from agent_service.infrastructure.skill.fs_skill_repository import (
    FsSkillRepository,
)
from api_gateway.application.services.mcp import mcp_handler, tools_registry
from shared.agent_tools import intent_tools, mcp_registry

DATASET_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           'datasets')
CONTRACT_FILE = os.path.join(DATASET_DIR, 'tools_list_contract.json')
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))

# 方案 §6.1 的 31 个意图工具（含 tool_search，业务意图工具 25 个）
SPEC_NAMES = frozenset({
    'platform_contract', 'tool_search', 'ui_tree', 'ui_action', 'api_spec',
    'memory_search', 'memory_write', 'audio_query', 'audio_import',
    'audio_annotate', 'testcase_query', 'testcase_generate', 'testcase_write',
    'tag_group_manage', 'evaluation_query', 'evaluation_manage',
    'algorithm_query', 'algorithm_manage', 'task_query', 'task_run',
    'task_diagnose', 'spl_calibrate', 'device_query', 'device_control',
    'report_query', 'report_generate', 'report_compare', 'report_export',
    'log_diagnose', 'driver_propose', 'dashboard_query',
})
M1_SKILLS = frozenset({
    'algorithm-config', 'audio-import', 'device-operations', 'driver-proposal',
    'evaluation-config', 'log-diagnostics', 'report-compare', 'report-studio',
    'spl-calibration', 'tag-group', 'task-operations', 'testcase-authoring',
})
MCP_TOTAL = 207

#: INT-2467（M2）：各 Skill 携带的**本域写工具**；其余 allowed-tools 仍须只读。
SKILL_WRITE_TOOLS = {
    'audio-import': {'audio_import', 'audio_annotate'},
    'device-operations': {'device_control'},
    'spl-calibration': {'spl_calibrate'},
    'driver-proposal': {'driver_propose'},
}


def _load_contract():
    with io.open(CONTRACT_FILE, encoding='utf-8') as handle:
        return json.load(handle)


def _payload_digest(tools):
    payload = json.dumps(tools, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def _registry():
    return SkillRegistry(
        FsSkillRepository(os.path.join(PROJECT_ROOT, 'skills')),
        known_tools=lambda: [t.name for t in intent_tools.INTENT_TOOLS]).load()


# ---------------------------------------------------------------- 31 个名称

def test_intent_registry_is_exactly_the_31_spec_tools():
    names = [tool.name for tool in intent_tools.INTENT_TOOLS]
    assert len(names) == 31
    assert len(names) == len(set(names))
    assert set(names) == set(SPEC_NAMES)
    assert frozenset(intent_tools.ENABLED_TOOLS) | frozenset(
        t.name for t in intent_tools.INTENT_TOOLS if not t.enabled
    ) == set(SPEC_NAMES)


def test_every_spec_name_in_tool_search_index_exactly_once():
    index_names = [entry['name'] for entry in intent_tools.TOOL_INDEX]
    assert len(index_names) == len(set(index_names))
    for name in SPEC_NAMES:
        assert index_names.count(name) == 1, f'{name} 在索引中缺失或重复'
    for name in intent_tools.ENABLED_TOOLS:
        assert name in index_names


def test_skills_allowed_tools_stay_inside_the_31_names():
    registry = _registry()
    assert not [i for i in registry.issues
                if i.code is SkillIssueCode.UNKNOWN_TOOL]
    seen_skills = set()
    for skill in registry.skills:
        if skill.name not in M1_SKILLS and skill.name != 'platform-reference':
            continue
        seen_skills.add(skill.name)
        allowed = list(skill.meta.allowed_tools)
        assert allowed, f'{skill.name} allowed-tools 为空'
        assert len(allowed) == len(set(allowed)), f'{skill.name} allowed-tools 重复'
        assert set(allowed) <= set(SPEC_NAMES), (
            f'{skill.name} 引用了未注册工具 '
            f'{set(allowed) - set(SPEC_NAMES)}')
        write_tools = SKILL_WRITE_TOOLS.get(skill.name, set())
        for name in allowed:
            tool = intent_tools.INTENT_TOOL_BY_NAME[name]
            assert tool.enabled is True, f'{skill.name} 引用未启用工具 {name}'
            if name in write_tools:
                # 写路径一律先提案后审批；Skill 只允许带本域写工具
                assert tool.risk in ('WRITE', 'DESTRUCTIVE'), name
            else:
                assert tool.risk == 'READ', f'{skill.name} 引用非只读工具 {name}'
    assert M1_SKILLS <= seen_skills, f'缺少 M1 Skill：{M1_SKILLS - seen_skills}'
    assert 'platform-reference' in seen_skills


# 首页统计没有专属 Skill（§4.3 清单空档）：INT-2461 的域任务直接覆盖该工具，
# 本卡不改 Skill 清单，显式登记为已知缺口，避免「无遗漏」口径含糊。
SKILL_LESS_ENABLED_READ = {'dashboard_query'}


def test_enabled_read_tools_are_declared_or_documented():
    """所有已启用只读意图工具都要被某个 Skill 声明，已知空档显式登记。

    Harness 级常驻工具（INT-2490 ``memory_search`` 等，见
    ``intent_tools.ALWAYS_AVAILABLE_TOOLS``）按设计不绑定任何 Skill、
    激活业务 Skill 时保持可用，故不参与「必须被某个 Skill 声明」的口径。
    """
    registry = _registry()
    declared = set()
    for skill in registry.skills:
        declared |= set(skill.meta.allowed_tools)
    enabled_read = {tool.name for tool in intent_tools.INTENT_TOOLS
                    if tool.enabled and tool.risk == 'READ'
                    and tool.name not in intent_tools.ALWAYS_AVAILABLE_TOOLS}
    declared_read = {name for name in declared
                     if intent_tools.INTENT_TOOL_BY_NAME[name].risk == 'READ'}
    assert enabled_read - declared_read == SKILL_LESS_ENABLED_READ, (
        f'未声明的已启用只读工具变了：{enabled_read - declared_read}')
    for name in declared:
        tool = intent_tools.INTENT_TOOL_BY_NAME[name]
        assert tool.enabled, f'Skill 声明了未启用工具：{name}'
        if tool.risk != 'READ':
            # 写工具只允许出现在携带它的本域 Skill 里（INT-2467）
            owners = {skill for skill, tools in SKILL_WRITE_TOOLS.items()
                      if name in tools}
            assert owners, f'写工具未登记归属：{name}'


# ---------------------------------------------------------------- tools/list

def test_gateway_tools_list_equals_shared_single_source():
    assert tools_registry.TOOLS is mcp_registry.TOOLS
    listed = tools_registry.list_tools()
    assert len(listed) == MCP_TOTAL
    assert set(listed[0]) == {'name', 'description', 'inputSchema'}
    names = [tool['name'] for tool in listed]
    assert len(names) == len(set(names))
    assert mcp_handler._handle_tools_list() == {'tools': listed}


def test_tools_list_contract_snapshot_has_no_drift():
    contract = _load_contract()
    listed = tools_registry.list_tools()
    digest = _payload_digest(listed)
    assert contract['count'] == MCP_TOTAL
    assert len(listed) == contract['count']
    assert [t['name'] for t in listed] == contract['names'] or (
        sorted(t['name'] for t in listed) == contract['names'])
    assert digest == contract['sha256'], (
        '对外 MCP tools/list 与快照不一致（契约漂移）：本卡不得改 '
        'mcp_registry；如确需新增 / 改名 / 改 Schema，请开卡并同步 '
        'tests/agent_eval/coverage/datasets/tools_list_contract.json')


def test_mcp_index_entries_match_registry_schema():
    for entry in intent_tools.TOOL_INDEX:
        if entry.get('kind') != 'mcp':
            continue
        tool = mcp_registry.get_tool(entry['name'])
        assert tool is not None, entry['name']
        assert entry['description'] == tool['description']
        assert entry['inputSchema'] == tool['inputSchema']
        assert entry['permissions'] == list(tool['permissions'])
        assert entry['risk'] == ('READ' if tool['method'] == 'GET' else 'WRITE')


def test_intent_index_entries_match_registry_schema():
    for entry in intent_tools.TOOL_INDEX:
        if entry.get('kind') == 'mcp':
            continue
        tool = intent_tools.INTENT_TOOL_BY_NAME.get(entry['name'])
        assert tool is not None, entry['name']
        assert entry['description'] == tool.description
        assert entry['inputSchema'] == tool.parameters
        assert entry['permissions'] == list(tool.permissions)
        assert entry['risk'] == tool.risk
        assert entry['enabled'] == tool.enabled
