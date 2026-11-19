# -*- coding: utf-8 -*-
"""INT-2601 会话消息删除（隐藏集合）：展示与模型上下文都过滤。

回归背景：前端删除用户输入只删本地列表，服务端 GET session 仍会回填；
现在删除落到 ``agent_hidden_message``，两条读取路径（会话展示 / 上下文组装）
都按同一份集合过滤，事件表保持完整（唯一事实源不被改写）。
"""
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from agent_service.domain.enums import EventType
from agent_service.domain.exceptions import SessionNotFound
from tests.unit.int2451_agent_fakes import FakeLlm, build_stack, new_session

OWNER = 7
TENANT = 't1'


def _stack(tmp_path):
    return build_stack(tmp_path / 'hide.db', FakeLlm([]))


def _seed_run_with_reply(container, session):
    run, created = container.run_service.create_run(
        session.id, owner_id=OWNER, tenant_id=TENANT, message='要删除的输入')
    assert created
    container.repositories['events'].append(
        run.id, EventType.MESSAGE_DELTA,
        {'message_id': 'msg-reply', 'delta': '保留的回答', 'index': 0,
         'turn': 0})
    latest = container.repositories['runs'].list_session_runs(session.id, 20)[-1]
    return run, latest


def test_hide_message_filters_session_and_model_context(tmp_path):
    container, _engine, _sf = _stack(tmp_path)
    session = new_session(container)
    run, latest = _seed_run_with_reply(container, session)

    messages = container.assembler.recent_messages(session.id, latest, 50)
    ids = [item['id'] for item in messages]
    assert f'user:{run.id}' in ids and 'msg-reply' in ids

    container.run_service.hide_message(
        session.id, f'user:{run.id}', owner_id=OWNER, tenant_id=TENANT)

    # 会话展示：被删的 user 消息不再返回，回答仍在
    filtered = container.assembler.recent_messages(session.id, latest, 50)
    filtered_ids = [item['id'] for item in filtered]
    assert f'user:{run.id}' not in filtered_ids
    assert 'msg-reply' in filtered_ids

    # 模型上下文：同一个删除集合生效
    assembled = container.assembler.assemble(session.id, latest)
    assert not any(message.content == '要删除的输入' for message in assembled)
    assert any(message.content == '保留的回答' for message in assembled)

    # 幂等：重复删除只落一行
    container.run_service.hide_message(
        session.id, f'user:{run.id}', owner_id=OWNER, tenant_id=TENANT)
    hidden = container.repositories['hidden_messages'].list_ids(session.id)
    assert hidden == {f'user:{run.id}'}
    container.shutdown()


def test_hide_message_rejects_foreign_session(tmp_path):
    container, _engine, _sf = _stack(tmp_path)
    session = new_session(container)
    _run, _latest = _seed_run_with_reply(container, session)

    with pytest.raises(SessionNotFound):
        container.run_service.hide_message(
            session.id, 'msg-reply', owner_id=OWNER + 1, tenant_id=TENANT)
    assert container.repositories['hidden_messages'].list_ids(session.id) == set()
    container.shutdown()
