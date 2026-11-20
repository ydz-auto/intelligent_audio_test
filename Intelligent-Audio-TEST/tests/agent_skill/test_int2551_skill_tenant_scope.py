# -*- coding: utf-8 -*-
"""INT-2551 TENANT 级共享 Skill（写入 / 隔离 / 同名 / 可见性 / 强制停用）。

验收锚点（卡面「可测验收标准」3、4、6、7、8）：
- 写入要求租户管理员双条件，``tenant_id`` 服务端填、``owner_id`` 记创建人；
- 跨租户：列表不可见、按 id 访问 404（不泄漏存在性）；
- 同名：PLATFORM 冲突 / 同租户同作用域拒绝 / TENANT 与 USER 同名 USER 优先
  且列表标注遮蔽；
- ``ACTIVE`` 才对同租户普通用户可见并进 L1，停用立即消失；
- 在办 run 按 ``agent_run_skill`` 快照继续，内容不漂移。
"""
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from agent_service.domain.enums import (
    SkillReviewAction, SkillReviewDecision, SkillScope, SkillStatus,
)
from agent_service.domain.exceptions import (
    SkillNameConflict, SkillNotFound, SkillReviewForbidden,
    SkillStatusInvalid,
)
from agent_service.domain.model.agent_skill import AgentRunSkill
from tests.agent_skill.helpers import (
    GATE_GOLDEN, OTHER_USER_ID, OWNER_ID, StaticGoldenTasks, TENANT_ID,
    build_skill_stack, create_draft, create_tenant_skill, demo_body,
    draft_payload,
)

OTHER_TENANT = 't2'
OTHER_ADMIN_ID = OWNER_ID + 1


def _stack(tmp_path):
    container, _store = build_skill_stack(
        tmp_path, golden=StaticGoldenTasks(GATE_GOLDEN))
    return container, container.skill_service, container.skill_review_service


def _activate(container, skills, reviews, view, *, actor=OWNER_ID):
    """提交 + 由另一个管理员批准 → ACTIVE。"""
    reviews.submit(view.id, owner_id=actor, tenant_id=TENANT_ID,
                   permissions=['*'], is_admin=True)
    reviews.decide(view.id, SkillReviewDecision.APPROVE,
                   owner_id=OTHER_ADMIN_ID, tenant_id=TENANT_ID,
                   permissions=['*'], is_admin=True)


# ---------------------------------------------------------------- 写入身份


def test_create_fills_tenant_and_owner_from_identity(tmp_path):
    _container, skills, _reviews = _stack(tmp_path)
    view = create_tenant_skill(skills, owner_id=OWNER_ID)
    assert view.scope is SkillScope.TENANT
    assert view.tenant_id == TENANT_ID
    # owner_id 记录创建人（审计 / 审核链要能看出谁创建）
    assert view.owner_id == OWNER_ID
    assert view.created_by == OWNER_ID
    assert view.status is SkillStatus.DRAFT


def test_tenant_create_requires_admin(tmp_path):
    _container, skills, _reviews = _stack(tmp_path)
    with pytest.raises(SkillReviewForbidden):
        create_tenant_skill(skills, is_admin=False)


def test_non_admin_cannot_update_or_disable_tenant_skill(tmp_path):
    _container, skills, _reviews = _stack(tmp_path)
    view = create_tenant_skill(skills)
    # 同租户普通用户（非管理员）看得到，但改不了
    with pytest.raises(SkillReviewForbidden):
        skills.update(view.id, draft_payload(body=demo_body('越权改')),
                      owner_id=OTHER_USER_ID, tenant_id=TENANT_ID,
                      permissions=['agent:skill:manage'], is_admin=False)
    with pytest.raises(SkillReviewForbidden):
        skills.disable(view.id, owner_id=OTHER_USER_ID, tenant_id=TENANT_ID,
                       permissions=['agent:skill:manage'], is_admin=False)


