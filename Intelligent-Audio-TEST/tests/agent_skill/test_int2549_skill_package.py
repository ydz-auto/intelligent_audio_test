# -*- coding: utf-8 -*-
"""INT-2549 zip 单一口径 + 导入安全（验收 8）。

锚点：
- 导出包解压后根级为 ``SKILL.md``（可直接被外部 Agent 识别）；
- 导出包可被本接口重新导入且版本内容一致（body / content_hash）；
- 与既有 ``GET /api/v1/agent/skill`` 的结构断言一致（根级 ``SKILL.md``）；
- 路径穿越 / 软链 / zip bomb / 二进制 / 缺 SKILL.md 均拒绝。
"""
import io
import os
import stat
import zipfile

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from agent_service.domain.enums import SkillIssueCode
from agent_service.domain.exceptions import SkillImportInvalid
from agent_service.domain.model import skill as skill_model
from shared import skill_package
from tests.agent_skill.helpers import (
    OWNER_ID, TENANT_ID, build_skill_stack, create_draft, draft_payload,
    issues_codes,
)

BODY = ('# demo\n\n包内正文标记 PACKAGE_MARKER\n\n## Gotchas\n\n- 无。\n\n'
        '## 验收\n\n- 无。\n')


def _stack(tmp_path):
    container, store = build_skill_stack(tmp_path)
    return container, container.skill_service, store


def _zip_bytes(entries):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
    return buf.getvalue()


def test_export_root_level_skill_md_and_roundtrip(tmp_path):
    container, service, _store = _stack(tmp_path)
    view = create_draft(service, draft_payload(
        body=BODY, resources={'references/guide.md': '指引内容'}))
    filename, data = service.export_package(
        view.id, owner_id=OWNER_ID, tenant_id=TENANT_ID, permissions=['*'])
    assert filename == 'demo-skill.zip'
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        names = sorted(archive.namelist())
        assert names == ['SKILL.md', 'references/guide.md']
        assert not any(name.startswith('demo-skill/') for name in names)
        skill_md = archive.read('SKILL.md').decode('utf-8')
    assert skill_md.startswith('---\n')
    assert 'name: demo-skill' in skill_md
    assert 'PACKAGE_MARKER' in skill_md

    # 同名同作用域禁止重复创建（不静默覆盖）：先删原名再导入
    service.delete(view.id, owner_id=OWNER_ID, tenant_id=TENANT_ID)
    imported = service.import_package(
        data, owner_id=OWNER_ID, tenant_id=TENANT_ID, permissions=['*'])
    assert imported.name == view.name
    assert imported.content_hash == view.content_hash
    versions = container.repositories['skills'].list_versions(imported.id)
    assert versions[0].body == BODY.rstrip('\n')
    assert versions[0].resources['references/guide.md'] \
        == f'agent-skill/{imported.id}/1/references/guide.md'


def test_platform_skill_export_is_importable_shape(tmp_path):
    _container, service, _store = _stack(tmp_path)
    _filename, data = service.export_package(
        'platform:platform-reference', owner_id=OWNER_ID,
        tenant_id=TENANT_ID, permissions=['*'])
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        assert archive.namelist() == ['SKILL.md']
        assert archive.read('SKILL.md').decode('utf-8').startswith('---\n')


def test_shared_package_structure_matches_platform_package(monkeypatch):
    """平台包与用户包走**同一个**打包实现、同一套根级口径（不出现双口径）。"""
    from api_gateway.application.services.mcp import skill_package as gateway_pkg
    calls = {}
    real_build_zip = gateway_pkg.build_zip

    def spy(entries, **kwargs):
        calls['entries'] = dict(entries)
        return real_build_zip(entries, **kwargs)

    monkeypatch.setattr(gateway_pkg, 'build_zip', spy)
    platform_bytes = gateway_pkg.build_skill_zip('http://example')
    assert 'entries' in calls, '平台包必须复用 shared.skill_package.build_zip'
    assert skill_package.SKILL_FILE_NAME in calls['entries']
    assert all('/' not in name for name in calls['entries'])

    platform = zipfile.ZipFile(io.BytesIO(platform_bytes))
    assert 'SKILL.md' in platform.namelist()
    assert all('/' not in name for name in platform.namelist())
    # 两处常量指向同一物理文件名 / 目录约定（不各写一套）
    assert skill_package.SKILL_FILE_NAME == skill_model.SKILL_FILE_NAME
    assert tuple(skill_package.RESOURCE_DIRS) == tuple(skill_model.RESOURCE_DIRS)
    for code in skill_package.PackageIssueCode:
        assert code.value in {item.value for item in SkillIssueCode}, code.value


def test_import_path_traversal_rejected(tmp_path):
    _container, service, _store = _stack(tmp_path)
    data = _zip_bytes({'SKILL.md': '---\nname: x\n---\n\n## Gotchas\n',
                       '../evil.txt': 'x'})
    with pytest.raises(SkillImportInvalid) as info:
        service.import_package(data, owner_id=OWNER_ID, tenant_id=TENANT_ID,
                               permissions=['*'])
    assert 'INVALID_PATH' in issues_codes(info.value)


