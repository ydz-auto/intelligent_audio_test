# -*- coding: utf-8 -*-
"""API 参数解析优先级单测：实例覆盖 > 策略 > 空（显式 WARN）。

语义（docs/spec/api_param_profile/spec.md）：
1. API 参数与 ``source='api'`` 映射的作用域 = ``api_id``；
2. ``param_profiles`` 是可复用**策略**，``api_param_bindings`` 给出
   ``api_id → profile_id``，``api_params`` 行是实例**覆盖**；
3. 解析优先级：实例覆盖（同键替换策略行）> 策略（未覆盖键回落）> 空（WARN）；
4. 算法类型级默认层（``api_id IS NULL``）已废弃，不传 ``api_id`` 返回空。

全部用例用 ``object.__new__(AlgorithmConfigCache)`` 直接安装快照，不连库。
"""
import os

import pytest

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from algorithm_service.infrastructure.persistence import config_cache as cc  # noqa: E402
from algorithm_service.infrastructure.persistence.config_cache import (  # noqa: E402
    AlgorithmConfigCache,
)

ALGO = 'translation'
PROFILE = 7
API_A = 201
API_B = 202
UNBOUND_API = 999
EMPTY_PROFILE_API = 203
EMPTY_PROFILE = 8
DIM_TEXT = 101
DIM_DURATION = 102

# 策略层：同一属性可被多个 API 绑定（direction, code）为参数合并唯一键
PROFILE_PARAMS = [
    {'id': 1, 'algorithm_type': ALGO, 'api_id': None, 'param_code': 'asr_text',
     'param_name': '策略识别文本', 'param_type': 'text', 'direction': 'output',
     'ui_order': 1},
    {'id': 2, 'algorithm_type': ALGO, 'api_id': None, 'param_code': 'vendor_conf',
     'param_name': '策略置信度', 'param_type': 'json', 'direction': 'output',
     'ui_order': 2},
]

# 实例覆盖层：A 覆盖 vendor_conf + 独有 extra_flag；B 只覆盖 asr_text
OVERRIDE_PARAMS = [
    {'id': 11, 'algorithm_type': ALGO, 'api_id': API_A, 'param_code': 'vendor_conf',
     'param_name': 'A家置信度', 'param_type': 'number', 'direction': 'output',
     'ui_order': 2},
    {'id': 12, 'algorithm_type': ALGO, 'api_id': API_A, 'param_code': 'extra_flag',
     'param_name': 'A家开关', 'param_type': 'text', 'direction': 'output',
     'ui_order': 3},
    {'id': 13, 'algorithm_type': ALGO, 'api_id': API_B, 'param_code': 'asr_text',
     'param_name': 'B家识别文本', 'param_type': 'text', 'direction': 'output',
     'ui_order': 1},
]

# 策略映射：非维度级 2 行 + 维度级 2 行（后者归入 evaluation 桶）
PROFILE_MAPPINGS = [
    {'algorithm_type': ALGO, 'source': 'api', 'source_direction': 'output',
     'source_param': 'asr_text', 'target_param': 'asr', 'dimension_id': None},
    {'algorithm_type': ALGO, 'source': 'api', 'source_direction': 'output',
     'source_param': 'vendor_conf', 'target_param': 'confidence',
     'dimension_id': None},
    {'algorithm_type': ALGO, 'source': 'api', 'source_direction': 'output',
     'source_param': 'asr_text', 'target_param': 'transcript',
     'dimension_id': DIM_TEXT, 'dimension_name': '文本'},
    {'algorithm_type': ALGO, 'source': 'api', 'source_direction': 'output',
     'source_param': 'vendor_conf', 'target_param': 'confidence_dim',
     'dimension_id': DIM_DURATION, 'dimension_name': '时长'},
]

# 实例覆盖映射：A 换 vendor_conf 的 target、换维度级 asr_text 的 target、追加独有键；
# B 只换非维度级 asr_text 的 target
OVERRIDE_MAPPINGS = [
    {'algorithm_type': ALGO, 'api_id': API_A, 'source': 'api',
     'source_direction': 'output', 'source_param': 'vendor_conf',
     'target_param': 'conf_201', 'dimension_id': None},
    {'algorithm_type': ALGO, 'api_id': API_A, 'source': 'api',
     'source_direction': 'output', 'source_param': 'extra_flag',
     'target_param': 'flag', 'dimension_id': None},
    {'algorithm_type': ALGO, 'api_id': API_A, 'source': 'api',
     'source_direction': 'output', 'source_param': 'asr_text',
     'target_param': 'transcript_v2', 'dimension_id': DIM_TEXT,
     'dimension_name': '文本'},
    {'algorithm_type': ALGO, 'api_id': API_B, 'source': 'api',
     'source_direction': 'output', 'source_param': 'asr_text',
     'target_param': 'asr_202', 'dimension_id': None},
]


def _snapshot():
    return {
        'algorithms': {},
        'device_params': {ALGO: []},
        'api_params': {ALGO: AlgorithmConfigCache._serialize_params(OVERRIDE_PARAMS)},
        'profile_params': {PROFILE: AlgorithmConfigCache._serialize_params(PROFILE_PARAMS)},
        'profile_mappings': {
            PROFILE: AlgorithmConfigCache._serialize_mappings(
                PROFILE_MAPPINGS, None, ALGO),
        },
        'api_bindings': {API_A: PROFILE, API_B: PROFILE},
        'case_params': {ALGO: []},
        'reference_params': {ALGO: []},
        'mappings': {
            ALGO: AlgorithmConfigCache._serialize_mappings(
                OVERRIDE_MAPPINGS, None, ALGO),
        },
        'evaluation_dimension_params': {},
    }


