# -*- coding: utf-8 -*-
"""平台 Skill 下载包：按 skills/ 生成 + 与导出包同结构（INT-2476 验收 1）。

锚点：
- ``GET /api/v1/agent/skill`` 的 zip 根级是带 frontmatter 的 ``SKILL.md``，
  资源只放 ``references/ scripts/ assets/``，不套外层目录；
- 正文来自 ``skills/platform-reference/``（不是静态模板），base_url 已注入；
- ``assets/mcp.json`` 指向 ``<base>/api/v1/mcp``，鉴权头是占位符；
- 与 ``GET /api/v1/agent/skills/{id}/export`` **同结构**（成员集合一致），
  但**不承诺回导**（INT-2612）：预填内网 / 回环地址的包导入会被
  ``INTERNAL_ADDRESS`` 拒绝 —— 这是预期行为，见本文件负向用例；
- 公网域名 base_url 的包仍可导入并原样导出；
- skills 目录缺失时回退内置模板，下载不 500（兜底包不保证可导入）。
"""
import io
import json
import os
import subprocess
import zipfile

import pytest

from api_gateway.application.services.mcp import skill_package
from agent_service.domain.exceptions import SkillServiceError
from shared.skill_package import (
    RESOURCE_PREFIXES, SKILL_FILE_NAME, PackageIssueCode, SkillPackageError,
    read_skill_directory, read_skill_package, split_frontmatter,
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
    """公网域名 base_url 的下载包仍可导入，导出包与下载包成员集合一致。"""
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


# ========================================================================
# INT-2612：预填内网 / 回环地址的平台包回导被拒（预期行为，不是缺陷）
# ========================================================================

INTERNAL_BASE_URLS = [
    'http://192.168.1.20:15000',   # 私网 192.168/16
    'http://10.0.0.8:8080',        # 私网 10/8
    'http://127.0.0.1:15000',      # 回环 IPv4
    'http://localhost:15000',      # 回环字面量（与 127.0.0.1 同判）
    'http://[::1]:15000',          # 回环 IPv6
    'http://myhost.local:15000',   # mDNS / 内部域名
]


@pytest.mark.parametrize('base_url', INTERNAL_BASE_URLS)
def test_internal_or_loopback_base_url_package_is_rejected(tmp_path,
                                                           base_url):
    """下载包里预填的内网 / 回环地址会让导入直接失败（两处命中）。

    口径（INT-2612 裁定 (c)）：平台包供外部宿主接入，回导不是有效用户流程；
    导入侧不放宽内网地址规则，因此这里钉死「正文 + ``assets/mcp.json`` 各
    一条 ``INTERNAL_ADDRESS``」的预期行为。
    """
    container, _store = build_skill_stack(tmp_path)
    with pytest.raises(SkillServiceError) as info:
        container.skill_service.import_package(
            skill_package.build_skill_zip(base_url, skills_root=SKILLS_ROOT),
            owner_id=OWNER_ID, tenant_id=TENANT_ID, permissions=['*'])
    located = [(issue.code.value, issue.field) for issue in info.value.issues]
    assert located == [
        ('INTERNAL_ADDRESS', 'body'),
        ('INTERNAL_ADDRESS', 'resources.assets/mcp.json'),
    ], f'{base_url} 的拒绝项不符合预期：{located}'


def test_loopback_localhost_and_127_are_judged_alike(tmp_path):
    """``localhost`` 与 ``127.0.0.1`` 判据一致：两者都必须被拒（INT-2612）。"""
    container, _store = build_skill_stack(tmp_path)
    for base_url in ('http://localhost:15000', 'http://127.0.0.1:15000'):
        with pytest.raises(SkillServiceError) as info:
            container.skill_service.import_package(
                skill_package.build_skill_zip(base_url,
                                              skills_root=SKILLS_ROOT),
                owner_id=OWNER_ID, tenant_id=TENANT_ID, permissions=['*'])
        codes = [issue.code.value for issue in info.value.issues]
        assert codes.count('INTERNAL_ADDRESS') == 2, (base_url, codes)


# ========================================================================
# INT-2612 P2：read_skill_directory 对链接目录显式拒绝
# ========================================================================

def _make_dir_link(link, target):
    """建目录链接：Windows 用 junction（无需管理员权限），其余平台用 symlink。"""
    if os.name == 'nt':
        # shell=True：mklink 是 cmd 内建命令，整串交给 cmd /c 才能正确解析引号
        result = subprocess.run(
            f'mklink /J "{link}" "{target}"', shell=True,
            capture_output=True, text=True, encoding='gbk', errors='replace')
        if result.returncode != 0:
            pytest.skip(f'无法创建 junction：{result.stderr or result.stdout}')
        return
    try:
        os.symlink(str(target), str(link), target_is_directory=True)
    except OSError as exc:
        pytest.skip(f'无法创建目录软链：{exc}')


def _skill_dir_with_marker(tmp_path):
    skill_dir = tmp_path / 'skills' / 'demo'
    skill_dir.mkdir(parents=True)
    (skill_dir / SKILL_FILE_NAME).write_text(
        '---\nname: demo\ndescription: 演示\n---\n\n## Gotchas\n\n- 无。\n',
        encoding='utf-8')
    return skill_dir


def test_top_level_resource_link_directory_rejected(tmp_path):
    """顶层资源目录是链接（软链 / junction）时不得被跟随读取。"""
    outside = tmp_path / 'outside'
    outside.mkdir()
    (outside / 'leak.md').write_text('外部内容', encoding='utf-8')
    skill_dir = _skill_dir_with_marker(tmp_path)
    _make_dir_link(skill_dir / 'references', outside)
    with pytest.raises(SkillPackageError) as info:
        read_skill_directory(str(skill_dir))
    assert info.value.code is PackageIssueCode.SYMLINK_REJECTED


def test_nested_resource_link_directory_rejected(tmp_path):
    """``references/`` 内的子目录是链接时同样拒绝（不只看顶层）。"""
    outside = tmp_path / 'outside'
    outside.mkdir()
    (outside / 'leak.md').write_text('外部内容', encoding='utf-8')
    skill_dir = _skill_dir_with_marker(tmp_path)
    references = skill_dir / 'references'
    references.mkdir()
    (references / 'guide.md').write_text('指引', encoding='utf-8')
    _make_dir_link(references / 'nested', outside)
    with pytest.raises(SkillPackageError) as info:
        read_skill_directory(str(skill_dir))
    assert info.value.code is PackageIssueCode.SYMLINK_REJECTED
