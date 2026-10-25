# -*- coding: utf-8 -*-
"""INT-1749 守卫：transform_type 执行侧批量变换能力。

关注点：
1. 变换实现复用 algorithm_service.FieldTransformService（不复制到消费方）；
2. 批量入口 ``ConvertFieldValues`` 一次 RPC 处理 N 个字段（不逐字段 RPC）；
3. 非法输入策略：保留原值 + 错误回传 / WARNING，不抛异常、不静默吞成空串；
4. 执行侧批量应用（realtime 轮次评估入参）只发一次变换请求，失败按原值保留。

纯单测：不触 DB / OSS / Redis / 真实 gRPC（桩掉配置缓存与 gRPC stub）。
"""
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import json

import pytest

from algorithm_service.domain.services.field_transforms import FieldTransformService
from algorithm_service.application.queries.field_mapping_queries import (
    FieldMappingQueryHandler,
)


# ──────────────────────────── 1. 变换领域服务边界 ────────────────────────────

class TestApplyTransformWithError:
    def test_none_and_empty_are_passthrough(self):
        for transform_type in ('none', '', None):
            value, error = FieldTransformService.apply_transform_with_error(
                transform_type, 'any')
            assert value == 'any'
            assert error is None

    def test_json_parse_object(self):
        value, error = FieldTransformService.apply_transform_with_error(
            'json_parse', '{"a": 1, "b": [2, 3]}')
        assert value == {'a': 1, 'b': [2, 3]}
        assert error is None

    def test_json_parse_invalid_keeps_original_with_error(self):
        value, error = FieldTransformService.apply_transform_with_error(
            'json_parse', '{not json')
        # 不吞成空串：原值原样保留，错误可见
        assert value == '{not json'
        assert error and 'JSONDecodeError' in error

    def test_json_parse_non_string_passthrough(self):
        for raw in ({'a': 1}, [1, 2], 42, None):
            value, error = FieldTransformService.apply_transform_with_error(
                'json_parse', raw)
            assert value == raw
            assert error is None

    def test_base64(self):
        value, error = FieldTransformService.apply_transform_with_error(
            'base64', 'hello')
        assert value == 'aGVsbG8='
        assert error is None

    def test_to_int_invalid_keeps_original_with_error(self):
        value, error = FieldTransformService.apply_transform_with_error(
            'to_int', 'abc')
        assert value == 'abc'
        assert error and 'ValueError' in error

    def test_to_int_none_is_zero(self):
        value, error = FieldTransformService.apply_transform_with_error(
            'to_int', None)
        assert value == 0
        assert error is None

    def test_to_bool(self):
        assert FieldTransformService.apply_transform_with_error('to_bool', 'true')[0] is True
        assert FieldTransformService.apply_transform_with_error('to_bool', 'no')[0] is False
        assert FieldTransformService.apply_transform_with_error('to_bool', 0)[0] is False

    def test_to_string_none_is_empty_by_definition(self):
        value, error = FieldTransformService.apply_transform_with_error(
            'to_string', None)
        assert value == ''
        assert error is None

    def test_unknown_transform_keeps_original_with_error(self):
        value, error = FieldTransformService.apply_transform_with_error(
            'uppercase', 'abc')
        assert value == 'abc'
        assert error and 'uppercase' in error

    def test_apply_transform_keeps_legacy_signature(self):
        # 旧调用点（输入侧映射 / BuildApiRequestData）行为不变：仍返回转换结果
        assert FieldTransformService.apply_transform('json_parse', '{"a": 1}') == {'a': 1}
        assert FieldTransformService.apply_transform('to_int', 'abc') == 'abc'


# ──────────────────────────── 2. 批量应用处理器 ────────────────────────────

class TestConvertFieldValuesHandler:
    def test_order_preserved_and_errors_indexed(self):
        result = FieldMappingQueryHandler.convert_field_values([
            {'transform_type': 'json_parse', 'value': '{"a": 1}'},
            {'transform_type': 'none', 'value': 'plain'},
            {'transform_type': 'to_int', 'value': 'abc'},
            {'transform_type': 'base64', 'value': 'hi'},
        ])
        assert result['values'] == [{'a': 1}, 'plain', 'abc', 'aGk=']
        assert len(result['errors']) == 1
        assert result['errors'][0]['index'] == 2
        assert result['errors'][0]['transform_type'] == 'to_int'

    def test_empty_items(self):
        assert FieldMappingQueryHandler.convert_field_values([]) == {
            'values': [], 'errors': []}
        assert FieldMappingQueryHandler.convert_field_values(None) == {
            'values': [], 'errors': []}

    def test_non_dict_item_kept_with_error(self):
        result = FieldMappingQueryHandler.convert_field_values(['raw'])
        assert result['values'] == ['raw']
        assert result['errors'][0]['index'] == 0

    def test_none_transform_type_treated_as_none(self):
        result = FieldMappingQueryHandler.convert_field_values(
            [{'transform_type': None, 'value': [1, 2]}])
        assert result['values'] == [[1, 2]]
        assert result['errors'] == []


# ──────────────────────────── 3. servicer 批量 RPC ────────────────────────────

