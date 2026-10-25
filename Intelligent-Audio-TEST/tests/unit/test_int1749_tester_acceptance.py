# -*- coding: utf-8 -*-
"""INT-1749 执行侧 transform_type —— 测试工程师独立复测（真实 gRPC 跨进程）。

与开发侧单测的差别（本文件不复用其夹具）：

- 变换调用走**真实** ``AlgorithmQueryAclRepositoryImpl`` → 真实
  ``shared.clients._grpc_algo_audio.algo_convert_field_values`` → 本机
  回环 gRPC server 上的**真实** ``AlgorithmQueryServicer`` →
  ``FieldMappingQueryHandler.convert_field_values`` → 真实
  ``FieldTransformService``。两侧分别来自 api_test_service 与
  algorithm_service 两个包，等于把「跨服务一次批量 RPC」整段跑通；
- 服务端计数在 servicer 层（``ConvertFieldValues`` 进入次数），不是客户端
  假 ACL 的记账；
- 映射结构来自**真实** ``FieldMappingQueryHandler.get_field_definitions``
  （喂与 DB 列同口径的行，含 ``transform_type``）；
- 评估侧取值用**真实** ``RoundDataBuilderMixin._build_single_round`` 复算。
"""
from __future__ import annotations

import json
import os
from concurrent import futures
from types import SimpleNamespace

# shared.infrastructure.config 在 import 期校验 OSS 凭据（required=True）；
# 本文件只走变换链路，不触对象存储，按 db_bootstrap 的口径喂本地占位值。
os.environ.setdefault('OSS_ACCESS_KEY', 'intelligent_audio_test')
os.environ.setdefault('OSS_SECRET_KEY', 'intelligent_audio_test666')

import grpc
import pytest

from algorithm_service.interfaces.grpc.algorithm_query_servicer import (
    AlgorithmQueryServicer,
)
from shared.proto import algorithm_service_pb2 as _pb
from shared.proto import algorithm_service_pb2_grpc as _pb_grpc


# ---------------------------------------------------------------- 真实 gRPC

class _CountingServicer(AlgorithmQueryServicer):
    """真实 servicer + 服务端计数（验收 5 的调用次数证据在这里）。"""

    def __init__(self):
        super().__init__()
        self.batch_calls = 0
        self.batch_items = []
        self.batch_errors = []

    def ConvertFieldValues(self, request, context=None):
        self.batch_calls += 1
        try:
            items = json.loads(request.data or '{}').get('items') or []
        except Exception:  # pragma: no cover - 请求体异常
            items = None
        self.batch_items.append(items)
        resp = super().ConvertFieldValues(request, context)
        try:
            payload = json.loads(resp.data or '{}')
        except Exception:  # pragma: no cover
            payload = {}
        self.batch_errors.append(payload.get('errors') if isinstance(payload, dict) else None)
        return resp


@pytest.fixture
def grpc_servicer(monkeypatch):
    servicer = _CountingServicer()
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=2))
    _pb_grpc.add_AlgorithmQueryServiceServicer_to_server(servicer, server)
    port = server.add_insecure_port('127.0.0.1:0')
    server.start()
    channel = grpc.insecure_channel(f'127.0.0.1:{port}')
    stub = _pb_grpc.AlgorithmQueryServiceStub(channel)
    import shared.clients._grpc_stubs as stubs
    monkeypatch.setattr(stubs, 'get_algorithm_query_service_stub', lambda: stub)
    try:
        yield servicer
    finally:
        channel.close()
        server.stop(0)


# ---------------------------------------------------------------- 映射结构

def _api_params():
    return [
        {'code': 'reply_text', 'param_type': 'text', 'direction': 'output',
         'field_path': 'data.text'},
        {'code': 'reply_audio', 'param_type': 'text', 'direction': 'output',
         'field_path': 'data.audio'},
        {'code': 'plain', 'param_type': 'text', 'direction': 'output'},
    ]


def _mapping_rows(answer_transform='json_parse', audio_transform='base64'):
    rows = [
        {'source': 'api', 'source_param': 'reply_text', 'target_param': 'answer',
         'transform_type': answer_transform, 'dimension_id': 1,
         'dimension_name': 'llm_judge'},
        {'source': 'api', 'source_param': 'reply_audio', 'target_param': 'audio_out',
         'transform_type': audio_transform, 'dimension_id': 1,
         'dimension_name': 'llm_judge'},
        # case 来源：执行侧不负责、不变换（C0 裁定 1）
        {'source': 'case', 'source_param': 'query', 'target_param': 'question',
         'transform_type': 'json_parse', 'dimension_id': 1,
         'dimension_name': 'llm_judge'},
    ]
    return rows


