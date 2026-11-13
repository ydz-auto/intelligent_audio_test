# -*- coding: utf-8 -*-
"""INT-2451 领域层：枚举 / 状态机 / 预算。

验收锚点（卡面第 6 条）：状态机非法迁移拒绝。
"""
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from agent_service.domain.enums import (
    CompactionLevel, EventType, RunStatus, SandboxTier, ToolRisk,
)
from agent_service.domain.exceptions import InvalidRunTransition
from agent_service.domain.model.budget import RunBudget
from agent_service.domain.services.state_machine import RunStateMachine


class TestEnums:
    def test_enum_values_match_design(self):
        assert {s.value for s in RunStatus} == {
            'QUEUED', 'RUNNING', 'WAITING_APPROVAL', 'SUCCEEDED',
            'FAILED', 'CANCELLED', 'BUDGET_EXCEEDED'}
        assert {r.value for r in ToolRisk} == {'READ', 'WRITE', 'DESTRUCTIVE'}
        assert {t.value for t in SandboxTier} == {
            'T0_NONE', 'T1_TRUSTED_SCRIPT', 'T2_UNTRUSTED_CODE'}
        assert {c.value for c in CompactionLevel} == {
            'L1_TRIM', 'L2_DEDUPE', 'L3_MEMO', 'L4_REBUILD'}
        assert {e.value for e in EventType} == {
            'run_started', 'message_delta', 'tool_call', 'tool_result',
            'approval_required', 'context_compacted',
            # INT-2549：对话沉淀建议（仅事件、不落库）
            'skill_draft_suggested',
            'run_finished', 'error'}

    def test_terminal_flags(self):
        assert RunStatus.SUCCEEDED.is_terminal
        assert RunStatus.CANCELLED.is_terminal
        assert RunStatus.BUDGET_EXCEEDED.is_terminal
        assert not RunStatus.RUNNING.is_terminal
        assert RunStatus.QUEUED.is_active

    def test_write_tools_require_approval(self):
        assert not ToolRisk.READ.requires_approval
        assert ToolRisk.WRITE.requires_approval
        assert ToolRisk.DESTRUCTIVE.requires_approval


class TestStateMachine:
    @pytest.mark.parametrize('current,target', [
        (RunStatus.QUEUED, RunStatus.RUNNING),
        (RunStatus.RUNNING, RunStatus.WAITING_APPROVAL),
        (RunStatus.WAITING_APPROVAL, RunStatus.RUNNING),
        (RunStatus.RUNNING, RunStatus.SUCCEEDED),
        (RunStatus.RUNNING, RunStatus.FAILED),
        (RunStatus.RUNNING, RunStatus.CANCELLED),
        (RunStatus.RUNNING, RunStatus.BUDGET_EXCEEDED),
        (RunStatus.QUEUED, RunStatus.CANCELLED),
    ])
    def test_allowed_transitions(self, current, target):
        assert RunStateMachine.assert_transition(current, target) is target

    @pytest.mark.parametrize('current,target', [
        (RunStatus.QUEUED, RunStatus.SUCCEEDED),
        (RunStatus.QUEUED, RunStatus.WAITING_APPROVAL),
        (RunStatus.SUCCEEDED, RunStatus.RUNNING),
        (RunStatus.CANCELLED, RunStatus.RUNNING),
        (RunStatus.FAILED, RunStatus.SUCCEEDED),
        (RunStatus.BUDGET_EXCEEDED, RunStatus.RUNNING),
    ])
    def test_illegal_transitions_rejected(self, current, target):
        assert not RunStateMachine.can_transition(current, target)
        with pytest.raises(InvalidRunTransition):
            RunStateMachine.assert_transition(current, target)

    def test_terminal_states_have_no_outgoing(self):
        for status in RunStatus:
            if status.is_terminal:
                assert not RunStateMachine.allowed_targets(status)


class TestBudget:
    def test_checks(self):
        budget = RunBudget.from_dict({
            'max_rounds': 2, 'max_tool_calls': 3, 'max_tokens': 100,
            'max_duration_seconds': 10, 'max_output_bytes': 1024})
        assert budget.check_rounds(1) is None
        assert budget.check_rounds(2) == 'max_rounds'
        assert budget.check_tool_calls(3) == 'max_tool_calls'
        assert budget.check_tokens(100) == 'max_tokens'
        assert budget.check_duration(10.5) == 'max_duration_seconds'
        assert budget.check_output_bytes(1024) == 'max_output_bytes'

    def test_zero_limit_disables_dimension(self):
        budget = RunBudget.from_dict({'max_rounds': 0, 'max_tokens': 0})
        assert budget.check_rounds(999) is None
        assert budget.check_tokens(999999) is None

    def test_to_dict_round_trip(self):
        source = {'max_rounds': 5, 'max_tool_calls': 6, 'max_tokens': 7,
                  'max_duration_seconds': 8, 'max_output_bytes': 9}
        assert RunBudget.from_dict(source).to_dict() == source
