# -*- coding: utf-8 -*-
"""INT-2299：``GET /algorithm/params?device_id=`` 返回三层解析结果 + 层来源标识。

契约（卡面 C1~C6）：

- C1 入参：``device_id: Optional[int] = Field(None, ge=1)``；``device_id < 1`` /
  非整数走既有 ValidationError 出口 422；带 ``device_id`` 但 ``algorithm_type``
  为空、或 ``param_type != 'device'`` → 400。
- C2 两条路径：不带 ``device_id`` 仍走 task_service ``ListParams``（原始行 + 分页
  信封）；带 ``device_id`` 走 algorithm_service ``GetDeviceParamsList``（裸数组）。
- C3 行契约：每行 ``resolved_from`` ∈ {algorithm, profile, device}；策略层行额外带
  ``profile_param_id`` 且 ``id`` 置空（``param_profile_params`` 与
  ``algorithm_device_params`` 自增可能同号，写侧按 ``param_type_source`` 选表会
  静默打到同号设备行上）。
- C5 打标只在 ``device_id`` 非空分支做；为空分支输出与改造前逐字节一致，且不得
  原地改快照行（否则污染 no-device 与执行链路）。
- C6 ``DeviceParamDTO`` 补 ``device_id``，no-device 响应恢复识别本设备覆盖行。

解析用例用 ``object.__new__(AlgorithmConfigCache)`` 直接安装快照，不连库。
"""
import json
import os
from types import SimpleNamespace
from unittest.mock import MagicMock

# BaseConfig 在 import 时校验环境变量（本用例不触库，与仓库既有测试同款兜底）
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest  # noqa: E402
from pydantic import ValidationError  # noqa: E402

from algorithm_service.infrastructure.persistence.config_cache import (  # noqa: E402
    AlgorithmConfigCache,
    ParamResolvedFrom,
)
from api_gateway.schemas._algorithm_param_schemas import (  # noqa: E402
    AlgorithmParamListQuery,
)

ALGO = 'ut_int2299_algo'
DEVICE = 801
OTHER_DEVICE = 802
PROFILE = 91

# 算法类型级默认行（device_id IS NULL）
ALGO_LEVEL_ROWS = [
    {'id': 1001, 'algorithm_type': ALGO, 'param_code': 'shared_key',
     'param_name': '算法级-同键', 'param_type': 'text', 'direction': 'input',
     'ui_order': 1},
    {'id': 1002, 'algorithm_type': ALGO, 'param_code': 'algo_only',
     'param_name': '算法级独有', 'param_type': 'text', 'direction': 'output',
     'ui_order': 2},
]

# 设备绑定策略行（param_profile_params，独立自增序列）
PROFILE_ROWS = [
    {'id': 2001, 'algorithm_type': ALGO, 'param_code': 'shared_key',
     'param_name': '策略-同键', 'param_type': 'audio_stream', 'direction': 'input',
     'ui_order': 1},
    {'id': 2002, 'algorithm_type': ALGO, 'param_code': 'profile_only',
     'param_name': '策略独有', 'param_type': 'text', 'direction': 'input',
     'ui_order': 3},
    {'id': 2003, 'algorithm_type': ALGO, 'param_code': 'device_wins',
     'param_name': '策略-被设备覆盖', 'param_type': 'text', 'direction': 'input',
     'ui_order': 4},
]

