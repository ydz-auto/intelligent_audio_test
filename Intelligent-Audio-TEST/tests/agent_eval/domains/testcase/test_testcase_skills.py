# -*- coding: utf-8 -*-
"""INT-2460 Skill：testcase-authoring / tag-group 的 L1/L2、只读边界与触发准确率。

验收锚点（卡面 3）：
3. 2 个 Skill 触发准确率 ≥ 90%；allowed-tools 只含已启用的只读工具。
另外校验 L2 正文覆盖真实字段口径（用例轮次 / 维度 / 参数、标签 / 分组字段），
避免模型按缺字段的说明回答。
"""
import urllib.parse

import pytest

from agent_service.domain.enums import SkillIssueCode, SkillIssueSeverity, ToolRisk
from shared.agent_tools import intent_tools, mcp_registry
from shared.agent_tools.intent_tools import TESTCASE_QUERY_ACTIONS
from tests.agent_eval.domains.testcase import fixtures
from tests.agent_eval.domains.testcase.skill_support import (
    get_skill, load_skills, route, skill_body, skill_meta,
)

SKILLS = ('testcase-authoring', 'tag-group')


def _split_url(path):
    parts = urllib.parse.urlsplit(path)
    query = {k: v[0] for k, v in urllib.parse.parse_qs(parts.query).items()}
    return parts.path, query


# ---------------------------------------------------------------- 装载

@pytest.mark.parametrize('name', SKILLS)
def test_skill_loads_without_errors_or_unknown_tools(name):
    registry = load_skills()
    skill = registry.get(name)
    assert skill is not None, f'skills/{name}/SKILL.md 未被装载'
    fatal = [i for i in registry.issues_for(name)
             if i.severity is SkillIssueSeverity.ERROR]
    assert fatal == []
    unknown = [i for i in registry.issues if i.code is SkillIssueCode.UNKNOWN_TOOL]
    assert unknown == []
    assert skill.body_line_count <= 500


@pytest.mark.parametrize('name', SKILLS)
def test_required_sections_and_frontmatter(name):
    meta = skill_meta(name)
    assert meta.name == name
    assert meta.description.strip()
    assert meta.version and meta.owner
    assert meta.permissions
    assert 0 < meta.max_tool_calls <= 40
    assert meta.max_tokens and meta.max_tokens <= 60000
    body = skill_body(name)
    assert '## Gotchas' in body
    assert '## 验收' in body
    # 写动作边界必须写明（M1 只读 / M2 审批）
    assert 'M2' in body


def test_testcase_skill_permission_matches_tool_domain():
    # INT-2468：M2 写意图工具挂进 Skill 后，Skill 权限码覆盖工具的写域
    assert skill_meta('testcase-authoring').permissions == (
        'testcase:read', 'testcase:create', 'testcase:update',
        'testcase:copy', 'testcase:delete')
    # tag-group 同时覆盖 tag_list（tag:read）/ group_list（group:read）与
    # batch_tag 用到的 testcase 写域
    assert skill_meta('tag-group').permissions == (
        'tag:read', 'group:read', 'tag:create', 'tag:update', 'tag:delete',
        'group:create', 'group:update', 'group:delete',
        'testcase:update', 'testcase:delete')


@pytest.mark.parametrize('name', SKILLS)
def test_allowed_tools_exist_and_are_enabled(name):
    meta = skill_meta(name)
    assert meta.allowed_tools, 'allowed-tools 不能为空'
    for tool_name in meta.allowed_tools:
        tool = intent_tools.INTENT_TOOL_BY_NAME.get(tool_name)
        assert tool is not None, f'未注册工具：{tool_name}'
        assert tool.enabled is True, f'工具未启用：{tool_name}'
        # M2 写意图（INT-2468）只能出现在对应域的 Skill 里，且仍走审批
        if ToolRisk(tool.risk) is not ToolRisk.READ:
            assert tool_name in {'testcase_write', 'tag_group_manage',
                                 'task_run'}, f'未登记的写工具：{tool_name}'
        assert set(tool.permissions) <= set(meta.permissions), (
            f'{name} 的 allowed-tools {tool_name} 需要 {tool.permissions}，'
            f'但 Skill 只声明了 {meta.permissions}')


