# -*- coding: utf-8 -*-
"""INT-2549 对话沉淀建议（验收 12）。

锚点：run 正常结束后只在事件里给出「沉淀为 Skill」草案建议；
未确认不落库，用户确认（POST /skills）后才创建 DRAFT，且不自动发布。
"""
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from agent_service.domain.enums import EventType, SkillStatus
from agent_service.domain.model.entities import ToolCallRequest
from tests.agent_skill.helpers import (
    OWNER_ID, TENANT_ID, build_skill_stack, create_draft, draft_payload,
)
from tests.unit.int2451_agent_fakes import FakeLlm, events_of, text_turn, tool_turn


def _run_with_two_tools(container):
    session = container.run_service.create_session(
        owner_id=OWNER_ID, tenant_id=TENANT_ID, title='沉淀建议',
        permissions=['*'])
    run, created = container.run_service.create_run(
        session.id, owner_id=OWNER_ID, tenant_id=TENANT_ID,
        message='帮我查任务并检索工具', permissions=['*'])
    assert created
    container.executor.submit(run.id)
    return container.repositories['runs'].get(run.id)


def test_suggestion_is_event_only_until_confirmed(tmp_path):
    calls = [
        ToolCallRequest(tool_call_id='c1', name='task_query', arguments={}),
        ToolCallRequest(tool_call_id='c2', name='tool_search',
                        arguments={'query': '任务'}),
    ]
    llm = FakeLlm([tool_turn(calls), text_turn('完成')])
    container, _store = build_skill_stack(tmp_path, llm=llm)
    run = _run_with_two_tools(container)
    assert run.status.value == 'SUCCEEDED'

    suggestions = [event for event in events_of(container, run.id)
                   if event.type is EventType.SKILL_DRAFT_SUGGESTED]
    assert len(suggestions) == 1
    payload = suggestions[0].payload
    assert payload['created'] is False
    assert payload['requires_confirmation'] is True
    assert sorted(payload['tools_used']) == ['task_query', 'tool_search']
    assert payload['suggested_name'].startswith('task-query')
    # 未确认：不落库
    assert container.repositories['skills'].list_active() == []
    assert container.repositories['skills'].list_visible(
        tenant_id=TENANT_ID, owner_id=OWNER_ID) == []

    # 用户确认后走 POST /skills 创建 DRAFT（本测试直接调服务等价入口）
    view = create_draft(container.skill_service, draft_payload(
        name=payload['suggested_name'], description='沉淀的流程 Skill'))
    assert view.status is SkillStatus.DRAFT
    assert len(container.repositories['skills'].list_visible(
        tenant_id=TENANT_ID, owner_id=OWNER_ID)) == 1


def test_single_tool_run_has_no_suggestion(tmp_path):
    calls = [ToolCallRequest(tool_call_id='c1', name='task_query',
                            arguments={})]
    llm = FakeLlm([tool_turn(calls), text_turn('完成')])
    container, _store = build_skill_stack(tmp_path, llm=llm)
    run = _run_with_two_tools(container)
    suggestions = [event for event in events_of(container, run.id)
                   if event.type is EventType.SKILL_DRAFT_SUGGESTED]
    assert suggestions == []
