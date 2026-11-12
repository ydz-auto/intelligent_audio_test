# -*- coding: utf-8 -*-
"""INT-2451 持久化约束：状态机条件更新 / (run_id,sequence) 唯一 /
幂等键唯一 / tool call 不重复。

验收锚点（卡面第 6 条）：
- (run_id, sequence) 唯一约束生效；
- Idempotency-Key 重复提交只产生一个 run。
"""
import os
import threading
import uuid

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest
from sqlalchemy.exc import IntegrityError

from agent_service.domain.enums import RunStatus
from agent_service.domain.model.entities import AgentRun, AgentToolCall
from agent_service.domain.enums import ToolCallStatus, ToolRisk
from tests.unit.int2451_agent_fakes import make_engine
from shared.utils.time_utils import utcnow


@pytest.fixture()
def stack(tmp_path):
    engine, sf = make_engine(tmp_path / 'store.db')
    yield sf
    engine.dispose()


def _new_run(session_id='s1', owner_id=7, key=None):
    now = utcnow()
    return AgentRun(
        id=str(uuid.uuid4()), session_id=session_id, owner_id=owner_id,
        tenant_id='t1', status=RunStatus.QUEUED, model='m',
        idempotency_key=key, created_at=now, updated_at=now)


def test_event_sequence_is_unique_per_run(stack):
    from agent_service.infrastructure.persistence.repositories import (
        SqlEventRepository,
    )
    from agent_service.domain.enums import EventType
    events = SqlEventRepository(stack)
    run_id = 'r1'
    # 直接写两条相同 sequence 应被唯一约束拒绝
    db = stack()
    try:
        from agent_service.infrastructure.persistence.models import agent_models as m
        db.add(m.AgentRunEvent(id=str(uuid.uuid4()), run_id=run_id,
                               sequence=1, type='run_started', payload={},
                               created_at=utcnow()))
        db.add(m.AgentRunEvent(id=str(uuid.uuid4()), run_id=run_id,
                               sequence=1, type='message_delta', payload={},
                               created_at=utcnow()))
        with pytest.raises(IntegrityError):
            db.commit()
    finally:
        db.rollback()
        db.close()

    e1 = events.append(run_id, EventType.RUN_STARTED, {'a': 1})
    e2 = events.append(run_id, EventType.MESSAGE_DELTA, {'b': 2})
    assert (e1.sequence, e2.sequence) == (1, 2)
    assert [e.sequence for e in events.list_after(run_id, 0, 10)] == [1, 2]


def test_concurrent_appends_produce_no_gaps(stack):
    from agent_service.infrastructure.persistence.repositories import (
        SqlEventRepository,
    )
    from agent_service.domain.enums import EventType
    events = SqlEventRepository(stack)
    run_id = 'r-concurrent'

    def worker():
        for _ in range(10):
            events.append(run_id, EventType.MESSAGE_DELTA, {'x': 1})

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    sequences = [e.sequence for e in events.list_after(run_id, 0, 100)]
    assert sequences == list(range(1, 41))


def test_idempotency_key_unique(stack):
    from agent_service.domain.repositories import RunRepository
    from agent_service.infrastructure.persistence.repositories import (
        SqlRunRepository,
    )
    runs = SqlRunRepository(stack)
    first, created = runs.add_if_absent(_new_run(key='t1:7:abc'))
    assert created
    second, created_again = runs.add_if_absent(_new_run(key='t1:7:abc'))
    assert not created_again
    assert second.id == first.id
    assert runs.get_by_idempotency_key('t1:7:abc').id == first.id


def test_transition_if_protects_terminal_state(stack):
    from agent_service.infrastructure.persistence.repositories import (
        SqlRunRepository,
    )
    runs = SqlRunRepository(stack)
    run = runs.add(_new_run(session_id='s-terminal'))
    assert runs.transition_if(run.id, {RunStatus.QUEUED}, RunStatus.RUNNING)
    assert runs.transition_if(run.id, {RunStatus.RUNNING}, RunStatus.SUCCEEDED)
    # 终态不可覆盖
    assert not runs.transition_if(
        run.id, {RunStatus.QUEUED, RunStatus.RUNNING}, RunStatus.CANCELLED)
    assert runs.get(run.id).status is RunStatus.SUCCEEDED


def test_tool_call_identities_are_unique(stack):
    from agent_service.infrastructure.persistence.repositories import (
        SqlToolCallRepository,
    )
    calls = SqlToolCallRepository(stack)
    now = utcnow()
    record = AgentToolCall(
        id=str(uuid.uuid4()), run_id='r1', tool_call_id='call_1',
        tool='task_query', args_hash='h1', risk=ToolRisk.READ,
        status=ToolCallStatus.PENDING, idempotency_key='k1',
        created_at=now, updated_at=now)
    calls.create(record)
    duplicate = AgentToolCall(
        id=str(uuid.uuid4()), run_id='r1', tool_call_id='call_1',
        tool='task_query', args_hash='h1', risk=ToolRisk.READ,
        status=ToolCallStatus.PENDING, idempotency_key='k2',
        created_at=now, updated_at=now)
    with pytest.raises(IntegrityError):
        calls.create(duplicate)
