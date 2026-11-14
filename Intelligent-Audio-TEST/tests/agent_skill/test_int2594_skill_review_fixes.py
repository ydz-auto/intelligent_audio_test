# -*- coding: utf-8 -*-
"""INT-2594 缺陷回归：TENANT Skill 审核流三项缺口（P1 / P2 / P3）。

来源：INT-2589（M2 收口一致性审计）对 INT-2551（``8baf27743``）的结论。
本文件的用例在修复前**失败**、修复后通过：

- **P1** 提交人可自批：租户管理员 B 提交管理员 A 的草稿后可以 B 身份批准，
  A 全程不参与，第二人复核失效；修复后 ``SKILL_SELF_REVIEW_FORBIDDEN``。
- **P2** ``PUT`` 越过审核状态机：``ACTIVE`` / ``DISABLED`` 的 TENANT Skill
  被直接改回 ``DRAFT`` 且不落 ``agent_skill_review``；修复后 ``ACTIVE`` 走
  显式 ``EDIT`` 边并写审计、``DISABLED`` 无出边直接 409。
- **P3** ``agent:skill:admin`` 权限码无效：只授该码的自定义角色过得了网关
  却被服务端 403；修复后网关按「管理员级授予」下发 ``X-User-Is-Admin``，
  服务端复核成立。

返工口径（审计打回项）：``ACTIVE`` 保存的「资源写 → 状态迁移 → 版本行 →
当前行 → EDIT 审计」任一失败都不得把已发布版本留在 DRAFT 且无审计的中间态
（资源写排在事务前，其余四件事在同一仓储事务里提交）；``submit`` 的
「先迁移、后审计」窗口在 ``decide`` 侧按 fail-closed 拒绝。
"""
import os
from datetime import datetime, timezone

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')
os.environ.setdefault('AGENT_ENABLED', 'true')

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent_service.app import create_app
from agent_service.domain.enums import (
    SkillReviewAction, SkillReviewDecision, SkillStatus,
)
from agent_service.domain.exceptions import (
    SkillSelfReviewForbidden, SkillStatusInvalid,
)
from agent_service.domain.model.agent_skill import (
    AgentSkillReview, AgentSkillVersion,
)
from agent_service.domain.services.skill_tenancy import is_tenant_admin
from shared.constants.permissions import SKILL_ADMIN_PERMISSION
from tests.agent_skill.helpers import (
    GATE_GOLDEN, OWNER_ID, PROJECT_ROOT, StaticGoldenTasks, TENANT_ID,
    build_skill_stack, create_tenant_skill, demo_body, draft_payload,
)

# 创建人（A）/ 提交人（B）/ 第三个管理员（C）
CREATOR_ID = OWNER_ID
SUBMITTER_ID = OWNER_ID + 1
THIRD_ADMIN_ID = OWNER_ID + 2


def _stack(tmp_path, *, golden=True):
    container, _store = build_skill_stack(
        tmp_path,
        golden=StaticGoldenTasks(GATE_GOLDEN if golden else {}))
    return container, container.skill_service, container.skill_review_service


def _submit(service, skill_id, *, actor):
    return service.submit(skill_id, owner_id=actor, tenant_id=TENANT_ID,
                          permissions=['*'], is_admin=True)


def _decide(service, skill_id, decision, *, actor, reason=''):
    return service.decide(skill_id, decision, owner_id=actor,
                          tenant_id=TENANT_ID, permissions=['*'],
                          is_admin=True, reason=reason)


def _edit(skills, skill_id, *, actor=CREATOR_ID, body='编辑后的正文'):
    return skills.update(
        skill_id, draft_payload(body=demo_body(body)), owner_id=actor,
        tenant_id=TENANT_ID, permissions=['*'], is_admin=True)


def _status(container, skill_id):
    return container.repositories['skills'].get(skill_id).status


def _history(reviews, skill_id, *, actor=CREATOR_ID):
    return reviews.history(skill_id, owner_id=actor, tenant_id=TENANT_ID)


def _activate(container, skills, reviews, *, creator=CREATOR_ID,
              submitter=CREATOR_ID, approver=SUBMITTER_ID):
    view = create_tenant_skill(skills, owner_id=creator)
    _submit(reviews, view.id, actor=submitter)
    _decide(reviews, view.id, SkillReviewDecision.APPROVE, actor=approver)
    assert _status(container, view.id) is SkillStatus.ACTIVE
    return view


# ---------------------------------------------------------------- P1 提交人自批


