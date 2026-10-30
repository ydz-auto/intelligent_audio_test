# -*- coding: utf-8 -*-
"""INT-1757（C6b）api_id 作用域调用点接线

覆盖卡面验收 2 / 3 / 4 的可离线部分（真实处理器 + 替身 ACL，不连库、不起栈）：

- algorithm_service 进程内输出声明缓存改键 ``(algorithm_type, api_id)``：同
  ``algorithm_type`` 下两家 API 不再互相命中缓存；
- 输出声明按 API 实例作用域解析：策略（param_profiles，经 api_param_bindings
  绑定）+ 实例覆盖（api_id=X 的行，同键覆盖策略、独有键追加、未覆盖键回落
  策略）；算法类型级默认层已废弃，不传 ``api_id`` 只取算法级仓储行
  （物理侧 / 历史视图）；
- 执行 / 评估 / 报告侧调用点把 ``api_id`` 带到 ACL：执行链（单轮 / 多轮 /
  Realtime）、评估 ``task_data`` 透传与 ``test_results.api_id`` 回源、报告侧
  输出声明读取。
"""
import os

import pytest

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from algorithm_service.infrastructure.persistence.config_cache import (  # noqa: E402
    AlgorithmConfigCache,
)

ALGO_TYPE = 'translation'  # 该类型无硬编码策略，走「策略 + 实例覆盖」解析
PROFILE_ID = 7
API_A = 201
API_B = 202


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


# 策略层（param_profiles / param_profile_mappings）：profile 7 的声明与映射
_PROFILE_PARAMS = [
    {'id': 11, 'algorithm_type': ALGO_TYPE, 'api_id': None,
     'param_code': 'asr_text', 'param_name': '识别文本', 'param_type': 'text',
     'direction': 'output', 'ui_order': 1},
    {'id': 12, 'algorithm_type': ALGO_TYPE, 'api_id': None,
     'param_code': 'vendor_conf', 'param_name': '置信度', 'param_type': 'json',
     'direction': 'output', 'ui_order': 2},
]
_PROFILE_MAPPINGS = [
    _mapping_row('asr_text', 'asr'),
    _mapping_row('vendor_conf', 'confidence'),
]

# 实例覆盖层（algorithm_api_params / param_mappings 的 api_id=X 行）
_OVERRIDE_PARAMS = [
    {'id': 21, 'algorithm_type': ALGO_TYPE, 'api_id': API_A,
     'param_code': 'vendor_conf', 'param_name': '覆盖置信度',
     'param_type': 'number', 'direction': 'output', 'ui_order': 2},
]
_OVERRIDE_MAPPINGS = [
    _mapping_row('vendor_conf', 'conf_201', api_id=API_A),
    _mapping_row('asr_text', 'asr_202', api_id=API_B),
]


def _bare_cache(snapshot):
    """绕过单例加载，直接安装快照（与 test_int1756 同构造手法）。"""
    cache = object.__new__(AlgorithmConfigCache)
    cache._config_cache = snapshot
    return cache


def _snapshot():
    """策略 + 实例覆盖的完整快照；映射与参数均经缓存自身的序列化方法构造。"""
    return {
        'algorithms': {},
        'device_params': {ALGO_TYPE: []},
        'api_params': {
            ALGO_TYPE: AlgorithmConfigCache._serialize_params(_OVERRIDE_PARAMS)},
        'profile_params': {
            PROFILE_ID: AlgorithmConfigCache._serialize_params(_PROFILE_PARAMS)},
        'profile_mappings': {
            PROFILE_ID: AlgorithmConfigCache._serialize_mappings(
                _PROFILE_MAPPINGS, None, ALGO_TYPE)},
        'api_bindings': {API_A: PROFILE_ID, API_B: PROFILE_ID},
        'case_params': {ALGO_TYPE: []},
        'reference_params': {ALGO_TYPE: []},
        'mappings': {
            ALGO_TYPE: AlgorithmConfigCache._serialize_mappings(
                _OVERRIDE_MAPPINGS, None, ALGO_TYPE)},
        'evaluation_dimension_params': {},
    }