def test_tenant_skill_cannot_be_deleted(tmp_path):
    container, skills, _reviews = _stack(tmp_path)
    view = create_tenant_skill(skills)
    with pytest.raises(SkillStatusInvalid):
        skills.delete(view.id, owner_id=OWNER_ID, tenant_id=TENANT_ID,
                      permissions=['*'], is_admin=True)
    assert container.repositories['skills'].get(view.id) is not None


# ---------------------------------------------------------------- 跨租户隔离


def test_other_tenant_cannot_see_or_touch_tenant_skill(tmp_path):
    container, skills, reviews = _stack(tmp_path)
    view = create_tenant_skill(skills)
    _activate(container, skills, reviews, view)

    listing = skills.list(owner_id=OTHER_USER_ID, tenant_id=OTHER_TENANT,
                          permissions=['*'])
    assert all(item.id != view.id for item in listing)

    with pytest.raises(SkillNotFound):
        skills.get(view.id, owner_id=OTHER_USER_ID, tenant_id=OTHER_TENANT,
                   permissions=['*'])
    with pytest.raises(SkillNotFound):
        skills.update(view.id, draft_payload(body=demo_body('跨租户改')),
                      owner_id=OTHER_USER_ID, tenant_id=OTHER_TENANT,
                      permissions=['*'], is_admin=True)
    with pytest.raises(SkillNotFound):
        reviews.submit(view.id, owner_id=OTHER_USER_ID, tenant_id=OTHER_TENANT,
                       permissions=['*'], is_admin=True)
    # 跨租户不泄漏存在性：错误码统一 SKILL_NOT_FOUND
    try:
        skills.get(view.id, owner_id=OTHER_USER_ID, tenant_id=OTHER_TENANT)
    except SkillNotFound as exc:
        assert exc.code == 'SKILL_NOT_FOUND'


def test_same_tenant_user_sees_active_tenant_skill(tmp_path):
    container, skills, reviews = _stack(tmp_path)
    view = create_tenant_skill(skills)
    _activate(container, skills, reviews, view)

    listing = skills.list(owner_id=OTHER_USER_ID, tenant_id=TENANT_ID,
                          permissions=['*'])
    assert any(item.id == view.id for item in listing)
    names = [s.name for s in container.skill_registry.visible_for(
        ['*'], owner_id=OTHER_USER_ID, tenant_id=TENANT_ID)]
    assert 'demo-skill' in names
    # 别的租户看不到
    names = [s.name for s in container.skill_registry.visible_for(
        ['*'], owner_id=OTHER_USER_ID, tenant_id=OTHER_TENANT)]
    assert 'demo-skill' not in names


# ---------------------------------------------------------------- 同名规则


def test_platform_name_conflict(tmp_path):
    _container, skills, _reviews = _stack(tmp_path)
    with pytest.raises(SkillNameConflict):
        create_tenant_skill(skills, draft_payload(name='platform-reference'))


def test_same_tenant_scope_duplicate_rejected(tmp_path):
    _container, skills, _reviews = _stack(tmp_path)
    create_tenant_skill(skills)
    with pytest.raises(SkillNameConflict):
        create_tenant_skill(skills)


def test_same_name_in_other_tenant_is_allowed(tmp_path):
    _container, skills, _reviews = _stack(tmp_path)
    create_tenant_skill(skills, tenant_id=TENANT_ID, owner_id=OWNER_ID)
    view = create_tenant_skill(skills, tenant_id=OTHER_TENANT,
                               owner_id=OTHER_USER_ID)
    assert view.tenant_id == OTHER_TENANT


