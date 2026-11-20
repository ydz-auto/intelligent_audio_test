# -*- coding: utf-8 -*-
"""INT-2551 REST 契约：TENANT 创建 / 提交审核 / 审批 / 撤回 / 待审队列。

验收锚点（卡面「可测验收标准」1~5、9）：
- 请求体携带 ``scope`` / ``tenant_id`` → 400；作用域只经 ``?scope=`` 选择；
- 非管理员 → 403（权限码 + 角色双条件，``X-User-Is-Admin: false`` 生效）；
- 自审自批 → 403 ``SKILL_SELF_REVIEW_FORBIDDEN``；驳回缺 reason → 400；
- ``PENDING_REVIEW`` 期间 PUT → 409；
- 跨租户按 id 访问 → 404。
"""
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from fastapi.testclient import TestClient

from agent_service.app import create_app
from tests.agent_skill.helpers import (
    GATE_GOLDEN, StaticGoldenTasks, build_skill_stack, demo_body,
)
from tests.unit.int2451_agent_fakes import FakeLlm, text_turn

OWNER_ID = 7
OTHER_ADMIN_ID = 8
ADMIN = {'X-User-Id': str(OWNER_ID), 'X-Tenant-Id': 't1',
         'X-User-Permissions': '*', 'X-User-Is-Admin': 'true'}
OTHER_ADMIN = {'X-User-Id': str(OTHER_ADMIN_ID), 'X-Tenant-Id': 't1',
               'X-User-Permissions': '*', 'X-User-Is-Admin': 'true'}
# 有权限码但没有管理员角色（服务端复核必须拒绝）
PERM_ONLY = {'X-User-Id': str(OWNER_ID), 'X-Tenant-Id': 't1',
             'X-User-Permissions': 'agent:skill:admin,agent:skill:manage',
             'X-User-Is-Admin': 'false'}
OTHER_TENANT = {**ADMIN, 'X-Tenant-Id': 't2'}

BODY = demo_body('TENANT 正文标记')


def _client(tmp_path):
    llm = FakeLlm([text_turn('ok') for _ in range(3)])
    container, _store = build_skill_stack(
        tmp_path, llm=llm, golden=StaticGoldenTasks(GATE_GOLDEN))
    return TestClient(create_app(container=container)), container


def _create_tenant(client, headers=ADMIN, **overrides):
    payload = {'name': 'demo-skill',
               'description': '演示 Skill。触发词：演示、样例', 'body': BODY}
    payload.update(overrides)
    return client.post('/api/v1/agent/skills?scope=TENANT', json=payload,
                       headers=headers)


def test_create_tenant_scope_via_query(tmp_path):
    client, _container = _client(tmp_path)
    with client:
        created = _create_tenant(client)
        assert created.status_code == 201, created.text
        item = created.json()
        assert item['scope'] == 'TENANT'
        assert item['tenant_id'] == 't1'
        assert item['owner_id'] == OWNER_ID
        assert item['status'] == 'DRAFT'


def test_body_scope_still_rejected(tmp_path):
    client, _container = _client(tmp_path)
    with client:
        resp = _create_tenant(client, scope='TENANT')
        assert resp.status_code == 400
        assert resp.json()['detail']['code'] == 'SKILL_VALIDATION_FAILED'


def test_tenant_create_requires_admin_role_header(tmp_path):
    client, _container = _client(tmp_path)
    with client:
        resp = _create_tenant(client, headers=PERM_ONLY)
        assert resp.status_code == 403, resp.text
        assert resp.json()['code'] == 'SKILL_REVIEW_FORBIDDEN'


def test_full_review_flow_via_api(tmp_path):
    client, _container = _client(tmp_path)
    with client:
        skill_id = _create_tenant(client).json()['id']

        submitted = client.post(
            f'/api/v1/agent/skills/{skill_id}/submit-review', headers=ADMIN)
        assert submitted.status_code == 200, submitted.text
        assert submitted.json()['skill']['status'] == 'PENDING_REVIEW'
        assert submitted.json()['review']['action'] == 'SUBMIT'

        # 审核中保存被拒
        frozen = client.put(f'/api/v1/agent/skills/{skill_id}',
                            json={'body': demo_body('审核中改动')},
                            headers=ADMIN)
        assert frozen.status_code == 409
        assert frozen.json()['code'] == 'SKILL_STATUS_INVALID'

        # 待审队列（仅本租户）
        queue = client.get('/api/v1/agent/skills/reviews?status=PENDING_REVIEW',
                           headers=ADMIN)
        assert queue.status_code == 200, queue.text
        assert [row['skill_id'] for row in queue.json()['items']] == [skill_id]
        # 别的租户看不到
        other_queue = client.get(
            '/api/v1/agent/skills/reviews?status=PENDING_REVIEW',
            headers=OTHER_TENANT)
        assert other_queue.json()['items'] == []

        # 创建人自批 → 403
        self_review = client.post(
            f'/api/v1/agent/skills/{skill_id}/review',
            json={'decision': 'APPROVE'}, headers=ADMIN)
        assert self_review.status_code == 403
        assert self_review.json()['code'] == 'SKILL_SELF_REVIEW_FORBIDDEN'

        # 另一个管理员批准
        approved = client.post(
            f'/api/v1/agent/skills/{skill_id}/review',
            json={'decision': 'APPROVE'}, headers=OTHER_ADMIN)
        assert approved.status_code == 200, approved.text
        assert approved.json()['skill']['status'] == 'ACTIVE'

        history = client.get(
            f'/api/v1/agent/skills/{skill_id}/reviews', headers=ADMIN)
        assert [row['action'] for row in history.json()['items']] == [
            'SUBMIT', 'APPROVE']


