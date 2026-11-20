# -*- coding: utf-8 -*-
"""INT-2474 返工回归（测试工程师打回的三条）。

1. **P1 长 run 控制事件被截断**：旧口径按「前 ``EVENT_SCAN_LIMIT`` 条事件」
   回放控制状态，暂停事件落在窗口之后就读不到 → 重启后「继续」409、恢复
   投递再暂停一次；``_output_bytes_so_far`` / ``_next_turn`` 同因少算。
   这里把扫描窗口调小来模拟长 run（等价于真实 run 的第 10000 条之后）。
2. **P2 续跑提示晚一轮**：``continue`` / ``resume`` 的 instruction 必须出现在
   **该轮**的模型请求里，而不是等下一轮从事件回放才补上。
3. **P2 失败暂停的继续连带确认预算暂停点**：因连续失败暂停后点「继续」，
   80% 预算暂停仍必须停下来交用户决策。
4. **P1 长 run 模型历史被截断**：``_messages_for_run`` 只取前
   ``event_fetch_limit`` 条事件，长 run 的最近轮次整段丢失（最老的轮次在、
   最近的没了）。这里同样用小窗口模拟，断言模型请求保留全部轮次。
"""
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from agent_service.config.config import Config
from agent_service.domain.enums import RunStatus
from agent_service.domain.model.entities import ToolCallRequest, ToolResult
from agent_service.domain.ports.llm import (
    LlmFinished, LlmTextDelta, LlmToolCalls,
)
from tests.agent_eval.auto.support import (
    FakeLlm, FakeToolGateway, auto_budget, events_by_type, finished_payload,
    make_auto_stack, read_tool, resume, start_run, status_of, steps_of,
    text_turn, tool_turn,
)
from tests.unit.int2451_agent_fakes import events_of

MARKER = '[[AUTO_DONE]]'
# 模拟「长 run」的扫描窗口：真实 run 的暂停事件会落在第 10000 条之后，
# 这里用同样的小窗口把「按前 N 条取」的旧缺陷暴露出来。
SMALL_SCAN_WINDOW = 12


def _tool_call(index: int, name: str = 'task_query') -> ToolCallRequest:
    return ToolCallRequest(tool_call_id=f'c{index}', name=name,
                           arguments={'i': index})


def _text_tool_turn(index: int, *, parts: int, delta: str = '片段',
                    name: str = 'task_query'):
    """一轮里先输出若干文本分片，再发起一次工具调用。"""
    chunks = [LlmTextDelta(f'{delta}{position}')
              for position in range(parts)]
    chunks.append(LlmToolCalls((_tool_call(index, name),)))
    chunks.append(LlmFinished())
    return chunks


class FlakyGateway(FakeToolGateway):
    """前 ``fail_calls`` 次调用失败，之后成功（制造失败暂停后继续的场景）。"""

    def __init__(self, *args, fail_calls: int = 0, **kwargs):
        super().__init__(*args, **kwargs)
        self._remaining_failures = int(fail_calls)

    def execute(self, call, context) -> ToolResult:
        with self._lock:
            self.executed.append((call.tool_call_id, call.name, call.arguments))
        if self._remaining_failures > 0:
            self._remaining_failures -= 1
            return ToolResult(tool_call_id=call.tool_call_id, tool=call.name,
                              ok=False, content='上游连接失败',
                              error_code='TOOL_FAILED')
        return ToolResult(tool_call_id=call.tool_call_id, tool=call.name,
                          ok=True, content=f'ok:{call.name}')


def _build(tmp_path, llm, gateway, *, name):
    return make_auto_stack(tmp_path, llm, gateway=gateway, name=name,
                           auto_budget_defaults=auto_budget(
                               max_rounds=20, max_tool_calls=5))


# ---------------------------------------------------------------- P1 控制状态

