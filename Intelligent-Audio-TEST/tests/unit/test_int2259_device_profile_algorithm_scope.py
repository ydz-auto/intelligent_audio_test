# -*- coding: utf-8 -*-
"""INT-2259：设备绑定策略必须按其声明的 algorithm_type 生效。

``param_profiles`` 唯一键是 ``(scope, algorithm_type, name)``，策略自带算法类型；
``device_param_bindings`` 对 ``device_id`` 唯一，但一台设备可以跑多种算法。
修复前 ``get_device_params`` / 设备映射解析直接合并 ``profile_params[profile_id]``
全量行，设备 5 绑定算法 A 的策略后跑算法 B 时，同 ``(direction, code)`` 的
A 策略行会覆盖 B 的参数声明（名称 / param_type / required / default_value）。

解析用例用 ``object.__new__(AlgorithmConfigCache)`` 直接安装快照，不连库。
"""
import os

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from algorithm_service.infrastructure.persistence.config_cache import (  # noqa: E402
    AlgorithmConfigCache,
)

ALGO_A = 'ut_a_profile_algo'
ALGO_B = 'ut_b_profile_algo'
PROFILE_A = 71
DEVICE = 601

A_LEVEL_PARAMS = [
    {'param_code': 'audio_in', 'param_name': 'A算法级音频', 'param_type': 'text',
     'direction': 'input', 'ui_order': 1},
    {'param_code': 'a_only', 'param_name': 'A算法独有', 'param_type': 'text',
     'direction': 'output', 'ui_order': 2},
]

# 策略 A 声明与算法 B 同键（audio_in）+ 策略独有行
PROFILE_A_PARAMS = [
    {'param_code': 'audio_in', 'param_name': 'A策略音频',
     'param_type': 'audio_stream', 'direction': 'input', 'required': True,
     'default_value': 'policy_default', 'ui_order': 1},
    {'param_code': 'policy_a', 'param_name': 'A策略独有', 'param_type': 'text',
     'direction': 'input', 'ui_order': 2},
]

A_DEVICE_OVERRIDES = [
    {'param_code': 'audio_in', 'param_name': 'A设备音频',
     'param_type': 'audio_stream', 'direction': 'input', 'device_id': DEVICE,
     'ui_order': 1},
]

B_LEVEL_PARAMS = [
    {'param_code': 'audio_in', 'param_name': 'B算法级音频', 'param_type': 'text',
     'direction': 'input', 'ui_order': 1},
    {'param_code': 'b_only', 'param_name': 'B算法独有', 'param_type': 'text',
     'direction': 'output', 'ui_order': 2},
]

B_DEVICE_OVERRIDES = [
    {'param_code': 'b_only', 'param_name': 'B设备文本', 'param_type': 'text',
     'direction': 'output', 'device_id': DEVICE, 'ui_order': 2},
]

A_LEVEL_MAPPINGS = [
    {'algorithm_type': ALGO_A, 'source': 'case', 'source_direction': 'input',
     'source_param': 'asr_result', 'target_param': 'audio_in', 'dimension_id': None},
]

PROFILE_A_MAPPINGS = [
    {'algorithm_type': ALGO_A, 'source': 'case', 'source_direction': 'input',
     'source_param': 'asr_result', 'target_param': 'audio_in_policy',
     'dimension_id': None},
    {'algorithm_type': ALGO_A, 'source': 'case', 'source_direction': 'input',
     'source_param': 'policy_src', 'target_param': 'audio_in', 'dimension_id': None},
]

B_LEVEL_MAPPINGS = [
    {'algorithm_type': ALGO_B, 'source': 'case', 'source_direction': 'input',
     'source_param': 'asr_result', 'target_param': 'b_audio_in', 'dimension_id': None},
]