def test_reject_requires_reason_via_api(tmp_path):
    client, _container = _client(tmp_path)
    with client:
        skill_id = _create_tenant(client).json()['id']
        client.post(f'/api/v1/agent/skills/{skill_id}/submit-review',
                    headers=ADMIN)
        missing = client.post(f'/api/v1/agent/skills/{skill_id}/review',
                              json={'decision': 'REJECT'}, headers=OTHER_ADMIN)
        assert missing.status_code == 400, missing.text
        ok = client.post(f'/api/v1/agent/skills/{skill_id}/review',
                         json={'decision': 'REJECT', 'reason': '触发词太泛'},
                         headers=OTHER_ADMIN)
        assert ok.status_code == 200, ok.text
        assert ok.json()['skill']['status'] == 'DRAFT'
        assert ok.json()['review']['reason'] == '触发词太泛'


def test_withdraw_via_api(tmp_path):
    client, _container = _client(tmp_path)
    with client:
        skill_id = _create_tenant(client).json()['id']
        client.post(f'/api/v1/agent/skills/{skill_id}/submit-review',
                    headers=ADMIN)
        withdrawn = client.post(f'/api/v1/agent/skills/{skill_id}/withdraw',
                                headers=ADMIN)
        assert withdrawn.status_code == 200, withdrawn.text
        assert withdrawn.json()['skill']['status'] == 'DRAFT'
        edited = client.put(f'/api/v1/agent/skills/{skill_id}',
                            json={'body': demo_body('撤回后改动')},
                            headers=ADMIN)
        assert edited.status_code == 200
        assert edited.json()['version'] == '2'


def test_non_admin_cannot_submit_or_decide(tmp_path):
    client, _container = _client(tmp_path)
    with client:
        skill_id = _create_tenant(client).json()['id']
        for path, payload in (
                ('submit-review', None),
                ('review', {'decision': 'APPROVE'}),
                ('withdraw', None)):
            resp = client.post(f'/api/v1/agent/skills/{skill_id}/{path}',
                               json=payload, headers=PERM_ONLY)
            assert resp.status_code == 403, (path, resp.text)


def test_platform_publish_still_works_for_user_skill(tmp_path):
    """INT-2549 的 USER 级路径无回归：不经审核流、本人发布。"""
    client, _container = _client(tmp_path)
    with client:
        created = client.post('/api/v1/agent/skills',
                              json={'name': 'demo-skill',
                                    'description': '演示 Skill。触发词：演示、样例',
                                    'body': BODY},
                              headers=ADMIN)
        assert created.status_code == 201
        assert created.json()['scope'] == 'USER'
        published = client.post(
            f"/api/v1/agent/skills/{created.json()['id']}/publish",
            headers=ADMIN)
        assert published.status_code == 200, published.text
        assert published.json()['skill']['status'] == 'ACTIVE'


def test_cross_tenant_id_access_is_404(tmp_path):
    client, _container = _client(tmp_path)
    with client:
        skill_id = _create_tenant(client).json()['id']
        # 别的租户按 id 直接访问 → 404（无存在性提示）
        versions = client.get(f'/api/v1/agent/skills/{skill_id}/versions',
                              headers=OTHER_TENANT)
        assert versions.status_code == 404
        assert versions.json()['code'] == 'SKILL_NOT_FOUND'
        exported = client.get(f'/api/v1/agent/skills/{skill_id}/export',
                              headers=OTHER_TENANT)
        assert exported.status_code == 404
        history = client.get(f'/api/v1/agent/skills/{skill_id}/reviews',
                             headers=OTHER_TENANT)
        assert history.status_code == 404


def test_tenant_delete_via_api_is_409(tmp_path):
    client, _container = _client(tmp_path)
    with client:
        skill_id = _create_tenant(client).json()['id']
        resp = client.delete(f'/api/v1/agent/skills/{skill_id}', headers=ADMIN)
        assert resp.status_code == 409
        assert resp.json()['code'] == 'SKILL_STATUS_INVALID'


def test_tenant_publish_via_api_is_rejected(tmp_path):
    client, _container = _client(tmp_path)
    with client:
        skill_id = _create_tenant(client).json()['id']
        resp = client.post(f'/api/v1/agent/skills/{skill_id}/publish',
                           headers=ADMIN)
        assert resp.status_code == 409
        assert resp.json()['code'] == 'SKILL_STATUS_INVALID'