def _field_mappings(monkeypatch, answer_transform='json_parse',
                    audio_transform='base64', api_params=None):
    """用真实 query handler 产出 original/mapped（喂 DB 同口径行）。"""
    from algorithm_service.application.queries import field_mapping_queries as q

    cache = SimpleNamespace(
        get_device_params=lambda algorithm_type: [],
        get_api_params=lambda algorithm_type, api_id=None: (
            _api_params() if api_params is None else api_params),
        get_reference_params=lambda algorithm_type: [],
        get_param_mapping=lambda algorithm_type, component, api_id=None: (
            _mapping_rows(answer_transform, audio_transform)
            if component == 'evaluation' else []),
        get_case_params=lambda algorithm_type: [],
    )
    monkeypatch.setattr(q, 'get_config_cache', lambda: cache)
    return q.FieldMappingQueryHandler.get_field_definitions('voice_llm')


# ---------------------------------------------------------------- 客户端替身

class _GrpcBackedAcl:
    """只把「变换」这一跳接到真实 ACL 实现，其余查询用固定映射。"""

    def __init__(self, field_mappings):
        from api_test_service.infrastructure.acl.algorithm_acl_repository import (
            AlgorithmQueryAclRepositoryImpl,
        )
        self._field_mappings = field_mappings
        self._impl = AlgorithmQueryAclRepositoryImpl()
        self.calls = []

    def get_field_mappings(self, algorithm_type, api_id=None):
        return self._field_mappings

    def get_device_params(self, *args, **kwargs):
        return []

    def get_api_params(self, *args, **kwargs):
        return []

    def get_param_mapping(self, *args, **kwargs):
        return []

    def convert_field_values(self, items):
        self.calls.append(list(items))
        return self._impl.convert_field_values(items)


def _session_executor():
    from api_test_service.core.api_session_executor import APISessionExecutor
    executor = object.__new__(APISessionExecutor)
    executor._executor = type('_Exec', (), {'_log': lambda *a, **k: None})()
    return executor


def _realtime_executor():
    from api_test_service.core.realtime_session_executor import RealtimeSessionExecutor
    return object.__new__(RealtimeSessionExecutor)


# ================================================================ 验收 1 / 2

def test_batch_rpc_json_parse_and_base64_over_real_grpc(grpc_servicer):
    """真实 ACL + 真实 gRPC + 真实 servicer：json_parse 出对象、base64 按编码。"""
    from api_test_service.infrastructure.acl.algorithm_acl_repository import (
        AlgorithmQueryAclRepositoryImpl,
    )
    acl = AlgorithmQueryAclRepositoryImpl()
    values = acl.convert_field_values([
        {'transform_type': 'json_parse', 'value': '{"a":1}'},
        {'transform_type': 'base64', 'value': 'abc'},
        {'transform_type': 'none', 'value': 'plain'},
    ])
    assert values == [{'a': 1}, 'YWJj', 'plain']
    assert grpc_servicer.batch_calls == 1          # 3 个值 1 次 RPC
    assert len(grpc_servicer.batch_items[0]) == 3


def test_invalid_json_keeps_original_and_reports_error(grpc_servicer):
    """非法 JSON：原值返回 + 服务端 errors 回传（不吞成空串、不抛异常）。"""
    from api_test_service.infrastructure.acl.algorithm_acl_repository import (
        AlgorithmQueryAclRepositoryImpl,
    )
    acl = AlgorithmQueryAclRepositoryImpl()
    values = acl.convert_field_values([
        {'transform_type': 'json_parse', 'value': '{bad'},
        {'transform_type': 'json_parse', 'value': '{"ok":2}'},
    ])
    assert values == ['{bad', {'ok': 2}]
    errors = grpc_servicer.batch_errors[0]
    assert errors and errors[0]['index'] == 0
    assert errors[0]['transform_type'] == 'json_parse'


def test_non_string_value_for_base64_keeps_original(grpc_servicer):
    """非字符串进 base64（dict）→ 原值保留 + error；空值保持转换自身语义。"""
    from api_test_service.infrastructure.acl.algorithm_acl_repository import (
        AlgorithmQueryAclRepositoryImpl,
    )
    acl = AlgorithmQueryAclRepositoryImpl()
    values = acl.convert_field_values([
        {'transform_type': 'base64', 'value': {'x': 1}},
        {'transform_type': 'base64', 'value': None},
        {'transform_type': 'json_parse', 'value': {'already': 'dict'}},
    ])
    assert values[0] == {'x': 1}
    assert values[2] == {'already': 'dict'}       # 非字符串原样返回，不当失败
    assert grpc_servicer.batch_errors[0][0]['index'] == 0


