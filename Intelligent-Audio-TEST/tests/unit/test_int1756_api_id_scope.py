# -*- coding: utf-8 -*-
"""INT-1756（C6a）api_id 作用域：合并读取语义 + proto/DTO 透传单测。

父卡 INT-1751 第二~四节定稿口径（本文件逐条守住）：
1. 缓存分桶键不动，行携带 ``api_id``；读时按**唯一键**合并——
   ``param_mappings``: ``(source, source_param, dimension_id)``；
   ``algorithm_api_params``: ``(direction, param_code)``（``target_param`` 不是合并键）；
2. API 级行覆盖同键算法级行，未覆盖的算法级行继续生效（合并而非二选一）；
3. 不传 ``api_id`` 只返回算法级行（存量行全部 ``api_id IS NULL``，与改动前一致）；
4. ``_get_evaluation_mappings`` 的四元组去重必须发生在合并**之后**；
5. 三个 RPC 的 ``optional int32 api_id`` 走 presence：不传=None（回落算法级），
   显式传值（含 0）原样透传。
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
from algorithm_service.infrastructure.persistence.config_cache import (  # noqa: E402
    AlgorithmConfigCache,
)
from algorithm_service.interfaces.grpc.algorithm_query_servicer import (  # noqa: E402
    AlgorithmQueryServicer,
    _optional_api_id,
)
from shared.proto import algorithm_service_pb2 as pb  # noqa: E402

ALGO = 'translation'
API_A = 11
API_B = 12
DIM_TEXT = 101
DIM_DURATION = 102

# 改动前的序列化键（用于回归比对：唯一允许的增量是 api_id）
OLD_PARAM_KEYS = {
    'id', 'algorithm_type', 'code', 'name', 'label', 'type', 'direction',
    'required', 'default_value', 'validation_rules', 'help_text', 'ui_order',
    'ui_group', 'hidden', 'param_type',
}
OLD_MAPPING_KEYS = {
    'source', 'source_param', 'source_direction', 'dimension_id',
    'dimension_name', 'target_param', 'transform_type',
}
# _get_evaluation_mappings 归一化后的键（direction 固定 output，无 source_direction）
OLD_EVAL_MAPPING_KEYS = {
    'source', 'source_param', 'target_param', 'direction', 'dimension_id',
    'dimension_name', 'transform_type',
}

# 算法级 lang/answer/duration + A 家覆盖 lang、独有 app_key + B 家覆盖 lang
RAW_API_PARAMS = [
    {'id': 1, 'algorithm_type': ALGO, 'api_id': None, 'param_code': 'lang',
     'param_name': '算法级语言', 'param_type': 'text', 'direction': 'input',
     'ui_order': 1},
    {'id': 2, 'algorithm_type': ALGO, 'api_id': None, 'param_code': 'answer',
     'param_name': '算法级答案', 'param_type': 'text', 'direction': 'output',
     'ui_order': 2},
    {'id': 3, 'algorithm_type': ALGO, 'api_id': None, 'param_code': 'duration',
     'param_name': '算法级时长', 'param_type': 'text', 'direction': 'output',
     'ui_order': 3},
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

# 算法级三条映射 + A 家同键覆盖（target 不同）+ A 家独有 + B 家覆盖
RAW_MAPPINGS = [
    {'id': 1, 'algorithm_type': ALGO, 'source': 'api',
     'source_param': 'answer', 'target_param': 'text',
     'dimension_id': DIM_TEXT, 'dimension_name': '文本'},
    {'id': 2, 'algorithm_type': ALGO, 'source': 'api',
     'source_param': 'duration', 'target_param': 'seconds',
     'dimension_id': DIM_DURATION, 'dimension_name': '时长'},
    {'id': 3, 'algorithm_type': ALGO, 'source': 'api',
     'source_param': 'lang', 'target_param': 'lang_code', 'dimension_id': None},
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
    """用真实序列化函数构建快照（覆盖 _serialize_params / _serialize_mappings 的 api_id 键）。"""
    return {
        'algorithms': {ALGO: {'id': 1, 'type': ALGO, 'name': '翻译',
                              'status': 'online'}},
        'device_params': {ALGO: AlgorithmConfigCache._serialize_params([
            {'id': 99, 'algorithm_type': ALGO, 'param_code': 'sample_rate',
             'param_name': '采样率', 'param_type': 'text', 'direction': 'input'},
        ])},
        'api_params': {ALGO: AlgorithmConfigCache._serialize_params(RAW_API_PARAMS)},
        'case_params': {ALGO: []},
        'reference_params': {ALGO: []},
        'mappings': {
            ALGO: AlgorithmConfigCache._serialize_mappings(RAW_MAPPINGS, None, ALGO)
        },
        'evaluation_dimension_params': {DIM_TEXT: [], DIM_DURATION: []},
    }


def _by_code(rows):
    return {row['code']: row for row in rows}


# ========== 1. 不传 api_id：只返回算法级行（与改动前一致） ==========

def test_api_params_without_api_id_returns_algorithm_level_only():
    cache = _bare_cache()
    rows = cache.get_api_params(ALGO)

    assert [r['code'] for r in rows] == ['lang', 'answer', 'duration']
    assert [r['name'] for r in rows] == ['算法级语言', '算法级答案', '算法级时长']
    # 唯一增量是行携带 api_id（父卡第三节「响应行里带 api_id」），其余键与改动前一致
    assert set(rows[0]) == OLD_PARAM_KEYS | {'api_id'}
    assert rows[0]['api_id'] is None


def test_api_params_unknown_api_id_falls_back_to_algorithm_level():
    cache = _bare_cache()
    rows = cache.get_api_params(ALGO, 999)
    assert [r['code'] for r in rows] == ['lang', 'answer', 'duration']


def test_mapping_without_api_id_returns_algorithm_level_only():
    cache = _bare_cache()
    evaluation = cache.get_param_mapping(ALGO, 'evaluation')
    assert {m['target_param'] for m in evaluation} == {
        'text', 'seconds', 'lang_code'}
    assert set(evaluation[0]) == OLD_EVAL_MAPPING_KEYS | {'api_id'}
    assert all(m['api_id'] is None for m in evaluation)

    api_bucket = cache.get_param_mapping(ALGO, 'api')
    assert {m['target_param'] for m in api_bucket} == {'lang_code'}
    assert set(api_bucket[0]) == OLD_MAPPING_KEYS | {'api_id'}


# ========== 2. 传 api_id：同键覆盖 + 未覆盖回落 + 其它 API 不串味 ==========

def test_api_params_api_level_overrides_same_key_and_keeps_fallback():
    cache = _bare_cache()
    rows = _by_code(cache.get_api_params(ALGO, API_A))

    # (direction, param_code) 同键覆盖
    assert rows['lang']['name'] == 'A家语言'
    assert rows['lang']['api_id'] == API_A
    # 未覆盖键仍取算法级默认
    assert rows['answer']['name'] == '算法级答案'
    assert rows['answer']['api_id'] is None
    assert rows['duration']['name'] == '算法级时长'
    # API 独有行追加
    assert rows['app_key']['api_id'] == API_A
    # 覆盖后同键仍只有一行（唯一键决定，不是两行并存）
    codes = [r['code'] for r in cache.get_api_params(ALGO, API_A)]
    assert codes.count('lang') == 1


def test_api_params_do_not_leak_across_apis():
    cache = _bare_cache()
    b_rows = _by_code(cache.get_api_params(ALGO, API_B))
    assert b_rows['lang']['name'] == 'B家语言'
    assert 'app_key' not in b_rows  # A 家独有行不能串到 B 家

    a_rows = _by_code(cache.get_api_params(ALGO, API_A))
    assert a_rows['lang']['name'] == 'A家语言'  # B 家覆盖不影响 A 家


def test_mapping_api_level_overrides_same_key_mapping():
    cache = _bare_cache()
    evaluation = cache.get_param_mapping(ALGO, 'evaluation', API_A)
    by_source_param = {m['source_param']: m for m in evaluation}

    # 同键（source, source_param, dimension_id）覆盖：target_param 不同也覆盖
    assert by_source_param['answer']['target_param'] == 'transcript'
    assert by_source_param['answer']['api_id'] == API_A
    # 未覆盖的算法级映射继续生效（回落）
    assert by_source_param['duration']['target_param'] == 'seconds'
    assert by_source_param['duration']['api_id'] is None


def test_evaluation_dedupe_happens_after_merge():
    """去重若发生在合并之前，算法级与 API 级 target 不同的两行会同时存活。"""
    cache = _bare_cache()
    evaluation = cache.get_param_mapping(ALGO, 'evaluation', API_A)
    answer_rows = [m for m in evaluation if m['source_param'] == 'answer']
    assert len(answer_rows) == 1
    assert answer_rows[0]['target_param'] == 'transcript'
    assert 'text' not in {m['target_param'] for m in evaluation}


def test_non_evaluation_bucket_merge_keeps_only_target_api_rows():
    cache = _bare_cache()
    a_bucket = cache.get_param_mapping(ALGO, 'api', API_A)
    a_targets = {m['source_param']: m['target_param'] for m in a_bucket}
    # lang 的算法级映射未被 A 家覆盖 → 保留；app_key 是 A 家独有
    assert a_targets == {'lang': 'lang_code', 'app_key': 'ak'}

    b_bucket = cache.get_param_mapping(ALGO, 'api', API_B)
    b_targets = {m['source_param']: m['target_param'] for m in b_bucket}
    # B 家覆盖 lang 同键映射；A 家独有行不串味
    assert b_targets == {'lang': 'lang_v2'}


# ========== 3. 其它读入口不串味 ==========

def test_get_algorithm_config_does_not_leak_api_level_rows():
    cache = _bare_cache()
    config = cache.get_algorithm_config(ALGO)
    assert [p['code'] for p in config['api_params']] == [
        'lang', 'answer', 'duration']
    assert all(p['api_id'] is None for p in config['api_params'])
    for bucket_rows in config['mappings'].values():
        assert all(m['api_id'] is None for m in bucket_rows)


def test_get_algorithm_params_keeps_algorithm_level_api_params():
    cache = _bare_cache()
    rows = cache.get_algorithm_params(ALGO)
    api_rows = [r for r in rows if r['code'] != 'sample_rate']
    assert [r['code'] for r in api_rows] == ['lang', 'answer', 'duration']
    assert all(r['api_id'] is None for r in api_rows)


# ========== 4. FieldMappingQueryHandler 合并入口 ==========

def test_field_definitions_merges_api_scope(monkeypatch):
    cache = _bare_cache()
    monkeypatch.setattr(
        field_mapping_queries, 'get_config_cache', lambda: cache)

    level = FieldMappingQueryHandler.get_field_definitions(ALGO)
    assert set(level['original']['api']['input']) == {'lang'}
    assert set(level['original']['api']['output']) == {'answer', 'duration'}
    assert level['original']['api']['input']['lang']['name'] == '算法级语言'
    assert set(level['mapped']['evaluation']) == {'text', 'seconds'}

    scoped = FieldMappingQueryHandler.get_field_definitions(ALGO, API_A)
    assert set(scoped['original']['api']['input']) == {'lang', 'app_key'}
    assert scoped['original']['api']['input']['lang']['name'] == 'A家语言'
    assert set(scoped['mapped']['evaluation']) == {'transcript', 'seconds'}


# ========== 5. proto / servicer 透传 ==========

def test_optional_api_id_presence_semantics():
    assert _optional_api_id(pb.GetApiParamsListRequest(algorithm_type=ALGO)) is None
    assert _optional_api_id(
        pb.GetApiParamsListRequest(algorithm_type=ALGO, api_id=API_A)) == API_A
    # 显式 0 与「未传」可区分（proto3 optional presence）
    assert _optional_api_id(
        pb.GetApiParamsListRequest(algorithm_type=ALGO, api_id=0)) == 0
    assert _optional_api_id(
        pb.GetParamMappingForComponentRequest(
            algorithm_type=ALGO, component_type='evaluation')) is None
    assert _optional_api_id(
        pb.GetParamMappingForComponentRequest(
            algorithm_type=ALGO, component_type='evaluation',
            api_id=API_A)) == API_A
    assert _optional_api_id(
        pb.GetFieldMappingsRequest(algorithm_type=ALGO)) is None
    assert _optional_api_id(
        pb.GetFieldMappingsRequest(algorithm_type=ALGO, api_id=API_B)) == API_B


class _FakeConfigHandler:
    def __init__(self):
        self.calls = []

    def get_api_params(self, algorithm_type, api_id=None):
        self.calls.append(('api_params', algorithm_type, api_id))
        return []

    def get_param_mapping(self, algorithm_type, component_type, api_id=None):
        self.calls.append(('mapping', algorithm_type, component_type, api_id))
        return []


class _FakeFieldMappingHandler:
    def __init__(self):
        self.calls = []

    def get_field_definitions(self, algorithm_type, api_id=None):
        self.calls.append(('fields', algorithm_type, api_id))
        return {'original': {}, 'mapped': {}}


@pytest.fixture()
def servicer():
    svc = AlgorithmQueryServicer()
    svc._config_handler = _FakeConfigHandler()
    svc._field_mapping_handler = _FakeFieldMappingHandler()
    return svc


def test_get_api_params_list_rpc_forwards_api_id(servicer):
    resp = servicer.GetApiParamsList(
        pb.GetApiParamsListRequest(algorithm_type=ALGO, api_id=API_A))
    assert resp.success is True
    assert servicer._config_handler.calls[-1] == ('api_params', ALGO, API_A)

    servicer.GetApiParamsList(pb.GetApiParamsListRequest(algorithm_type=ALGO))
    assert servicer._config_handler.calls[-1] == ('api_params', ALGO, None)


def test_get_param_mapping_rpc_forwards_api_id(servicer):
    servicer.GetParamMappingForComponent(pb.GetParamMappingForComponentRequest(
        algorithm_type=ALGO, component_type='evaluation', api_id=API_A))
    assert servicer._config_handler.calls[-1] == (
        'mapping', ALGO, 'evaluation', API_A)

    servicer.GetParamMappingForComponent(pb.GetParamMappingForComponentRequest(
        algorithm_type=ALGO, component_type='evaluation'))
    assert servicer._config_handler.calls[-1] == (
        'mapping', ALGO, 'evaluation', None)


def test_get_field_mappings_rpc_forwards_api_id(servicer):
    servicer.GetFieldMappings(pb.GetFieldMappingsRequest(
        algorithm_type=ALGO, api_id=API_B))
    assert servicer._field_mapping_handler.calls[-1] == ('fields', ALGO, API_B)

    servicer.GetFieldMappings(pb.GetFieldMappingsRequest(algorithm_type=ALGO))
    assert servicer._field_mapping_handler.calls[-1] == ('fields', ALGO, None)


# ========== 6. 端到端（进程内）：servicer → 真实 handler → 缓存 ==========

def _json_data(resp):
    import json
    return json.loads(resp.data) if resp.data else None


def test_rpcs_merge_through_real_handlers(monkeypatch):
    """不经 fake handler：三个 RPC 走真实 handler + 快照，验证 api_id 生效/回落。"""
    from algorithm_service.application.queries import algorithm_config_queries

    cache = _bare_cache()
    monkeypatch.setattr(
        algorithm_config_queries, 'get_config_cache', lambda: cache)
    monkeypatch.setattr(
        field_mapping_queries, 'get_config_cache', lambda: cache)
    svc = AlgorithmQueryServicer()

    level = _json_data(svc.GetApiParamsList(
        pb.GetApiParamsListRequest(algorithm_type=ALGO)))
    assert [p['name'] for p in level] == ['算法级语言', '算法级答案', '算法级时长']

    scoped = _json_data(svc.GetApiParamsList(
        pb.GetApiParamsListRequest(algorithm_type=ALGO, api_id=API_A)))
    by_code = {p['code']: p for p in scoped}
    assert by_code['lang']['name'] == 'A家语言'
    assert by_code['answer']['name'] == '算法级答案'
    assert by_code['app_key']['api_id'] == API_A

    mapping_level = _json_data(svc.GetParamMappingForComponent(
        pb.GetParamMappingForComponentRequest(
            algorithm_type=ALGO, component_type='evaluation')))
    assert {m['target_param'] for m in mapping_level} == {
        'text', 'seconds', 'lang_code'}
    mapping_scoped = _json_data(svc.GetParamMappingForComponent(
        pb.GetParamMappingForComponentRequest(
            algorithm_type=ALGO, component_type='evaluation', api_id=API_A)))
    assert {m['target_param'] for m in mapping_scoped} == {
        'transcript', 'seconds', 'lang_code', 'ak'}

    fields_level = _json_data(svc.GetFieldMappings(
        pb.GetFieldMappingsRequest(algorithm_type=ALGO)))
    assert set(fields_level['mapped']['evaluation']) == {'text', 'seconds'}
    fields_scoped = _json_data(svc.GetFieldMappings(
        pb.GetFieldMappingsRequest(algorithm_type=ALGO, api_id=API_A)))
    assert set(fields_scoped['mapped']['evaluation']) == {
        'transcript', 'seconds'}
