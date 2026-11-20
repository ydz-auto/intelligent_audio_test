# -*- coding: utf-8 -*-
"""INT-2474 验收 1：Auto 跑跨域长任务 ≥ 50 轮，预算内完成且全程有进度事件。

同一进程内用脚本化模型跑 55 个跨域工具轮 + 一轮完成答复。默认 Auto 预算
（60 轮）下，第 48 轮（80%）会按 §9.4 暂停交用户决策 → 用户「继续」后
跑完剩余轮次。断言：
- 轮次 ≥ 50、run SUCCEEDED（reason=auto_complete）；
- 预算暂停按 80% 触发且转 WAITING_APPROVAL；
- 每一轮都有 ``auto_step`` 进度事件（当前步骤 / 预算消耗 / 产物）；
- 每个 step 的 plan_snapshot 带 scratchpad（目标 + 计划 + 预算水位）；
- 事件 sequence 严格递增无空洞。
"""
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from agent_service.domain.enums import RunStatus
from agent_service.domain.model.entities import ToolCallRequest
from tests.agent_eval.auto.support import (
    FakeLlm, FakeToolGateway, auto_budget, events_by_type, finished_payload,
    make_auto_stack, read_tool, resume, start_run, status_of, steps_of,
    text_turn, tool_turn,
)

MARKER = '[[AUTO_DONE]]'
DOMAINS = ('task_query', 'device_query', 'audio_query', 'testcase_query',
           'report_query')
ROUNDS = 55


def _long_task_script():
    calls = [
        ToolCallRequest(tool_call_id=f'call_{index}',
                        name=DOMAINS[index % len(DOMAINS)],
                        arguments={'cursor': index})
        for index in range(ROUNDS)
    ]
    return ([tool_turn([call]) for call in calls]
            + [text_turn('三个域已汇总完成，报告已生成 ', MARKER)])


def test_auto_long_task_completes_with_progress_events(tmp_path):
    llm = FakeLlm(_long_task_script())
    gateway = FakeToolGateway(tools=[read_tool(name) for name in DOMAINS])
    container, _engine, _sf = make_auto_stack(
        tmp_path, llm, gateway=gateway,
        auto_budget_defaults=auto_budget())
    run = start_run(container)

    # §9.4：预算消耗到 80%（48/60 轮）暂停交用户决策
    assert status_of(container, run.id) is RunStatus.WAITING_APPROVAL
    paused = events_by_type(container, run.id, 'run_paused')
    assert paused and paused[-1].payload['reason'] == 'budget_threshold'
    assert paused[-1].payload['usage']['rounds'] == 48
    assert paused[-1].payload['ratio'] >= 0.8

    # 用户确认继续 → 跑完剩余轮次（同一暂停点不再触发）
    resume(container, run.id)
    assert status_of(container, run.id) is RunStatus.SUCCEEDED
    assert len(events_by_type(container, run.id, 'run_resumed')) == 1
    finished = finished_payload(container, run.id)
    assert finished['reason'] == 'auto_complete'

    steps = steps_of(container, run.id)
    assert len(steps) == ROUNDS + 1 >= 50
    assert len(llm.requests) == ROUNDS + 1

    progress = events_by_type(container, run.id, 'auto_step')
    assert len(progress) == len(steps)

    # 每一步都有进度载荷：步骤号、预算消耗 / 上限、产物、目标
    for index, event in enumerate(progress, start=1):
        payload = event.payload
        assert payload['mode'] == 'auto'
        assert payload['step'] == index
        # 暂停恢复后的第一轮带 resume 提示，其余都是常规步
        assert payload['phase'] in ('step', 'resume')
        assert payload['goal'] == '把任务、设备与报告三个域的数据汇总成一份报告'
        assert set(payload['usage']) == {
            'rounds', 'tool_calls', 'tokens', 'elapsed_seconds', 'output_bytes'}
        assert payload['limits']['max_rounds'] == 60
        assert 0.0 <= payload['ratio'] <= 1.0
        assert isinstance(payload['artifacts'], list)
        assert payload['artifact_count'] == len(payload['artifacts'])

    # 每轮都有进度事件：48 轮后暂停，继续后新增一轮 resume 提示 + 剩余轮次
    phases = [item.payload['phase'] for item in progress]
    assert phases[47] == 'step'
    assert phases[48] == 'resume'
    assert '已确认继续' in progress[48].payload['instruction']

    # 每个 step 的 scratchpad 记录目标 / 计划 / 预算水位
    for step in steps:
        scratchpad = step.plan_snapshot['scratchpad']
        assert scratchpad['mode'] == 'auto'
        assert scratchpad['goal']
        assert 'usage' in scratchpad and 'ratio' in scratchpad

    # 事件 sequence 严格递增无空洞
    sequences = [event.sequence for event in _all_events(container, run.id)]
    assert sequences == list(range(1, len(sequences) + 1))

    # 跨域：调用覆盖 5 个域的全部只读工具
    used = {call[1] for call in gateway.executed}
    assert used == set(DOMAINS)

    # 进度里能看出预算消耗在增长（末轮 ratio > 首轮）
    assert progress[-1].payload['ratio'] > progress[0].payload['ratio']
    container.shutdown()


def _all_events(container, run_id):
    return container.repositories['events'].list_after(run_id, 0, 10000)


def test_auto_task_plan_is_written_to_scratchpad(tmp_path):
    """首轮文本是模型给的计划：后续步骤的 scratchpad.plan 必须带上。"""
    calls = [ToolCallRequest(tool_call_id='c1', name='task_query',
                             arguments={})]
    llm = FakeLlm([text_turn('计划：先查任务，再查设备 '),
                   tool_turn(calls),
                   text_turn(f'完成 {MARKER}')])
    gateway = FakeToolGateway(tools=[read_tool('task_query')])
    container, _engine, _sf = make_auto_stack(
        tmp_path, llm, gateway=gateway, auto_budget_defaults=auto_budget())
    run = start_run(container)

    assert status_of(container, run.id) is RunStatus.SUCCEEDED
    # 首轮纯文本没有完成标记 → 必须补一次续跑提示，而不是直接结束
    progress = events_by_type(container, run.id, 'auto_step')
    assert [item.payload['phase'] for item in progress] == [
        'step', 'continue', 'step']
    assert '继续推进目标' in progress[1].payload['instruction']
    # 续跑提示作为 user 消息回灌给模型（第三轮请求里能看到）
    roles = [message.role for message in llm.requests[-1].messages]
    assert roles.count('user') >= 2
    # 计划进 scratchpad
    steps = steps_of(container, run.id)
    assert steps[-1].plan_snapshot['scratchpad']['plan'].startswith('计划：')
    container.shutdown()
