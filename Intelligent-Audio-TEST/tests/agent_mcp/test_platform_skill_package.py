# -*- coding: utf-8 -*-
"""平台 Skill 下载包：按 skills/ 生成 + 与导出包同结构可互导（INT-2476 验收 1）。

锚点：
- ``GET /api/v1/agent/skill`` 的 zip 根级是带 frontmatter 的 ``SKILL.md``，
  资源只放 ``references/ scripts/ assets/``，不套外层目录；
- 正文来自 ``skills/platform-reference/``（不是静态模板），base_url 已注入；
- ``assets/mcp.json`` 指向 ``<base>/api/v1/mcp``，鉴权头是占位符；
- 与 ``GET /api/v1/agent/skills/{id}/export`` 同一结构，且下载包可被导入；
- skills 目录缺失时回退内置模板，下载不 500。
"""
import io
import json
import os
import zipfile

import pytest

from api_gateway.application.services.mcp import skill_package
from shared.skill_package import (
    RESOURCE_PREFIXES, SKILL_FILE_NAME, read_skill_package,
    split_frontmatter,
)
from tests.agent_skill.helpers import (
    OWNER_ID, TENANT_ID, build_skill_stack, draft_payload,
)

BASE_URL = 'http://platform.example.com'
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
SKILLS_ROOT = os.path.join(PROJECT_ROOT, 'skills')


def _zip_members(data: bytes):
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def _platform_entries():
    return _zip_members(skill_package.build_skill_zip(
        BASE_URL, skills_root=SKILLS_ROOT))


def test_package_is_generated_from_platform_reference():
    entries = _platform_entries()
    assert SKILL_FILE_NAME in entries
    members = set(entries)
    assert skill_package.MCP_ASSET_PATH in members
    # platform-reference 的 L3 资源随包带出（说明正文确实来自 skills/）
    assert 'references/endpoints.md' in members
    assert skill_package.TOOLS_REFERENCE_PATH in members
    skill_md = entries[SKILL_FILE_NAME].decode('utf-8')
    assert skill_md.startswith('---\n')
    # platform-reference 专有内容（静态模板里没有）
    assert 'tool_search 用法' in skill_md
    assert '枚举速查' in skill_md


def test_package_root_level_structure_has_no_outer_directory():
    members = set(_platform_entries())
    assert SKILL_FILE_NAME in members
    for name in members - {SKILL_FILE_NAME}:
        assert name.startswith(RESOURCE_PREFIXES), (
            f'根级只允许 SKILL.md 与资源目录：{name}')
    assert not any(name.startswith(f'{skill_package.PACKAGE_SKILL_NAME}/')
                   for name in members)


def test_skill_md_frontmatter_is_external_agent_compatible():
    skill_md = _platform_entries()[SKILL_FILE_NAME].decode('utf-8')
    frontmatter, body = split_frontmatter(skill_md)
    assert frontmatter is not None
    import yaml
    meta = yaml.safe_load(frontmatter)
    assert meta['name'] == skill_package.PACKAGE_SKILL_NAME
    assert meta['description'].strip()
    assert '触发词' in meta['description']
    # 平台落库校验要求的两节仍在（下载包可导入）
    assert '## Gotchas' in body
    assert '## 验收' in body


def test_base_url_injected_into_skill_and_mcp_config():
    entries = _platform_entries()
    skill_md = entries[SKILL_FILE_NAME].decode('utf-8')
    mcp = json.loads(entries[skill_package.MCP_ASSET_PATH].decode('utf-8'))
    assert mcp['url'] == f'{BASE_URL}/api/v1/mcp'
    assert mcp['headers']['Authorization'] == 'Bearer <ACCESS_TOKEN>'
    assert f'{BASE_URL}/api/v1/mcp' in skill_md
    for payload in entries.values():
        text = payload.decode('utf-8')
        assert '{{BASE_URL}}' not in text


def test_mcp_tools_reference_matches_registry_count():
    from shared.agent_tools import mcp_registry
    reference = _platform_entries()[skill_package.TOOLS_REFERENCE_PATH] \
        .decode('utf-8')
    for tool in mcp_registry.TOOLS:
        assert f'`{tool["name"]}`' in reference
    assert str(len(mcp_registry.TOOLS)) in reference


def test_package_parses_with_the_import_reader():
    package = read_skill_package(
        skill_package.build_skill_zip(BASE_URL, skills_root=SKILLS_ROOT))
    assert package.skill_md.startswith('---\n')
    assert package.frontmatter_text
    assert 'references/endpoints.md' in package.resources


def test_package_is_importable_and_export_roundtrips(tmp_path):
    """下载包可导入；导入后导出的包同结构（两边所产包可互相导入）。"""
    container, _store = build_skill_stack(tmp_path)
    service = container.skill_service
    view = service.import_package(
        skill_package.build_skill_zip(BASE_URL, skills_root=SKILLS_ROOT),
        owner_id=OWNER_ID, tenant_id=TENANT_ID, permissions=['*'])
    assert view.name == skill_package.PACKAGE_SKILL_NAME

    filename, exported = service.export_package(
        view.id, owner_id=OWNER_ID, tenant_id=TENANT_ID, permissions=['*'])
    assert filename.endswith('.zip')
    exported_members = _zip_members(exported)
    assert SKILL_FILE_NAME in exported_members
    for name in set(exported_members) - {SKILL_FILE_NAME}:
        assert name.startswith(RESOURCE_PREFIXES), name
    # 导出包的资源键与下载包一致（同一结构、同一文件名）
    download_members = set(_platform_entries())
    assert set(exported_members) == download_members
    assert split_frontmatter(
        exported_members[SKILL_FILE_NAME].decode('utf-8'))[0] is not None


def test_exported_user_package_has_same_structure(tmp_path):
    """用户自定义 Skill 导出包与平台包同一结构（根级 SKILL.md，无外层目录）。"""
    container, _store = build_skill_stack(tmp_path)
    service = container.skill_service
    view = service.create(draft_payload(
        body='# demo\n\n## Gotchas\n\n- 无。\n\n## 验收\n\n- 无。\n',
        resources={'references/guide.md': '指引'}), owner_id=OWNER_ID,
        tenant_id=TENANT_ID, permissions=['*'])
    _filename, exported = service.export_package(
        view.id, owner_id=OWNER_ID, tenant_id=TENANT_ID, permissions=['*'])
    members = set(_zip_members(exported))
    assert members == {'SKILL.md', 'references/guide.md'}
    assert read_skill_package(exported).skill_md.startswith('---\n')


def test_missing_skills_directory_falls_back_without_error():
    data = skill_package.build_skill_zip(
        BASE_URL, skills_root=os.path.join(PROJECT_ROOT, 'no-such-skills'))
    members = set(_zip_members(data))
    assert SKILL_FILE_NAME in members
    assert skill_package.MCP_ASSET_PATH in members
    # 兜底模板下没有 platform-reference 的 references
    assert 'references/endpoints.md' not in members
    package = read_skill_package(data)
    assert package.frontmatter_text
    assert f'{BASE_URL}/api/v1/mcp' in package.skill_md


def test_missing_platform_reference_falls_back(tmp_path):
    empty_root = tmp_path / 'skills'
    empty_root.mkdir()
    data = skill_package.build_skill_zip(BASE_URL, skills_root=str(empty_root))
    package = read_skill_package(data)
    assert package.frontmatter_text
    assert 'references/endpoints.md' not in package.resources