def test_control_state_survives_events_beyond_scan_window(tmp_path, monkeypatch):
    """暂停事件在扫描窗口之后，重启后仍能读出暂停事实并继续。"""
    monkeypatch.setattr(Config, 'EVENT_SCAN_LIMIT', SMALL_SCAN_WINDOW)
    llm = FakeLlm([_text_tool_turn(index, parts=4) for index in range(10)])
    gateway = FakeToolGateway(tools=[read_tool('task_query')])
    container_a, _engine_a, _sf_a = _build(tmp_path, llm, gateway,
                                           name='int2474_long_control.db')
    run = start_run(container_a)

    # 4/5 = 80% 工具预算 → 暂停；暂停事件已在小窗口之后
    assert status_of(container_a, run.id) is RunStatus.WAITING_APPROVAL
    paused = events_by_type(container_a, run.id, 'run_paused')
    assert paused[-1].payload['reason'] == 'budget_threshold'
    assert paused[-1].payload['ratio'] >= 0.8
    assert events_of(container_a, run.id)[-1].sequence > SMALL_SCAN_WINDOW
    container_a.shutdown()

    # ---------------------------------------------------------- 进程重启
    requests_before = len(llm.requests)
    container_b, _engine_b, _sf_b = _build(tmp_path, llm, gateway,
                                           name='int2474_long_control.db')

    # 控制状态从事件尾部重建（旧实现按前 N 条 → paused=False）
    state = container_b.run_service._control_state(run.id)
    assert state.paused is True
    assert state.pause_reason == 'budget_threshold'

    # 恢复投递不得静默续跑、也不得再暂停一次
    resumable = container_b.recovery.recover()
    assert run.id in resumable
    for run_id in resumable:
        container_b.executor.submit(run_id)
    assert status_of(container_b, run.id) is RunStatus.WAITING_APPROVAL
    assert len(llm.requests) == requests_before
    assert len(events_by_type(container_b, run.id, 'run_paused')) == 1

    # 用户继续：旧实现这里会 409 RUN_NOT_PAUSED（run 永久卡死）
    resume(container_b, run.id)
    assert len(events_by_type(container_b, run.id, 'run_resumed')) == 1
    # 继续不放宽硬预算：第 6 次工具调用 → BUDGET_EXCEEDED(max_tool_calls)
    assert finished_payload(container_b, run.id)['reason'] == 'max_tool_calls'

    # 同因修复：轮次号从尾部续上，重启后不会回退造成 turn 冲突
    turns = [event.payload['turn'] for event in
             events_by_type(container_b, run.id, 'auto_step')]
    assert turns == sorted(turns)
    assert len(set(turns)) == len(turns)
    container_b.shutdown()


def test_output_bytes_accumulate_across_scan_window(tmp_path, monkeypatch):
    """跨重启累计输出字节：只算前 N 条会让重启后的 run 突破输出预算。"""
    monkeypatch.setattr(Config, 'EVENT_SCAN_LIMIT', SMALL_SCAN_WINDOW)
    # 首段 30 片共 140 字节后连续两次工具失败暂停
    first = _text_tool_turn(0, parts=30, delta='abc')
    llm = FakeLlm([
        first,
        tool_turn([_tool_call(1, 'broken_query')]),
        # 继续后 40 片 × 3 字节：140 + 60 = 200 ≥ 200 → BUDGET_EXCEEDED
        [LlmTextDelta('abc') for _ in range(40)] + [LlmFinished()],
        text_turn(f'完成 {MARKER}'),
    ])
    gateway = FlakyGateway(tools=[read_tool('task_query'),
                                  read_tool('broken_query')],
                           fail_calls=2)
    budget = auto_budget(max_rounds=20, max_tool_calls=50,
                         max_output_bytes=200)
    container_a, _engine_a, _sf_a = make_auto_stack(
        tmp_path, llm, gateway=gateway, name='int2474_long_bytes.db',
        auto_budget_defaults=budget)
    run = start_run(container_a)
    paused = events_by_type(container_a, run.id, 'run_paused')
    assert paused[-1].payload['reason'] == 'consecutive_tool_failures'
    assert len(llm.requests) == 2
    assert events_of(container_a, run.id)[-1].sequence > SMALL_SCAN_WINDOW
    container_a.shutdown()

    container_b, _engine_b, _sf_b = make_auto_stack(
        tmp_path, llm, gateway=gateway, name='int2474_long_bytes.db',
        auto_budget_defaults=budget)
    for run_id in container_b.recovery.recover():
        container_b.executor.submit(run_id)
    resume(container_b, run.id)

    assert status_of(container_b, run.id) is RunStatus.BUDGET_EXCEEDED
    assert finished_payload(container_b, run.id)['reason'] == 'max_output_bytes'
    produced = sum(
        len(str((event.payload or {}).get('delta') or '').encode('utf-8'))
        for event in events_by_type(container_b, run.id, 'message_delta'))
    # 累计口径：重启前的输出必须计入（旧实现只算到窗口内 ≈ 40 字节，
    # 加上继续后的 120 字节也到不了 200 → 不会超限）
    assert produced >= 200
    container_b.shutdown()


