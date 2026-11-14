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
import re
import stat
import zipfile

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from agent_service.application.skill_service import SkillSettings
from agent_service.domain.enums import SkillIssueCode, SkillScope
from agent_service.domain.exceptions import SkillImportInvalid
from agent_service.domain.model import skill as skill_model
from agent_service.interfaces.api.upload_limit import (
    SkillImportUploadLimitMiddleware,
)
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
    # 资源键带本次写请求的一次性段（INT-2594：并发落败方不得覆盖胜出版本）
    key = versions[0].resources['references/guide.md']
    assert re.fullmatch(
        r'agent-skill/{0}/1/[0-9a-f]{{32}}/references/guide\.md'.format(
            re.escape(imported.id)), key), key


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

    platform = zipfile.ZipFile(io.BytesIO(platform_bytes))
    assert 'SKILL.md' in platform.namelist()
    # INT-2476：根级只有 SKILL.md，资源只放 references/scripts/assets/
    for name in platform.namelist():
        assert name == skill_package.SKILL_FILE_NAME \
            or name.startswith(skill_package.RESOURCE_PREFIXES), name
    # 两处常量指向同一物理文件名 / 目录约定（不各写一套）
    assert skill_package.SKILL_FILE_NAME == skill_model.SKILL_FILE_NAME
    assert tuple(skill_package.RESOURCE_DIRS) == tuple(skill_model.RESOURCE_DIRS)
    for code in skill_package.PackageIssueCode:
        assert code.value in {item.value for item in SkillIssueCode}, code.value
    # 网关不依赖 agent_service 包，导入错误码与域枚举同值（不各写一套）
    from agent_service.domain.enums import SkillErrorCode
    assert skill_package.SKILL_IMPORT_INVALID_CODE \
        == SkillErrorCode.SKILL_IMPORT_INVALID.value


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


def test_platform_package_is_importable_after_int2476(tmp_path):
    """INT-2476：平台下载包与用户包同结构，导入不再被 ``mcp.json`` 拒绝。

    平台包根级是带 frontmatter 的 ``SKILL.md``，MCP 配置模板落在
    ``assets/mcp.json``（资源目录），因此可以原样经
    ``POST /api/v1/agent/skills/import`` 落库；导入后再导出仍是同一结构。
    """
    from api_gateway.application.services.mcp.skill_package import build_skill_zip
    _container, service, _store = _stack(tmp_path)
    imported = service.import_package(build_skill_zip('http://example.com'),
                                      owner_id=OWNER_ID, tenant_id=TENANT_ID,
                                      permissions=['*'])
    assert imported.name == 'intelligent-audio-test'
    _filename, exported = service.export_package(
        imported.id, owner_id=OWNER_ID, tenant_id=TENANT_ID, permissions=['*'])
    with zipfile.ZipFile(io.BytesIO(exported)) as archive:
        names = archive.namelist()
    assert names == ['SKILL.md', 'assets/mcp.json',
                     'references/endpoints.md', 'references/mcp-tools.md']
    with zipfile.ZipFile(io.BytesIO(exported)) as archive:
        assert archive.read('SKILL.md').decode('utf-8').startswith('---\n')


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


# ---------------------------------------------------------------- 返工 P3

DATE_SKILL_MD = (
    '---\nname: date-skill\ndescription: 日期标量演示。触发词：日期\n'
    'released: 2026-11-14\n---\n\n'
    '# date\n\n## Gotchas\n\n- 无。\n\n## 验收\n\n- 无。\n')

BINARY_SCALAR_SKILL_MD = (
    '---\nname: bin-skill\ndescription: 二进制标量演示。触发词：二进制\n'
    'blob: !!binary aGVsbG8=\n---\n\n'
    '# bin\n\n## Gotchas\n\n- 无。\n\n## 验收\n\n- 无。\n')


def test_import_yaml_date_scalar_is_normalized(tmp_path):
    """返工 P3：YAML 日期标量不能把 content_hash / JSONB 打成 500。"""
    container, service, _store = _stack(tmp_path)
    imported = service.import_package(
        _zip_bytes({'SKILL.md': DATE_SKILL_MD}), owner_id=OWNER_ID,
        tenant_id=TENANT_ID, permissions=['*'])
    assert imported.name == 'date-skill'
    assert imported.content_hash
    version = container.repositories['skills'].get_version(imported.id, '1')
    # 归一为 ISO 字符串（date/datetime 原对象不可 JSON 序列化）
    assert version.frontmatter['released'] == '2026-11-14'
    assert isinstance(version.frontmatter['released'], str)
    # 导出 → 重新导入内容指纹一致（归一化不破坏单一包口径）
    _filename, exported = service.export_package(
        imported.id, owner_id=OWNER_ID, tenant_id=TENANT_ID, permissions=['*'])
    service.delete(imported.id, owner_id=OWNER_ID, tenant_id=TENANT_ID)
    again = service.import_package(exported, owner_id=OWNER_ID,
                                   tenant_id=TENANT_ID, permissions=['*'])
    assert again.content_hash == imported.content_hash


def test_import_non_json_scalar_is_rejected_with_reason_code(tmp_path):
    """``!!binary`` 等非 JSON 标量 → 4xx INVALID_FRONTMATTER（不是 500）。"""
    _container, service, _store = _stack(tmp_path)
    with pytest.raises(SkillImportInvalid) as exc:
        service.import_package(
            _zip_bytes({'SKILL.md': BINARY_SCALAR_SKILL_MD}),
            owner_id=OWNER_ID, tenant_id=TENANT_ID, permissions=['*'])
    assert 'INVALID_FRONTMATTER' in issues_codes(exc.value)


def test_import_upload_size_limited_before_parse(tmp_path):
    """上传原始字节超过上限：解析前拒绝（PACKAGE_TOO_LARGE，不落库）。"""
    container, _store = build_skill_stack(
        tmp_path, settings=SkillSettings(max_upload_bytes=32))
    service = container.skill_service
    data = _zip_bytes({'SKILL.md': DATE_SKILL_MD})
    assert len(data) > 32
    with pytest.raises(SkillImportInvalid) as exc:
        service.import_package(data, owner_id=OWNER_ID,
                               tenant_id=TENANT_ID, permissions=['*'])
    assert 'PACKAGE_TOO_LARGE' in issues_codes(exc.value)
    assert container.repositories['skills'].find_by_name(
        SkillScope.USER, 'date-skill', owner_id=OWNER_ID) is None


def test_upload_limit_middleware_rejects_declared_length():
    """中间件在解析 multipart 之前按 Content-Length 拒绝（413）。"""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()

    @app.post('/api/v1/agent/skills/import')
    async def _import():  # pragma: no cover - 不应被调用
        return {'ok': True}

    app.add_middleware(SkillImportUploadLimitMiddleware, max_bytes=16)
    client = TestClient(app)
    resp = client.post('/api/v1/agent/skills/import', content=b'x' * 32,
                       headers={'Content-Type': 'application/zip'})
    assert resp.status_code == 413
    assert resp.json()['code'] == 'SKILL_IMPORT_INVALID'
    assert resp.json()['issues'][0]['code'] == 'PACKAGE_TOO_LARGE'