def test_import_absolute_path_rejected(tmp_path):
    _container, service, _store = _stack(tmp_path)
    data = _zip_bytes({'SKILL.md': '---\nname: x\n---\n\n## Gotchas\n',
                       '/etc/passwd': 'x'})
    with pytest.raises(SkillImportInvalid) as info:
        service.import_package(data, owner_id=OWNER_ID, tenant_id=TENANT_ID,
                               permissions=['*'])
    assert 'INVALID_PATH' in issues_codes(info.value)


def test_import_symlink_rejected(tmp_path):
    _container, service, _store = _stack(tmp_path)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as archive:
        archive.writestr('SKILL.md', '---\nname: x\n---\n\n## Gotchas\n')
        info = zipfile.ZipInfo('references/link.md')
        info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(info, 'target')
    with pytest.raises(SkillImportInvalid) as exc:
        service.import_package(buf.getvalue(), owner_id=OWNER_ID,
                               tenant_id=TENANT_ID, permissions=['*'])
    assert 'SYMLINK_REJECTED' in issues_codes(exc.value)


def test_import_zip_bomb_rejected(tmp_path):
    _container, service, _store = _stack(tmp_path)
    data = _zip_bytes({'SKILL.md': '---\nname: x\n---\n\n## Gotchas\n',
                       'references/zeros.txt': '0' * (2 * 1024 * 1024)})
    with pytest.raises(SkillImportInvalid) as exc:
        service.import_package(data, owner_id=OWNER_ID, tenant_id=TENANT_ID,
                               permissions=['*'])
    assert 'PACKAGE_TOO_LARGE' in issues_codes(exc.value)


def test_import_binary_resource_rejected(tmp_path):
    _container, service, _store = _stack(tmp_path)
    data = _zip_bytes({'SKILL.md': '---\nname: x\n---\n\n## Gotchas\n',
                       'assets/bin.dat': b'\x00\x01\x02'})
    with pytest.raises(SkillImportInvalid) as exc:
        service.import_package(data, owner_id=OWNER_ID, tenant_id=TENANT_ID,
                               permissions=['*'])
    assert 'BINARY_CONTENT' in issues_codes(exc.value)


def test_import_missing_skill_md_rejected(tmp_path):
    _container, service, _store = _stack(tmp_path)
    data = _zip_bytes({'references/guide.md': 'x'})
    with pytest.raises(SkillImportInvalid) as exc:
        service.import_package(data, owner_id=OWNER_ID, tenant_id=TENANT_ID,
                               permissions=['*'])
    assert 'SKILL_FILE_MISSING' in issues_codes(exc.value)


def test_platform_package_not_importable_until_int2476(tmp_path):
    """平台下载包（SKILL.md + mcp.json）当前**不支持**导入 —— 归 INT-2476。

    卡面「导入接受同一结构」指打包口径：根级直接是 ``SKILL.md``、不套外层
    目录、资源只放 ``references/ scripts/ assets/``。``GET /api/v1/agent/skill``
    额外带的 ``mcp.json`` 是网关 MCP 配置模板，且其 ``SKILL.md`` 没有
    frontmatter（不是可落库的用户 Skill）；平台包生成对齐由 INT-2476 负责，
    本卡先钉住「明确拒绝 + 给原因码」，避免静默接受半成品。
    """
    from api_gateway.application.services.mcp.skill_package import build_skill_zip
    _container, service, _store = _stack(tmp_path)
    with pytest.raises(SkillImportInvalid) as exc:
        service.import_package(build_skill_zip('http://example'),
                               owner_id=OWNER_ID, tenant_id=TENANT_ID,
                               permissions=['*'])
    assert 'INVALID_PATH' in issues_codes(exc.value)


def test_import_unexpected_root_file_rejected(tmp_path):
    _container, service, _store = _stack(tmp_path)
    data = _zip_bytes({'SKILL.md': '---\nname: x\n---\n\n## Gotchas\n',
                       'mcp.json': '{}'})
    with pytest.raises(SkillImportInvalid) as exc:
        service.import_package(data, owner_id=OWNER_ID, tenant_id=TENANT_ID,
                               permissions=['*'])
    assert 'INVALID_PATH' in issues_codes(exc.value)


def test_import_too_many_entries_rejected(tmp_path):
    _container, service, _store = _stack(tmp_path)
    entries = {'SKILL.md': '---\nname: x\n---\n\n## Gotchas\n'}
    entries.update({f'references/{index}.md': 'x' for index in range(220)})
    with pytest.raises(SkillImportInvalid) as exc:
        service.import_package(_zip_bytes(entries), owner_id=OWNER_ID,
                               tenant_id=TENANT_ID, permissions=['*'])
    assert 'TOO_MANY_ENTRIES' in issues_codes(exc.value)
