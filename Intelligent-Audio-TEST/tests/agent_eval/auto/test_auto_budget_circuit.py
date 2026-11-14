# -*- coding: utf-8 -*-
"""INT-2474 验收 2 / 3：超预算保留产物、连续失败熔断不无限重试。

- 硬预算（轮次 / 输出字节）到点 → ``BUDGET_EXCEEDED``，已完成事件与产物可查；
- 连续工具失败 2 次暂停（``WAITING_APPROVAL`` + ``run_paused``），用户继续后
  第三次失败 → 熔断 ``FAILED``（不再自动重试）；
- Auto 的暂停 / 熔断不影响 chat 模式（chat 仍在连续失败阈值处直接 FAILED）。
"""
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from agent_service.application.auto_mode import AutoSettings
from agent_service.domain.enums import RunStatus, ToolCallStatus
from agent_service.domain.model.entities import (
    AgentArtifact, ToolCallRequest, ToolResult,
)
from shared.utils.time_utils import utcnow
from tests.agent_eval.auto.support import (
    FakeLlm, FakeToolGateway, auto_budget, events_by_type, finished_payload,
    make_auto_stack, read_tool, resume, start_run, status_of, steps_of,
    text_turn, tool_turn,
)

MARKER = '[[AUTO_DONE]]'


class FailingGateway(FakeToolGateway):
    """只让 ``broken_query`` 失败，其余工具正常（模拟局部上游故障）。"""

    def execute(self, call: ToolCallRequest, context) -> ToolResult:
        with self._lock:
            self.executed.append((call.tool_call_id, call.name, call.arguments))
        if call.name == 'broken_query':
            return ToolResult(tool_call_id=call.tool_call_id, tool=call.name,
                              ok=False, content='上游连接失败',
                              error_code='TOOL_FAILED')
        return ToolResult(tool_call_id=call.tool_call_id, tool=call.name,
                          ok=True, content=f'ok:{call.name}')


def _turns(names, count):
    return [tool_turn([ToolCallRequest(
        tool_call_id=f'c{index}', name=names[index % len(names)],
        arguments={'i': index})]) for index in range(count)]


# ---------------------------------------------------------------- 硬预算

def test_rounds_budget_exceeded_keeps_events_and_artifacts(tmp_path):
    llm = FakeLlm(_turns(['task_query'], 5))
    gateway = FakeToolGateway(tools=[read_tool('task_query')])
    container, _engine, _sf = make_auto_stack(
        tmp_path, llm, gateway=gateway,
        auto_budget_defaults=auto_budget(),
        # 关掉 80% 暂停，单独验证硬预算收口
        auto_settings=AutoSettings(pause_budget_ratio=0,
                                   max_consecutive_failures=3))
    session = container.run_service.create_session(
        owner_id=7, tenant_id='t1', title='预算')
    run, _created = container.run_service.create_run(
        session.id, owner_id=7, tenant_id='t1', message='预算边界',
        permissions=['*'], mode='auto',
        budget_overrides={'max_rounds': 3})
    # 进度事件要能看到已产生的产物：先登记一条
    container.repositories['artifacts'].add(AgentArtifact(
        id='art-auto-1', run_id=run.id, kind='auto_report',
        uri='oss://bucket/auto/report.md', size=128, created_at=utcnow()))
    container.executor.submit(run.id)

    assert status_of(container, run.id) is RunStatus.BUDGET_EXCEEDED
    assert finished_payload(container, run.id)['reason'] == 'max_rounds'

    # 已完成的工作保留：3 轮 step + 3 条 tool_result 事件 + 产物可查
    steps = steps_of(container, run.id)
    assert len(steps) == 3
    assert all(step.status.value == 'COMPLETED' for step in steps)
    assert len(events_by_type(container, run.id, 'tool_result')) == 3
    artifacts = container.repositories['artifacts'].list_by_run(run.id)
    assert [item.uri for item in artifacts] == ['oss://bucket/auto/report.md']

    # 每条进度事件都带产物摘要
    progress = events_by_type(container, run.id, 'auto_step')
    assert len(progress) == 3
    assert progress[0].payload['artifact_count'] == 1
    assert progress[0].payload['artifacts'][0]['uri'] == \
        'oss://bucket/auto/report.md'
    # 工具调用记录可查（已执行 3 次，没有第 4 次）
    records = container.repositories['tool_calls'].list_by_run(run.id)
    assert len(records) == 3
    assert all(record.status is ToolCallStatus.COMPLETED for record in records)
    container.shutdown()


def test_output_bytes_budget_exceeded(tmp_path):
    llm = FakeLlm([text_turn('这是一段明显超过预算上限的长文本内容')])
    container, _engine, _sf = make_auto_stack(
        tmp_path, llm, auto_budget_defaults=auto_budget(),
        auto_settings=AutoSettings(pause_budget_ratio=0))
    session = container.run_service.create_session(
        owner_id=7, tenant_id='t1', title='输出预算')
    run, _created = container.run_service.create_run(
        session.id, owner_id=7, tenant_id='t1', message='输出预算',
        permissions=['*'], mode='auto',
        budget_overrides={'max_output_bytes': 8})
    container.executor.submit(run.id)

    assert status_of(container, run.id) is RunStatus.BUDGET_EXCEEDED
    assert finished_payload(container, run.id)['reason'] == 'max_output_bytes'
    # 跨重启累计口径：已产生的输出字节不再从 0 起算
    assert container.orchestrator._output_bytes_so_far(run.id) > 8  # noqa: SLF001
    container.shutdown()