# 本设备覆盖行（algorithm_device_params，device_id 非空）
DEVICE_ROWS = [
    {'id': 3001, 'algorithm_type': ALGO, 'param_code': 'shared_key',
     'param_name': '设备覆盖-同键', 'param_type': 'audio_stream',
     'direction': 'input', 'device_id': DEVICE, 'ui_order': 1},
    {'id': 3002, 'algorithm_type': ALGO, 'param_code': 'device_wins',
     'param_name': '设备覆盖-策略同键', 'param_type': 'text',
     'direction': 'input', 'device_id': DEVICE, 'ui_order': 4},
    {'id': 3003, 'algorithm_type': ALGO, 'param_code': 'device_out',
     'param_name': '设备独有输出', 'param_type': 'text',
     'direction': 'output', 'device_id': DEVICE, 'ui_order': 5},
    # 其它设备的覆盖行不得串进来
    {'id': 3009, 'algorithm_type': ALGO, 'param_code': 'other_device_only',
     'param_name': '别的设备', 'param_type': 'text', 'direction': 'input',
     'device_id': OTHER_DEVICE, 'ui_order': 9},
]


def _cache(bind_device=DEVICE, profile_algorithm_type=ALGO) -> AlgorithmConfigCache:
    """装快照：算法级 + 策略 + 本设备覆盖。"""
    cache = object.__new__(AlgorithmConfigCache)
    bindings = {bind_device: PROFILE} if bind_device is not None else {}
    cache._config_cache = {
        'algorithms': {},
        'device_params': {
            ALGO: AlgorithmConfigCache._serialize_params(ALGO_LEVEL_ROWS + DEVICE_ROWS),
        },
        'api_params': {ALGO: []},
        'case_params': {ALGO: []},
        'reference_params': {ALGO: []},
        'evaluation_dimension_params': {},
        'mappings': {ALGO: {}},
        'profile_params': {
            PROFILE: AlgorithmConfigCache._serialize_params(PROFILE_ROWS),
        },
        'profile_mappings': {},
        'api_bindings': {},
        'device_bindings': bindings,
        'profile_algorithm_types': {PROFILE: profile_algorithm_type},
    }
    return cache


def _by_code(rows):
    return {(row['direction'], row['code']): row for row in rows}


# ---------------------------------------------------------------- C3 三层打标

def test_three_layers_are_tagged_with_their_source():
    """① 仅策略层有、② 策略与设备覆盖同键、③ 仅算法级的键各归其层。"""
    rows = _cache().get_device_params(ALGO, DEVICE)
    by_key = _by_code(rows)

    # ③ 仅算法级
    assert by_key[('output', 'algo_only')]['resolved_from'] == ParamResolvedFrom.ALGORITHM
    assert by_key[('output', 'algo_only')]['id'] == 1002

    # ① 仅策略层有
    profile_row = by_key[('input', 'profile_only')]
    assert profile_row['resolved_from'] == ParamResolvedFrom.PROFILE
    assert profile_row['name'] == '策略独有'

    # ② 策略与设备覆盖同键 → 取设备覆盖值
    device_row = by_key[('input', 'device_wins')]
    assert device_row['resolved_from'] == ParamResolvedFrom.DEVICE
    assert device_row['name'] == '设备覆盖-策略同键'

    # 同键三层的 shared_key：设备覆盖最优先
    shared = by_key[('input', 'shared_key')]
    assert shared['resolved_from'] == ParamResolvedFrom.DEVICE
    assert shared['name'] == '设备覆盖-同键'

    # 其它设备的行不串进来
    assert ('input', 'other_device_only') not in by_key


def test_profile_layer_row_has_null_id_and_profile_param_id():
    """策略行 id 与设备参数行各自自增、可能同号：置空并另带 profile_param_id。"""
    profile_row = _by_code(_cache().get_device_params(ALGO, DEVICE))[('input', 'profile_only')]
    assert profile_row['id'] is None
    assert profile_row['profile_param_id'] == 2002

    # algorithm / device 层行 id 原样保留（都来自 algorithm_device_params，可写）
    by_key = _by_code(_cache().get_device_params(ALGO, DEVICE))
    assert by_key[('output', 'algo_only')]['id'] == 1002
    assert by_key[('input', 'shared_key')]['id'] == 3001
    # 非策略层行不带 profile_param_id
    assert 'profile_param_id' not in by_key[('input', 'shared_key')]


