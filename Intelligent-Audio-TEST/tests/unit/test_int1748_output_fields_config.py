# -*- coding: utf-8 -*-
"""INT-1748 voice_llm 输出映射去硬编码（C3）契约测试。

覆盖：
- 输出字段清单改由 algorithm_api_params(direction=output) 声明驱动（含映射 target_param）；
- 零声明时明确降级（空清单 + WARNING），不再回落到硬编码字段表；
- 配置路径与改造前硬编码路径结果逐字段一致（声明等价时）；
- 轮内未声明的键不输出（键集合来自配置）；
- map_api_results 全链路删除（handler / 客户端封装 / RPC 桩返回明确失败）。
"""
import os

import pytest

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from algorithm_service.application.queries import result_field_mapping_queries as queries
from algorithm_service.application.queries.result_field_mapping_queries import (
    ResultFieldMappingQueryHandler,
)
from shared.constants.device_fields import DEVICE_FIELDS
from shared.domain.algorithm_result_strategy import (
    AlgorithmStrategyFactory,
    DefaultStrategy,
    VoiceLlmStrategy,
)


class _FakeParamRepo:
    def __init__(self, api_params, device_params=None):
        self._by_type = {'api': api_params, 'device': device_params or []}
        self.calls = []

    def list_by_algorithm(self, algorithm_type, param_type):
        self.calls.append((algorithm_type, param_type))
        return list(self._by_type.get(param_type, []))


class _FakeMappingRepo:
    def __init__(self, mappings):
        self._mappings = mappings
        self.calls = []

    def list_by_algorithm(self, algorithm_type, source_type=None, dimension_id=None):
        self.calls.append((algorithm_type, source_type, dimension_id))
        return list(self._mappings)


@pytest.fixture(autouse=True)
def _clear_output_field_cache():
    ResultFieldMappingQueryHandler.clear_cache()
    yield
    ResultFieldMappingQueryHandler.clear_cache()


def _declared(param_code, param_type='text', ui_order=0, pid=1, **extra):
    item = {
        'id': pid,
        'param_code': param_code,
        'param_type': param_type,
        'direction': 'output',
        'ui_order': ui_order,
        'label': extra.get('label'),
        'param_name': extra.get('param_name'),
    }
    item.update(extra)
    return item


def _patch_repos(monkeypatch, params, mappings=None, device_params=None):
    monkeypatch.setattr(
        queries, 'algorithm_param_repository',
        _FakeParamRepo(params, device_params),
    )
    monkeypatch.setattr(queries, 'mapping_repository', _FakeMappingRepo(mappings or []))


# ---------- get_output_fields：声明驱动 ----------

def test_output_fields_from_declaration_with_mapping(monkeypatch):
    """字段清单/类型取声明，target_param 取 api 输出映射，无映射时按恒等。"""
    _patch_repos(
        monkeypatch,
        params=[
            _declared('session_id', 'text', ui_order=10, pid=2, label='session ID'),
            _declared('total_latency', 'number', ui_order=20, pid=3),
            _declared('asr_text', 'text', ui_order=30, pid=4),
            dict(_declared('request_text', 'text', ui_order=40, pid=5), direction='input'),
        ],
        mappings=[
            {'source': 'api', 'source_param': 'asr_text', 'target_param': 'answer',
             'source_direction': 'output', 'dimension_id': 7,
             'transform_type': 'uppercase'},
            {'source': 'api', 'source_param': 'total_latency', 'target_param': 'latency_in',
             'source_direction': 'input', 'dimension_id': None, 'transform_type': 'none'},
            {'source': 'device', 'source_param': 'session_id', 'target_param': 'sid',
             'source_direction': 'output', 'dimension_id': None, 'transform_type': 'none'},
        ],
    )

    fields = ResultFieldMappingQueryHandler.get_output_fields('voice_llm')

    assert [f['source_param'] for f in fields] == ['session_id', 'total_latency', 'asr_text']
    by_code = {f['source_param']: f for f in fields}
    assert by_code['session_id']['target_param'] == 'session_id'  # device 映射不参与
    assert by_code['session_id']['label'] == 'session ID'
    assert by_code['total_latency']['param_type'] == 'number'
    assert by_code['total_latency']['target_param'] == 'total_latency'  # input 映射不参与
    assert by_code['asr_text']['target_param'] == 'answer'
    assert by_code['asr_text']['dimension_id'] == 7
    assert by_code['asr_text']['transform_type'] == 'uppercase'


