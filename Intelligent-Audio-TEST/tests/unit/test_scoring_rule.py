# -*- coding: utf-8 -*-
"""ScoringRule 评分规则测试。

测试 evaluation_service.domain.entities.evaluation_dimension.ScoringRule：
- from_dict() / to_dict() 序列化
- validate() 规则校验
- calculate() direct/linear/threshold 计算（按 rules 条件匹配）
"""
import pytest

from evaluation_service.domain.entities.evaluation_dimension import ScoringRule


class TestFromDict:
    def test_from_dict_full(self):
        data = {
            'type': 'linear',
            'min': 0,
            'max': 10,
            'score_min': 0,
            'score_max': 100,
            'thresholds': [{'value': 5, 'score': 50}],
            'rules': [{'condition': '>', 'value': 5, 'score': 80}],
        }
        rule = ScoringRule.from_dict(data)
        assert rule.type == 'linear'
        assert rule.min == 0
        assert rule.max == 10
        assert rule.score_min == 0
        assert rule.score_max == 100
        assert rule.thresholds == [{'value': 5, 'score': 50}]
        assert rule.rules == [{'condition': '>', 'value': 5, 'score': 80}]

    def test_from_dict_empty_returns_default(self):
        rule = ScoringRule.from_dict(None)
        assert rule.type == 'direct'
        assert rule.min == 0
        assert rule.max == 1
        assert rule.score_min == 0
        assert rule.score_max == 100
        assert rule.thresholds == []
        assert rule.rules == []

    def test_from_dict_empty_dict(self):
        rule = ScoringRule.from_dict({})
        assert rule.type == 'direct'
        assert rule.rules == []

    def test_from_dict_partial_uses_defaults(self):
        rule = ScoringRule.from_dict({'type': 'threshold'})
        assert rule.type == 'threshold'
        assert rule.min == 0
        assert rule.max == 1
        assert rule.score_min == 0
        assert rule.score_max == 100

    def test_from_dict_none_thresholds(self):
        rule = ScoringRule.from_dict({'thresholds': None, 'rules': None})
        assert rule.thresholds == []
        assert rule.rules == []


class TestToDict:
    def test_to_dict_roundtrip(self):
        data = {
            'type': 'linear',
            'min': 0,
            'max': 10,
            'score_min': 0,
            'score_max': 100,
            'thresholds': [{'value': 5, 'score': 50}],
            'rules': [{'condition': '>', 'value': 5, 'score': 80}],
        }
        rule = ScoringRule.from_dict(data)
        d = rule.to_dict()
        assert d['type'] == 'linear'
        assert d['min'] == 0
        assert d['max'] == 10
        assert d['score_min'] == 0
        assert d['score_max'] == 100
        assert d['thresholds'] == [{'value': 5, 'score': 50}]
        assert d['rules'] == [{'condition': '>', 'value': 5, 'score': 80}]

    def test_to_dict_default(self):
        rule = ScoringRule()
        d = rule.to_dict()
        assert d['type'] == 'direct'
        assert d['thresholds'] == []
        assert d['rules'] == []

    def test_to_dict_contains_all_keys(self):
        rule = ScoringRule()
        d = rule.to_dict()
        expected_keys = {'type', 'min', 'max', 'score_min', 'score_max',
                         'thresholds', 'rules'}
        assert set(d.keys()) == expected_keys


class TestValidate:
    def test_validate_empty_rules_passes(self):
        rule = ScoringRule()
        ok, msg = rule.validate()
        assert ok is True

    def test_validate_valid_rules_passes(self):
        rule = ScoringRule(rules=[
            {'condition': '>', 'value': 0.5, 'score': 90},
            {'condition': '<=', 'value': 0.5, 'score': 60},
        ])
        ok, msg = rule.validate()
        assert ok is True

    def test_validate_invalid_condition_fails(self):
        rule = ScoringRule(rules=[
            {'condition': '~', 'value': 0.5, 'score': 90},
        ])
        ok, msg = rule.validate()
        assert ok is False
        assert '无效' in msg or '条件' in msg

    def test_validate_missing_condition_fails(self):
        rule = ScoringRule(rules=[
            {'value': 0.5, 'score': 90},
        ])
        ok, msg = rule.validate()
        assert ok is False
        assert '必要字段' in msg or 'condition' in msg

    def test_validate_missing_value_fails(self):
        rule = ScoringRule(rules=[
            {'condition': '>', 'score': 90},
        ])
        ok, msg = rule.validate()
        assert ok is False
        assert '必要字段' in msg or 'value' in msg

    def test_validate_missing_score_fails(self):
        rule = ScoringRule(rules=[
            {'condition': '>', 'value': 0.5},
        ])
        ok, msg = rule.validate()
        assert ok is False
        assert '必要字段' in msg or 'score' in msg

    def test_validate_non_dict_rule_fails(self):
        rule = ScoringRule(rules=['not a dict'])
        ok, msg = rule.validate()
        assert ok is False
        assert '对象' in msg

    def test_validate_non_numeric_value_fails(self):
        rule = ScoringRule(rules=[
            {'condition': '>', 'value': 'abc', 'score': 90},
        ])
        ok, msg = rule.validate()
        assert ok is False
        assert '数字' in msg

    def test_validate_non_numeric_score_fails(self):
        rule = ScoringRule(rules=[
            {'condition': '>', 'value': 0.5, 'score': 'abc'},
        ])
        ok, msg = rule.validate()
        assert ok is False
        assert '得分' in msg and '数字' in msg

    def test_validate_all_valid_conditions(self):
        for cond in ['>', '>=', '<', '<=', '==', '!=']:
            rule = ScoringRule(rules=[
                {'condition': cond, 'value': 0.5, 'score': 90},
            ])
            ok, _ = rule.validate()
            assert ok is True, f"condition {cond} should be valid"

    def test_validate_returns_tuple(self):
        rule = ScoringRule()
        result = rule.validate()
        assert isinstance(result, tuple)
        assert len(result) == 2


