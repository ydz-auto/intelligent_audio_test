# -*- coding: utf-8 -*-
"""用例参数提取的 API 实例作用域（ExtractCaseAllParams 侧）。

语义（见 doc/spec/api_param_profile/spec.md）：
- ``case_config`` 里的保留键 ``api_id`` = 本用例所属 API 实例；
- 有 api_id：API 输入声明与评估映射按「策略 + 实例覆盖」解析；
- 无 api_id（物理/未指定）：API 输入声明为空，且**不得**触发
  ``get_api_params(api_id=None)`` 的「默认层已废弃」告警刷屏。
"""
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from algorithm_service.application.queries import case_parameter_queries as cpq  # noqa: E402

ALGO = 'translation'
API = 11


class _FakeCache:
    """config cache 最小替身：记录被调用时的 api_id，并按 instance 返回声明。"""

    def __init__(self):
        self.param_calls = []
        self.mapping_calls = []

    def get_api_params(self, algorithm_type, api_id=None):
        self.param_calls.append((algorithm_type, api_id))
        if api_id != API:
            return []
        return [
            {'code': 'src_lang', 'direction': 'input', 'default_value': 'zh'},
            {'code': 'asr_text', 'direction': 'output'},
        ]

    def get_param_mapping(self, algorithm_type, component_type, api_id=None):
        self.mapping_calls.append((algorithm_type, component_type, api_id))
        if component_type != 'evaluation' or api_id != API:
            return []
        return [{
            'source': 'api', 'source_param': 'asr_text',
            'target_param': 'wer', 'transform_type': 'none',
        }]

    def get_device_params(self, algorithm_type):
        return []


def _patch(monkeypatch):
    cache = _FakeCache()
    monkeypatch.setattr(cpq, 'get_config_cache', lambda: cache)
    return cache


def _case_config(**extra):
    base = {'algorithm_type': ALGO, 'algorithm_params': {'src_lang': 'en'}}
    base.update(extra)
    return base


def test_api_params_scoped_by_case_config_api_id(monkeypatch):
    cache = _patch(monkeypatch)
    result = cpq.CaseParameterQueryHandler.get_api_params(_case_config(api_id=API))

    # 用例里的算法参数值覆盖声明默认值，且只保留 input 声明
    assert result == {'src_lang': 'en'}
    assert cache.param_calls == [(ALGO, API)]


def test_api_params_without_api_id_returns_empty_without_cache_call(monkeypatch):
    cache = _patch(monkeypatch)
    assert cpq.CaseParameterQueryHandler.get_api_params(_case_config()) == {}
    # 关键：没有 api_id 时不应触碰 get_api_params（避免每用例一条 WARN）
    assert cache.param_calls == []


def test_evaluation_mappings_scoped_by_api_id(monkeypatch):
    cache = _patch(monkeypatch)
    result = cpq.CaseParameterQueryHandler.get_evaluation_params(
        _case_config(api_id=API),
        dimension_ids=None,
        algorithm_result={'api': {'asr_text': 'hello'}},
        device_type='http_api',
        round_number=0,
    )
    assert result == {'wer': 'hello'}
    assert cache.mapping_calls == [(ALGO, 'evaluation', API)]


def test_evaluation_mappings_without_api_id_pass_none(monkeypatch):
    cache = _patch(monkeypatch)
    result = cpq.CaseParameterQueryHandler.get_evaluation_params(
        _case_config(),
        algorithm_result={'api': {'asr_text': 'hello'}},
        device_type='physical',
    )
    assert result == {}
    assert cache.mapping_calls == [(ALGO, 'evaluation', None)]


def test_get_api_id_normalizes_and_ignores_bad_values(monkeypatch):
    _patch(monkeypatch)
    handler = cpq.CaseParameterQueryHandler
    assert handler.get_api_id({'api_id': '11'}) == API
    assert handler.get_api_id({'api_id': None}) is None
    assert handler.get_api_id({}) is None
    assert handler.get_api_id({'api_id': 'abc'}) is None


def test_get_all_params_merges_api_segment(monkeypatch):
    _patch(monkeypatch)
    all_params = cpq.CaseParameterQueryHandler.get_all_params(_case_config(api_id=API))
    assert all_params['api'] == {'src_lang': 'en'}
    assert all_params['algorithm_type'] == ALGO
