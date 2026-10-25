# -*- coding: utf-8 -*-
"""INT-1757（C6b）api_id 作用域调用点接线

覆盖卡面验收 2 / 3 / 4 的可离线部分（真实处理器 + 替身 ACL，不连库、不起栈）：

- algorithm_service 进程内输出声明缓存改键 ``(algorithm_type, api_id)``：同
  ``algorithm_type`` 下两家 API 不再互相命中缓存；
- 输出声明加载按唯一键合并（API 级覆盖算法级、未覆盖键回落），不传 ``api_id``
  只取算法级行（存量行为不变）；
- 执行 / 评估 / 报告侧调用点把 ``api_id`` 带到 ACL：执行链（单轮 / 多轮 /
  Realtime）、评估 ``task_data`` 透传与 ``test_results.api_id`` 回源、报告侧
  输出声明读取。
"""
import os

import pytest

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

ALGO_TYPE = 'translation'  # 该类型无硬编码策略，走仓库加载分支


# ------------------------------------------------------------------ 假仓库

def _mapping_row(source_param, target_param, api_id=None, transform_type='none'):
    return {
        'source': 'api',
        'source_param': source_param,
        'source_direction': 'output',
        'target_param': target_param,
        'transform_type': transform_type,
        'dimension_id': None,
        'dimension_name': None,
        'api_id': api_id,
    }


class _FakeMappingRepo:
    """param_mappings 行：算法级 2 行 + API 201 各配 1 覆盖 + 1 独有。"""

    def __init__(self):
        self.calls = []
        self.rows = [
            _mapping_row('asr_text', 'asr'),
            _mapping_row('vendor_conf', 'confidence'),
            _mapping_row('asr_text', 'asr_201', api_id=201),
            _mapping_row('vendor_conf', 'conf_201', api_id=201),
            _mapping_row('asr_text', 'asr_202', api_id=202),
        ]

    def list_by_algorithm(self, algorithm_type, *args, **kwargs):
        self.calls.append(algorithm_type)
        return list(self.rows)


class _FakeParamRepo:
    # 现基线（INT-1748）输出字段清单来源 = algorithm_api_params(direction=output)
    # 声明，故替身行必须带 direction='output'（与真实表同形）。
    def __init__(self):
        self.rows = [
            {'param_code': 'asr_text', 'param_type': 'text', 'api_id': None,
             'direction': 'output'},
            {'param_code': 'vendor_conf', 'param_type': 'json', 'api_id': None,
             'direction': 'output'},
            {'param_code': 'vendor_conf', 'param_type': 'number', 'api_id': 201,
             'direction': 'output'},
        ]

    def list_by_algorithm(self, algorithm_type, param_type):
        return list(self.rows) if param_type == 'api' else []


@pytest.fixture()
def field_query(monkeypatch):
    from algorithm_service.application.queries import result_field_mapping_queries as q

    mapping_repo = _FakeMappingRepo()
    param_repo = _FakeParamRepo()
    monkeypatch.setattr(q, 'mapping_repository', mapping_repo)
    monkeypatch.setattr(q, 'algorithm_param_repository', param_repo)
    q.ResultFieldMappingQueryHandler._output_field_cache.clear()
    yield q, mapping_repo
    q.ResultFieldMappingQueryHandler._output_field_cache.clear()


# ------------------------------------------------- 验收 2：缓存按 (type, api_id)

def test_output_field_cache_keyed_by_algorithm_type_and_api_id(field_query):
    q, _ = field_query
    handler = q.ResultFieldMappingQueryHandler

    level_fields = handler.get_output_fields(ALGO_TYPE)
    api201_fields = handler.get_output_fields(ALGO_TYPE, api_id=201)
    api202_fields = handler.get_output_fields(ALGO_TYPE, api_id=202)

    # 三家各自的结果都正确（不是命中上一家的缓存）
    assert [f['target_param'] for f in level_fields] == ['asr', 'confidence']
    assert [f['target_param'] for f in api201_fields] == ['asr_201', 'conf_201']
    assert [f['target_param'] for f in api202_fields] == ['asr_202', 'confidence']

    # 缓存按 (algorithm_type, api_id) 分桶
    assert set(handler._output_field_cache) == {
        (ALGO_TYPE, None), (ALGO_TYPE, 201), (ALGO_TYPE, 202),
    }

    # 再取不触发仓库查询（命中各自分桶）
    mapping_repo_calls = len(field_query[1].calls)
    assert handler.get_output_fields(ALGO_TYPE, api_id=201) == api201_fields
    assert len(field_query[1].calls) == mapping_repo_calls


# ------------------------------------------------- 验收 4：不传 api_id 行为不变

def test_level_rows_only_without_api_id(field_query):
    q, _ = field_query
    fields = q.ResultFieldMappingQueryHandler.get_output_fields(ALGO_TYPE)
    # API 实例级独有的 vendor_conf→conf_201 不会串进算法级默认
    assert [f['target_param'] for f in fields] == ['asr', 'confidence']


def test_api_param_type_overrides_level(field_query):
    q, _ = field_query
    fields = q.ResultFieldMappingQueryHandler.get_output_fields(ALGO_TYPE, api_id=201)
    by_source = {f['source_param']: f for f in fields}
    # 参数类型取 API 级行（number），不是算法级（json）
    assert by_source['vendor_conf']['param_type'] == 'number'