def test_user_skill_wins_over_tenant_with_same_name(tmp_path):
    container, skills, reviews = _stack(tmp_path)
    tenant_view = create_tenant_skill(skills)
    _activate(container, skills, reviews, tenant_view)

    user_view = create_draft(skills)  # 同名 USER 草稿：允许（USER 优先）
    published = skills.publish(user_view.id, owner_id=OWNER_ID,
                               tenant_id=TENANT_ID, permissions=['*'])
    assert published.skill.status is SkillStatus.ACTIVE

    items = skills.list(owner_id=OWNER_ID, tenant_id=TENANT_ID,
                        permissions=['*'])
    same = [item for item in items if item.name == 'demo-skill']
    effective = [item for item in same if not item.masked_by]
    masked = [item for item in same if item.masked_by]
    assert [item.scope for item in effective] == [SkillScope.USER]
    assert [item.scope for item in masked] == [SkillScope.TENANT]
    assert masked[0].masked_by == SkillScope.USER.value
    # L1 只取生效项（USER）
    visible = container.skill_registry.visible_for(
        ['*'], owner_id=OWNER_ID, tenant_id=TENANT_ID)
    hits = [s for s in visible if s.name == 'demo-skill']
    assert [s.scope for s in hits] == [SkillScope.USER]


# ---------------------------------------------------------------- 强制停用


def test_admin_can_disable_any_tenant_skill_and_it_disappears(tmp_path):
    container, skills, reviews = _stack(tmp_path)
    view = create_tenant_skill(skills, owner_id=OWNER_ID)
    _activate(container, skills, reviews, view, actor=OWNER_ID)
    assert 'demo-skill' in [s.name for s in container.skill_registry.visible_for(
        ['*'], owner_id=OTHER_USER_ID, tenant_id=TENANT_ID)]

    disabled = skills.disable(view.id, owner_id=OTHER_ADMIN_ID,
                              tenant_id=TENANT_ID, permissions=['*'],
                              is_admin=True, reason='内容过期')
    assert disabled.status is SkillStatus.DISABLED
    assert 'demo-skill' not in [
        s.name for s in container.skill_registry.visible_for(
            ['*'], owner_id=OTHER_USER_ID, tenant_id=TENANT_ID)]
    # 停用落一条 DISABLE 审计（谁、哪版、什么理由）
    history = reviews.history(view.id, owner_id=OTHER_ADMIN_ID,
                              tenant_id=TENANT_ID)
    assert history[-1].action is SkillReviewAction.DISABLE
    assert history[-1].status_from is SkillStatus.ACTIVE
    assert history[-1].status_to is SkillStatus.DISABLED
    assert history[-1].reviewer_id == OTHER_ADMIN_ID
    assert history[-1].reason == '内容过期'


def test_disable_is_idempotent_no_duplicate_audit(tmp_path):
    container, skills, reviews = _stack(tmp_path)
    view = create_tenant_skill(skills)
    skills.disable(view.id, owner_id=OWNER_ID, tenant_id=TENANT_ID,
                   permissions=['*'], is_admin=True)
    skills.disable(view.id, owner_id=OWNER_ID, tenant_id=TENANT_ID,
                   permissions=['*'], is_admin=True)
    history = reviews.history(view.id, owner_id=OWNER_ID, tenant_id=TENANT_ID)
    assert [row.action for row in history] == [SkillReviewAction.DISABLE]


def test_inflight_run_keeps_snapshot_after_disable(tmp_path):
    """在办 run 按 ``agent_run_skill`` 快照继续，停用后内容不漂移。"""
    container, skills, _reviews = _stack(tmp_path)
    view = create_tenant_skill(skills)
    repo = container.repositories['skills']
    repo.update(view.id, status=SkillStatus.ACTIVE.value)
    skills.refresh_registry()
    container.repositories['run_skills'].add(AgentRunSkill(
        run_id='run-1', skill_id=view.id, version=view.version,
        content_hash=view.content_hash))

    skills.disable(view.id, owner_id=OWNER_ID, tenant_id=TENANT_ID,
                   permissions=['*'], is_admin=True)
    snapshot = skills.snapshot_skill('run-1')
    assert snapshot is not None
    assert snapshot.skill_id == view.id
    assert '演示内容' in snapshot.body
    # 新 run 不再可见
    assert 'demo-skill' not in [
        s.name for s in container.skill_registry.visible_for(
            ['*'], owner_id=OTHER_USER_ID, tenant_id=TENANT_ID)]
