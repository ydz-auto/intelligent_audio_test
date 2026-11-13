# -*- coding: utf-8 -*-
"""INT-2549 REST 契约（接口 10）：CRUD / 发布 / 停用 / 删除 / fork / 导入导出。

锚点：
- 请求体携带 ``scope`` / ``owner_id`` / ``tenant_id`` → 400；
- 非本人一律 404（不泄漏存在性）；
- 错误码枚举化（SKILL_NAME_CONFLICT / SKILL_VALIDATION_FAILED ...）。
"""
import io
import os
import zipfile

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from fastapi.testclient import TestClient

from agent_service.app import create_app
from agent_service.domain.enums import SkillStatus
from tests.agent_skill.helpers import (
    OWNER_ID, build_skill_stack, demo_body,
)
from tests.unit.int2451_agent_fakes import FakeLlm, text_turn

OWNER = {'X-User-Id': str(OWNER_ID), 'X-Tenant-Id': 't1',
         'X-User-Permissions': '*'}
OTHER = {'X-User-Id': '8', 'X-Tenant-Id': 't1',
         'X-User-Permissions': '*'}

BODY = demo_body('API 正文标记')


def _client(tmp_path):
    llm = FakeLlm([text_turn('ok') for _ in range(3)])
    container, store = build_skill_stack(tmp_path, llm=llm)
    app = create_app(container=container)
    return TestClient(app), container, llm


def _create(client, **overrides):
    payload = {'name': 'api-skill', 'description': 'API 演示。触发词：演示',
               'body': BODY}
    payload.update(overrides)
    return client.post('/api/v1/agent/skills', json=payload, headers=OWNER)


def test_create_rejects_identity_fields(tmp_path):
    client, _container, _llm = _client(tmp_path)
    with client:
        for field, value in (('scope', 'USER'), ('owner_id', 7),
                             ('tenant_id', 't1')):
            resp = _create(client, **{field: value})
            assert resp.status_code == 400, resp.text
            assert resp.json()['detail']['code'] == 'SKILL_VALIDATION_FAILED'


def test_create_list_update_disable_delete(tmp_path):
    client, _container, _llm = _client(tmp_path)
    with client:
        created = _create(client)
        assert created.status_code == 201, created.text
        item = created.json()
        assert item['scope'] == 'USER'
        assert item['status'] == 'DRAFT'
        assert item['version'] == '1'
        skill_id = item['id']

        listing = client.get('/api/v1/agent/skills?scope=USER&status=DRAFT',
                             headers=OWNER)
        assert listing.status_code == 200
        assert any(row['id'] == skill_id for row in listing.json()['items'])

        updated = client.put(
            f'/api/v1/agent/skills/{skill_id}',
            json={'body': demo_body('第二版')}, headers=OWNER)
        assert updated.status_code == 200, updated.text
        assert updated.json()['version'] == '2'
        assert updated.json()['status'] == 'DRAFT'

        versions = client.get(f'/api/v1/agent/skills/{skill_id}/versions',
                              headers=OWNER)
        assert [row['version'] for row in versions.json()['items']] == ['1', '2']

        published = client.post(f'/api/v1/agent/skills/{skill_id}/publish',
                                headers=OWNER)
        assert published.status_code == 200, published.text
        body = published.json()
        assert body['gate']['passed'] is False
        assert body['skill']['status'] == 'DRAFT'
        assert body['participates_in_trigger'] is False

        disabled = client.post(f'/api/v1/agent/skills/{skill_id}/disable',
                               headers=OWNER)
        assert disabled.json()['status'] == 'DISABLED'

        deleted = client.delete(f'/api/v1/agent/skills/{skill_id}',
                                headers=OWNER)
        assert deleted.status_code == 204
        listing = client.get('/api/v1/agent/skills', headers=OWNER)
        assert all(row['id'] != skill_id for row in listing.json()['items'])


def test_platform_name_conflict_maps_to_409(tmp_path):
    client, _container, _llm = _client(tmp_path)
    with client:
        resp = _create(client, name='platform-reference')
        assert resp.status_code == 409
        assert resp.json()['code'] == 'SKILL_NAME_CONFLICT'


