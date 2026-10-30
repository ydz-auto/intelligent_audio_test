# -*- coding: utf-8 -*-
"""INT-1756/INT-2xxx api_id 作用域：策略 + 实例覆盖解析单测（本轮语义）。

设计变更（docs/spec/api_param_profile/spec.md）：
1. API 参数与 ``source='api'`` 映射的作用域 = ``api_id``；算法类型级默认层
   （``api_id IS NULL``）已废弃，迁移后软删；
2. ``api_params`` 行 = 实例**覆盖**，``param_profiles`` = 可复用**策略**，
   ``api_param_bindings`` = ``api_id → profile_id``；
3. 解析优先级：**实例覆盖 > 策略 > 空**；空声明必须显式告警；
4. 不传 ``api_id`` 一律返回空（调用方必须带作用域）。
"""
import os

import pytest

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from algorithm_service.application.queries import field_mapping_queries  # noqa: E402
from algorithm_service.application.queries.field_mapping_queries import (  # noqa: E402
    FieldMappingQueryHandler,
)
from algorithm_service.infrastructure.persistence import config_cache as cc  # noqa: E402
from algorithm_service.infrastructure.persistence.config_cache import (  # noqa: E402
    AlgorithmConfigCache,
)
from algorithm_service.interfaces.grpc.algorithm_query_servicer import (  # noqa: E402
    _optional_api_id,
)
from shared.proto import algorithm_service_pb2 as pb  # noqa: E402

ALGO = 'translation'
PROFILE = 7
API_A = 11
API_B = 12
DIM_TEXT = 101
DIM_DURATION = 102

# 策略层（同一算法类型可被多个 API 引用）
RAW_PROFILE_PARAMS = [
    {'id': 1, 'algorithm_type': ALGO, 'api_id': None, 'param_code': 'lang',
     'param_name': '策略语言', 'param_type': 'text', 'direction': 'input',
     'ui_order': 1},
    {'id': 2, 'algorithm_type': ALGO, 'api_id': None, 'param_code': 'answer',
     'param_name': '策略答案', 'param_type': 'text', 'direction': 'output',
     'ui_order': 2},
    {'id': 3, 'algorithm_type': ALGO, 'api_id': None, 'param_code': 'duration',
     'param_name': '策略时长', 'param_type': 'text', 'direction': 'output',
     'ui_order': 3},
]

# 实例覆盖层：A 家覆盖 lang + 独有 app_key；B 家只覆盖 lang
RAW_OVERRIDE_PARAMS = [
    {'id': 4, 'algorithm_type': ALGO, 'api_id': API_A, 'param_code': 'lang',
     'param_name': 'A家语言', 'param_type': 'text', 'direction': 'input',
     'ui_order': 1},
    {'id': 5, 'algorithm_type': ALGO, 'api_id': API_A, 'param_code': 'app_key',
     'param_name': 'A家密钥', 'param_type': 'text', 'direction': 'input',
     'ui_order': 4},
    {'id': 6, 'algorithm_type': ALGO, 'api_id': API_B, 'param_code': 'lang',
     'param_name': 'B家语言', 'param_type': 'text', 'direction': 'input',
     'ui_order': 1},
]

RAW_PROFILE_MAPPINGS = [
    {'id': 1, 'algorithm_type': ALGO, 'source': 'api', 'source_param': 'answer',
     'target_param': 'text', 'dimension_id': DIM_TEXT, 'dimension_name': '文本'},
    {'id': 2, 'algorithm_type': ALGO, 'source': 'api', 'source_param': 'duration',
     'target_param': 'seconds', 'dimension_id': DIM_DURATION, 'dimension_name': '时长'},
    {'id': 3, 'algorithm_type': ALGO, 'source': 'api', 'source_param': 'lang',
     'target_param': 'lang_code', 'dimension_id': None},
]

RAW_OVERRIDE_MAPPINGS = [
    {'id': 4, 'algorithm_type': ALGO, 'api_id': API_A, 'source': 'api',
     'source_param': 'answer', 'target_param': 'transcript',
     'dimension_id': DIM_TEXT, 'dimension_name': '文本'},
    {'id': 5, 'algorithm_type': ALGO, 'api_id': API_A, 'source': 'api',
     'source_param': 'app_key', 'target_param': 'ak', 'dimension_id': None},
    {'id': 6, 'algorithm_type': ALGO, 'api_id': API_B, 'source': 'api',
     'source_param': 'lang', 'target_param': 'lang_v2', 'dimension_id': None},
]


def _bare_cache(snapshot=None):
    cache = object.__new__(AlgorithmConfigCache)
    cache._config_cache = snapshot if snapshot is not None else _snapshot()
    return cache


def _snapshot():
    return {
        'algorithms': {ALGO: {'id': 1, 'type': ALGO, 'name': '翻译',
                              'status': 'online'}},
        'device_params': {ALGO: AlgorithmConfigCache._serialize_params([
            {'id': 99, 'algorithm_type': ALGO, 'param_code': 'sample_rate',
             'param_name': '采样率', 'param_type': 'text', 'direction': 'input'},
        ])},
        'api_params': {ALGO: AlgorithmConfigCache._serialize_params(RAW_OVERRIDE_PARAMS)},
        'profile_params': {
            PROFILE: AlgorithmConfigCache._serialize_params(RAW_PROFILE_PARAMS)
        },
        'profile_mappings': {
            PROFILE: AlgorithmConfigCache._serialize_mappings(
                RAW_PROFILE_MAPPINGS, None, ALGO)
        },
        'api_bindings': {API_A: PROFILE, API_B: PROFILE},
        'case_params': {ALGO: []},
        'reference_params': {ALGO: []},
        'mappings': {
            ALGO: AlgorithmConfigCache._serialize_mappings(
                RAW_OVERRIDE_MAPPINGS, None, ALGO)
        },
        'evaluation_dimension_params': {DIM_TEXT: [], DIM_DURATION: []},
    }


