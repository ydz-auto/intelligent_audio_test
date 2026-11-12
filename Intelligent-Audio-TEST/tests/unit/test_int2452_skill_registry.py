# -*- coding: utf-8 -*-
"""INT-2452 SkillRegistry：目录扫描 / frontmatter 校验 / 权限过滤 / 披露层级。

验收锚点（卡面可测标准 1、4）：
1. 目录扫描、frontmatter 校验（缺字段 / 未注册工具 / 超长正文）各一组用例；
2. 权限过滤：permissions 不满足的用户看不到该 Skill（OR 语义，'*' 通配）；
3. L1 = name + description 常驻；L2 = 正文只在激活时注入；
4. L1 常驻 token 在 system 区段预算（窗口 15%）内。
"""
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from agent_service.application.skill_registry import SkillRegistry
from agent_service.config.config import Config
from agent_service.domain.enums import SkillIssueCode, SkillIssueSeverity
from agent_service.domain.exceptions import SkillValidationError
from agent_service.domain.model.skill import Skill, SkillMeta
from agent_service.infrastructure.skill.fs_skill_repository import (
    FsSkillRepository,
)
from agent_service.domain.services.token_estimator import estimate_tokens

PROJECT_ROOT = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))))
SKILLS_ROOT = os.path.join(PROJECT_ROOT, 'skills')

FRONTMATTER = """---
name: {name}
description: {description}
version: 1.0.0
owner: test-team
allowed-tools:
{tools}
permissions:
{permissions}
budgets:
  maxToolCalls: 10
  maxTokens: 2000
---
"""

BODY = """# {name}

正文第一行。

## Gotchas

- 坑一。

## 验收

- 检查项一。
"""


def _tools(*names):
    return '\n'.join(f'  - {name}' for name in names) or '  []'


def _permissions(*codes):
    return '\n'.join(f'  - {code}' for code in codes) or '  []'


def _write_skill(root, name, *, description='测试 Skill 描述', tools=(),
                 permissions=(), body=None, frontmatter=None):
    directory = os.path.join(str(root), name)
    os.makedirs(directory, exist_ok=True)
    text = frontmatter or FRONTMATTER.format(
        name=name, description=description, tools=_tools(*tools),
        permissions=_permissions(*permissions))
    with open(os.path.join(directory, 'SKILL.md'), 'w', encoding='utf-8') as f:
        f.write(text + (body if body is not None else BODY.format(name=name)))
    return directory


def _registry(root, *, known_tools=(), strict=False, max_body_lines=500,
              l1_budget_tokens=0):
    registry = SkillRegistry(
        FsSkillRepository(str(root)),
        known_tools=lambda: list(known_tools),
        max_body_lines=max_body_lines,
        strict=strict,
        l1_budget_tokens=l1_budget_tokens,
    )
    return registry.load()


# ---------------------------------------------------------------- scan

def test_real_platform_reference_is_loaded_and_contract_complete():
    registry = _registry(SKILLS_ROOT, known_tools=('platform_contract',
                                                   'tool_search'))
    names = [s.name for s in registry.skills]
    assert 'platform-reference' in names

    skill = registry.get('platform-reference')
    meta = skill.meta
    assert meta.description and '触发词' in meta.description
    assert '不适用' in meta.description          # §4.2 规则 1：不适用边界
    assert meta.version and meta.owner
    assert meta.allowed_tools == ('platform_contract', 'tool_search')
    assert meta.permissions == ()                # 空 = 不额外要求权限
    assert meta.max_tool_calls == 20 and meta.max_tokens == 30000
    assert skill.has_section('Gotchas')
    assert skill.has_section('验收')
    assert skill.body_line_count <= 500
    assert 'references/endpoints.md' in skill.references


def test_directory_scan_lists_references_scripts_assets(tmp_path):
    directory = _write_skill(tmp_path, 'demo', tools=('tool_a',))
    os.makedirs(os.path.join(directory, 'scripts'))
    os.makedirs(os.path.join(directory, 'references'))
    os.makedirs(os.path.join(directory, 'assets', 'templates'))
    with open(os.path.join(directory, 'scripts', 'run.py'), 'w',
              encoding='utf-8') as f:
        f.write('print(1)')
    with open(os.path.join(directory, 'assets', 'templates', 't.html'), 'w',
              encoding='utf-8') as f:
        f.write('<html/>')
    with open(os.path.join(directory, 'references', 'notes.md'), 'w',
              encoding='utf-8') as f:
        f.write('notes')

    registry = _registry(tmp_path, known_tools=('tool_a',))
    skill = registry.get('demo')
    assert skill.scripts == ('scripts/run.py',)
    assert skill.assets == ('assets/templates/t.html',)
    assert skill.references == ('references/notes.md',)