# ------------------------------------------------- 验收 3：调用点把 api_id 带下去

def test_api_acl_forwards_api_id(monkeypatch):
    """api_test_service ACL 实现把 api_id 透传给 gRPC 客户端。"""
    import shared.clients.grpc_clients as gc
    from api_test_service.infrastructure.acl import algorithm_acl_repository as impl

    seen = {}

    def _fake_field(algorithm_type, api_id=None):
        seen['field'] = api_id
        return {}

    def _fake_params(algorithm_type, api_id=None):
        seen['params'] = api_id
        return []

    def _fake_mapping(algorithm_type, component_type, api_id=None):
        seen['mapping'] = (component_type, api_id)
        return []

    monkeypatch.setattr(gc, 'algo_get_field_mappings', _fake_field)
    monkeypatch.setattr(gc, 'algo_get_api_params', _fake_params)
    monkeypatch.setattr(gc, 'algo_get_param_mapping', _fake_mapping)

    repo = impl.AlgorithmQueryAclRepositoryImpl()
    repo.get_field_mappings(ALGO_TYPE, api_id=201)
    repo.get_api_params(ALGO_TYPE, api_id=201)
    repo.get_param_mapping(ALGO_TYPE, 'evaluation', api_id=201)

    assert seen == {'field': 201, 'params': 201, 'mapping': ('evaluation', 201)}


def test_realtime_collect_eval_fields_passes_api_id(monkeypatch):
    """Realtime 链 _collect_eval_fields 取输出声明时带 api_id。"""
    from api_test_service.core import realtime_session_executor as rt

    seen = {}

    class _Acl:
        def get_field_mappings(self, algorithm_type, api_id=None):
            seen['api_id'] = api_id
            return {'original': {}, 'mapped': {}}

    monkeypatch.setattr(rt, '_algo_acl', _Acl())
    executor = object.__new__(rt.RealtimeSessionExecutor)
    executor._executor = type('_Exec', (), {'_log': lambda *a, **k: None})()

    executor._collect_eval_fields(
        {'input': {'text': 'q'}}, {'text': 'a'}, 'translation', api_id=201)

    assert seen['api_id'] == 201


def test_build_task_data_carries_api_id():
    """评估侧 task_data 透传 api_id；None 时不写键（存量形状不变）。"""
    from evaluation_service.infrastructure.evaluation_api.task_dispatcher import (
        TaskDispatcherMixin,
    )

    class _FieldMapper:
        def get_mapped_device_output_field_keys(self, algorithm_type):
            return []

    dispatcher = object.__new__(TaskDispatcherMixin)

    task_data = dispatcher._build_task_data(
        1, 2, 'case-1', {}, {'id': 1}, [({'id': 1}, 11)], ALGO_TYPE, 'api', None,
        _FieldMapper(), {}, api_id=201)
    assert task_data['api_id'] == 201

    legacy = dispatcher._build_task_data(
        1, 2, 'case-1', {}, {'id': 1}, [({'id': 1}, 11)], ALGO_TYPE, 'api', None,
        _FieldMapper(), {})
    assert 'api_id' not in legacy


def test_evaluate_case_resolves_api_id_from_test_result():
    """评估侧 api_id 回源：显式传入优先，否则读 test_results.api_id。"""
    from evaluation_service.domain.dto.evaluation_acl_dto import TestResultDTO
    from evaluation_service.domain.services.evaluation_service.case_evaluation import (
        CaseEvaluationMixin,
    )

    class _Repo:
        def __init__(self, dto):
            self.dto = dto
            self.calls = 0

        def get_test_result_by_id(self, result_id):
            self.calls += 1
            return self.dto

    evaluator = object.__new__(CaseEvaluationMixin)

    evaluator._task_acl_repo = _Repo(TestResultDTO(id=9, api_id=201))
    kwargs = {}
    assert evaluator._resolve_evaluation_api_id(1, 'c', 9, kwargs) == 201
    assert kwargs == {}

    # 显式传入优先，并从 kwargs 摘掉（不注入评估请求 context）
    kwargs = {'api_id': 202}
    assert evaluator._resolve_evaluation_api_id(1, 'c', 9, kwargs) == 202
    assert 'api_id' not in kwargs

    # 设备链 / 读不到：None（算法级默认）
    evaluator._task_acl_repo = _Repo(TestResultDTO(id=9, api_id=None))
    assert evaluator._resolve_evaluation_api_id(1, 'c', 9, {}) is None


def test_report_output_fields_scoped_by_result_api_id(monkeypatch):
    """报告侧回退提取按 result.api_id 取输出声明。"""
    import shared.clients.grpc_clients as gc
    from report_service.application.services import report_data_builder_case_mixin as mixin

    seen = []

    def _fake_output_fields(algorithm_type, test_type=None, api_id=None):
        seen.append(api_id)
        return []

    monkeypatch.setattr(gc, 'algo_get_output_fields', _fake_output_fields)

    mixin.ReportDataCaseMixin._build_case_basic_info(
        {'id': 'case-1', 'name': 'n', 'algorithm_type': ALGO_TYPE},
        [{'id': 1, 'api_id': 201, 'algorithm_result': {'asr': 'x'}}],
        {'id': 1},
    )
    assert seen == [201]
