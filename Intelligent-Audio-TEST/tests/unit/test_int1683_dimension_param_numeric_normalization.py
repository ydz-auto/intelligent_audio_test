# -*- coding: utf-8 -*-
"""INT-1683 回归：评估维度参数数值/布尔字段空串不得静默丢参数。

缺陷：POST /api/v1/evaluation/dimensions 的 output_fields.pass_threshold 传 ""
时，algorithm_service 把 "" 直接交给 double precision 列，数据库解析失败 →
CreateDimensionParam 返回失败 → 整条参数被丢弃，而上层仍回 201。

修复口径（期望 1，优先归一）：写侧把空串归一为 NULL，与前端
``toNullableNumber('') → null`` 一致；覆盖 evaluation_dimension_params
全部非文本列（int / float / bool），不只是 pass_threshold；非法非空值抛
ValueError，让 RPC 明确失败而不是写坏数据。
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from algorithm_service.interfaces.grpc.mixins import dimension_mixin
from algorithm_service.interfaces.grpc.mixins.dimension_mixin import _DimensionMixin
from algorithm_service.interfaces.grpc.mixins.param_helpers import (
    _normalize_dimension_param_data,
)


class _FakeRequest:
    def __init__(self, data):
        self.data = json.dumps(data)


class _FakeRepo:
    def __init__(self):
        self.created = []

    def create(self, data):
        self.created.append(data)
        return {'id': 100 + len(self.created)}


class _MixinForTest(_DimensionMixin):
    @staticmethod
    def _invalidate_cache(**_kwargs):
        # INT-1666 起 dimension_mixin 按受影响范围失效（algorithm_types / dimension_ids），
        # 夹具按缺省全量失效语义吞掉参数即可。
        return None


def _call_create(data, monkeypatch):
    repo = _FakeRepo()
    monkeypatch.setattr(dimension_mixin, '_loads', lambda raw, default=None: json.loads(raw))
    import algorithm_service.infrastructure.persistence.algorithm_repository as repo_module
    monkeypatch.setattr(repo_module, 'dimension_param_repository', repo)
    resp = _MixinForTest().CreateDimensionParam(_FakeRequest(data))
    return resp, repo


# ==================== 1. 归一函数 ====================

class TestNormalizeDimensionParamData:
    def test_empty_pass_threshold_to_null(self):
        out = _normalize_dimension_param_data({'pass_threshold': ''})
        assert out['pass_threshold'] is None

    def test_empty_ui_order_to_null(self):
        assert _normalize_dimension_param_data({'ui_order': ''})['ui_order'] is None

    def test_empty_bool_fields_to_null(self):
        out = _normalize_dimension_param_data({'required': '', 'visible_in_report': ' '})
        assert out['required'] is None
        assert out['visible_in_report'] is None

    def test_numeric_strings_parsed(self):
        out = _normalize_dimension_param_data({
            'pass_threshold': '0.1', 'ui_order': '3',
            'required': 'false', 'visible_in_report': 'true',
        })
        assert out['pass_threshold'] == 0.1
        assert out['ui_order'] == 3
        assert out['required'] is False
        assert out['visible_in_report'] is True

    def test_integral_float_ui_order_accepted(self):
        assert _normalize_dimension_param_data({'ui_order': 3.0})['ui_order'] == 3
        assert _normalize_dimension_param_data({'ui_order': '3.0'})['ui_order'] == 3

    def test_fractional_ui_order_rejected(self):
        import pytest
        with pytest.raises(ValueError):
            _normalize_dimension_param_data({'ui_order': 3.7})

    def test_native_values_untouched(self):
        out = _normalize_dimension_param_data({
            'pass_threshold': 0.0, 'ui_order': 0, 'required': False,
        })
        assert out['pass_threshold'] == 0.0
        assert out['ui_order'] == 0
        assert out['required'] is False

    def test_none_stays_none(self):
        out = _normalize_dimension_param_data({'pass_threshold': None})
        assert out['pass_threshold'] is None

    def test_text_fields_not_touched(self):
        out = _normalize_dimension_param_data({
            'param_code': '', 'field_path': 'wer', 'agg_role': '',
        })
        assert out['param_code'] == ''
        assert out['field_path'] == 'wer'
        assert out['agg_role'] == ''

    def test_invalid_number_raises(self):
        import pytest
        with pytest.raises(ValueError):
            _normalize_dimension_param_data({'pass_threshold': 'abc'})
        with pytest.raises(ValueError):
            _normalize_dimension_param_data({'ui_order': '1.2.3'})

    def test_input_dict_not_mutated(self):
        src = {'pass_threshold': ''}
        _normalize_dimension_param_data(src)
        assert src['pass_threshold'] == ''


# ==================== 2. CreateDimensionParam 写路径 ====================

class TestCreateDimensionParamNormalization:
    def test_empty_threshold_param_still_created_with_null(self, monkeypatch):
        payload = {
            'dimension_id': 10, 'param_code': 'wer', 'param_direction': 'output',
            'field_type': 'number', 'agg_role': 'pass_le', 'pass_threshold': '',
            'ui_order': 0,
        }
        resp, repo = _call_create(payload, monkeypatch)
        assert resp.success is True
        # 参数没有被丢弃，空串落成 NULL
        assert len(repo.created) == 1
        assert repo.created[0]['param_code'] == 'wer'
        assert repo.created[0]['pass_threshold'] is None

    def test_empty_ui_order_param_still_created(self, monkeypatch):
        payload = {
            'dimension_id': 10, 'param_code': 'acc', 'param_direction': 'output',
            'ui_order': '',
        }
        resp, repo = _call_create(payload, monkeypatch)
        assert resp.success is True
        assert repo.created[0]['ui_order'] is None

    def test_valid_threshold_kept(self, monkeypatch):
        payload = {
            'dimension_id': 10, 'param_code': 'wer', 'param_direction': 'output',
            'pass_threshold': 0.1,
        }
        resp, repo = _call_create(payload, monkeypatch)
        assert resp.success is True
        assert repo.created[0]['pass_threshold'] == 0.1

    def test_invalid_threshold_fails_instead_of_writing(self, monkeypatch):
        payload = {
            'dimension_id': 10, 'param_code': 'wer', 'param_direction': 'output',
            'pass_threshold': 'abc',
        }
        resp, repo = _call_create(payload, monkeypatch)
        assert resp.success is False
        assert 'pass_threshold' in resp.message
        assert repo.created == []
