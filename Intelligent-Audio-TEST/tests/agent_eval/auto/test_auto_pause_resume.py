# -*- coding: utf-8 -*-
"""INT-2474：预算暂停 → 继续 的完整交互（服务层 + REST）。

- 预算到 80% 暂停：run WAITING_APPROVAL + ``run_paused``（用户可继续）；
- ``POST /runs/{id}/resume`` 继续；同一暂停点不再触发，硬预算仍生效；
- 待审批提案存在时不允许「继续」（先决策审批单）；
- 非 Auto / 非暂停态 / 非本人继续都被拒绝（409 / 404）。
"""
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from agent_service.domain.enums import RunStatus
from agent_service.domain.model.entities import ToolCallRequest
from tests.agent_eval.auto.support import (
    FakeLlm, FakeToolGateway, auto_budget, events_by_type, finished_payload,
    make_auto_stack, read_tool, start_run, status_of, text_turn, tool_turn,
    write_tool,
)

MARKER = '[[AUTO_DONE]]'
OWNER = {'X-User-Id': '7', 'X-Tenant-Id': 't1',
         'X-User-Permissions': '*'}
OTHER = {'X-User-Id': '8', 'X-Tenant-Id': 't1',
         'X-User-Permissions': '*'}


def _client(container):
    from fastapi.testclient import TestClient
    from agent_service.app import create_app
    return TestClient(create_app(container=container))


def _tool_turns(count, name='task_query'):
    return [tool_turn([ToolCallRequest(tool_call_id=f'c{index}', name=name,
                                       arguments={'i': index})])
            for index in range(count)]


def _paused_stack(tmp_path, *, rounds=5, turns=10):
    llm = FakeLlm(_tool_turns(turns))
    gateway = FakeToolGateway(tools=[read_tool('task_query')])
    container, _engine, _sf = make_auto_stack(
        tmp_path, llm, gateway=gateway,
        auto_budget_defaults=auto_budget(max_rounds=rounds,
                                         max_tool_calls=turns * 2))
    return container, llm, gateway


def test_budget_pause_can_resume_and_hard_budget_still_applies(tmp_path):
    container, llm, _gateway = _paused_stack(tmp_path, rounds=5, turns=10)
    with _client(container) as client:
        session = client.post('/api/v1/agent/sessions', json={},
                              headers=OWNER).json()
        run = client.post(
            f"/api/v1/agent/sessions/{session['id']}/runs",
            json={'message': '汇总报告', 'mode': 'auto'},
            headers=OWNER).json()['run']
        run_id = run['id']

        # 4/5 = 80% → 暂停
        assert container.repositories['runs'].get(run_id).status is \
            RunStatus.WAITING_APPROVAL
        paused = events_by_type(container, run_id, 'run_paused')
        assert paused[-1].payload['reason'] == 'budget_threshold'
        assert paused[-1].payload['ratio'] >= 0.8

        resumed = client.post(f'/api/v1/agent/runs/{run_id}/resume',
                              headers=OWNER)
        assert resumed.status_code == 200, resumed.text
        assert resumed.json()['status'] == RunStatus.BUDGET_EXCEEDED.value
        assert resumed.json()['mode'] == 'auto'
        # 继续后同一暂停点不再暂停：只暂停过一次
        assert len(events_by_type(container, run_id, 'run_paused')) == 1
        assert len(events_by_type(container, run_id, 'run_resumed')) == 1
        # 到达 5/5 硬预算 → BUDGET_EXCEEDED（继续不是放宽上限）
        assert finished_payload(container, run_id)['reason'] == 'max_rounds'
        # 再点继续：run 已终态 → 409
        again = client.post(f'/api/v1/agent/runs/{run_id}/resume',
                            headers=OWNER)
        assert again.status_code == 409
        assert again.json()['code'] == 'RUN_NOT_PAUSED'
    container.shutdown()


def test_resume_rejected_when_approval_pending(tmp_path):
    call = ToolCallRequest(tool_call_id='w1', name='task_create',
                           arguments={'body': {'name': '汇总'}})
    llm = FakeLlm([tool_turn([call]), text_turn(f'完成 {MARKER}')])
    gateway = FakeToolGateway(tools=[write_tool('task_create')])
    container, _engine, _sf = make_auto_stack(
        tmp_path, llm, gateway=gateway, auto_budget_defaults=auto_budget())
    with _client(container) as client:
        session = client.post('/api/v1/agent/sessions', json={},
                              headers=OWNER).json()
        run = client.post(
            f"/api/v1/agent/sessions/{session['id']}/runs",
            json={'message': '写操作', 'mode': 'auto'},
            headers=OWNER).json()['run']
        run_id = run['id']
        assert container.repositories['runs'].get(run_id).status is \
            RunStatus.WAITING_APPROVAL

        # 有待审批提案：先决策，不能「继续」
        blocked = client.post(f'/api/v1/agent/runs/{run_id}/resume',
                              headers=OWNER)
        assert blocked.status_code == 409
        assert '审批' in blocked.json()['detail']
        assert gateway.executed == []
        # 非本人继续同样不可（404，不泄漏存在性）
        other = client.post(f'/api/v1/agent/runs/{run_id}/resume',
                            headers=OTHER)
        assert other.status_code == 404
    container.shutdown()


def test_resume_rejected_for_chat_mode(tmp_path):
    call = ToolCallRequest(tool_call_id='w1', name='task_create',
                           arguments={'body': {'name': '对话写'}})
    llm = FakeLlm([tool_turn([call]), text_turn('完成')])
    gateway = FakeToolGateway(tools=[write_tool('task_create')])
    container, _engine, _sf = make_auto_stack(
        tmp_path, llm, gateway=gateway)
    with _client(container) as client:
        session = client.post('/api/v1/agent/sessions', json={},
                              headers=OWNER).json()
        run = client.post(
            f"/api/v1/agent/sessions/{session['id']}/runs",
            json={'message': '写操作'}, headers=OWNER).json()['run']
        assert run['mode'] == 'chat'
        rejected = client.post(f"/api/v1/agent/runs/{run['id']}/resume",
                               headers=OWNER)
        assert rejected.status_code == 409
        assert 'Auto' in rejected.json()['detail']
    container.shutdown()


def test_paused_run_is_not_auto_resumed_by_recovery(tmp_path):
    """重启恢复不得静默续跑暂停态（必须由用户点继续）。"""
    container, llm, gateway = _paused_stack(tmp_path, rounds=5, turns=10)
    run = start_run(container)
    assert status_of(container, run.id) is RunStatus.WAITING_APPROVAL
    before = len(llm.requests)

    resumable = container.recovery.recover()
    assert run.id in resumable
    for run_id in resumable:
        container.executor.submit(run_id)

    # 恢复投递后仍停在暂停态，没有再发起模型调用
    assert status_of(container, run.id) is RunStatus.WAITING_APPROVAL
    assert len(llm.requests) == before
    assert len(events_by_type(container, run.id, 'run_resumed')) == 0
    container.shutdown()