# ---------------------------------------------------------------- P2 续跑提示

def _user_texts(request) -> list:
    return [message.content or '' for message in request.messages
            if message.role == 'user']


def test_continue_instruction_is_in_that_round_request(tmp_path):
    """「继续推进目标」必须在 continue 那一轮的请求里，而不是晚一轮。"""
    llm = FakeLlm([
        text_turn('第一步：先看一下现状'),
        tool_turn([_tool_call(0)]),
        text_turn(f'完成 {MARKER}'),
    ])
    gateway = FakeToolGateway(tools=[read_tool('task_query')])
    container, _engine, _sf = _build(tmp_path, llm, gateway,
                                     name='int2474_instruction.db')
    run = start_run(container)

    phases = [event.payload['phase'] for event in
              events_by_type(container, run.id, 'auto_step')]
    assert phases == ['step', 'continue', 'step']
    # 第 2 轮（continue）的请求必须已经带上续跑提示
    second_round = _user_texts(llm.requests[1])
    assert any('继续推进目标' in text for text in second_round)
    assert sum('继续推进目标' in text for text in second_round) == 1
    container.shutdown()


def test_resume_instruction_is_in_first_resumed_request(tmp_path):
    """用户「继续」的确认必须送达恢复后的第一轮模型请求。"""
    llm = FakeLlm([tool_turn([_tool_call(index)]) for index in range(10)])
    gateway = FakeToolGateway(tools=[read_tool('task_query')])
    container, _engine, _sf = _build(tmp_path, llm, gateway,
                                     name='int2474_resume_instruction.db')
    run = start_run(container)
    assert status_of(container, run.id) is RunStatus.WAITING_APPROVAL
    assert len(llm.requests) == 4  # 4/5 = 80% 暂停

    resume(container, run.id)

    first_resumed = _user_texts(llm.requests[4])
    assert any('用户已确认继续' in text for text in first_resumed)
    assert any('budget_threshold' in text for text in first_resumed)
    # 当轮送达且不重复（下一轮才是从事件回放补进历史）
    assert sum('用户已确认继续' in text for text in first_resumed) == 1
    container.shutdown()


# ---------------------------------------------------------------- P2 预算确认