def test_missing_skills_root_is_empty_not_fatal(tmp_path):
    registry = _registry(tmp_path / 'nope')
    assert registry.skills == ()
    assert registry.issues == ()


# ---------------------------------------------------------------- validation

def test_missing_name_is_error_and_skill_excluded(tmp_path):
    _write_skill(tmp_path, 'no-name', frontmatter=(
        '---\ndescription: 只有描述\n---\n'))
    registry = _registry(tmp_path)
    assert registry.skills == ()
    codes = {i.code for i in registry.issues}
    assert SkillIssueCode.MISSING_NAME in codes
    issue = [i for i in registry.issues
             if i.code is SkillIssueCode.MISSING_NAME][0]
    assert issue.severity is SkillIssueSeverity.ERROR


def test_missing_description_is_error(tmp_path):
    _write_skill(tmp_path, 'no-desc', frontmatter='---\nname: no-desc\n---\n')
    registry = _registry(tmp_path)
    assert registry.skills == ()
    assert SkillIssueCode.MISSING_DESCRIPTION in {i.code
                                                  for i in registry.issues}


def test_unregistered_tool_warns_but_keeps_skill(tmp_path):
    _write_skill(tmp_path, 'warn-tool', tools=('not_registered',))
    registry = _registry(tmp_path, known_tools=('tool_a',))
    assert [s.name for s in registry.skills] == ['warn-tool']
    unknown = [i for i in registry.issues
               if i.code is SkillIssueCode.UNKNOWN_TOOL]
    assert unknown and unknown[0].severity is SkillIssueSeverity.WARNING
    assert 'not_registered' in unknown[0].message


def test_unregistered_tool_fails_startup_in_strict_mode(tmp_path):
    _write_skill(tmp_path, 'warn-tool', tools=('not_registered',))
    with pytest.raises(SkillValidationError):
        _registry(tmp_path, known_tools=('tool_a',), strict=True)


def test_body_over_500_lines_is_error(tmp_path):
    long_body = '# long\n\n' + '\n'.join(f'行 {i}' for i in range(520)) + \
        '\n\n## Gotchas\n\n- x\n\n## 验收\n\n- y\n'
    _write_skill(tmp_path, 'long', body=long_body)
    registry = _registry(tmp_path)
    assert registry.skills == ()
    codes = {i.code for i in registry.issues}
    assert SkillIssueCode.BODY_TOO_LONG in codes


def test_missing_required_sections_is_error(tmp_path):
    _write_skill(tmp_path, 'no-sections', body='# t\n\n只有正文。\n')
    registry = _registry(tmp_path)
    assert registry.skills == ()
    missing = [i for i in registry.issues
               if i.code is SkillIssueCode.MISSING_REQUIRED_SECTION]
    assert {i.message for i in missing}  # Gotchas / 验收 各一条
    assert len(missing) == 2


def test_duplicate_name_keeps_first_only(tmp_path):
    same = FRONTMATTER.format(name='dup', description='重复名',
                              tools='  []', permissions='  []')
    _write_skill(tmp_path, 'first', frontmatter=same)
    _write_skill(tmp_path, 'second', frontmatter=same)
    registry = _registry(tmp_path)
    assert [s.name for s in registry.skills] == ['dup']
    assert SkillIssueCode.DUPLICATE_NAME in {i.code for i in registry.issues}


def test_broken_frontmatter_reports_load_error(tmp_path):
    _write_skill(tmp_path, 'broken', frontmatter='---\nname: [unclosed\n---\n')
    registry = _registry(tmp_path)
    assert registry.skills == ()
    assert SkillIssueCode.INVALID_FRONTMATTER in {i.code
                                                  for i in registry.issues}


# ---------------------------------------------------------------- permissions

def test_permission_filter_uses_or_semantics_and_wildcard(tmp_path):
    _write_skill(tmp_path, 'open')
    _write_skill(tmp_path, 'restricted', permissions=('report:read',))
    registry = _registry(tmp_path)

    assert [s.name for s in registry.visible_for(())] == ['open']
    assert registry.get_visible('restricted', ()) is None
    assert registry.get_visible('restricted', ('task:read',)) is None
    assert registry.get_visible('restricted', ('report:read',)) is not None
    assert registry.get_visible('restricted', ('*',)) is not None
    assert registry.get_visible('open', ()) is not None
    # L1 只列可见 Skill
    assert 'restricted' not in registry.l1_block(())
    assert 'restricted' in registry.l1_block(('report:read',))