def test_output_fields_order_by_ui_order_then_id(monkeypatch):
    """展示顺序按 ui_order / id，保证不依赖数据库默认顺序。"""
    _patch_repos(monkeypatch, params=[
        _declared('c', ui_order=20, pid=9),
        _declared('a', ui_order=10, pid=8),
        _declared('b', ui_order=10, pid=7),
    ])
    fields = ResultFieldMappingQueryHandler.get_output_fields('voice_llm')
    assert [f['source_param'] for f in fields] == ['b', 'a', 'c']


def test_zero_declaration_degrades_to_empty_with_warning(monkeypatch):
    """零 output 声明：返回空清单并写 WARNING，不回落到硬编码字段。"""
    _patch_repos(monkeypatch, params=[
        dict(_declared('question', 'text'), direction='input'),
    ])
    logged = []
    monkeypatch.setattr(
        queries, 'log_not_emit',
        lambda level, module, content, **kwargs: logged.append((level, content)),
    )

    assert ResultFieldMappingQueryHandler.get_output_fields('voice_llm') == []
    assert logged and logged[0][0] == 'WARNING'
    assert '无 direction=output 的输出字段声明' in logged[0][1]
    # 降级结果不缓存：补齐声明后无需重启即可生效
    assert 'voice_llm' not in ResultFieldMappingQueryHandler._output_field_cache


def test_device_output_declarations_merged_after_api(monkeypatch):
    """设备输出声明并入展示字段（API 已声明的键不重复），类型取声明。"""
    _patch_repos(
        monkeypatch,
        params=[_declared('asr_text', 'text', ui_order=10, pid=1)],
        device_params=[
            dict(_declared('start_ms', 'timestamp', ui_order=1, pid=11)),
            dict(_declared('user_wav', 'audio_file', ui_order=2, pid=12)),
            dict(_declared('asr_text', 'text', ui_order=3, pid=13)),
            dict(_declared('input_text', 'text', ui_order=4, pid=14), direction='input'),
        ],
    )
    fields = ResultFieldMappingQueryHandler.get_output_fields('voice_llm')
    assert [f['source_param'] for f in fields] == ['asr_text', 'start_ms', 'user_wav']
    by_code = {f['source_param']: f for f in fields}
    assert by_code['asr_text']['source'] == 'api'  # API 声明优先
    assert by_code['start_ms']['param_type'] == 'timestamp'


def test_new_algorithm_type_config_only(monkeypatch):
    """新增算法类型只改配置：未在策略工厂登记也能产出输出字段与映射。"""
    _patch_repos(
        monkeypatch,
        params=[_declared('vendor_score', 'number', ui_order=1, pid=1)],
        mappings=[{'source': 'api', 'source_param': 'vendor_score',
                   'target_param': 'score', 'source_direction': 'output'}],
    )
    fields = ResultFieldMappingQueryHandler.get_output_fields('brand_new_algo')
    assert fields[0]['target_param'] == 'score'
    assert isinstance(AlgorithmStrategyFactory.get_strategy('brand_new_algo'), DefaultStrategy)


# ---------- process_algorithm_result：配置路径与基线等价 ----------