# ---------------------------------------------------------------- 熔断

def test_consecutive_failures_pause_then_circuit_break(tmp_path):
    llm = FakeLlm(_turns(['broken_query'], 6))
    gateway = FailingGateway(tools=[read_tool('broken_query')])
    container, _engine, _sf = make_auto_stack(
        tmp_path, llm, gateway=gateway, auto_budget_defaults=auto_budget())
    run = start_run(container)

    # 连续 2 次失败 → 暂停（§9.4），不继续自动重试
    assert status_of(container, run.id) is RunStatus.WAITING_APPROVAL
    paused = events_by_type(container, run.id, 'run_paused')
    assert paused and paused[-1].payload['reason'] == \
        'consecutive_tool_failures'
    assert paused[-1].payload['consecutive_failures'] == 2
    assert len(gateway.executed) == 2
    assert len(llm.requests) == 2

    # 用户继续 → 下一次失败直接熔断（3 ≥ 阈值），不再循环
    resume(container, run.id)
    assert status_of(container, run.id) is RunStatus.FAILED
    assert (container.repositories['runs'].get(run.id).error or '') == \
        'CONSECUTIVE_TOOL_FAILURES'
    assert len(gateway.executed) == 3
    assert len(llm.requests) == 3
    errors = events_by_type(container, run.id, 'error')
    assert errors and errors[-1].payload['code'] == 'CONSECUTIVE_TOOL_FAILURES'
    # 同一段失败连击不重复暂停（只暂停过一次）
    assert len(events_by_type(container, run.id, 'run_paused')) == 1
    container.shutdown()


def test_chat_mode_keeps_direct_failure_without_pause(tmp_path):
    """chat 不受 Auto 暂停影响：连续失败到阈值直接 FAILED，无暂停事件。"""
    llm = FakeLlm(_turns(['broken_query'], 6))
    gateway = FailingGateway(tools=[read_tool('broken_query')])
    container, _engine, _sf = make_auto_stack(
        tmp_path, llm, gateway=gateway)
    run = start_run(container, mode='chat')

    assert status_of(container, run.id) is RunStatus.FAILED
    assert len(gateway.executed) == 3
    assert events_by_type(container, run.id, 'run_paused') == []
    assert events_by_type(container, run.id, 'auto_step') == []
    assert finished_payload(container, run.id)['reason'] is None
    container.shutdown()


# ---------------------------------------------------------------- 请求口径

def _client(container):
    from fastapi.testclient import TestClient
    from agent_service.app import create_app
    return TestClient(create_app(container=container))


OWNER = {'X-User-Id': '7', 'X-Tenant-Id': 't1',
         'X-User-Permissions': 'agent:chat'}


def test_api_auto_mode_budget_tighten_and_mode_roundtrip(tmp_path):
    llm = FakeLlm([text_turn(f'完成 {MARKER}')])
    container, _engine, _sf = make_auto_stack(
        tmp_path, llm, auto_budget_defaults=auto_budget())
    with _client(container) as client:
        session = client.post('/api/v1/agent/sessions', json={},
                              headers=OWNER).json()
        created = client.post(
            f"/api/v1/agent/sessions/{session['id']}/runs",
            json={'message': '汇总报告', 'mode': 'auto',
                  'budget': {'max_rounds': 5, 'max_tool_calls': 999}},
            headers=OWNER)
        assert created.status_code == 201, created.text
        run = created.json()['run']
        assert run['mode'] == 'auto'
        assert run['budget']['max_rounds'] == 5        # 请求收紧生效
        assert run['budget']['max_tool_calls'] == 120  # 放宽被夹回 Auto 上限

        snapshot = client.get(f"/api/v1/agent/runs/{run['id']}",
                              headers=OWNER).json()
        assert snapshot['mode'] == 'auto'

        started = [e for e in container.repositories['events'].list_after(
            run['id'], 0, 100) if e.type.value == 'run_started'][0]
        assert started.payload['mode'] == 'auto'
        # 「启动前展示计划与预算」：暂停规则随 run_started 下发
        assert started.payload['pause_policy'] == {
            'budget_ratio': 0.8, 'consecutive_failures': 2}
    container.shutdown()


def test_api_invalid_mode_and_budget_rejected(tmp_path):
    llm = FakeLlm([text_turn('ok')])
    container, _engine, _sf = make_auto_stack(
        tmp_path, llm, auto_budget_defaults=auto_budget())
    with _client(container) as client:
        session = client.post('/api/v1/agent/sessions', json={},
                              headers=OWNER).json()
        bad_mode = client.post(
            f"/api/v1/agent/sessions/{session['id']}/runs",
            json={'message': 'x', 'mode': 'turbo'}, headers=OWNER)
        assert bad_mode.status_code == 400
        assert bad_mode.json()['code'] == 'INVALID_RUN_MODE'

        bad_budget = client.post(
            f"/api/v1/agent/sessions/{session['id']}/runs",
            json={'message': 'x', 'mode': 'auto',
                  'budget': {'max_nope': 1}}, headers=OWNER)
        assert bad_budget.status_code == 400
        assert bad_budget.json()['code'] == 'INVALID_BUDGET'
    container.shutdown()
