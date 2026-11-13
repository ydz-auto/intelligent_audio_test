# -*- coding: utf-8 -*-
"""INT-2549 落库前逐项校验（验收 2）。

每个负例都断言：返回对应原因码，且**不落库**（当前行 / 版本行均为空）。
"""
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from agent_service.domain.exceptions import SkillServiceError
from tests.agent_skill.helpers import (
    OWNER_ID, TENANT_ID, build_skill_stack, demo_body, draft_payload,
    issues_codes,
)


@pytest.fixture()
def service(tmp_path):
    container, _store = build_skill_stack(tmp_path)
    return container


def _expect(service, payload, code):
    with pytest.raises(SkillServiceError) as info:
        service.skill_service.create(
            payload, owner_id=OWNER_ID, tenant_id=TENANT_ID,
            permissions=['*'], created_by=OWNER_ID)
    assert code in issues_codes(info.value), issues_codes(info.value)
    rows = service.repositories['skills'].list_visible(
        tenant_id=TENANT_ID, owner_id=OWNER_ID)
    assert rows == [], '校验失败不得落库'
    assert service.repositories['skills'].list_active() == []
    return info.value


def test_invalid_name_rejected(service):
    _expect(service, draft_payload('Bad_Name!'), 'INVALID_NAME')


def test_missing_description_rejected(service):
    _expect(service, draft_payload('no-desc', description=''),
            'MISSING_DESCRIPTION')


def test_missing_gotchas_section_rejected(service):
    body = '# demo\n\n内容。\n\n## 验收\n\n- 无。\n'
    _expect(service, draft_payload(body=body), 'MISSING_REQUIRED_SECTION')


def test_missing_acceptance_section_rejected(service):
    body = '# demo\n\n内容。\n\n## Gotchas\n\n- 无。\n'
    _expect(service, draft_payload(body=body), 'MISSING_REQUIRED_SECTION')


def test_body_over_500_lines_rejected(service):
    filler = '\n'.join(f'- 第 {index} 行' for index in range(520))
    body = ('# demo\n\n' + filler + '\n\n## Gotchas\n\n- 无。\n\n'
            '## 验收\n\n- 无。\n')
    _expect(service, draft_payload(body=body), 'BODY_TOO_LONG')


def test_skill_md_over_64kb_rejected(service):
    body = demo_body(marker='x' * (70 * 1024))
    _expect(service, draft_payload(body=body), 'BODY_TOO_LARGE')


def test_resource_over_512kb_rejected(service):
    payload = draft_payload(resources={
        'references/big.txt': 'a' * (600 * 1024)})
    _expect(service, payload, 'RESOURCE_TOO_LARGE')


def test_package_over_5mb_rejected(service):
    payload = draft_payload(resources={
        'references/a.txt': 'a' * (3 * 1024 * 1024),
        'references/b.txt': 'b' * (3 * 1024 * 1024)})
    _expect(service, payload, 'PACKAGE_TOO_LARGE')


def test_absolute_resource_path_rejected(service):
    _expect(service, draft_payload(resources={'/etc/passwd': 'x'}),
            'INVALID_PATH')


def test_parent_dir_resource_path_rejected(service):
    _expect(service, draft_payload(resources={'references/../evil.txt': 'x'}),
            'INVALID_PATH')


def test_external_link_resource_rejected(service):
    _expect(service,
            draft_payload(resources={'https://evil.example/x.md': 'x'}),
            'EXTERNAL_LINK_REJECTED')


def test_resource_outside_allowed_dirs_rejected(service):
    _expect(service, draft_payload(resources={'other/x.txt': 'x'}),
            'INVALID_PATH')


def test_embedded_secret_rejected(service):
    body = demo_body(marker='api_key = sk-abcdefghijklmnop1234')
    _expect(service, draft_payload(body=body), 'EMBEDDED_SECRET')


def test_internal_address_rejected(service):
    body = demo_body(marker='调用 http://192.168.1.10:8080/api 即可')
    _expect(service, draft_payload(body=body), 'INTERNAL_ADDRESS')


def test_binary_resource_rejected(service):
    _expect(service,
            draft_payload(resources={'assets/bin.dat': '\x00\x01\x02'}),
            'BINARY_CONTENT')


def test_unknown_tool_rejected(service):
    _expect(service, draft_payload(allowed_tools=['not_a_registered_tool']),
            'UNKNOWN_TOOL')


def test_registered_tools_accepted(service):
    view = service.skill_service.create(
        draft_payload(allowed_tools=['task_query', 'tool_search']),
        owner_id=OWNER_ID, tenant_id=TENANT_ID, permissions=['*'],
        created_by=OWNER_ID)
    assert view.status.value == 'DRAFT'