def test_testcase_skill_allowed_tools_cover_its_intent_tools():
    allowed = set(skill_meta('testcase-authoring').allowed_tools)
    assert {'testcase_query', 'testcase_generate', 'testcase_write'} <= allowed
    # 标签域只读靠 tool_search 发现 tag_list / group_list；写操作挂
    # tag_group_manage（INT-2468）
    tag_allowed = set(skill_meta('tag-group').allowed_tools)
    assert 'tool_search' in tag_allowed
    assert 'tag_group_manage' in tag_allowed
    # 域写工具不跨 Skill：用例写只归 testcase-authoring，标签写只归 tag-group
    assert 'tag_group_manage' not in allowed
    assert 'testcase_write' not in tag_allowed
    assert 'audio_import' not in allowed | tag_allowed


# ---------------------------------------------------------------- L2 覆盖

def test_testcase_skill_documents_every_query_action():
    body = skill_body('testcase-authoring')
    for action in TESTCASE_QUERY_ACTIONS:
        assert f'`{action}`' in body, f'L2 正文没有覆盖动作 {action}'
    for field in ('page', 'per_page', 'keyword', 'tag', 'group_id',
                  'algorithm_type', 'dimension_id', 'lab_id', 'visibility',
                  'favorite', 'only_deleted', 'include_deleted'):
        assert field in body, f'列表过滤参数未说明 {field}'


def test_testcase_skill_documents_write_actions():
    """INT-2468：写意图章节覆盖动作、审批三态与破坏性口径。"""
    from shared.agent_tools import testcase_write_tools

    body = skill_body('testcase-authoring')
    for action in testcase_write_tools.ACTION_NAMES:
        assert f'`{action}`' in body, f'L2 正文没有覆盖写动作 {action}'
    for keyword in ('testcase_write', '提案', '审批', 'DESTRUCTIVE', '软删',
                    '回收站', 'tag_mode', 'body'):
        assert keyword in body, keyword


def test_tag_group_skill_documents_write_actions():
    from shared.agent_tools import tag_group_tools

    body = skill_body('tag-group')
    for action in tag_group_tools.ACTION_NAMES:
        assert f'`{action}`' in body, f'L2 正文没有覆盖写动作 {action}'
    for keyword in ('tag_group_manage', tag_group_tools.BATCH_ADD_TAGS,
                    tag_group_tools.BATCH_REMOVE_TAGS,
                    tag_group_tools.BATCH_RENAME_TAG, 'cascade',
                    'DESTRUCTIVE', '提案', '审批'):
        assert keyword in body, keyword


def test_testcase_skill_documents_generate_contract():
    body = skill_body('testcase-authoring')
    for field in ('audio_ids', 'algorithm_type', 'device_type', 'dimension_ids',
                  'dimension_round_scope', 'group_id', 'spl',
                  'playback_device_id', 'inherit_tags'):
        assert field in body, f'testcase_generate 参数未说明 {field}'
    assert 'persisted' in body and 'writes' in body
    assert '不落库' in body
    assert '没有用例 ID' in body or '没有真实用例 ID' in body


def test_testcase_skill_documents_every_case_field():
    """字段表必须覆盖网关契约字段，避免回答时漏字段或编造。"""
    from api_gateway.schemas.testcase import (
        RoundConfigItem, TestCaseAudioConfigItem, TestCaseConfig,
        TestCaseDetailData, TestCaseListItem,
    )

    body = skill_body('testcase-authoring')
    for model in (TestCaseListItem, TestCaseDetailData, TestCaseConfig,
                  RoundConfigItem, TestCaseAudioConfigItem):
        missing = [name for name in model.model_fields if name not in body]
        assert missing == [], f'{model.__name__} 字段未覆盖：{missing}'
    assert 'round_scope' in body and 'multi' in body


def test_tag_group_skill_documents_real_fields():
    from api_gateway.schemas.group import GroupItem
    from api_gateway.schemas.testcase import TagItem

    body = skill_body('tag-group')
    for model in (TagItem, GroupItem):
        missing = [name for name in model.model_fields if name not in body]
        assert missing == [], f'{model.__name__} 字段未覆盖：{missing}'
    assert 'tag_list' in body and 'group_list' in body
    assert 'tool_search' in body
    assert 'shared' in body and 'private' in body
    # 批量打标动作与前置条件
    for action in ('add_tag', 'remove_tag', 'rename_tag'):
        assert action in body, action
    assert 'ids' in body and 'tags' in body


# ---------------------------------------------------------------- 标签 / 分组任务

def test_ten_tag_tasks_are_distinct():
    assert len(fixtures.TAG_TASKS) == 10
    assert len({t['id'] for t in fixtures.TAG_TASKS}) == 10


