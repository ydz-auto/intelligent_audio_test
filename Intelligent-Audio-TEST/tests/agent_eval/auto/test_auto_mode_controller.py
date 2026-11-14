# -*- coding: utf-8 -*-
"""INT-2474 验收 5：预算边界与熔断阈值单测（纯策略，不起 Loop）。

覆盖：
- 硬预算由 RunBudget 判定（含 "limit ≤ 0 不启用" 与边界值）；
- Auto 暂停：预算比例恰好 80% 触发、79.9% 不触发；继续后不再因预算暂停；
- 连续失败：2 次暂停、3 次熔断、继续后同一失败连击不重复暂停；
- 完成标记 / 空转上限；
- 请求侧预算只能收紧（§9.4 请求不可放宽）；
- 控制状态从事件流重建（重启后不依赖进程内标志）。
"""
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from agent_service.application.auto_mode import (
    COMPLETE_REASON, IDLE_REASON, PAUSE_REASON_BUDGET, PAUSE_REASON_FAILURES,
    PHASE_CONTINUE, PHASE_RESUME, AutoAction, AutoControlState,
    AutoModeController, AutoSettings, BudgetUsage,
)
from agent_service.domain.enums import EventType
from agent_service.domain.model.budget import RunBudget
from agent_service.domain.model.entities import AgentRunEvent

MARKER = '[[AUTO_DONE]]'

AUTO_LIMITS = {'max_rounds': 60, 'max_tool_calls': 120, 'max_tokens': 400000,
               'max_duration_seconds': 1800, 'max_output_bytes': 20971520}


def usage(**overrides) -> BudgetUsage:
    values = dict(rounds=0, tool_calls=0, tokens=0, elapsed_seconds=0.0,
                  output_bytes=0, limits=dict(AUTO_LIMITS),
                  consecutive_failures=0)
    values.update(overrides)
    return BudgetUsage(**values)


def controller(**overrides) -> AutoModeController:
    return AutoModeController(AutoSettings(**overrides))


def event(event_type, payload, sequence=1):
    return AgentRunEvent(id=f'e{sequence}', run_id='r1', sequence=sequence,
                         type=event_type, payload=payload)


# ---------------------------------------------------------------- 硬预算

class TestHardBudgetBoundary:
    def test_limit_reached_counts_as_exceeded(self):
        budget = RunBudget.from_dict({
            'max_rounds': 3, 'max_tool_calls': 5, 'max_tokens': 100,
            'max_duration_seconds': 10, 'max_output_bytes': 1024})
        assert budget.check_rounds(2) is None
        assert budget.check_rounds(3) == 'max_rounds'
        assert budget.check_tokens(99) is None
        assert budget.check_tokens(100) == 'max_tokens'
        assert budget.check_duration(9.99) is None
        assert budget.check_duration(10.0) == 'max_duration_seconds'
        assert budget.check_output_bytes(1023) is None
        assert budget.check_output_bytes(1024) == 'max_output_bytes'

    def test_zero_limit_disables_dimension(self):
        budget = RunBudget.from_dict({'max_rounds': 0, 'max_tokens': 0})
        assert budget.check_rounds(10 ** 6) is None
        assert budget.check_tokens(10 ** 9) is None

    def test_request_can_only_tighten(self):
        base = RunBudget.from_dict(AUTO_LIMITS)
        tightened = base.tightened({'max_rounds': 10, 'max_tool_calls': 999,
                                    'max_tokens': 0, 'max_output_bytes': None})
        assert tightened.max_rounds == 10            # 收紧生效
        assert tightened.max_tool_calls == 120       # 放宽被夹回服务端值
        assert tightened.max_tokens == 400000        # 0 = 不覆盖
        assert tightened.max_output_bytes == 20971520  # None = 不覆盖

    def test_unknown_budget_key_rejected(self):
        with pytest.raises(ValueError):
            RunBudget.from_dict(AUTO_LIMITS).tightened({'max_everything': 1})

    def test_non_integer_budget_rejected(self):
        with pytest.raises(ValueError):
            RunBudget.from_dict(AUTO_LIMITS).tightened({'max_rounds': 'x'})


# ---------------------------------------------------------------- 预算暂停

class TestBudgetPause:
    def test_pause_exactly_at_ratio(self):
        ctl = controller()
        # 48/60 = 0.80 → 暂停
        assert ctl.preflight(usage=usage(rounds=48),
                             control=AutoControlState()) is AutoAction.PAUSE_BUDGET
        # 47/60 ≈ 0.783 → 继续
        assert ctl.preflight(usage=usage(rounds=47),
                             control=AutoControlState()) is None

    def test_pause_uses_highest_dimension(self):
        ctl = controller()
        # 轮次才 10/60，但输出字节已到 80%
        paused = ctl.preflight(
            usage=usage(rounds=10,
                        output_bytes=int(AUTO_LIMITS['max_output_bytes'] * 0.8)),
            control=AutoControlState())
        assert paused is AutoAction.PAUSE_BUDGET

    def test_resume_ack_disables_budget_pause_only(self):
        ctl = controller()
        acked = AutoControlState(budget_pause_acked=True)
        # 已确认继续：同一水位不再暂停
        assert ctl.preflight(usage=usage(rounds=48), control=acked) is None
        # 但熔断阈值仍然生效
        assert ctl.preflight(usage=usage(rounds=10, consecutive_failures=3),
                             control=acked) is AutoAction.FAIL_CIRCUIT

    def test_disabled_ratio(self):
        ctl = controller(pause_budget_ratio=0)
        assert ctl.preflight(usage=usage(rounds=59),
                             control=AutoControlState()) is None