def _by_code(rows):
    return {row['code']: row for row in rows}


# ========== 1. 不传 api_id：空声明 + 显式告警 ==========

def test_api_params_without_api_id_returns_empty(monkeypatch):
    warnings = []

    def _fake_log(level, logger_name, message, **kwargs):
        warnings.append((level, message))

    monkeypatch.setattr(cc, 'log_not_emit', _fake_log)
    cache = _bare_cache()

    assert cache.get_api_params(ALGO) == []
    assert warnings and warnings[0][0] == 'WARN'
    assert ALGO in warnings[0][1]


def test_api_params_unbound_api_id_returns_empty(monkeypatch):
    warnings = []
    monkeypatch.setattr(
        cc, 'log_not_emit',
        lambda level, name, message, **kw: warnings.append((level, message)))
    cache = _bare_cache()

    assert cache.get_api_params(ALGO, 999) == []
    assert any('api_id=999' in message for _, message in warnings)


# ========== 2. 策略 + 实例覆盖：覆盖 > 策略，未覆盖回落策略 ==========

def test_api_params_profile_only():
    snapshot = _snapshot()
    snapshot['api_params'] = {ALGO: []}
    cache = _bare_cache(snapshot)

    rows = _by_code(cache.get_api_params(ALGO, API_A))
    assert set(rows) == {'lang', 'answer', 'duration'}
    assert rows['lang']['name'] == '策略语言'


def test_api_params_override_wins_and_falls_back_to_profile():
    cache = _bare_cache()
    rows = _by_code(cache.get_api_params(ALGO, API_A))

    # 同键（direction, code）覆盖为实例行
    assert rows['lang']['name'] == 'A家语言'
    assert rows['lang']['api_id'] == API_A
    # 未覆盖键回落策略
    assert rows['answer']['name'] == '策略答案'
    assert rows['answer']['api_id'] is None
    assert rows['duration']['name'] == '策略时长'
    # 实例独有行追加
    assert rows['app_key']['api_id'] == API_A
    # 覆盖后同键只有一行
    assert [r['code'] for r in cache.get_api_params(ALGO, API_A)].count('lang') == 1


def test_api_params_do_not_leak_across_apis():
    cache = _bare_cache()
    b_rows = _by_code(cache.get_api_params(ALGO, API_B))
    assert b_rows['lang']['name'] == 'B家语言'
    assert 'app_key' not in b_rows

    a_rows = _by_code(cache.get_api_params(ALGO, API_A))
    assert a_rows['lang']['name'] == 'A家语言'


# ========== 3. 映射：策略 + 覆盖，跨桶取输出映射 ==========

def test_evaluation_mapping_merges_profile_and_override():
    cache = _bare_cache()
    evaluation = cache.get_param_mapping(ALGO, 'evaluation', API_A)
    by_source_param = {m['source_param']: m for m in evaluation}

    assert by_source_param['answer']['target_param'] == 'transcript'
    assert by_source_param['answer']['api_id'] == API_A
    assert by_source_param['duration']['target_param'] == 'seconds'
    assert by_source_param['duration']['api_id'] is None
    # 合并后同键只有一行（去重发生在合并之后）
    assert len([m for m in evaluation if m['source_param'] == 'answer']) == 1


def test_non_evaluation_bucket_keeps_profile_and_override_rows():
    cache = _bare_cache()
    a_targets = {m['source_param']: m['target_param']
                 for m in cache.get_param_mapping(ALGO, 'api', API_A)}
    assert a_targets == {'lang': 'lang_code', 'app_key': 'ak'}

    b_targets = {m['source_param']: m['target_param']
                 for m in cache.get_param_mapping(ALGO, 'api', API_B)}
    assert b_targets == {'lang': 'lang_v2'}


def test_get_source_mappings_spans_all_buckets():
    cache = _bare_cache()
    rows = cache.get_source_mappings(ALGO, 'api', API_A)
    assert {(m['source_param'], m['target_param']) for m in rows} == {
        ('answer', 'transcript'), ('duration', 'seconds'),
        ('lang', 'lang_code'), ('app_key', 'ak'),
    }
    assert all(m['source'] == 'api' for m in rows)


# ========== 4. 字段定义合并入口 ==========

def test_field_definitions_merges_api_scope(monkeypatch):
    cache = _bare_cache()
    monkeypatch.setattr(field_mapping_queries, 'get_config_cache', lambda: cache)

    scoped = FieldMappingQueryHandler.get_field_definitions(ALGO, API_A)
    assert set(scoped['original']['api']['input']) == {'lang', 'app_key'}
    assert scoped['original']['api']['input']['lang']['name'] == 'A家语言'
    assert set(scoped['original']['api']['output']) == {'answer', 'duration'}
    assert set(scoped['mapped']['evaluation']) == {'transcript', 'seconds'}


# ========== 5. proto / servicer 透传 ==========

def test_optional_api_id_presence_semantics():
    assert _optional_api_id(pb.GetFullFieldMappingRequest(
        algorithm_type=ALGO)) is None
    assert _optional_api_id(pb.GetFullFieldMappingRequest(
        algorithm_type=ALGO, api_id=API_A)) == API_A
    # proto3 optional presence：显式 0 与未传可区分
    assert _optional_api_id(pb.GetFullFieldMappingRequest(
        algorithm_type=ALGO, api_id=0)) == 0
    assert _optional_api_id(pb.GetApiParamsListRequest(
        algorithm_type=ALGO, api_id=API_B)) == API_B
    assert _optional_api_id(pb.GetFieldMappingsRequest(
        algorithm_type=ALGO)) is None