class TestConvertFieldValuesServicer:
    def test_batch_rpc_returns_values_and_errors(self):
        from algorithm_service.interfaces.grpc.algorithm_query_servicer import (
            AlgorithmQueryServicer,
        )
        from shared.proto import algorithm_service_pb2 as pb
        from shared.utils.grpc_json import loads

        servicer = AlgorithmQueryServicer()
        # 处理器为纯静态查询，无 DB 依赖；显式注入避免懒加载路径
        servicer._field_mapping_handler = FieldMappingQueryHandler

        request = pb.ConvertFieldValuesRequest(data=json.dumps({
            'items': [
                {'transform_type': 'json_parse', 'value': '{"k": "v"}'},
                {'transform_type': 'to_float', 'value': 'oops'},
            ]
        }, ensure_ascii=False))
        resp = servicer.ConvertFieldValues(request)

        assert resp.success is True
        data = loads(resp.data, {})
        assert data['values'] == [{'k': 'v'}, 'oops']
        assert data['errors'][0]['index'] == 1


# ──────────────────────────── 4. 客户端封装只发一次 RPC ────────────────────────────

class TestBatchClient:
    def test_single_rpc_for_n_values(self, monkeypatch):
        from shared.clients import _grpc_algo_audio as client_mod
        from shared.utils.grpc_json import dumps

        calls = []

        def fake_call(method_name, **kwargs):
            calls.append((method_name, kwargs))
            payload = json.loads(kwargs['data'])
            # 服务端语义：逐项应用，返回同序 values
            values = [FieldTransformService.apply_transform(
                item.get('transform_type'), item.get('value'))
                for item in payload['items']]
            return json.loads(dumps({'values': values, 'errors': []}))

        monkeypatch.setattr(client_mod, '_call_algo_query_rpc', fake_call)
        values = client_mod.algo_convert_field_values([
            {'transform_type': 'json_parse', 'value': '{"a": 1}'},
            {'transform_type': 'none', 'value': 'x'},
            {'transform_type': 'to_int', 'value': '7'},
        ])
        assert values == [{'a': 1}, 'x', 7]
        assert len(calls) == 1
        assert calls[0][0] == 'ConvertFieldValues'

    def test_returns_none_when_rpc_fails(self, monkeypatch):
        from shared.clients import _grpc_algo_audio as client_mod
        monkeypatch.setattr(client_mod, '_call_algo_query_rpc',
                            lambda *a, **kw: None)
        assert client_mod.algo_convert_field_values(
            [{'transform_type': 'none', 'value': 1}]) is None


# ──────────────────────────── 5. ACL 批量封装 ────────────────────────────

class TestAclBatch:
    def test_length_mismatch_returns_none(self, monkeypatch):
        from api_test_service.infrastructure.acl import algorithm_acl_repository as mod
        import shared.clients.grpc_clients as gc

        monkeypatch.setattr(gc, 'algo_convert_field_values', lambda items: ['only-one'])
        acl = mod.AlgorithmQueryAclRepositoryImpl()
        assert acl.convert_field_values([
            {'transform_type': 'none', 'value': 1},
            {'transform_type': 'none', 'value': 2},
        ]) is None

    def test_success_passthrough(self, monkeypatch):
        from api_test_service.infrastructure.acl import algorithm_acl_repository as mod
        import shared.clients.grpc_clients as gc

        monkeypatch.setattr(gc, 'algo_convert_field_values',
                            lambda items: [item['value'] for item in items])
        acl = mod.AlgorithmQueryAclRepositoryImpl()
        assert acl.convert_field_values([
            {'transform_type': 'none', 'value': 1},
            {'transform_type': 'none', 'value': 2},
        ]) == [1, 2]


# ──────────────────────────── 6. 线上契约：客户端 ↔ servicer 真 gRPC 走通 ────────────────────────────

class TestBatchRpcOverWire:
    """proto 重新生成后客户端/服务端 stub 一致性守卫（本机回环，不连 docker）。"""

    def test_batch_rpc_over_grpc(self, monkeypatch):
        from concurrent import futures

        import grpc

        from shared.proto import algorithm_service_pb2_grpc as pb_grpc
        from shared.clients import _grpc_stubs
        from algorithm_service.interfaces.grpc.algorithm_query_servicer import (
            AlgorithmQueryServicer,
        )

        server = grpc.server(futures.ThreadPoolExecutor(max_workers=2))
        pb_grpc.add_AlgorithmQueryServiceServicer_to_server(
            AlgorithmQueryServicer(), server)
        port = server.add_insecure_port('127.0.0.1:0')
        server.start()
        try:
            channel = grpc.insecure_channel(f'127.0.0.1:{port}')
            stub = pb_grpc.AlgorithmQueryServiceStub(channel)
            monkeypatch.setattr(
                _grpc_stubs, 'get_algorithm_query_service_stub', lambda: stub)

            from shared.clients._grpc_algo_audio import algo_convert_field_values
            values = algo_convert_field_values([
                {'transform_type': 'json_parse', 'value': '{"a": 1}'},
                {'transform_type': 'base64', 'value': 'hi'},
            ])
            assert values == [{'a': 1}, 'aGk=']
        finally:
            server.stop(0)