def test_http_multi_round_chain_output_transformed(monkeypatch, grpc_servicer):
    """HTTP 多轮：rounds[i].output 在写入前已变换（真实 gRPC 一跳）。"""
    mappings = _field_mappings(monkeypatch)
    acl = _GrpcBackedAcl(mappings)
    import api_test_service.core.api_session_executor as sess_mod
    monkeypatch.setattr(sess_mod, '_algo_acl', acl)

    round_result = {
        'round_number': 1,
        'answer_text': '{"a": 1}',
        'raw_response': {'data': {'text': '{"a": 1}', 'audio': 'abc'},
                         'plain': 'p'},
    }
    _session_executor()._attach_api_output_fields(
        round_result, mappings, 'voice_llm', 't-1749')

    assert round_result['output']['answer'] == {'a': 1}      # 验收 1
    assert round_result['output']['audio_out'] == 'YWJj'     # 验收 2（编码语义）
    assert round_result['output']['plain'] == 'p'            # 未配转换字段原样
    assert 'reply_text' not in round_result['output']        # 源键不残留
    assert round_result['output_fields']['reply_text'] == '{"a": 1}'
    assert grpc_servicer.batch_calls == 1
    assert len(grpc_servicer.batch_items[0]) == 2            # 验收 5：N 字段 1 次


def test_http_single_round_chain_output_transformed(monkeypatch, grpc_servicer):
    """HTTP 单轮：extract_final_result 同一变换入口。"""
    from api_test_service.core import api_task_runner as runner_mod

    mappings = _field_mappings(monkeypatch)
    acl = _GrpcBackedAcl(mappings)
    monkeypatch.setattr(runner_mod, '_algo_acl', acl)

    runner = runner_mod.APITaskRunner(type('_Exec', (), {
        '_log': lambda *a, **k: None})())
    result, _latency = runner.extract_final_result(
        1, {'json': {'code': 0, 'data': {'text': '{"a": 1}', 'audio': 'abc'}},
            'latency': 7}, 'voice_llm')

    assert result['answer'] == {'a': 1}
    assert result['audio_out'] == 'YWJj'
    assert grpc_servicer.batch_calls == 1


def test_realtime_chain_output_transformed(monkeypatch, grpc_servicer):
    """Realtime：WS 轮次 output 同样在写入前变换。"""
    # WS 聚合输出是扁平的：声明不带 field_path（按 param_code 取顶层键）
    flat_params = [
        {'code': 'reply_text', 'param_type': 'text', 'direction': 'output'},
        {'code': 'reply_audio', 'param_type': 'text', 'direction': 'output'},
    ]
    mappings = _field_mappings(monkeypatch, api_params=flat_params)
    acl = _GrpcBackedAcl(mappings)
    import api_test_service.core.realtime_session_executor as rt_mod
    monkeypatch.setattr(rt_mod, '_algo_acl', acl)

    out = _realtime_executor()._collect_eval_fields(
        {}, {'reply_text': '{"a": 1}', 'reply_audio': 'abc'}, 'voice_llm',
        text_output=None)
    assert out['answer'] == {'a': 1}
    assert out['audio_out'] == 'YWJj'
    assert grpc_servicer.batch_calls == 1


# ================================================================ 验收 3

def test_evaluation_side_reads_executed_value_unchanged(monkeypatch, grpc_servicer):
    """评估侧按 target_param 直接取，值与执行侧落库值逐字段一致（不二次变换）。"""
    from evaluation_service.domain.services.evaluation_service.round_data_builder import (
        RoundDataBuilderMixin,
    )

    mappings = _field_mappings(monkeypatch)
    acl = _GrpcBackedAcl(mappings)
    import api_test_service.core.api_session_executor as sess_mod
    monkeypatch.setattr(sess_mod, '_algo_acl', acl)

    round_result = {
        'round_number': 1,
        'answer_text': '{"a": 1}',
        'raw_response': {'data': {'text': '{"a": 1}', 'audio': 'abc'},
                         'plain': 'p'},
    }
    _session_executor()._attach_api_output_fields(
        round_result, mappings, 'voice_llm', 't-1749')
    executed = dict(round_result['output'])

    builder = RoundDataBuilderMixin()
    item = builder._build_single_round(
        {'output': executed, 'round_number': 1}, None,
        [{'source': 'api', 'source_param': 'reply_text', 'target_param': 'answer',
          'transform_type': 'json_parse', 'dimension_id': 1},
         {'source': 'api', 'source_param': 'reply_audio', 'target_param': 'audio_out',
          'transform_type': 'base64', 'dimension_id': 1}],
        'api', 'voice_llm', 't-1749', 'c-1',
        lambda algorithm_type: [], lambda *a, **k: {})

    assert item['answer'] == executed['answer'] == {'a': 1}
    assert item['audio_out'] == executed['audio_out'] == 'YWJj'
    assert {k: v for k, v in item.items() if k != 'round'} == {
        'answer': {'a': 1}, 'audio_out': 'YWJj'}