def test_unbound_device_has_no_profile_layer():
    """未绑定策略的设备：只有 algorithm / device 两层，不存在 profile 标记。"""
    rows = _cache(bind_device=None).get_device_params(ALGO, DEVICE)
    layers = {row['resolved_from'] for row in rows}
    assert layers == {ParamResolvedFrom.ALGORITHM, ParamResolvedFrom.DEVICE}
    by_key = _by_code(rows)
    # 算法级同键行未被策略改名
    assert by_key[('input', 'shared_key')]['name'] == '设备覆盖-同键'


def test_profile_of_other_algorithm_type_is_skipped():
    """INT-2259：策略声明的算法类型不匹配时不参与合并，本卡只加打标不改判定。"""
    rows = _cache(profile_algorithm_type='ut_other_algo').get_device_params(ALGO, DEVICE)
    by_key = _by_code(rows)
    assert ('input', 'profile_only') not in by_key
    assert ParamResolvedFrom.PROFILE not in {row['resolved_from'] for row in rows}


# ---------------------------------------------------------------- C5 无污染

def test_no_device_path_is_byte_identical_and_untagged():
    """device_id 为空：输出与改造前一致（原始行、无新增键），且行未被复制。"""
    cache = _cache()
    snapshot_rows = cache._config_cache['device_params'][ALGO]
    level_rows = [row for row in snapshot_rows if row.get('device_id') is None]

    result = cache.get_device_params(ALGO)

    assert result == level_rows
    for row in result:
        assert 'resolved_from' not in row
        assert 'profile_param_id' not in row
    # 逐字节一致的最强形式：返回的就是快照里的对象本身（未复制、未写键）
    assert all(a is b for a, b in zip(result, level_rows))


def test_device_scoped_call_does_not_pollute_snapshot_or_no_device_path():
    """打标必须 dict(row) 复制后写：快照行与后续 no-device 调用都不得带新键。"""
    cache = _cache()
    before = [dict(row) for row in cache.get_device_params(ALGO)]

    cache.get_device_params(ALGO, DEVICE)

    # 快照行本身没被写进层标识
    for row in cache._config_cache['device_params'][ALGO]:
        assert 'resolved_from' not in row
        assert 'profile_param_id' not in row
    for row in cache._config_cache['profile_params'][PROFILE]:
        assert 'resolved_from' not in row
        assert 'profile_param_id' not in row
    # 再查 no-device 路径输出与打标前逐行相同
    assert cache.get_device_params(ALGO) == before


def test_profile_row_id_is_not_nulled_in_snapshot():
    """策略层行 id 置空只发生在输出副本上，快照里的 profile id 不变。"""
    cache = _cache()
    _by_code(cache.get_device_params(ALGO, DEVICE))
    snapshot_ids = [row['id'] for row in cache._config_cache['profile_params'][PROFILE]]
    assert snapshot_ids == [2001, 2002, 2003]


# ---------------------------------------------------------------- gRPC 往返

def test_servicer_roundtrip_preserves_layer_fields():
    """gRPC 行 → JSON → 响应：resolved_from / profile_param_id / id=null 不被吞。"""
    from algorithm_service.interfaces.grpc.algorithm_query_servicer import (
        AlgorithmQueryServicer,
    )
    from shared.proto import algorithm_service_pb2 as algo_pb

    servicer = AlgorithmQueryServicer()
    servicer._config_handler = _cache()

    resp = servicer.GetDeviceParamsList(algo_pb.GetDeviceParamsListRequest(
        algorithm_type=ALGO, device_id=DEVICE))
    assert resp.success is True
    rows = json.loads(resp.data)
    by_key = {(row['direction'], row['code']): row for row in rows}

    assert isinstance(rows, list)  # 裸数组，不套分页信封
    assert by_key[('input', 'profile_only')]['resolved_from'] == 'profile'
    assert by_key[('input', 'profile_only')]['profile_param_id'] == 2002
    assert by_key[('input', 'profile_only')]['id'] is None
    assert by_key[('input', 'shared_key')]['resolved_from'] == 'device'


