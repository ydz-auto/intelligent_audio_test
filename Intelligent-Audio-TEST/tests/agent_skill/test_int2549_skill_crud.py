# -*- coding: utf-8 -*-
"""INT-2549 三层来源 / 同名规则 / 本人可见（验收 1）。

锚点：
- 与内置 Skill 同名 → ``SKILL_NAME_CONFLICT``；
- 同一作用域同名 → 拒绝，不静默覆盖；
- TENANT + USER 同名 → USER 生效、列表返回被遮蔽项并带 ``masked_by``；
- 其他用户不可见（USER 私有）；PLATFORM 无写入口。
"""
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from agent_service.application.skill_service import SkillDraftPayload
from agent_service.domain.enums import SkillScope, SkillStatus
from agent_service.domain.exceptions import (
    SkillNameConflict, SkillNotFound,
)
from agent_service.domain.model.agent_skill import AgentSkill, AgentSkillVersion
from tests.agent_skill.helpers import (
    OTHER_USER_ID, OWNER_ID, TENANT_ID, build_skill_stack, create_draft,
    draft_payload,
)


def _service(tmp_path):
    container, store = build_skill_stack(tmp_path)
    return container, container.skill_service, store


def test_create_draft_defaults(tmp_path):
    container, service, _store = _service(tmp_path)
    view = create_draft(service)
    assert view.scope is SkillScope.USER
    assert view.status is SkillStatus.DRAFT
    assert view.version == '1'
    assert view.owner_id == OWNER_ID
    assert view.content_hash
    stored = container.repositories['skills'].get(view.id)
    assert stored.tenant_id == TENANT_ID


def test_platform_name_conflict_is_rejected(tmp_path):
    _container, service, _store = _service(tmp_path)
    with pytest.raises(SkillNameConflict) as info:
        create_draft(service, draft_payload('platform-reference'))
    assert info.value.code == 'SKILL_NAME_CONFLICT'


def test_same_scope_duplicate_is_rejected_not_overwritten(tmp_path):
    container, service, _store = _service(tmp_path)
    first = create_draft(service)
    with pytest.raises(SkillNameConflict):
        create_draft(service)
    rows = container.repositories['skills'].list_visible(
        tenant_id=TENANT_ID, owner_id=OWNER_ID)
    assert [row.id for row in rows] == [first.id]


def test_tenant_skill_masked_by_user_skill(tmp_path):
    container, service, _store = _service(tmp_path)
    tenant_skill = container.repositories['skills'].add(AgentSkill(
        id='tenant-demo', scope=SkillScope.TENANT, tenant_id=TENANT_ID,
        owner_id=None, name='demo-skill', description='租户级演示',
        version='1', status=SkillStatus.ACTIVE, content_hash='x'))
    container.repositories['skills'].add_version(AgentSkillVersion(
        skill_id=tenant_skill.id, version='1', content_hash='x',
        body='# tenant\n\n## Gotchas\n\n- 无。\n\n## 验收\n\n- 无。\n',
        frontmatter={'name': 'demo-skill', 'description': '租户级演示'}))
    user_view = create_draft(service)
    service.publish  # noqa: B018 - 仅确认属性存在
    # USER 层要参与合并必须先 ACTIVE：直接置状态（不走发布门槛）
    container.repositories['skills'].update(
        user_view.id, status=SkillStatus.ACTIVE.value, version='1')
    container.skill_registry.reload()
    service._refresh_registry()

    items = service.list(owner_id=OWNER_ID, tenant_id=TENANT_ID,
                         permissions=['*'])
    by_name = {item.scope: item for item in items if item.name == 'demo-skill'}
    assert SkillScope.USER in by_name
    assert SkillScope.TENANT in by_name
    assert by_name[SkillScope.TENANT].masked_by == 'USER'
    assert by_name[SkillScope.USER].masked_by is None
    # L1 只取生效项（USER），不出现被遮蔽的 TENANT
    registry = container.skill_registry
    visible = registry.visible_for(['*'], owner_id=OWNER_ID,
                                   tenant_id=TENANT_ID)
    assert [s.name for s in visible if s.name == 'demo-skill'] == ['demo-skill']
    assert visible[[s.name for s in visible].index('demo-skill')].scope \
        is SkillScope.USER