def test_evaluation_service_never_applies_transform():
    """静态守卫：evaluation_service 内不得出现变换调用（否则二次变换）。"""
    import pathlib
    root = pathlib.Path('evaluation_service')
    offenders = []
    for path in root.rglob('*.py'):
        text = path.read_text(encoding='utf-8', errors='ignore')
        for needle in ('apply_transform', 'ConvertFieldValues', 'convert_field_values'):
            if needle in text:
                offenders.append(f'{path}:{needle}')
    assert offenders == []


# ================================================================ 验收 4

@pytest.mark.parametrize('transform_type', ['none', None, ''])
def test_none_or_empty_transform_keeps_value(monkeypatch, grpc_servicer, transform_type):
    """none / 空 transform_type：值不变，且不进批量请求（改前行为）。"""
    from shared.utils.api_output_extractor import get_output_transform_types

    mappings = _field_mappings(monkeypatch, answer_transform=transform_type,
                               audio_transform=transform_type)
    assert get_output_transform_types(mappings) == {}

    acl = _GrpcBackedAcl(mappings)
    import api_test_service.core.api_session_executor as sess_mod
    monkeypatch.setattr(sess_mod, '_algo_acl', acl)

    round_result = {
        'round_number': 1,
        'answer_text': '{"a": 1}',
        'raw_response': {'data': {'text': '{"a": 1}', 'audio': 'abc'}},
    }
    _session_executor()._attach_api_output_fields(
        round_result, mappings, 'voice_llm', 't-1749')

    assert round_result['output']['answer'] == '{"a": 1}'    # 原字符串
    assert round_result['output']['audio_out'] == 'abc'
    assert acl.calls == []                                   # 未发起变换
    assert grpc_servicer.batch_calls == 0


# ================================================================ 降级

def test_algorithm_service_unavailable_degrades_to_original(monkeypatch):
    """算法服务不可达：整体按原值落库，用例不中断。"""
    from shared.clients.grpc_clients import algo_convert_field_values

    assert algo_convert_field_values([{'transform_type': 'json_parse',
                                       'value': '{"a":1}'}]) is None
    from api_test_service.infrastructure.acl.algorithm_acl_repository import (
        AlgorithmQueryAclRepositoryImpl,
    )
    assert AlgorithmQueryAclRepositoryImpl().convert_field_values(
        [{'transform_type': 'json_parse', 'value': '{"a":1}'}]) is None


# ================================================================ 落库边界

def test_multi_round_result_payload_carries_transformed_output(monkeypatch, grpc_servicer):
    """落库 payload 边界：提交给 task_service 的 rounds[i].output 已是变换后的值。

    真实链入口 → 真实 gRPC 变换 → ``APIResultProcessor.create_multi_round_test_result``
    组装 result_data（对象存储与 task_service 换替身，只验证写库前的 payload）。
    """
    from api_test_service.core import api_result_processor as proc_mod

    mappings = _field_mappings(monkeypatch)
    acl = _GrpcBackedAcl(mappings)
    import api_test_service.core.api_session_executor as sess_mod
    monkeypatch.setattr(sess_mod, '_algo_acl', acl)

    round_result = {
        'round_number': 1,
        'answer_text': '{"a": 1}',
        'success': True,
        'latency': 12,
        'raw_response': {'data': {'text': '{"a": 1}', 'audio': 'abc'}},
    }
    _session_executor()._attach_api_output_fields(
        round_result, mappings, 'voice_llm', 't-1749')

    captured = {}

    class _SinkAcl:
        def submit_result(self, task_id, result_data):
            captured.update(result_data)
            return 4242

    monkeypatch.setattr(proc_mod, 'write_result_data_file',
                        lambda *a, **k: 'oss://bucket/t-1749.json')
    monkeypatch.setattr(proc_mod, 'split_result_data', lambda data: (data, None))
    monkeypatch.setattr(proc_mod, '_task_data_acl', _SinkAcl())

    class _SilentLog:
        def __call__(self, *args, **kwargs):
            pass

    processor = proc_mod.APIResultProcessor(
        type('_Exec', (), {'_log': _SilentLog()})())
    monkeypatch.setattr(processor, '_finalize_task_case_status',
                        lambda **k: None)

    processor.create_multi_round_test_result(
        1, 'c-1', 9, 'voice_llm',
        {'total_latency': 12, 'round_count': 1,
         'algorithm_result': {'rounds': [round_result]}}, True)

    written = captured['algorithm_result']['rounds'][0]['output']
    assert written['answer'] == {'a': 1}
    assert written['audio_out'] == 'YWJj'
    # execution_steps 是同一条 rounds JSON，两处口径一致
    steps = json.loads(captured['execution_steps'])
    assert steps[0]['output']['answer'] == {'a': 1}