def test_servicer_without_device_id_is_untagged():
    """旧调用方（无 device_id）走 presence 缺失分支，输出保持算法级口径。"""
    from algorithm_service.interfaces.grpc.algorithm_query_servicer import (
        AlgorithmQueryServicer,
    )
    from shared.proto import algorithm_service_pb2 as algo_pb

    servicer = AlgorithmQueryServicer()
    servicer._config_handler = _cache()

    resp = servicer.GetDeviceParamsList(
        algo_pb.GetDeviceParamsListRequest(algorithm_type=ALGO))
    rows = json.loads(resp.data)
    assert [row['code'] for row in rows] == ['shared_key', 'algo_only']
    assert all('resolved_from' not in row for row in rows)


# ---------------------------------------------------------------- C1 入参校验

@pytest.mark.parametrize('raw', [0, -1, 'abc'])
def test_invalid_device_id_is_rejected_with_422(raw):
    """device_id < 1 或非整数 → pydantic ValidationError（由 error_handlers 转 422）。"""
    with pytest.raises(ValidationError):
        AlgorithmParamListQuery.model_validate({'device_id': raw})


def test_param_type_defaults_to_device():
    """?device_id=N 等价 ?param_type=device&device_id=N。"""
    query = AlgorithmParamListQuery.model_validate({'device_id': 801})
    assert query.param_type == 'device'
    assert query.device_id == 801


class _FakeArgs:
    def __init__(self, params):
        self._params = params

    def to_dict(self):
        return dict(self._params)


class _FakeRequest:
    def __init__(self, params):
        self.args = _FakeArgs(params)


def _gateway_service(monkeypatch, params):
    from api_gateway.application.services.algorithm import algorithm_query_service as aqs

    acl = MagicMock(name='algorithm_acl')
    acl.get_device_params.return_value = {
        'success': True, 'message': '', 'data': [{'code': 'x', 'resolved_from': 'device'}]}
    acl.list_params.return_value = {
        'success': True, 'message': '',
        'data': {'items': [], 'total': 0, 'page': 1, 'per_page': 1, 'pages': 1}}
    monkeypatch.setattr(aqs, '_algorithm_acl', acl)
    monkeypatch.setattr(aqs, 'request', _FakeRequest(params))
    return aqs, acl


def test_gateway_routes_device_id_to_device_params_acl(monkeypatch):
    """带 device_id → 新 ACL 方法，透传 algorithm_type / device_id，响应为裸数组。"""
    aqs, acl = _gateway_service(monkeypatch, {
        'algorithm_type': ALGO, 'param_type': 'device', 'device_id': str(DEVICE)})

    payload, http = aqs.AlgorithmQueryService.list_params()

    assert http == 200
    assert payload['data'] == [{'code': 'x', 'resolved_from': 'device'}]
    acl.get_device_params.assert_called_once_with(
        algorithm_type=ALGO, device_id=DEVICE)
    acl.list_params.assert_not_called()


def test_gateway_without_device_id_keeps_task_service_path(monkeypatch):
    """不带 device_id → 仍走 task_service ListParams（原始行 + 信封）。"""
    aqs, acl = _gateway_service(monkeypatch, {'algorithm_type': ALGO})

    payload, http = aqs.AlgorithmQueryService.list_params()

    assert http == 200
    assert payload['data'] == {'items': [], 'total': 0, 'page': 1,
                               'per_page': 1, 'pages': 1}
    acl.list_params.assert_called_once_with(algorithm_type=ALGO, param_type='device')
    acl.get_device_params.assert_not_called()