def test_other_user_cannot_see_or_touch_private_skill(tmp_path):
    container, service, _store = _service(tmp_path)
    view = create_draft(service)
    other_items = service.list(owner_id=OTHER_USER_ID, tenant_id=TENANT_ID,
                               permissions=['*'])
    assert all(item.id != view.id for item in other_items)
    with pytest.raises(SkillNotFound):
        service.get(view.id, owner_id=OTHER_USER_ID, tenant_id=TENANT_ID,
                    permissions=['*'])
    with pytest.raises(SkillNotFound):
        service.update(view.id, draft_payload(), owner_id=OTHER_USER_ID,
                       tenant_id=TENANT_ID, permissions=['*'])


def test_platform_skill_has_no_write_entry(tmp_path):
    _container, service, _store = _service(tmp_path)
    platform_id = 'platform:platform-reference'
    with pytest.raises(SkillNotFound):
        service.update(platform_id, draft_payload(), owner_id=OWNER_ID,
                       tenant_id=TENANT_ID, permissions=['*'])
    with pytest.raises(SkillNotFound):
        service.disable(platform_id, owner_id=OWNER_ID, tenant_id=TENANT_ID)
    # 但可以读（列表里的平台行）
    view = service.get(platform_id, owner_id=OWNER_ID, tenant_id=TENANT_ID,
                       permissions=['*'])
    assert view.scope is SkillScope.PLATFORM


def test_update_increments_version_and_returns_to_draft(tmp_path):
    container, service, _store = _service(tmp_path)
    view = create_draft(service)
    updated = service.update(
        view.id, draft_payload(body=demo_body_with_marker('第二版')),
        owner_id=OWNER_ID, tenant_id=TENANT_ID, permissions=['*'])
    assert updated.version == '2'
    assert updated.status is SkillStatus.DRAFT
    versions = container.repositories['skills'].list_versions(view.id)
    assert [item.version for item in versions] == ['1', '2']


def demo_body_with_marker(marker):
    return f"""# demo

{marker}

## Gotchas

- 无。

## 验收

- 无。
"""


def test_put_only_body_keeps_resources_and_frontmatter(tmp_path):
    """PUT 语义：未出现的字段不改（只改正文不能把资源 / frontmatter 清空）。"""
    container, service, _store = _service(tmp_path)
    view = create_draft(service, draft_payload(
        resources={'references/guide.md': '指引'},
        permissions=['task:read']))
    updated = service.update(
        view.id, SkillDraftPayload(body=demo_body_with_marker('只改正文')),
        owner_id=OWNER_ID, tenant_id=TENANT_ID, permissions=['task:read'])
    assert updated.version == '2'
    assert updated.permissions == ('task:read',)
    version = container.repositories['skills'].get_version(view.id, '2')
    assert version.body.startswith('# demo')
    assert 'references/guide.md' in version.resources
    assert _store.get(version.resources['references/guide.md']) == '指引'.encode()


def test_put_without_body_keeps_current_version_body(tmp_path):
    container, service, _store = _service(tmp_path)
    view = create_draft(service, draft_payload(
        body=demo_body_with_marker('原始正文')))
    updated = service.update(
        view.id, SkillDraftPayload(description='改过的描述。触发词：演示'),
        owner_id=OWNER_ID, tenant_id=TENANT_ID, permissions=['*'])
    assert updated.version == '2'
    version = container.repositories['skills'].get_version(view.id, '2')
    assert '原始正文' in version.body
    assert version.frontmatter['description'] == '改过的描述。触发词：演示'
