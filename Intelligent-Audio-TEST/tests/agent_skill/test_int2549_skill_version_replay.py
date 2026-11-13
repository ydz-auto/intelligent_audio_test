# -*- coding: utf-8 -*-
"""INT-2549 版本快照与回放 + 停用/删除立即生效（验收 5、9）。"""
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from agent_service.domain.enums import SkillStatus
from tests.agent_skill.helpers import (
    OWNER_ID, TENANT_ID, StaticGoldenTasks, build_skill_stack, create_draft,
    draft_payload,
)
from tests.unit.int2451_agent_fakes import FakeLlm, text_turn

MARKER_V1 = '第一版流程标记'
MARKER_V2 = '第二版流程标记'
GOLDEN = {'demo-skill': ['演示 一下', '样例 给我', '看样例']}


def _body(marker):
    return (f'# demo\n\n{marker}\n\n## Gotchas\n\n- 无。\n\n'
            '## 验收\n\n- 无。\n')


@pytest.fixture()
def stack(tmp_path):
    llm = FakeLlm([text_turn('ok') for _ in range(4)])
    container, _store = build_skill_stack(
        tmp_path, golden=StaticGoldenTasks(GOLDEN), llm=llm)
    return container, llm


def _activate(container, skill_id):
    return container.skill_service.publish(
        skill_id, owner_id=OWNER_ID, tenant_id=TENANT_ID,
        permissions=['*'])


def _start_run(container, skill_name='demo-skill'):
    session = container.run_service.create_session(
        owner_id=OWNER_ID, tenant_id=TENANT_ID, title='快照测试',
        permissions=['*'], active_skill=skill_name)
    run, created = container.run_service.create_run(
        session.id, owner_id=OWNER_ID, tenant_id=TENANT_ID,
        message='演示一下', permissions=['*'])
    assert created
    return run


def test_run_snapshot_does_not_change_after_skill_update(stack):
    stack, _llm = stack
    service = stack.skill_service
    view = create_draft(service, draft_payload(body=_body(MARKER_V1)))
    assert _activate(stack, view.id).skill.status is SkillStatus.ACTIVE
    run = _start_run(stack)
    snapshots = stack.repositories['run_skills'].list_by_run(run.id)
    assert len(snapshots) == 1
    snapshot = snapshots[0]
    assert snapshot.skill_id == view.id
    assert snapshot.version == '1'
    original_hash = snapshot.content_hash

    # 修改 Skill → version +1、回到 DRAFT；run 快照不变
    service.update(view.id, draft_payload(body=_body(MARKER_V2)),
                   owner_id=OWNER_ID, tenant_id=TENANT_ID, permissions=['*'])
    assert stack.repositories['run_skills'].list_by_run(run.id) == snapshots
    assert snapshot.content_hash == original_hash

    # 按版本表回放：仍是 v1 内容且 hash 一致
    items = service.replay(run.id, owner_id=OWNER_ID, tenant_id=TENANT_ID)
    assert len(items) == 1
    item = items[0]
    assert item['version'] == '1'
    assert MARKER_V1 in item['body']
    assert MARKER_V2 not in item['body']
    assert item['content_hash'] == original_hash
    assert item['content_hash_matches'] is True
    assert item['resolved'] is True


def test_disable_is_immediate_but_inflight_run_uses_snapshot(stack):
    stack, llm = stack
    service = stack.skill_service
    view = create_draft(service, draft_payload(body=_body(MARKER_V1)))
    _activate(stack, view.id)
    # 发起但先不执行（在办 run）
    run = _start_run(stack)
    names_before = [s.name for s in stack.skill_registry.visible_for(
        ['*'], owner_id=OWNER_ID, tenant_id=TENANT_ID)]
    assert 'demo-skill' in names_before

    service.disable(view.id, owner_id=OWNER_ID, tenant_id=TENANT_ID)
    names_after = [s.name for s in stack.skill_registry.visible_for(
        ['*'], owner_id=OWNER_ID, tenant_id=TENANT_ID)]
    assert 'demo-skill' not in names_after

    # 在办 run 继续按快照执行，不报错且 L2 仍是 v1 正文
    stack.executor.submit(run.id)
    finished = stack.repositories['runs'].get(run.id)
    assert finished.status.value == 'SUCCEEDED'
    system_messages = [
        message for request in llm.requests
        for message in request.messages
        if message.role == 'system']
    assert any(MARKER_V1 in message.content for message in system_messages)


def test_delete_keeps_snapshot_replayable(stack):
    stack, _llm = stack
    service = stack.skill_service
    view = create_draft(service, draft_payload(body=_body(MARKER_V1)))
    _activate(stack, view.id)
    run = _start_run(stack)
    service.delete(view.id, owner_id=OWNER_ID, tenant_id=TENANT_ID)
    assert stack.repositories['skills'].get(view.id) is None
    assert stack.repositories['skills'].list_versions(view.id), \
        '删除当前行时版本行必须保留（回放依赖）'
    items = service.replay(run.id, owner_id=OWNER_ID, tenant_id=TENANT_ID)
    assert MARKER_V1 in items[0]['body']
    assert items[0]['content_hash_matches'] is True
    # 删除后新 run 的激活候选不再出现
    assert 'demo-skill' not in [
        s.name for s in stack.skill_registry.visible_for(
            ['*'], owner_id=OWNER_ID, tenant_id=TENANT_ID)]