class TestCalculate:
    """calculate() 根据条件匹配返回分数。"""

    def test_calculate_no_rules_returns_zero(self):
        rule = ScoringRule()
        assert rule.calculate(0.8) == 0.0

    def test_calculate_greater_than_match(self):
        rule = ScoringRule(rules=[
            {'condition': '>', 'value': 0.5, 'score': 90},
        ])
        assert rule.calculate(0.8) == 90.0

    def test_calculate_greater_than_no_match(self):
        rule = ScoringRule(rules=[
            {'condition': '>', 'value': 0.5, 'score': 90},
        ])
        assert rule.calculate(0.3) == 0.0

    def test_calculate_greater_equal_match(self):
        rule = ScoringRule(rules=[
            {'condition': '>=', 'value': 0.5, 'score': 90},
        ])
        assert rule.calculate(0.5) == 90.0

    def test_calculate_less_than_match(self):
        rule = ScoringRule(rules=[
            {'condition': '<', 'value': 0.5, 'score': 30},
        ])
        assert rule.calculate(0.3) == 30.0

    def test_calculate_less_equal_match(self):
        rule = ScoringRule(rules=[
            {'condition': '<=', 'value': 0.5, 'score': 30},
        ])
        assert rule.calculate(0.5) == 30.0

    def test_calculate_equal_match(self):
        rule = ScoringRule(rules=[
            {'condition': '==', 'value': 1, 'score': 100},
        ])
        assert rule.calculate(1) == 100.0

    def test_calculate_not_equal_match(self):
        rule = ScoringRule(rules=[
            {'condition': '!=', 'value': 0, 'score': 50},
        ])
        assert rule.calculate(1) == 50.0

    def test_calculate_not_equal_no_match(self):
        rule = ScoringRule(rules=[
            {'condition': '!=', 'value': 0, 'score': 50},
        ])
        assert rule.calculate(0) == 0.0

    def test_calculate_first_match_wins(self):
        # 多条规则，返回第一个匹配的
        rule = ScoringRule(rules=[
            {'condition': '>', 'value': 0.5, 'score': 90},
            {'condition': '>', 'value': 0.3, 'score': 60},
        ])
        assert rule.calculate(0.8) == 90.0

    def test_calculate_second_rule_matches(self):
        rule = ScoringRule(rules=[
            {'condition': '>', 'value': 0.9, 'score': 100},
            {'condition': '>', 'value': 0.5, 'score': 80},
        ])
        assert rule.calculate(0.6) == 80.0

    def test_calculate_no_match_returns_zero(self):
        rule = ScoringRule(rules=[
            {'condition': '>', 'value': 0.9, 'score': 100},
        ])
        assert rule.calculate(0.1) == 0.0

    def test_calculate_string_input_numeric(self):
        # 字符串数字会被转换为数值
        rule = ScoringRule(rules=[
            {'condition': '>', 'value': 0.5, 'score': 90},
        ])
        assert rule.calculate('0.8') == 90.0

    def test_calculate_string_integer_input(self):
        rule = ScoringRule(rules=[
            {'condition': '==', 'value': 1, 'score': 100},
        ])
        assert rule.calculate('1.0') == 100.0

    def test_calculate_non_numeric_string_raises_typeerror(self):
        # 'abc' 无法转 float，保持原字符串，与 float 比较抛 TypeError
        rule = ScoringRule(rules=[
            {'condition': '>', 'value': 0.5, 'score': 90},
        ])
        with pytest.raises(TypeError):
            rule.calculate('abc')

    def test_calculate_returns_float(self):
        rule = ScoringRule(rules=[
            {'condition': '>', 'value': 0.5, 'score': 90},
        ])
        result = rule.calculate(0.8)
        assert isinstance(result, float)
        assert result == 90.0


class TestCalculateDirectLinearThresholdTypes:
    """不同 type 的规则仍走 rules 条件匹配逻辑。"""

    def test_direct_type_with_rules(self):
        rule = ScoringRule(type='direct', rules=[
            {'condition': '==', 'value': 1, 'score': 50},
        ])
        assert rule.calculate(1) == 50.0

    def test_linear_type_with_rules(self):
        rule = ScoringRule(type='linear', rules=[
            {'condition': '>', 'value': 0.5, 'score': 80},
        ])
        assert rule.calculate(0.6) == 80.0

    def test_threshold_type_with_rules(self):
        rule = ScoringRule(type='threshold', rules=[
            {'condition': '>=', 'value': 0.5, 'score': 100},
            {'condition': '<', 'value': 0.5, 'score': 0},
        ])
        assert rule.calculate(0.7) == 100.0
        assert rule.calculate(0.3) == 0.0
