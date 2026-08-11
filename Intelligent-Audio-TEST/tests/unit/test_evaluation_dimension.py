# -*- coding: utf-8 -*-
"""EvaluationDimension 聚合根测试。

测试 evaluation_service.domain.entities.evaluation_dimension.EvaluationDimension：
- add_score() 添加评分
- is_active() 对 online/offline 状态
"""
import pytest

from evaluation_service.domain.entities.evaluation_dimension import (
    DimensionScore,
    DimensionSnapshot,
    EvaluationDimension,
    ScoringRule,
)


def make_snapshot(api_status='online') -> DimensionSnapshot:
    return DimensionSnapshot(
        id=1,
        name='测试维度',
        algorithm_type='voice',
        api_status=api_status,
    )


def make_dimension(api_status='online',
                   scores=None) -> EvaluationDimension:
    return EvaluationDimension(
        id=1,
        name='测试维度',
        algorithm_type='voice',
        snapshot=make_snapshot(api_status=api_status),
        scores=scores or [],
    )


def make_score(**kwargs) -> DimensionScore:
    defaults = dict(
        test_result_id=1,
        dimension_id=1,
        algorithm_type='voice',
    )
    defaults.update(kwargs)
    return DimensionScore(**defaults)


class TestAddScore:
    def test_add_single_score(self):
        dim = make_dimension()
        assert len(dim.scores) == 0
        dim.add_score(make_score())
        assert len(dim.scores) == 1

    def test_add_multiple_scores(self):
        dim = make_dimension()
        dim.add_score(make_score())
        dim.add_score(make_score())
        assert len(dim.scores) == 2

    def test_add_score_preserves_reference(self):
        dim = make_dimension()
        score = make_score()
        dim.add_score(score)
        assert dim.scores[0] is score

    def test_add_score_appends(self):
        dim = make_dimension()
        s1 = make_score(round_number=0)
        s2 = make_score(round_number=1)
        dim.add_score(s1)
        dim.add_score(s2)
        assert dim.scores[0].round_number == 0
        assert dim.scores[1].round_number == 1


class TestIsActive:
    def test_is_active_online(self):
        dim = make_dimension(api_status='online')
        assert dim.is_active() is True

    def test_is_active_offline(self):
        dim = make_dimension(api_status='offline')
        assert dim.is_active() is False

    def test_is_active_other_status(self):
        dim = make_dimension(api_status='unknown')
        assert dim.is_active() is False

    def test_is_active_default_online(self):
        # DimensionSnapshot 默认 api_status='online'
        dim = EvaluationDimension(
            id=1,
            name='维度',
            algorithm_type='voice',
            snapshot=DimensionSnapshot(id=1, name='维度',
                                       algorithm_type='voice'),
        )
        assert dim.is_active() is True


class TestSnapshotWithScoringRule:
    def test_snapshot_default_rule(self):
        snap = DimensionSnapshot(id=1, name='维度',
                                 algorithm_type='voice')
        assert isinstance(snap.rule, ScoringRule)
        assert snap.rule.type == 'direct'

    def test_snapshot_custom_rule(self):
        rule = ScoringRule(type='linear', rules=[
            {'condition': '>', 'value': 0.5, 'score': 80},
        ])
        snap = DimensionSnapshot(id=1, name='维度',
                                 algorithm_type='voice', rule=rule)
        assert snap.rule.type == 'linear'

    def test_snapshot_default_api_endpoints(self):
        snap = DimensionSnapshot(id=1, name='维度',
                                 algorithm_type='voice')
        assert snap.api_endpoints == []

    def test_snapshot_default_rounds_empty(self):
        dim = make_dimension()
        assert dim.scores == []