def _baseline_fields():
    """改造前 VoiceLlmStrategy 的硬编码字段表（等价声明，含轮内子键）。"""
    return [
        {'source_param': 'session_id', 'target_param': 'session_id', 'param_type': 'text', 'label': 'session ID'},
        {'source_param': 'round_count', 'target_param': 'round_count', 'param_type': 'number', 'label': 'round count'},
        {'source_param': 'total_latency', 'target_param': 'total_latency', 'param_type': 'number', 'label': 'total latency(ms)'},
        {'source_param': 'context_mode', 'target_param': 'context_mode', 'param_type': 'text', 'label': 'context mode'},
        {'source_param': 'history_count', 'target_param': 'history_count', 'param_type': 'number', 'label': 'history count'},
        {'source_param': 'error', 'target_param': 'error', 'param_type': 'text', 'label': 'error'},
        {'source_param': 'rounds', 'target_param': 'rounds', 'param_type': 'json', 'label': 'round results'},
        {'source_param': 'asr_text', 'target_param': 'asr_text', 'param_type': 'text', 'label': 'asr_text'},
        {'source_param': 'answer', 'target_param': 'answer', 'param_type': 'text', 'label': 'answer'},
    ]


def test_voice_llm_config_path_equals_baseline_path():
    """声明等价时，配置路径与改造前硬编码路径逐字段一致（含顺序/类型/展示名）。"""
    combined = {
        'session_id': 's1', 'round_count': 1,
        'rounds': [{'round': 0, 'output': {'asr_text': '你好', 'answer': '您好', 'evaluation': {'x': 1}}}],
    }
    expected = [
        ('session_id', 'text', 'session ID', 's1', None),
        ('round_count', 'number', 'round count', 1, None),
        ('asr_text@round:1', 'text', 'asr_text (第1轮)', '你好', 1),
        ('answer@round:1', 'text', 'answer (第1轮)', '您好', 1),
        ('rounds', 'json', 'round results', combined['rounds'], None),
    ]
    rows = VoiceLlmStrategy().process_algorithm_result(
        combined, _baseline_fields(), 'api_01', DEVICE_FIELDS, None, None, None,
    )
    assert [
        (r['param_code'], r['param_type'], r['label'], r['value'], r.get('round_number'))
        for r in rows
    ] == expected


def test_voice_llm_round_keys_come_from_config():
    """轮内未声明的键（及 evaluation 子字典）不输出；类型取声明。"""
    fields = [
        {'source_param': 'rounds', 'target_param': 'rounds', 'param_type': 'json', 'label': 'round results'},
        {'source_param': 'asr_text', 'target_param': 'asr_text', 'param_type': 'text', 'label': 'asr_text'},
        {'source_param': 'score', 'target_param': 'score', 'param_type': 'number', 'label': 'score'},
    ]
    combined = {'rounds': [
        {'round': 0, 'output': {'asr_text': 'hi', 'score': 0.5,
                                'undeclared_key': 'x', 'evaluation': {'y': 1}}},
    ]}
    rows = VoiceLlmStrategy().process_algorithm_result(
        combined, fields, 'api_01', DEVICE_FIELDS, None, None, None,
    )
    assert [r['param_code'] for r in rows] == [
        'asr_text@round:1', 'score@round:1', 'rounds',
    ]
    assert {r['param_code']: r['param_type'] for r in rows}['score@round:1'] == 'number'


def test_zero_output_fields_emits_nothing():
    """零声明时不再靠硬编码表产出任何条目（明确降级）。"""
    combined = {'session_id': 's1', 'rounds': [{'round': 0, 'output': {'asr_text': 'hi'}}]}
    assert VoiceLlmStrategy().process_algorithm_result(
        combined, [], 'api_01', DEVICE_FIELDS, None, None, None,
    ) == []


# ---------- map_api_results 全链路删除 ----------

def test_map_api_results_removed_everywhere():
    assert not hasattr(ResultFieldMappingQueryHandler, 'map_api_results')
    for strategy in (VoiceLlmStrategy(), DefaultStrategy()):
        assert not hasattr(strategy, 'map_api_results')
    import shared.clients.grpc_clients as grpc_clients
    assert not hasattr(grpc_clients, 'algo_map_api_results')
    import shared.clients._grpc_algo_audio as algo_audio
    assert not hasattr(algo_audio, 'algo_map_api_results')


def test_map_api_results_rpc_is_deprecated_stub():
    from algorithm_service.interfaces.grpc.algorithm_query_servicer import (
        AlgorithmQueryServicer,
    )
    resp = AlgorithmQueryServicer().MapApiResults(request=None, context=None)
    assert resp.success is False
    assert '已废弃' in resp.message