class _FakeMappingRepo:
    """仅服务 api_id=None 的算法级仓储口径（API 实例行由配置缓存提供）。"""

    def __init__(self):
        self.calls = []
        self.rows = [
            _mapping_row('asr_text', 'asr'),
            _mapping_row('vendor_conf', 'confidence'),
        ]

    def list_by_algorithm(self, algorithm_type, *args, **kwargs):
        self.calls.append(algorithm_type)
        return list(self.rows)


class _FakeParamRepo:
    """仅服务 api_id=None 的算法级仓储口径（照真实表带 direction='output'）。"""

    def __init__(self):
        self.rows = [
            {'param_code': 'asr_text', 'param_type': 'text', 'api_id': None,
             'direction': 'output'},
            {'param_code': 'vendor_conf', 'param_type': 'json', 'api_id': None,
             'direction': 'output'},
        ]

    def list_by_algorithm(self, algorithm_type, param_type):
        return list(self.rows) if param_type == 'api' else []


@pytest.fixture()
def field_query(monkeypatch):
    from algorithm_service.application.queries import result_field_mapping_queries as q

    mapping_repo = _FakeMappingRepo()
    param_repo = _FakeParamRepo()
    cache = _bare_cache(_snapshot())
    monkeypatch.setattr(q, 'mapping_repository', mapping_repo)
    monkeypatch.setattr(q, 'algorithm_param_repository', param_repo)
    monkeypatch.setattr(q, 'get_config_cache', lambda: cache)
    q.ResultFieldMappingQueryHandler._output_field_cache.clear()
    yield q, mapping_repo
    q.ResultFieldMappingQueryHandler._output_field_cache.clear()


# ------------------------------------------------- 验收 2：缓存按 (type, api_id)

def test_output_field_cache_keyed_by_algorithm_type_and_api_id(field_query):
    q, mapping_repo = field_query
    handler = q.ResultFieldMappingQueryHandler

    level_fields = handler.get_output_fields(ALGO_TYPE)
    api201_fields = handler.get_output_fields(ALGO_TYPE, api_id=API_A)
    api202_fields = handler.get_output_fields(ALGO_TYPE, api_id=API_B)

    # 三家各自的结果都正确（不是命中上一家的缓存）：
    # - 算法级视图取仓储行；
    # - API 视图 = 策略 + 实例覆盖（同键覆盖、未覆盖回落策略）
    assert [f['target_param'] for f in level_fields] == ['asr', 'confidence']
    assert [f['target_param'] for f in api201_fields] == ['asr', 'conf_201']
    assert [f['target_param'] for f in api202_fields] == ['asr_202', 'confidence']

    # 缓存按 (algorithm_type, api_id) 分桶
    assert set(handler._output_field_cache) == {
        (ALGO_TYPE, None), (ALGO_TYPE, 201), (ALGO_TYPE, 202),
    }

    # 再取 201 不触发假仓储查询（API 视图走配置缓存 + 命中分桶）
    mapping_repo_calls = len(mapping_repo.calls)
    assert handler.get_output_fields(ALGO_TYPE, api_id=API_A) == api201_fields
    assert len(mapping_repo.calls) == mapping_repo_calls


# ------------------------------------------------- 验收 4：不传 api_id 行为不变

def test_level_rows_only_without_api_id(field_query):
    q, _ = field_query
    fields = q.ResultFieldMappingQueryHandler.get_output_fields(ALGO_TYPE)
    # API 实例级独有的 vendor_conf→conf_201 不会串进算法级默认
    assert [f['target_param'] for f in fields] == ['asr', 'confidence']


def test_api_param_type_overrides_level(field_query):
    q, _ = field_query
    fields = q.ResultFieldMappingQueryHandler.get_output_fields(ALGO_TYPE, api_id=API_A)
    by_source = {f['source_param']: f for f in fields}
    # 参数类型取实例覆盖行（number），不是策略行（json）
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

    def _fake_output_fields(algorithm_type, device_type=None, api_id=None):
        seen.append(api_id)
        return []

    monkeypatch.setattr(gc, 'algo_get_output_fields', _fake_output_fields)

    mixin.ReportDataCaseMixin._build_case_basic_info(
        {'id': 'case-1', 'name': 'n', 'algorithm_type': ALGO_TYPE},
        [{'id': 1, 'api_id': 201, 'algorithm_result': {'asr': 'x'}}],
        {'id': 1},
    )
    assert seen == [201]