def test_submitter_cannot_approve_own_submission(tmp_path):
    """A 创建 → B 提交 → B 批准：必须 403，状态不变（修复前会通过）。"""
    container, skills, reviews = _stack(tmp_path)
    view = create_tenant_skill(skills, owner_id=CREATOR_ID)
    _submit(reviews, view.id, actor=SUBMITTER_ID)

    with pytest.raises(SkillSelfReviewForbidden) as info:
        _decide(reviews, view.id, SkillReviewDecision.APPROVE,
                actor=SUBMITTER_ID)
    assert info.value.code == 'SKILL_SELF_REVIEW_FORBIDDEN'
    assert _status(container, view.id) is SkillStatus.PENDING_REVIEW


def test_submitter_cannot_reject_own_submission(tmp_path):
    """驳回同理：自提要第二人处理。"""
    container, skills, reviews = _stack(tmp_path)
    view = create_tenant_skill(skills, owner_id=CREATOR_ID)
    _submit(reviews, view.id, actor=SUBMITTER_ID)

    with pytest.raises(SkillSelfReviewForbidden):
        _decide(reviews, view.id, SkillReviewDecision.REJECT,
                actor=SUBMITTER_ID, reason='自拒')
    assert _status(container, view.id) is SkillStatus.PENDING_REVIEW


def test_third_admin_can_approve_after_another_admin_submitted(tmp_path):
    """A 创建 → B 提交 → C 批准：第三人复核成立，不被新拦截误伤。"""
    container, skills, reviews = _stack(tmp_path)
    view = create_tenant_skill(skills, owner_id=CREATOR_ID)
    _submit(reviews, view.id, actor=SUBMITTER_ID)

    approved = _decide(reviews, view.id, SkillReviewDecision.APPROVE,
                       actor=THIRD_ADMIN_ID)
    assert approved.skill.status is SkillStatus.ACTIVE
    assert _status(container, view.id) is SkillStatus.ACTIVE


def test_decide_fails_closed_while_submit_audit_not_yet_landed(tmp_path):
    """submit 的「先迁移、后审计」窗口：查不到提交人时不放行审批。

    同一人并发 submit + decide 时，可能出现状态已是 PENDING_REVIEW、SUBMIT
    审计行尚未落库的瞬间；此时无法核对提交人，按 fail-closed 拒绝（可刷新
    重试），而不是让同一人自批。
    """
    container, skills, reviews = _stack(tmp_path)
    view = create_tenant_skill(skills, owner_id=CREATOR_ID)
    repository = container.repositories['skills']
    # 模拟并发窗口：只迁移状态，不写 SUBMIT 审计行
    assert repository.transition_if(
        view.id, [SkillStatus.DRAFT], SkillStatus.PENDING_REVIEW)

    with pytest.raises(SkillStatusInvalid):
        _decide(reviews, view.id, SkillReviewDecision.APPROVE,
                actor=SUBMITTER_ID)
    assert _status(container, view.id) is SkillStatus.PENDING_REVIEW


# ---------------------------------------------------------------- P2 编辑绕过


def test_active_tenant_edit_uses_edit_edge_and_writes_audit(tmp_path):
    """ACTIVE 保存 → 显式 EDIT 回 DRAFT，落审计（修复前无审计行）。"""
    container, skills, reviews = _stack(tmp_path)
    view = _activate(container, skills, reviews)
    active_version = container.repositories['skills'].get(view.id).version

    updated = _edit(skills, view.id, actor=CREATOR_ID, body='已发布版本改动')
    assert updated.status is SkillStatus.DRAFT
    assert updated.version == str(int(active_version) + 1)
    assert _status(container, view.id) is SkillStatus.DRAFT

    chain = _history(reviews, view.id)
    edits = [row for row in chain if row.action is SkillReviewAction.EDIT]
    assert len(edits) == 1, chain
    assert edits[0].status_from is SkillStatus.ACTIVE
    assert edits[0].status_to is SkillStatus.DRAFT
    assert edits[0].version == active_version
    assert edits[0].reviewer_id == CREATOR_ID
    # 回到 DRAFT 后不参与自动触发，须重新提交 + 审批
    assert updated.status.participates_in_trigger is False