# ---------------------------------------------------------------- disclosure

def test_l1_contains_name_and_description_l2_contains_body(tmp_path):
    _write_skill(tmp_path, 'demo', description='一句话说明', tools=())
    registry = _registry(tmp_path)

    l1 = registry.l1_block()
    assert 'demo' in l1 and '一句话说明' in l1
    assert '正文第一行' not in l1          # L1 不含正文

    body = registry.l2_block(registry.get('demo'))
    assert '正文第一行' in body and '## Gotchas' in body

    without = registry.system_section((), None)
    assert '正文第一行' not in without
    with_active = registry.system_section((), 'demo')
    assert '正文第一行' in with_active


def test_activation_of_invisible_skill_injects_no_l2(tmp_path):
    _write_skill(tmp_path, 'restricted', permissions=('report:read',))
    registry = _registry(tmp_path)
    section = registry.system_section((), 'restricted')
    assert 'restricted' not in section
    assert '正文第一行' not in section


def test_l1_budget_marks_excess(tmp_path):
    _write_skill(tmp_path, 'demo', description='x' * 400)
    registry = _registry(tmp_path, l1_budget_tokens=10)
    assert SkillIssueCode.L1_BUDGET_EXCEEDED in {i.code for i in registry.issues}


def test_platform_reference_l1_within_system_budget():
    """卡面可测标准 4：L1 常驻在 system 区段 15% 预算内（§8.3）。"""
    registry = _registry(SKILLS_ROOT, known_tools=('platform_contract',
                                                   'tool_search'))
    budget = Config.skill_l1_budget_tokens()
    tokens = registry.l1_tokens(())
    assert budget == int(Config.CONTEXT_WINDOW_TOKENS
                         * Config.SYSTEM_SECTION_RATIO)
    assert 0 < tokens < budget
    # 与实际渲染一致（防止 l1_tokens 与 l1_block 双口径）
    assert tokens == estimate_tokens(registry.l1_block())
    assert not [i for i in registry.issues
                if i.code is SkillIssueCode.L1_BUDGET_EXCEEDED]


def test_token_estimator_is_monotonic():
    assert estimate_tokens('') == 0
    assert estimate_tokens('abcd') == 1
    assert estimate_tokens('中文') == 2
    assert estimate_tokens('中文abcd') == 3
    assert estimate_tokens('中文' * 10) > estimate_tokens('中文' * 5)


def test_skill_entity_section_detection():
    body = '# x\n\n## Gotchas\n\n## 验收\n'
    skill = Skill(meta=SkillMeta(name='x'), body=body, path='x')
    assert skill.has_section('Gotchas') and skill.has_section('验收')
    assert not skill.has_section('不存在')
    assert skill.body_line_count == 5


def test_golden_tasks_fixture_ready_for_eval_base():
    """卡面可测标准 5 的输入侧：10 条 golden tasks 已就位（联跑由 INT-2454）。

    这里只做集合自检：条数、id 唯一、正/负样本都有、正样本命中 description
    里的触发词——真正的触发判定要用模型跑评测基座，不在单测里伪造。
    """
    import json

    path = os.path.join(PROJECT_ROOT, 'tests', 'fixtures',
                        'int2452_platform_reference_golden.json')
    with open(path, encoding='utf-8') as handle:
        data = json.load(handle)
    tasks = data['tasks']
    assert data['skill'] == 'platform-reference'
    assert len(tasks) == 10
    assert len({t['id'] for t in tasks}) == 10
    assert all(t.get('prompt') and isinstance(t.get('expect_trigger'), bool)
               for t in tasks)

    positives = [t for t in tasks if t['expect_trigger']]
    negatives = [t for t in tasks if not t['expect_trigger']]
    assert len(positives) >= 4 and len(negatives) >= 4

    registry = _registry(SKILLS_ROOT, known_tools=('platform_contract',
                                                   'tool_search'))
    description = registry.get('platform-reference').description
    trigger_part = description.split('触发词：')[-1].split('不适用：')[0]
    # 触发词是多字短语，样本句会换语序，因此按核心名词校验样本质量
    core_words = [w for w in ('接口', '枚举', '权限码', '字段', 'tool_search',
                              'Schema', '前缀', '状态')
                  if w.lower() in trigger_part.lower()]
    assert core_words
    for task in positives:
        assert any(word.lower() in task['prompt'].lower()
                   for word in core_words), task['id']
    for task in negatives:
        assert task.get('reason')