@pytest.mark.parametrize('task', fixtures.TAG_TASKS,
                         ids=[t['id'] for t in fixtures.TAG_TASKS])
def test_tag_task_tool_is_searchable_readonly_and_path_matches(task):
    tool = mcp_registry.get_tool(task['tool'])
    assert tool is not None, task['tool']
    assert tool['method'] == 'GET'
    assert tool['permissions'] == ['tag:read'] or tool['permissions'] == ['group:read']

    found = [t['name'] for t in intent_tools.tool_search(
        task['search_query'], tuple(tool['permissions']))['tools']]
    assert task['tool'] in found, f"{task['id']}：tool_search('{task['search_query']}') 未命中 {task['tool']}（{found}）"

    path, query = _split_url(mcp_registry.build_path(tool, task['arguments']))
    expected_path, expected_query = _split_url(task['expected_path'])
    assert path == expected_path
    assert query == expected_query


def test_tag_task_arguments_only_use_declared_schema_fields():
    for task in fixtures.TAG_TASKS:
        properties = mcp_registry.get_tool(task['tool'])['inputSchema']['properties']
        for name in task['arguments']:
            assert name in properties, f"{task['id']} 未声明参数 {name}"


# ---------------------------------------------------------------- 触发准确率

def _accuracy(positives, negatives, expected):
    hits = [q for q in positives if route(q)[0] == expected]
    false_positive = [q for q in negatives if route(q)[0] == expected]
    total = len(positives) + len(negatives)
    correct = len(hits) + (len(negatives) - len(false_positive))
    misses = [q for q in positives if q not in hits]
    return correct / total, misses, false_positive


def test_testcase_skill_trigger_accuracy_at_least_90_percent():
    positives = ([task['query'] for task in fixtures.TESTCASE_TASKS]
                 + fixtures.TESTCASE_TRIGGER_EXTRA)
    accuracy, misses, false_positive = _accuracy(
        positives, fixtures.TESTCASE_NEGATIVES, 'testcase-authoring')
    assert accuracy >= 0.9, (
        f'触发准确率 {accuracy:.0%} < 90%；未命中={misses}；'
        f'误命中={false_positive}')


def test_tag_skill_trigger_accuracy_at_least_90_percent():
    positives = ([task['query'] for task in fixtures.TAG_TASKS]
                 + fixtures.TAG_TRIGGER_EXTRA)
    accuracy, misses, false_positive = _accuracy(
        positives, fixtures.TAG_NEGATIVES, 'tag-group')
    assert accuracy >= 0.9, (
        f'触发准确率 {accuracy:.0%} < 90%；未命中={misses}；'
        f'误命中={false_positive}')


@pytest.mark.parametrize('query,expected', [
    ('帮我生成用例草案', 'testcase-authoring'),
    ('这条用例的轮次配置怎么看的', 'testcase-authoring'),
    ('用例参考参数刷新的进度到哪了', 'testcase-authoring'),
    ('平台有哪些标签', 'tag-group'),
    ('用例分组下有多少条用例', 'tag-group'),
    ('想给一批用例批量打标，现在能直接做吗', 'tag-group'),
    # 自然改写样本（打回复测 P2-3：不由夹具派生）
    ('这个分组下多少条用例', 'tag-group'),
    ('某个分组里有多少用例', 'tag-group'),
    ('分组能不能设成私有', 'tag-group'),
    ('第 2 轮的参考参数还没生成吗', 'testcase-authoring'),
    ('参考参数刷新任务的状态', 'testcase-authoring'),
    ('这个分组下的用例有哪些', 'testcase-authoring'),
    ('用例一共多少条，按分组怎么分布', 'testcase-authoring'),
])
def test_representative_queries_route_to_own_skill(query, expected):
    assert route(query)[0] == expected, route(query)


@pytest.mark.parametrize('query,other', [
    ('查询评估维度的评分口径', 'testcase-authoring'),
    ('算法参数怎么配置', 'tag-group'),
    ('音频文件的采样率是多少', 'tag-group'),
])
def test_off_domain_skill_does_not_borrow_our_core_terms(query, other):
    """别的域问题不能被本域核心词抢走（与 INT-2511 同口径）。"""
    assert route(query)[0] != other, route(query)


def test_skills_are_visible_with_their_permissions():
    registry = load_skills()
    visible = {s.name for s in registry.visible_for(
        ('testcase:read', 'tag:read'))}
    assert set(SKILLS) <= visible
    hidden = {s.name for s in registry.visible_for(('audio:read',))}
    assert not (set(SKILLS) & hidden)