def test_resume_from_failures_pause_keeps_budget_pause(tmp_path):
    """因连续失败暂停后的继续，不得把 80% 预算暂停点标记为已确认。"""
    llm = FakeLlm([tool_turn([_tool_call(index)]) for index in range(10)])
    gateway = FlakyGateway(tools=[read_tool('task_query')], fail_calls=2)
    container, _engine, _sf = make_auto_stack(
        tmp_path, llm, gateway=gateway, name='int2474_budget_ack.db',
        auto_budget_defaults=auto_budget(max_rounds=10,
                                         max_tool_calls=50))
    run = start_run(container)

    first_pause = events_by_type(container, run.id, 'run_paused')
    assert len(first_pause) == 1
    assert first_pause[-1].payload['reason'] == 'consecutive_tool_failures'
    assert len(steps_of(container, run.id)) == 2

    resume(container, run.id)

    pauses = events_by_type(container, run.id, 'run_paused')
    assert len(pauses) == 2, '80% 预算暂停点被失败暂停的继续连带确认掉了'
    assert pauses[-1].payload['reason'] == 'budget_threshold'
    assert pauses[-1].payload['ratio'] >= 0.8
    assert status_of(container, run.id) is RunStatus.WAITING_APPROVAL
    container.shutdown()


# ---------------------------------------------------------------- P1 历史完整性

def _assistant_texts(request) -> list:
    return [message.content or '' for message in request.messages
            if message.role == 'assistant']


def test_long_run_history_keeps_recent_turns(tmp_path, monkeypatch):
    """事件超过扫描窗口时，最近的轮次仍必须回灌模型（旧实现只取最前 N 条）。"""
    monkeypatch.setattr(Config, 'EVENT_SCAN_LIMIT', SMALL_SCAN_WINDOW)
    llm = FakeLlm(
        [_text_tool_turn(index, parts=4, delta=f'T{index}-')
         for index in range(5)] + [text_turn(f'完成 {MARKER}')])
    gateway = FakeToolGateway(tools=[read_tool('task_query')])
    container, _engine, _sf = make_auto_stack(
        tmp_path, llm, gateway=gateway, name='int2474_long_history.db',
        auto_budget_defaults=auto_budget(max_rounds=20, max_tool_calls=50))
    run = start_run(container)

    assert status_of(container, run.id) is RunStatus.SUCCEEDED
    assert events_of(container, run.id)[-1].sequence > SMALL_SCAN_WINDOW
    # 最后一轮请求必须看到此前每一轮（旧实现窗口之后 turn 全部缺失）
    history = '\n'.join(_assistant_texts(llm.requests[-1]))
    for index in range(5):
        assert f'T{index}-' in history, f'turn{index} 的历史丢失'
    container.shutdown()


def test_resumed_request_rebuilds_history_beyond_scan_window(tmp_path,
                                                             monkeypatch):
    """重启 + 继续后的第一轮请求仍能重建暂停前的完整历史（验收 4）。"""
    monkeypatch.setattr(Config, 'EVENT_SCAN_LIMIT', SMALL_SCAN_WINDOW)
    llm = FakeLlm([_text_tool_turn(index, parts=4, delta=f'T{index}-')
                   for index in range(10)])
    gateway = FakeToolGateway(tools=[read_tool('task_query')])
    budget = auto_budget(max_rounds=20, max_tool_calls=5)
    container_a, _engine_a, _sf_a = make_auto_stack(
        tmp_path, llm, gateway=gateway, name='int2474_long_resume.db',
        auto_budget_defaults=budget)
    run = start_run(container_a)
    assert status_of(container_a, run.id) is RunStatus.WAITING_APPROVAL
    assert len(events_by_type(container_a, run.id, 'auto_step')) == 4
    assert events_of(container_a, run.id)[-1].sequence > SMALL_SCAN_WINDOW
    container_a.shutdown()

    container_b, _engine_b, _sf_b = make_auto_stack(
        tmp_path, llm, gateway=gateway, name='int2474_long_resume.db',
        auto_budget_defaults=budget)
    for run_id in container_b.recovery.recover():
        container_b.executor.submit(run_id)
    requests_before = len(llm.requests)
    resume(container_b, run.id)

    history = '\n'.join(_assistant_texts(llm.requests[requests_before]))
    for index in range(4):
        assert f'T{index}-' in history, f'暂停前 turn{index} 的历史丢失'
    container_b.shutdown()
