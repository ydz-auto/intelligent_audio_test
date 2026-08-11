# -*- coding: utf-8 -*-
"""DimensionScore 实体测试。

测试 evaluation_service.domain.entities.evaluation_dimension.DimensionScore：
- is_completed()
- is_multi_round()
- mark_running / mark_completed / mark_failed
"""
import pytest

from evaluation_service.domain.entities.evaluation_dimension import (
    DimensionScore,
    RoundResult,
)


def make_score(**kwargs) -> DimensionScore:
    defaults = dict(
        test_result_id=1,
        dimension_id=1,
        algorithm_type='voice',
    )
    defaults.update(kwargs)
    return DimensionScore(**defaults)


class TestIsCompleted:
    def test_is_completed_true(self):
        score = make_score(evaluation_status='completed')
        assert score.is_completed() is True

    def test_is_completed_false_pending(self):
        score = make_score(evaluation_status='pending')
        assert score.is_completed() is False

    def test_is_completed_false_running(self):
        score = make_score(evaluation_status='running')
        assert score.is_completed() is False

    def test_is_completed_default(self):
        score = make_score()
        assert score.is_completed() is False
        assert score.evaluation_status == 'pending'


class TestIsMultiRound:
    def test_is_multi_round_with_rounds_and_none_round_number(self):
        score = make_score(round_number=None, rounds=[
            RoundResult(round_number=0),
            RoundResult(round_number=1),
        ])
        assert score.is_multi_round() is True

    def test_not_multi_round_with_specific_round_number(self):
        score = make_score(round_number=0, rounds=[
            RoundResult(round_number=0),
        ])
        assert score.is_multi_round() is False

    def test_not_multi_round_no_rounds(self):
        score = make_score(round_number=None)
        assert score.is_multi_round() is False

    def test_not_multi_round_empty_rounds(self):
        score = make_score(round_number=None, rounds=[])
        assert score.is_multi_round() is False

    def test_is_multi_round_single_round(self):
        score = make_score(round_number=None, rounds=[
            RoundResult(round_number=0),
        ])
        assert score.is_multi_round() is True


class TestMarkRunning:
    def test_mark_running_sets_status(self):
        score = make_score(evaluation_status='pending')
        score.mark_running()
        assert score.evaluation_status == 'running'

    def test_mark_running_from_completed(self):
        score = make_score(evaluation_status='completed')
        score.mark_running()
        assert score.evaluation_status == 'running'


class TestMarkCompleted:
    def test_mark_completed_sets_score_and_status(self):
        score = make_score(evaluation_status='running')
        score.mark_completed(85.5)
        assert score.score == 85.5
        assert score.status == 'passed'
        assert score.evaluation_status == 'completed'

    def test_mark_completed_custom_status(self):
        score = make_score(evaluation_status='running')
        score.mark_completed(30.0, status='failed')
        assert score.score == 30.0
        assert score.status == 'failed'
        assert score.evaluation_status == 'completed'

    def test_mark_completed_default_passed(self):
        score = make_score()
        score.mark_completed(90.0)
        assert score.status == 'passed'

    def test_mark_completed_zero_score(self):
        score = make_score()
        score.mark_completed(0.0)
        assert score.score == 0.0
        assert score.evaluation_status == 'completed'

    def test_is_completed_after_mark_completed(self):
        score = make_score()
        score.mark_completed(90.0)
        assert score.is_completed() is True


class TestMarkFailed:
    def test_mark_failed_sets_error_and_status(self):
        score = make_score(evaluation_status='running')
        score.mark_failed('评估超时')
        assert score.error_message == '评估超时'
        assert score.status == 'failed'
        assert score.evaluation_status == 'completed'

    def test_mark_failed_is_completed(self):
        score = make_score()
        score.mark_failed('error')
        assert score.is_completed() is True

    def test_mark_failed_empty_message(self):
        score = make_score()
        score.mark_failed('')
        assert score.error_message == ''
        assert score.status == 'failed'


class TestDimensionScoreDefaults:
    def test_default_evaluation_status(self):
        score = make_score()
        assert score.evaluation_status == 'pending'

    def test_default_status_none(self):
        score = make_score()
        assert score.status is None

    def test_default_score_none(self):
        score = make_score()
        assert score.score is None

    def test_default_rounds_empty(self):
        score = make_score()
        assert score.rounds == []

    def test_default_error_message_none(self):
        score = make_score()
        assert score.error_message is None