def test_active_tenant_edit_store_failure_keeps_status_and_audit(tmp_path):
    """资源存储失败：状态仍 ACTIVE、版本不变、无 EDIT 审计（返工阻塞项）。

    修复前 ``transition_if`` 排在 ``_store_resources`` 之前：一次存储抖动就
    把已发布版本静默打回 DRAFT，而内容 / 版本 / 审计都没落库。
    """
    container, store = build_skill_stack(
        tmp_path, golden=StaticGoldenTasks(GATE_GOLDEN))
    skills, reviews = container.skill_service, container.skill_review_service
    resource = {'references/guide.md': '# 指南\n'}
    view = create_tenant_skill(skills, draft_payload(resources=resource))
    _submit(reviews, view.id, actor=CREATOR_ID)
    _decide(reviews, view.id, SkillReviewDecision.APPROVE, actor=SUBMITTER_ID)
    repository = container.repositories['skills']
    before = repository.get(view.id)
    audit_before = _history(reviews, view.id)

    written = []
    real_put = store.put

    def fail_put(key, data, content_type='application/octet-stream'):
        written.append(key)
        raise RuntimeError('OSS 存储抖动')

    store.put = fail_put
    new_resource = {'references/guide.md': '# 指南 v2\n'}
    with pytest.raises(RuntimeError):
        skills.update(
            view.id, draft_payload(body=demo_body('编辑后的正文'),
                                   resources=new_resource),
            owner_id=CREATOR_ID, tenant_id=TENANT_ID,
            permissions=['*'], is_admin=True)
    assert written, '资源存储未被调用，用例没有命中失败路径'

    after = repository.get(view.id)
    assert after.status is SkillStatus.ACTIVE
    assert after.version == before.version
    assert after.content_hash == before.content_hash
    assert _history(reviews, view.id) == audit_before

    # 存储恢复后原样重试可以成功：没有孤儿版本号挡住 version + 1
    store.put = real_put
    updated = skills.update(
        view.id, draft_payload(body=demo_body('存储恢复后重试'),
                               resources=new_resource),
        owner_id=CREATOR_ID, tenant_id=TENANT_ID,
        permissions=['*'], is_admin=True)
    assert updated.status is SkillStatus.DRAFT
    assert updated.version == str(int(before.version) + 1)
    edits = [row for row in _history(reviews, view.id)
             if row.action is SkillReviewAction.EDIT]
    assert len(edits) == 1
    assert edits[0].status_from is SkillStatus.ACTIVE
    assert edits[0].status_to is SkillStatus.DRAFT


def test_apply_edit_rolls_back_state_when_audit_write_fails(tmp_path):
    """事务边界：条件迁移已执行、审计写失败 → 状态与版本整体回滚。

    这是 ``apply_edit`` 与旧「先迁移后写审计」的区别：迁移、版本行、当前行、
    审计四件事同生同灭，不会留下「已发布版本变成 DRAFT 但没有审计」的中间态。
    """
    container, skills, reviews = _stack(tmp_path)
    view = _activate(container, skills, reviews)
    repository = container.repositories['skills']
    before = repository.get(view.id)
    next_version = str(int(before.version) + 1)

    def bad_review():
        return AgentSkillReview(
            id='bad-review', skill_id=view.id, version=before.version,
            action='BOGUS',  # 让 PO 构造在条件迁移之后抛错
            status_from=SkillStatus.ACTIVE, status_to=SkillStatus.DRAFT,
            reviewer_id=CREATOR_ID, tenant_id=TENANT_ID,
            created_at=datetime.now(timezone.utc).replace(tzinfo=None))

    apply_edit = getattr(repository, 'apply_edit', None)
    assert callable(apply_edit), 'AgentSkillRepository 缺少事务写入口 apply_edit'
    with pytest.raises(AttributeError):
        apply_edit(
            view.id, from_status=SkillStatus.ACTIVE,
            row_fields={'status': SkillStatus.DRAFT.value,
                        'version': next_version},
            version=AgentSkillVersion(
                skill_id=view.id, version=next_version,
                content_hash='rolled-back', body=demo_body('回滚验证')),
            review=bad_review())

    after = repository.get(view.id)
    assert after.status is SkillStatus.ACTIVE
    assert after.version == before.version
    assert repository.get_version(view.id, next_version) is None
    assert [row for row in _history(reviews, view.id)
            if row.action is SkillReviewAction.EDIT] == []


def test_disabled_tenant_edit_is_rejected(tmp_path):
    """DISABLED 无出边：保存必须 409，状态与审计链不变（修复前会复活成 DRAFT）。"""
    container, skills, reviews = _stack(tmp_path)
    view = _activate(container, skills, reviews)
    skills.disable(view.id, owner_id=CREATOR_ID, tenant_id=TENANT_ID,
                   permissions=['*'], is_admin=True, reason='联调结束')
    assert _status(container, view.id) is SkillStatus.DISABLED
    before = len(_history(reviews, view.id))

    with pytest.raises(SkillStatusInvalid) as info:
        _edit(skills, view.id, actor=CREATOR_ID)
    assert info.value.code == 'SKILL_STATUS_INVALID'
    assert _status(container, view.id) is SkillStatus.DISABLED
    assert len(_history(reviews, view.id)) == before