# ──────────────────────────── 7. 执行侧批量应用（realtime 轮次评估入参） ────────────────────────────

class TestEvalOutputTransformService:
    """执行侧唯一变换点：{target_param: value} + transform_type → 一次批量 RPC。"""

    def _acl(self, values):
        class _Acl:
            def __init__(self):
                self.calls = []

            def convert_field_values(inner, items):  # noqa: N805
                inner.calls.append(items)
                return values
        return _Acl()

    def test_only_non_none_targets_sent_in_one_call(self):
        from api_test_service.domain.services.eval_output_transform_service import (
            EvalOutputTransformService,
        )
        acl = self._acl([{'a': 1}])
        fields = {'answer': '{"a": 1}', 'query': 'q', 'latency': 3}
        EvalOutputTransformService.apply(
            fields,
            {'answer': 'json_parse', 'query': 'none', 'latency': None},
            acl)
        assert acl.calls == [[{'transform_type': 'json_parse',
                               'value': '{"a": 1}'}]]
        assert fields == {'answer': {'a': 1}, 'query': 'q', 'latency': 3}

    def test_no_transform_config_no_rpc(self):
        from api_test_service.domain.services.eval_output_transform_service import (
            EvalOutputTransformService,
        )
        acl = self._acl([None])
        fields = {'query': 'q'}
        assert EvalOutputTransformService.apply(
            fields, {'query': 'none'}, acl) == {'query': 'q'}
        assert acl.calls == []

    def test_acl_unavailable_keeps_originals(self):
        from api_test_service.domain.services.eval_output_transform_service import (
            EvalOutputTransformService,
        )
        acl = self._acl(None)
        fields = {'answer': 'raw'}
        EvalOutputTransformService.apply(
            fields, {'answer': 'json_parse'}, acl)
        assert fields == {'answer': 'raw'}
        assert len(acl.calls) == 1


class _FakeAlgoAcl:
    def __init__(self, field_mappings, values=None):
        self._field_mappings = field_mappings
        self._values = values
        self.calls = []

    def get_field_mappings(self, algorithm_type):
        return self._field_mappings

    def convert_field_values(self, items):
        self.calls.append(items)
        if self._values is None:
            return None
        return self._values


def _make_executor():
    """绕过 __init__ 构造执行器实例：被测方法不依赖实例状态。"""
    from api_test_service.core.realtime_session_executor import RealtimeSessionExecutor
    return object.__new__(RealtimeSessionExecutor)


def _field_mappings_with_transform():
    return {
        'original': {
            'evaluation': {
                'output': {
                    'answer': {'source': 'api', 'source_param': 'asr_text',
                               'transform_type': 'json_parse'},
                    'query': {'source': 'case', 'source_param': 'question',
                              'transform_type': 'none'},
                }
            },
            'api': {'output': {'asr_text': {'code': 'asr_text'}}},
        }
    }


class TestRealtimeCollectEvalFieldsTransform:
    def test_applies_transform_in_one_batch_call(self, monkeypatch):
        import api_test_service.core.realtime_session_executor as mod

        acl = _FakeAlgoAcl(_field_mappings_with_transform(),
                           values=[{'text': 'hello'}])
        monkeypatch.setattr(mod, '_algo_acl', acl)
        executor = _make_executor()

        fields = executor._collect_eval_fields(
            {'question': 'q1'}, {'asr_text': '{"text": "hello"}'}, 'voice_llm')

        # 只有配了非 none 变换的 target_param 进批量请求，且只发一次
        assert acl.calls == [[{'transform_type': 'json_parse',
                               'value': '{"text": "hello"}'}]]
        # C1（INT-1746）结构：output 内只有映射后的 target_param，
        # 源键不残留；case 来源由评估侧按轮加载，不进执行侧 output
        assert fields == {'answer': {'text': 'hello'}}

    def test_no_transform_config_skips_rpc(self, monkeypatch):
        import api_test_service.core.realtime_session_executor as mod

        mappings = _field_mappings_with_transform()
        mappings['original']['evaluation']['output']['answer']['transform_type'] = 'none'
        acl = _FakeAlgoAcl(mappings)
        monkeypatch.setattr(mod, '_algo_acl', acl)
        executor = _make_executor()

        fields = executor._collect_eval_fields(
            {'question': 'q1'}, {'asr_text': 'raw'}, 'voice_llm')
        assert acl.calls == []
        assert fields['answer'] == 'raw'

    def test_rpc_failure_keeps_original_values(self, monkeypatch):
        import api_test_service.core.realtime_session_executor as mod

        acl = _FakeAlgoAcl(_field_mappings_with_transform(), values=None)
        monkeypatch.setattr(mod, '_algo_acl', acl)
        executor = _make_executor()

        fields = executor._collect_eval_fields(
            {'question': 'q1'}, {'asr_text': '{"text": "hello"}'}, 'voice_llm')
        assert len(acl.calls) == 1
        assert fields['answer'] == '{"text": "hello"}'