def _cache(with_profile_algorithm_types=True) -> AlgorithmConfigCache:
    cache = object.__new__(AlgorithmConfigCache)
    cache._config_cache = {
        'algorithms': {},
        'device_params': {
            ALGO_A: AlgorithmConfigCache._serialize_params(
                A_LEVEL_PARAMS + A_DEVICE_OVERRIDES),
            ALGO_B: AlgorithmConfigCache._serialize_params(
                B_LEVEL_PARAMS + B_DEVICE_OVERRIDES),
        },
        'api_params': {ALGO_A: [], ALGO_B: []},
        'case_params': {ALGO_A: [], ALGO_B: []},
        'reference_params': {ALGO_A: [], ALGO_B: []},
        'evaluation_dimension_params': {},
        'mappings': {
            ALGO_A: AlgorithmConfigCache._serialize_mappings(
                A_LEVEL_MAPPINGS, None, ALGO_A),
            ALGO_B: AlgorithmConfigCache._serialize_mappings(
                B_LEVEL_MAPPINGS, None, ALGO_B),
        },
        'profile_params': {
            PROFILE_A: AlgorithmConfigCache._serialize_params(PROFILE_A_PARAMS),
        },
        'profile_mappings': {
            PROFILE_A: AlgorithmConfigCache._serialize_mappings(
                PROFILE_A_MAPPINGS, None, ALGO_A),
        },
        'api_bindings': {},
        'device_bindings': {DEVICE: PROFILE_A},
    }
    if with_profile_algorithm_types:
        cache._config_cache['profile_algorithm_types'] = {PROFILE_A: ALGO_A}
    return cache


def _params_by_code(rows):
    return {row['code']: row for row in rows}


# ---------------------------------------------------------------- 参数解析

def test_device_params_bind_to_their_own_algorithm_type():
    """查询策略所属算法 A：策略层仍按 设备覆盖 > 策略 > 算法级 生效。"""
    by_code = _params_by_code(_cache().get_device_params(ALGO_A, DEVICE))
    assert set(by_code) == {'audio_in', 'a_only', 'policy_a'}
    assert by_code['audio_in']['name'] == 'A设备音频'   # 设备覆盖最优先
    assert by_code['policy_a']['name'] == 'A策略独有'   # 策略独有行保留


def test_device_params_do_not_leak_into_other_algorithm():
    """设备绑算法 A 的策略，跑算法 B 时 A 的策略行不得参与合并。"""
    by_code = _params_by_code(_cache().get_device_params(ALGO_B, DEVICE))
    # A 策略独有行不出现
    assert set(by_code) == {'audio_in', 'b_only'}
    # 同名 audio_in 保持 B 的算法级声明（名称 / 类型未被 A 策略换掉）
    assert by_code['audio_in']['name'] == 'B算法级音频'
    assert by_code['audio_in']['type'] == 'text'
    assert not by_code['audio_in']['required']
    assert by_code['audio_in']['default_value'] is None
    # B 自己的设备覆盖行照常生效
    assert by_code['b_only']['name'] == 'B设备文本'


def test_device_params_without_profile_algorithm_type_fail_closed():
    """旧快照缺 profile_id → algorithm_type 时按不匹配处理，不跨算法串参。"""
    cache = _cache(with_profile_algorithm_types=False)
    by_code = _params_by_code(cache.get_device_params(ALGO_B, DEVICE))
    assert set(by_code) == {'audio_in', 'b_only'}
    assert by_code['audio_in']['name'] == 'B算法级音频'
    # 策略被跳过时，本设备覆盖行仍按算法桶生效
    a_by_code = _params_by_code(cache.get_device_params(ALGO_A, DEVICE))
    assert a_by_code['audio_in']['name'] == 'A设备音频'
    assert 'policy_a' not in a_by_code


# ---------------------------------------------------------------- 映射解析

def _case_bucket(cache, algorithm_type):
    return {
        row['source_param']: row['target_param']
        for row in cache.get_param_mapping(
            algorithm_type, 'case', device_id=DEVICE)
        if row.get('source') == 'case'
    }


def test_device_mappings_bind_to_their_own_algorithm_type():
    assert _case_bucket(_cache(), ALGO_A) == {
        'asr_result': 'audio_in_policy',   # 策略覆盖同键算法级行
        'policy_src': 'audio_in',          # 策略独有行保留
    }


def test_device_mappings_do_not_leak_into_other_algorithm():
    assert _case_bucket(_cache(), ALGO_B) == {'asr_result': 'b_audio_in'}