def test_draft_tenant_edit_adds_no_review_row(tmp_path):
    """DRAFT 原地修改不走状态机：不产生 EDIT 审计噪音。"""
    container, skills, reviews = _stack(tmp_path)
    view = create_tenant_skill(skills, owner_id=CREATOR_ID)
    updated = _edit(skills, view.id, actor=CREATOR_ID)
    assert updated.status is SkillStatus.DRAFT
    assert [row for row in _history(reviews, view.id)
            if row.action is SkillReviewAction.EDIT] == []


def test_active_user_skill_edit_keeps_previous_behaviour(tmp_path):
    """USER 级不受影响：本人编辑 ACTIVE 仍直接回 DRAFT（INT-2549 无回归）。"""
    _container, skills, _reviews = _stack(tmp_path)
    view = skills.create(draft_payload(), owner_id=CREATOR_ID,
                         tenant_id=TENANT_ID, permissions=['*'])
    skills.publish(view.id, owner_id=CREATOR_ID, tenant_id=TENANT_ID,
                   permissions=['*'])
    updated = _edit(skills, view.id, actor=CREATOR_ID)
    assert updated.status is SkillStatus.DRAFT


# ---------------------------------------------------------------- P3 权限码


def test_permission_code_is_a_tenant_admin_credential():
    """只授 ``agent:skill:admin`` 的动作管理员也构成管理员级授予。"""
    assert is_tenant_admin(permissions=[SKILL_ADMIN_PERMISSION],
                           is_admin=True) is True
    # 双条件不放松：没有管理员级授予（网关算出的 X-User-Is-Admin=false）仍拒绝
    assert is_tenant_admin(permissions=[SKILL_ADMIN_PERMISSION],
                           is_admin=False) is False
    assert is_tenant_admin(permissions=['agent:skill:read'],
                           is_admin=False) is False


def test_gateway_admin_flag_follows_permission_code():
    """网关把仅持该码的自定义角色按管理员下发（修复前恒 false）。"""
    from api_gateway.middleware import RequestAdapterMiddleware
    from api_gateway.routes import agent_runtime_bp, agent_skill_bp

    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={'items': []})

    app = FastAPI()
    app.add_middleware(RequestAdapterMiddleware)

    @app.middleware('http')
    async def _inject(request, call_next):
        request.state.user_id = 7
        request.state.permissions = ['agent:skill:read', 'agent:skill:manage',
                                     SKILL_ADMIN_PERMISSION]
        return await call_next(request)

    app.include_router(agent_runtime_bp.router, prefix='/api/v1/agent')
    app.include_router(agent_skill_bp.router, prefix='/api/v1/agent')
    agent_runtime_bp._transport_override = httpx.MockTransport(handler)
    try:
        TestClient(app).get('/api/v1/agent/skills')
    finally:
        agent_runtime_bp._transport_override = None

    assert calls[0].headers['X-User-Is-Admin'] == 'true'
    assert calls[0].headers['X-User-Permissions'] == (
        'agent:skill:read,agent:skill:manage,' + SKILL_ADMIN_PERMISSION)


def test_seed_grants_admin_code_to_admin_role():
    path = os.path.join(PROJECT_ROOT, 'scripts', 'migrations', '202608',
                        'seed_rbac.py')
    text = open(path, encoding='utf-8').read()
    assert "('admin', ['*', 'agent:skill:admin'])" in text


def test_service_accepts_code_role_end_to_end(tmp_path):
    """网关下发的 ``X-User-Is-Admin: true`` + 该码 = 可建 TENANT Skill。"""
    container, _store = build_skill_stack(
        tmp_path, golden=StaticGoldenTasks(GATE_GOLDEN))
    client = TestClient(create_app(container=container))
    headers = {'X-User-Id': str(CREATOR_ID), 'X-Tenant-Id': TENANT_ID,
               'X-User-Permissions': f'agent:skill:manage,{SKILL_ADMIN_PERMISSION}',
               'X-User-Is-Admin': 'true'}
    with client:
        resp = client.post('/api/v1/agent/skills?scope=TENANT',
                           json={'name': 'demo-skill',
                                 'description': '演示 Skill。触发词：演示、样例',
                                 'body': demo_body('TENANT 正文标记')},
                           headers=headers)
    assert resp.status_code == 201, resp.text
    assert resp.json()['scope'] == 'TENANT'
