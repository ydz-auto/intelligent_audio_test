# -*- coding: utf-8 -*-
"""INT-222 后端测试：算法参数 default_value 非 JSON 文本读回原文（宽松读语义）。

历史缺陷：default_value 存非 JSON 文本（如 'zh'）时写路径正常落库，但读路径
（PO.to_dict / converter）json.loads 解析失败静默返 None → GET definitions 回读
空，重开算法配置模态窗默认值丢失。

修复后五处读点统一宽松语义（共享 helper parse_json_or_raw，四类 PO 的
_parse_json 私有副本与 converter 的 _parse_json_value 全部收敛）：
- 空值（None / ''）→ None
- 合法 JSON 形态（'{"k":1}' / '[1,2]' / '42'）→ 解析后对象（回归不破坏）
- 解析失败（'zh' / 截断 JSON）→ 原始字符串
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from algorithm_service.infrastructure.persistence.models.algorithm_models import (
    AlgorithmApiParam,
    AlgorithmDeviceParam,
    CaseAlgorithmParam,
    EvaluationDimensionParam,
    parse_json_or_raw,
)
from algorithm_service.infrastructure.persistence._algorithm_converters import (
    _param_po_to_entity,
)
from algorithm_service.infrastructure.persistence._param_converters import _po_to_dict


# ==================== 1. 共享 helper 语义 ====================

def test_parse_json_or_raw_semantics():
    """空值返 None；合法 JSON 解析为对象；解析失败（纯文本/截断）返原串。"""
    assert parse_json_or_raw('zh') == 'zh'
    assert parse_json_or_raw('{"k":1}') == {'k': 1}
    assert parse_json_or_raw('[1,2]') == [1, 2]
    assert parse_json_or_raw('42') == 42
    assert parse_json_or_raw('true') is True
    assert parse_json_or_raw('null') is None
    assert parse_json_or_raw(None) is None
    assert parse_json_or_raw('') is None
    assert parse_json_or_raw('{"k":') == '{"k":'
    assert parse_json_or_raw(' ') == ' '


# ==================== 2. 四类 PO.to_dict ====================

def test_case_param_default_value_non_json_text_read_back():
    """用例参数 default_value='zh' 读回 'zh'（重开模态窗不再丢默认值）。"""
    po = CaseAlgorithmParam(id=1, algorithm_type='voice_llm', param_code='lang',
                            param_type='text', default_value='zh')
    assert po.to_dict()['default_value'] == 'zh'


def test_case_param_default_value_json_form_still_parsed():
    po = CaseAlgorithmParam(id=1, algorithm_type='voice_llm', param_code='cfg',
                            param_type='json', default_value='{"k":1}')
    assert po.to_dict()['default_value'] == {'k': 1}


def test_case_param_default_value_empty_stays_none():
    po = CaseAlgorithmParam(id=1, algorithm_type='voice_llm', param_code='lang',
                            param_type='text', default_value=None)
    po_empty = CaseAlgorithmParam(id=2, algorithm_type='voice_llm', param_code='lang',
                                  param_type='text', default_value='')
    assert po.to_dict()['default_value'] is None
    assert po_empty.to_dict()['default_value'] is None


def test_device_param_default_value_and_validation_read_back():
    """设备参数 default_value 与 validation（同 helper）统一宽松保真。"""
    po = AlgorithmDeviceParam(id=1, algorithm_type='voice_llm', param_code='lang',
                              param_type='text', default_value='zh',
                              validation_rules='zh')
    d = po.to_dict()
    assert d['default_value'] == 'zh'
    assert d['validation'] == 'zh'


def test_device_param_default_value_json_form_still_parsed():
    po = AlgorithmDeviceParam(id=1, algorithm_type='voice_llm', param_code='vol',
                              param_type='text', default_value='[1,2]')
    assert po.to_dict()['default_value'] == [1, 2]


def test_api_param_default_value_non_json_text_read_back():
    po = AlgorithmApiParam(id=1, algorithm_type='voice_llm', param_code='lang',
                           param_type='text', default_value='zh')
    assert po.to_dict()['default_value'] == 'zh'


def test_dimension_param_default_value_non_json_text_read_back():
    po = EvaluationDimensionParam(id=1, dimension_id=1, param_code='lang',
                                  field_type='text', param_direction='input',
                                  default_value='zh')
    assert po.to_dict()['default_value'] == 'zh'


# ==================== 3. gRPC 读链 ACL 序列化 ====================

def test_param_converters_po_to_dict_passes_through_lenient_value():
    """gRPC 读路径经 _param_converters._po_to_dict → PO.to_dict，宽松值透传。"""
    po = CaseAlgorithmParam(id=1, algorithm_type='voice_llm', param_code='lang',
                            param_type='text', default_value='zh')
    assert _po_to_dict(po)['default_value'] == 'zh'


# ==================== 4. converter（device/api PO → Entity）====================

def test_converter_device_param_default_value_non_json_text():
    po = AlgorithmDeviceParam(id=7, algorithm_type='voice_llm', param_code='lang',
                              param_type='text', default_value='zh')
    entity = _param_po_to_entity(po, definition_id=9)
    assert entity.default_value == 'zh'
    assert entity.param_kind == 'device'


def test_converter_api_param_default_value_non_json_text():
    po = AlgorithmApiParam(id=8, algorithm_type='voice_llm', param_code='lang',
                           param_type='text', default_value='zh')
    entity = _param_po_to_entity(po, definition_id=9)
    assert entity.default_value == 'zh'
    assert entity.param_kind == 'api'


def test_converter_default_value_json_and_empty_unchanged():
    device_po = AlgorithmDeviceParam(id=7, algorithm_type='voice_llm', param_code='cfg',
                                     param_type='json', default_value='{"k":1}')
    api_po = AlgorithmApiParam(id=8, algorithm_type='voice_llm', param_code='cfg',
                               param_type='json', default_value=None)
    assert _param_po_to_entity(device_po).default_value == {'k': 1}
    assert _param_po_to_entity(api_po).default_value is None
