# -*- coding: utf-8 -*-
"""INT-2549 不得提权 / 不得越权引用工具（验收 3、4）。"""
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from agent_service.domain.exceptions import (
    SkillPermissionEscalation, SkillServiceError,
)
from tests.agent_skill.helpers import (
    OWNER_ID, TENANT_ID, build_skill_stack, draft_payload, issues_codes,
)


@pytest.fixture()
def container(tmp_path):
    container, _store = build_skill_stack(tmp_path)
    return container


def _create(container, payload, permissions):
    return container.skill_service.create(
        payload, owner_id=OWNER_ID, tenant_id=TENANT_ID,
        permissions=permissions, created_by=OWNER_ID)


def test_permission_not_held_is_rejected(container):
    with pytest.raises(SkillPermissionEscalation) as info:
        _create(container,
                draft_payload(permissions=['report:delete']),
                ['report:read'])
    assert info.value.code == 'SKILL_PERMISSION_ESCALATION'
    assert 'PERMISSION_ESCALATION' in issues_codes(info.value)
    assert container.repositories['skills'].list_active() == []


def test_wildcard_permission_requires_wildcard_user(container):
    with pytest.raises(SkillPermissionEscalation):
        _create(container, draft_payload(permissions=['*']),
                ['task:read', 'report:read'])
    # 本身拥有通配权限的用户可以放行
    view = _create(container, draft_payload(permissions=['*']), ['*'])
    assert view.status.value == 'DRAFT'


def test_subset_permissions_pass(container):
    view = _create(container, draft_payload(permissions=['task:read']),
                   ['task:read', 'task:create'])
    assert view.permissions == ('task:read',)


def test_unknown_tool_is_validation_error(container):
    with pytest.raises(SkillServiceError) as info:
        _create(container, draft_payload(allowed_tools=['task_delete_all']),
                ['*'])
    assert 'UNKNOWN_TOOL' in issues_codes(info.value)


def test_intent_and_tool_search_tools_pass(container):
    view = _create(container,
                   draft_payload(allowed_tools=['task_query', 'tool_search']),
                   ['*'])
    assert view.allowed_tools == ('task_query', 'tool_search')