def _bare_cache(snapshot=None):
    """绕过单例加载（不查库、不起 pubsub），直接安装快照。"""
    cache = object.__new__(AlgorithmConfigCache)
    cache._config_cache = snapshot if snapshot is not None else _snapshot()
    return cache


def _warnings(monkeypatch):
    captured = []

    def _fake_log(level, logger_name, message, **kwargs):
        captured.append((level, message))

    monkeypatch.setattr(cc, 'log_not_emit', _fake_log)
    return captured


def _by_code(rows):
    return {row['code']: row for row in rows}


# ========== 1. api_id 缺省：空声明 + WARN ==========

def test_api_id_none_returns_empty_with_warn(monkeypatch):
    warnings = _warnings(monkeypatch)
    cache = _bare_cache()

    assert cache.get_api_params(ALGO) == []
    assert warnings and warnings[0][0] == 'WARN'
    assert ALGO in warnings[0][1]


# ========== 2. 仅策略：返回策略行，api_id 为 None ==========

def test_profile_only_rows_keep_api_id_none():
    snapshot = _snapshot()
    snapshot['api_params'] = {ALGO: []}
    cache = _bare_cache(snapshot)

    rows = _by_code(cache.get_api_params(ALGO, API_A))
    assert set(rows) == {'asr_text', 'vendor_conf'}
    assert all(row['api_id'] is None for row in rows.values())


# ========== 3. 覆盖优先：同键替换且只保留一行 ==========

def test_override_replaces_same_key_without_duplicates():
    cache = _bare_cache()
    rows = cache.get_api_params(ALGO, API_A)
    by_code = _by_code(rows)

    assert by_code['vendor_conf']['api_id'] == API_A
    assert by_code['vendor_conf']['name'] == 'A家置信度'
    assert [r['code'] for r in rows].count('vendor_conf') == 1


# ========== 4. 覆盖独有键追加、未覆盖键回落策略 ==========

def test_override_only_key_appended_and_profile_falls_back():
    cache = _bare_cache()
    by_code = _by_code(cache.get_api_params(ALGO, API_A))

    assert by_code['extra_flag']['api_id'] == API_A
    assert by_code['extra_flag']['name'] == 'A家开关'
    assert by_code['asr_text']['api_id'] is None
    assert by_code['asr_text']['name'] == '策略识别文本'


# ========== 5. 两个 API 绑定同一策略但覆盖不同，互不串味 ==========

def test_two_apis_sharing_profile_do_not_leak():
    cache = _bare_cache()
    a_rows = _by_code(cache.get_api_params(ALGO, API_A))
    b_rows = _by_code(cache.get_api_params(ALGO, API_B))

    assert a_rows['vendor_conf']['api_id'] == API_A
    assert 'extra_flag' in a_rows
    assert a_rows['asr_text']['api_id'] is None  # A 未覆盖 asr_text

    assert b_rows['asr_text']['api_id'] == API_B
    assert 'extra_flag' not in b_rows
    assert b_rows['vendor_conf']['api_id'] is None  # B 回落策略


# ========== 6. 空声明告警（已绑定空策略 / 未绑定 api_id） ==========

def test_empty_declaration_warns_with_api_id(monkeypatch):
    warnings = _warnings(monkeypatch)
    snapshot = _snapshot()
    snapshot['api_bindings'] = {
        API_A: PROFILE, API_B: PROFILE, EMPTY_PROFILE_API: EMPTY_PROFILE,
    }
    cache = _bare_cache(snapshot)

    assert cache.get_api_params(ALGO, EMPTY_PROFILE_API) == []
    assert cache.get_api_params(ALGO, UNBOUND_API) == []

    bound = [message for level, message in warnings
             if level == 'WARN' and f'api_id={EMPTY_PROFILE_API}' in message]
    unbound = [message for level, message in warnings
               if level == 'WARN' and f'api_id={UNBOUND_API}' in message]
    assert bound and '空声明' in bound[0]
    assert unbound and '空声明' in unbound[0]


# ========== 7. 映射侧：策略 + 覆盖同键去重，跨桶汇总 ==========

def test_mapping_side_merges_and_deduplicates():
    cache = _bare_cache()

    evaluation = cache.get_param_mapping(ALGO, 'evaluation', API_A)
    by_key = {(m['source_param'], m['dimension_id']): m for m in evaluation}

    # 同键（source, source_param, dimension_id）被实例行替换，且只保留一行
    assert by_key[('asr_text', DIM_TEXT)]['target_param'] == 'transcript_v2'
    assert by_key[('asr_text', DIM_TEXT)]['api_id'] == API_A
    assert len([
        m for m in evaluation
        if m['source_param'] == 'asr_text' and m['dimension_id'] == DIM_TEXT
    ]) == 1

    # 策略行与覆盖行同时存在
    assert by_key[('vendor_conf', DIM_DURATION)]['target_param'] == 'confidence_dim'
    assert by_key[('vendor_conf', DIM_DURATION)]['api_id'] is None
    assert by_key[('vendor_conf', None)]['target_param'] == 'conf_201'
    assert by_key[('vendor_conf', None)]['api_id'] == API_A

    # 跨桶汇总：该 API 的全部 source='api' 行（策略 + 覆盖、跨 evaluation 桶）
    rows = cache.get_source_mappings(ALGO, 'api', API_A)
    assert {(m['source_param'], m['target_param']) for m in rows} == {
        ('asr_text', 'asr'),
        ('vendor_conf', 'conf_201'),
        ('extra_flag', 'flag'),
        ('asr_text', 'transcript_v2'),
        ('vendor_conf', 'confidence_dim'),
    }
    assert all(m['source'] == 'api' for m in rows)
