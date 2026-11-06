# -*- coding: utf-8 -*-
"""INT-1398 单元测试：评估维度 default_value 写侧 truthiness 缺口。

缺陷：_save_output_params / _save_input_params 旧代码 `json.dumps(x) if x else None`
把数值 0 / 布尔 false（falsy）静默落成 NULL。修复后写侧统一走
_serialize_default_value：
- None → NULL（保持原语义）
- 数值 0 / 布尔 false → '0' / 'false'（不再被 falsy 吞掉）
- JSON 字符串兜底解析（'0' → 0 再 dumps 成 '0'，与读侧 parse_json_or_raw 口径闭合）
- 非 JSON 纯文本 → 原样 JSON 序列化（'"zh"'，读回 'zh' 不变）

读侧（algorithm_service _po_to_dict → parse_json_or_raw）不受本卡改动影响，
此处以同语义的宽松解析断言落库文本的往返闭合。
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from evaluation_service.application.commands._dimension_params_mixin import (
    _serialize_default_value,
    DimensionParamsMixin,
)


def _read_side_parse(value):
    """镜像读侧 parse_json_or_raw 宽松语义：空→None；合法 JSON→对象；失败→原串。"""
    if not value:
        return None
    try:
        return json.loads(value)
    except (ValueError, TypeError):
        return value


# ==================== 1. 写侧序列化函数 ====================

class TestSerializeDefaultValue:
    def test_none_to_null(self):
        assert _serialize_default_value(None) is None

    def test_numeric_zero_preserved(self):
        assert _serialize_default_value(0) == '0'

    def test_float_preserved(self):
        assert _serialize_default_value(0.5) == '0.5'

    def test_boolean_false_preserved(self):
        assert _serialize_default_value(False) == 'false'

    def test_boolean_true_preserved(self):
        assert _serialize_default_value(True) == 'true'

    def test_json_string_normalized(self):
        # 旧客户端上送 JSON 字符串：'0' → 原生 0 → '0'，读回 int 0，不落成 '"0"'
        assert _serialize_default_value('0') == '0'
        assert _serialize_default_value('0.5') == '0.5'
        assert _serialize_default_value('false') == 'false'
        assert _serialize_default_value('true') == 'true'

    def test_plain_text_quoted(self):
        # 非 JSON 纯文本：读回原文不变
        assert _serialize_default_value('zh') == '"zh"'

    def test_object_round_trip(self):
        assert _serialize_default_value({'k': 1}) == '{"k": 1}'
        assert _serialize_default_value([1, 2]) == '[1, 2]'


class TestSerializeRoundTrip:
    """写侧落库文本 → 读侧 parse_json_or_raw 往返闭合。"""

    def test_zero_round_trip(self):
        stored = _serialize_default_value(0)
        assert _read_side_parse(stored) == 0

    def test_false_round_trip(self):
        stored = _serialize_default_value(False)
        assert _read_side_parse(stored) is False

    def test_float_round_trip(self):
        stored = _serialize_default_value(0.5)
        assert _read_side_parse(stored) == 0.5

    def test_json_string_zero_round_trip(self):
        stored = _serialize_default_value('0')
        assert _read_side_parse(stored) == 0

    def test_plain_text_round_trip(self):
        stored = _serialize_default_value('zh')
        assert _read_side_parse(stored) == 'zh'

    def test_none_round_trip(self):
        stored = _serialize_default_value(None)
        assert _read_side_parse(stored) is None


# ==================== 2. Mixin 写路径（fake repo 捕获入参） ====================

class _FakeRepo:
    def __init__(self):
        self.calls = []

    def add_dimension_param(self, data):
        self.calls.append(data)
        return 1


def _make_mixin():
    mixin = DimensionParamsMixin()
    mixin.repo = _FakeRepo()
    return mixin


class TestSaveInputParams:
    def test_zero_default_preserved(self):
        mixin = _make_mixin()
        mixin._save_input_params(1, [{'param_code': 'x', 'default_value': 0}])
        assert mixin.repo.calls[0]['default_value'] == '0'

    def test_false_default_preserved(self):
        mixin = _make_mixin()
        mixin._save_input_params(1, [{'param_code': 'x', 'default_value': False}])
        assert mixin.repo.calls[0]['default_value'] == 'false'

    def test_absent_default_is_null(self):
        mixin = _make_mixin()
        mixin._save_input_params(1, [{'param_code': 'x'}])
        assert mixin.repo.calls[0]['default_value'] is None

    def test_explicit_none_is_null(self):
        mixin = _make_mixin()
        mixin._save_input_params(1, [{'param_code': 'x', 'default_value': None}])
        assert mixin.repo.calls[0]['default_value'] is None


class TestSaveOutputParams:
    def test_zero_default_preserved(self):
        mixin = _make_mixin()
        mixin._save_output_params(1, [{'param_code': 'wer', 'field_type': 'number', 'default_value': 0}])
        assert mixin.repo.calls[0]['default_value'] == '0'

    def test_float_default_preserved(self):
        mixin = _make_mixin()
        mixin._save_output_params(1, [{'param_code': 'acc', 'field_type': 'number', 'default_value': 0.5}])
        assert mixin.repo.calls[0]['default_value'] == '0.5'

    def test_false_default_preserved(self):
        mixin = _make_mixin()
        mixin._save_output_params(1, [{'param_code': 'flag', 'field_type': 'boolean', 'default_value': False}])
        assert mixin.repo.calls[0]['default_value'] == 'false'

    def test_true_default_preserved(self):
        mixin = _make_mixin()
        mixin._save_output_params(1, [{'param_code': 'flag2', 'field_type': 'boolean', 'default_value': True}])
        assert mixin.repo.calls[0]['default_value'] == 'true'

    def test_absent_default_is_null(self):
        mixin = _make_mixin()
        mixin._save_output_params(1, [{'param_code': 'wer', 'field_type': 'number'}])
        assert mixin.repo.calls[0]['default_value'] is None

    def test_old_client_json_string_zero_normalized(self):
        mixin = _make_mixin()
        mixin._save_output_params(1, [{'param_code': 'wer', 'field_type': 'number', 'default_value': '0'}])
        assert mixin.repo.calls[0]['default_value'] == '0'
