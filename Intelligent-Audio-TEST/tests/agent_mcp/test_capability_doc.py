# -*- coding: utf-8 -*-
"""外部能力清单文档 ↔ 代码一致（INT-2476 验收 4：无暗能力）。

``doc/agent化/09_外部Agent能力清单.md`` 是外部能力清单的唯一归属文件。
本测试保证它不漂移：注册表 / 意图工具 / 内置 Skill 新增或改名而文档未同步，
这里直接失败（INT-2478 只在文末「发布说明」追加，不影响本口径）。

Skill 来源只有 PLATFORM / TENANT / USER 三层：PLATFORM 层由 fs 扫描 ``skills/``
只读得到、**没有写入 / 导入 / 发布入口**，所以「自定义包 → 平台层」这个方向
不成立（INT-2610 P3-7 的 N/A 依据）；要复用平台 Skill 只能 fork 成 USER 副本。
本文件与 ``test_platform_skill_package.py`` 都不得为 PLATFORM 层补写入口。
"""
import io
import os

from shared.agent_tools import coverage, intent_tools, mcp_registry

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
DOC_PATH = os.path.join(PROJECT_ROOT, 'doc', 'agent化',
                        '09_外部Agent能力清单.md')
SKILLS_ROOT = os.path.join(PROJECT_ROOT, 'skills')


def _doc() -> str:
    with io.open(DOC_PATH, encoding='utf-8') as handle:
        return handle.read()


def _skill_names():
    return sorted(name for name in os.listdir(SKILLS_ROOT)
                  if os.path.isdir(os.path.join(SKILLS_ROOT, name)))


def test_doc_exists_and_is_the_single_owner():
    assert os.path.exists(DOC_PATH), '外部能力清单缺失'
    text = _doc()
    assert '唯一归属文件' in text
    assert 'INT-2478' in text  # 发布说明的归属交接写清楚
    assert '## 9. 发布说明' in text


def test_every_external_mcp_tool_is_listed():
    text = _doc()
    missing = [tool['name'] for tool in mcp_registry.TOOLS
               if f'`{tool["name"]}`' not in text]
    assert not missing, f'能力清单漏了对外 MCP 工具：{missing[:10]}'


def test_every_internal_intent_tool_is_listed():
    text = _doc()
    missing = [tool.name for tool in intent_tools.INTENT_TOOLS
               if f'`{tool.name}`' not in text]
    assert not missing, f'能力清单漏了内部意图工具：{missing}'


def test_every_platform_skill_is_listed():
    text = _doc()
    missing = [name for name in _skill_names() if f'`{name}`' not in text]
    assert not missing, f'能力清单漏了内置 Skill：{missing}'


def test_external_only_tools_are_explicitly_marked():
    text = _doc()
    assert '仅外部 MCP（不内部暴露）' in text
    missing = [name for name in coverage.EXTERNAL_ONLY
               if f'`{name}`' not in text]
    assert not missing, f'仅外部 MCP 工具未在能力清单标注：{missing}'


def test_counts_and_auth_model_match_code():
    text = _doc()
    assert f'{len(mcp_registry.TOOLS)}' in text
    assert f'{len(intent_tools.INTENT_TOOLS)}' in text
    stats = coverage.summary()
    assert f'内部归属 {stats["owned"]}' in text
    assert f'仅外部 {stats["external"]}' in text
    assert '用户当前权限 ∩ token scopes' in text
    # 对外工具清单与文档声明的数量一致（207 项 1:1 契约）
    assert f'| **合计** | **{len(mcp_registry.TOOLS)}**' in text