@pytest.mark.parametrize('params', [
    # 带 device_id 但无 algorithm_type
    {'param_type': 'device', 'device_id': '801'},
    # 带 device_id 且 param_type != device
    {'algorithm_type': ALGO, 'param_type': 'api', 'device_id': '801'},
    {'algorithm_type': ALGO, 'param_type': 'api', 'api_id': '9', 'device_id': '801'},
    {'algorithm_type': ALGO, 'param_type': 'case', 'device_id': '801'},
])
def test_gateway_semantic_conflicts_are_400(monkeypatch, params):
    aqs, acl = _gateway_service(monkeypatch, params)

    payload, http = aqs.AlgorithmQueryService.list_params()

    assert http == 400
    assert payload['success'] is False
    acl.get_device_params.assert_not_called()
    acl.list_params.assert_not_called()
    acl.get_api_params.assert_not_called()


def test_gateway_param_type_api_without_device_id_unchanged(monkeypatch):
    """param_type=api 且无 device_id 的既有 400 校验不受影响。"""
    aqs, acl = _gateway_service(monkeypatch, {'algorithm_type': ALGO, 'param_type': 'api'})

    payload, http = aqs.AlgorithmQueryService.list_params()

    assert http == 400
    assert 'api_id' in payload['message']
    acl.get_api_params.assert_not_called()


# ---------------------------------------------------------------- 执行链路回归

def _strip_layer_fields(rows):
    """把打标结果还原成改造前的行形态（去掉两个新键、恢复策略行 id）。"""
    out = []
    for row in rows:
        clean = {k: v for k, v in row.items()
                 if k not in ('resolved_from', 'profile_param_id')}
        if row['resolved_from'] == ParamResolvedFrom.PROFILE:
            clean['id'] = row['profile_param_id']
        out.append(clean)
    return out


def test_execution_chain_consumers_are_unaffected_by_layer_fields(monkeypatch):
    """既有带 device_id 的消费方只读 code / param_type / direction / ui_group。

    验收 4：打标行（含策略行 ``id=None``）与还原前的行喂给真实消费方，输出必须一致。
    """
    from shared.clients import _grpc_algo_audio
    from shared.infrastructure.base_executor._results_mixin import (
        _get_algorithm_output_keys,
    )

    tagged = _cache().get_device_params(ALGO, DEVICE)
    clean = _strip_layer_fields(tagged)

    class _Acl:
        def __init__(self, rows):
            self._rows = rows

        def get_device_params(self, algorithm_type, device_id=None):
            assert device_id == DEVICE
            return self._rows

    # 1) base_executor：输出键派生（direction / source_lang / target_lang）
    assert _get_algorithm_output_keys(ALGO, algo_acl=_Acl(tagged), device_id=DEVICE) \
        == _get_algorithm_output_keys(ALGO, algo_acl=_Acl(clean), device_id=DEVICE)

    # 2) shared ACL：设备输出声明派生
    def _output_fields(rows):
        monkeypatch.setattr(
            _grpc_algo_audio, 'algo_get_device_params',
            lambda algorithm_type, device_id=None: rows)
        return _grpc_algo_audio.algo_get_device_output_fields(ALGO, DEVICE)

    tagged_fields = _output_fields(tagged)
    assert tagged_fields == _output_fields(clean)
    assert [f['source_param'] for f in tagged_fields] == ['algo_only', 'device_out']


# ---------------------------------------------------------------- C6 DTO 补字段

def test_device_param_dto_carries_device_id():
    """no-device 响应每行新增 device_id：算法级 null、设备级为 int。"""
    from dataclasses import asdict

    from task_service.domain.dto.task_acl_dto import DeviceParamDTO

    level = asdict(DeviceParamDTO(id=1, algorithm_type=ALGO, param_code='a'))
    assert level['device_id'] is None
    scoped = asdict(DeviceParamDTO(id=2, algorithm_type=ALGO, param_code='b',
                                   device_id=DEVICE))
    assert scoped['device_id'] == DEVICE
    # 其余 13 个键不变
    assert len(level) == 14