def test_validation_error_lists_issues(tmp_path):
    client, _container, _llm = _client(tmp_path)
    with client:
        resp = _create(client, body='# no sections\n')
        assert resp.status_code == 400
        payload = resp.json()
        assert payload['code'] == 'SKILL_VALIDATION_FAILED'
        codes = {issue['code'] for issue in payload['issues']}
        assert 'MISSING_REQUIRED_SECTION' in codes


def test_other_user_gets_404(tmp_path):
    client, _container, _llm = _client(tmp_path)
    with client:
        skill_id = _create(client).json()['id']
        resp = client.put(f'/api/v1/agent/skills/{skill_id}',
                          json={'body': BODY}, headers=OTHER)
        assert resp.status_code == 404
        assert resp.json()['code'] == 'SKILL_NOT_FOUND'
        listing = client.get('/api/v1/agent/skills', headers=OTHER)
        assert all(row['id'] != skill_id for row in listing.json()['items'])


def test_fork_platform_skill(tmp_path):
    client, _container, _llm = _client(tmp_path)
    with client:
        resp = client.post(
            '/api/v1/agent/skills/platform:platform-reference/fork',
            json={'name': 'platform-copy'}, headers=OWNER)
        assert resp.status_code == 201, resp.text
        item = resp.json()
        assert item['name'] == 'platform-copy'
        assert item['scope'] == 'USER'
        assert item['status'] == 'DRAFT'
        # fork 带上平台 Skill 的 references（正文引用的资料不在草稿里断裂）
        version = _container.repositories['skills'].get_version(
            item['id'], '1')
        assert version.resources.get('references/endpoints.md')


def test_import_export_roundtrip_via_api(tmp_path):
    client, _container, _llm = _client(tmp_path)
    with client:
        skill_id = _create(client).json()['id']
        exported = client.get(f'/api/v1/agent/skills/{skill_id}/export',
                              headers=OWNER)
        assert exported.status_code == 200
        assert exported.headers['content-type'] == 'application/zip'
        with zipfile.ZipFile(io.BytesIO(exported.content)) as archive:
            assert archive.namelist() == ['SKILL.md']

        client.delete(f'/api/v1/agent/skills/{skill_id}', headers=OWNER)
        imported = client.post(
            '/api/v1/agent/skills/import',
            files={'file': ('api-skill.zip', exported.content,
                            'application/zip')},
            headers=OWNER)
        assert imported.status_code == 201, imported.text
        assert imported.json()['name'] == 'api-skill'


def test_run_skill_snapshot_endpoint(tmp_path):
    client, container, _llm = _client(tmp_path)
    with client:
        container.repositories['skills']  # 仓储已装配
        skill_id = _create(client).json()['id']
        # 直接置 ACTIVE（发布门槛单测已覆盖），用于 run 激活
        container.skill_service._repository.update(
            skill_id, status=SkillStatus.ACTIVE.value)
        container.skill_service._refresh_registry()
        session = client.post('/api/v1/agent/sessions',
                              json={'title': 't', 'active_skill': 'api-skill'},
                              headers=OWNER)
        assert session.status_code == 201, session.text
        run = client.post(
            f"/api/v1/agent/sessions/{session.json()['id']}/runs",
            json={'message': '演示'}, headers=OWNER)
        assert run.status_code == 201, run.text
        run_id = run.json()['run']['id']
        snapshots = client.get(f'/api/v1/agent/runs/{run_id}/skills',
                               headers=OWNER)
        assert snapshots.status_code == 200, snapshots.text
        items = snapshots.json()['items']
        assert len(items) == 1
        assert items[0]['skill_id'] == skill_id
        assert items[0]['resolved'] is True
        assert items[0]['content_hash_matches'] is True
        assert 'API 正文标记' in items[0]['body']
        # 非本人 404
        assert client.get(f'/api/v1/agent/runs/{run_id}/skills',
                          headers=OTHER).status_code == 404