# ---------------------------------------------------------------- 熔断

class TestCircuitBreaker:
    def test_pause_at_two_failures(self):
        ctl = controller()
        assert ctl.preflight(usage=usage(consecutive_failures=1),
                             control=AutoControlState()) is None
        assert ctl.preflight(
            usage=usage(consecutive_failures=2),
            control=AutoControlState()) is AutoAction.PAUSE_FAILURES

    def test_circuit_break_at_three_failures(self):
        ctl = controller()
        assert ctl.preflight(usage=usage(consecutive_failures=3),
                             control=AutoControlState()) is AutoAction.FAIL_CIRCUIT

    def test_resume_records_failure_watermark(self):
        ctl = controller()
        acked = AutoControlState(failures_acked=2)
        # 同一失败连击（=2）不重复暂停
        assert ctl.preflight(usage=usage(consecutive_failures=2),
                             control=acked) is None
        # 继续后又失败第三次 → 熔断（暂停档已越过）
        assert ctl.preflight(usage=usage(consecutive_failures=3),
                             control=acked) is AutoAction.FAIL_CIRCUIT


# ---------------------------------------------------------------- 完成 / 空转

class TestCompletion:
    def test_marker_completes(self):
        ctl = controller()
        assert ctl.after_turn(text=f'已完成。{MARKER}', has_tool_calls=False,
                              control=AutoControlState()) is AutoAction.COMPLETE

    def test_text_without_marker_continues(self):
        ctl = controller()
        assert ctl.after_turn(text='做了一半', has_tool_calls=False,
                              control=AutoControlState()) is AutoAction.CONTINUE

    def test_idle_limit_completes(self):
        ctl = controller(max_idle_turns=2)
        control = AutoControlState(idle_nudges=2)
        assert ctl.after_turn(text='没有标记', has_tool_calls=False,
                              control=control) is AutoAction.COMPLETE_IDLE

    def test_tool_calls_always_continue(self):
        ctl = controller()
        assert ctl.after_turn(text='', has_tool_calls=True,
                              control=AutoControlState(idle_nudges=99)) \
            is AutoAction.CONTINUE

    def test_custom_marker(self):
        ctl = controller(complete_marker='DONE_NOW')
        assert ctl.is_complete('好的 DONE_NOW')
        assert not ctl.is_complete(MARKER)


# ---------------------------------------------------------------- 控制状态

class TestControlState:
    def test_rebuild_from_events(self):
        events = [
            event(EventType.RUN_STARTED, {}, 1),
            event(EventType.RUN_PAUSED, {'reason': PAUSE_REASON_FAILURES}, 2),
            event(EventType.RUN_RESUMED, {'consecutive_failures': 2}, 3),
            event(EventType.AUTO_STEP, {'phase': PHASE_CONTINUE}, 4),
            event(EventType.AUTO_STEP, {'phase': PHASE_CONTINUE}, 5),
        ]
        state = AutoControlState.from_events(events)
        assert not state.paused
        assert state.pause_reason == PAUSE_REASON_FAILURES
        assert state.budget_pause_acked is True
        assert state.failures_acked == 2
        assert state.idle_nudges == 2
        # 已经跑过一轮（auto_step）→ 不再补 resume 提示
        assert state.pending_resume is False

    def test_pending_resume_until_first_step(self):
        events = [
            event(EventType.RUN_PAUSED, {'reason': PAUSE_REASON_BUDGET}, 1),
            event(EventType.RUN_RESUMED, {}, 2),
        ]
        state = AutoControlState.from_events(events)
        assert state.paused is False
        assert state.pending_resume is True
        assert state.pause_reason == PAUSE_REASON_BUDGET

    def test_paused_is_last_control_event(self):
        events = [
            event(EventType.RUN_PAUSED, {'reason': PAUSE_REASON_BUDGET}, 1),
            event(EventType.RUN_RESUMED, {}, 2),
            event(EventType.RUN_PAUSED, {'reason': PAUSE_REASON_BUDGET}, 3),
        ]
        state = AutoControlState.from_events(events)
        assert state.paused is True


# ---------------------------------------------------------------- 提示词

class TestPrompts:
    def test_system_prompt_contains_marker_and_limits(self):
        prompt = controller().system_prompt(RunBudget.from_dict(AUTO_LIMITS))
        assert MARKER in prompt
        assert '80%' in prompt
        assert '60' in prompt and '120' in prompt

    def test_instruction_states_goal_and_budget(self):
        text = controller().instruction(
            goal='汇总报告', step=7, usage=usage(rounds=6))
        assert '汇总报告' in text and '第 7 步' in text and MARKER in text
        resume_text = controller().instruction(
            goal='汇总报告', step=7, usage=usage(rounds=6),
            phase=PHASE_RESUME, pause_reason='budget_threshold')
        assert '用户已确认继续' in resume_text
        assert 'budget_threshold' in resume_text

    def test_plan_digest_truncates(self):
        ctl = controller(plan_max_chars=10)
        assert ctl.plan_digest('一二三四五六七八九十十一') == '一二三四五六七八九十…'


def test_reason_codes_are_stable():
    """reason 码是前端与审计的契约，改动需同步 INT-2477。"""
    assert COMPLETE_REASON == 'auto_complete'
    assert IDLE_REASON == 'auto_idle_limit'
