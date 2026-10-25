# -*- coding: utf-8 -*-
"""INT-1789（A1）gRPC 传输层 / 适配器 / 流式道策略单测。

覆盖卡面 §六 单测要求：
- descriptor 加载（含 import 白名单、体积上限、method_kind 交叉校验）；
- JSON → message（ParseDict）；
- `MessageToDict(preserving_proto_field_name=True)` 字段名保持 snake_case；
- gRPC status → biz_code 映射（含 4 类异常分类）；
- unary / server-stream / bidi 三形态真实调用（进程内 mock gRPC 服务）；
- 流式道策略：server-stream 推 3 条消息 → rounds 3 轮；bidi 2 轮会话。
"""
import concurrent.futures
import os
import time

# 与 tests/unit/test_int1799_* 同口径：导入 adapters 包会拉起 BaseConfig，
# 先给必需键兜底（pytest conftest 的 OSS_ENDPOINT 断网守卫仍生效）。
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import grpc
import pytest
from google.protobuf import message_factory

from shared.models.common_enums import (
    APIProtocol,
    AdapterProtocol,
    AVAILABLE_PROTOCOL_STREAMING,
    is_protocol_streaming_available,
    lane_of,
    ExecutionLane,
)
from shared.utils.error_mapping import (
    GRPC_STATUS_TO_BIZ,
    grpc_error_fields,
    grpc_status_to_biz,
)

from api_test_service.infrastructure.adapters.transport.grpc_client import (
    GrpcBidiSession,
    GrpcCallError,
    GrpcClient,
    GrpcMethodKindError,
    GrpcProtoError,
    clear_proto_cache,
    compile_proto,
    load_compiled_proto,
    message_to_payload,
    parse_request,
    validate_metadata,
    validate_proto_imports,
)
from api_test_service.infrastructure.adapters.registry import infer_protocol

ECHO_PROTO = """\
syntax = "proto3";
package int1789;

message EchoRequest {
  string session_id = 1;
  int32 round_number = 2;
  string input_text = 3;
}

message EchoResponse {
  string session_id = 1;
  string text_result = 2;
  bool is_sentence_end = 3;
  bool session_finished = 4;
  int32 round_number = 5;
}

service EchoService {
  rpc Unary (EchoRequest) returns (EchoResponse);
  rpc ServerStream (EchoRequest) returns (stream EchoResponse);
  rpc Bidi (stream EchoRequest) returns (stream EchoResponse);
  rpc NotRegistered (EchoRequest) returns (EchoResponse);
}
"""


# ── mock gRPC 服务 ──────────────────────────────────────────────────────
class _EchoServer:
    def __init__(self, proto_bytes: bytes, delay_seconds: float = 0.0):
        self.compiled = load_compiled_proto(proto_bytes)
        self.delay = delay_seconds
        self.server = grpc.server(
            concurrent.futures.ThreadPoolExecutor(max_workers=4))
        service = self.compiled.pool.FindServiceByName('int1789.EchoService')
        input_cls = message_factory.GetMessageClass(service.methods_by_name['Unary'].input_type)
        output_cls = message_factory.GetMessageClass(service.methods_by_name['Unary'].output_type)
        self.input_cls = input_cls
        self.output_cls = output_cls

        def _resp(req, *, text=None, finished=False, rnd=None):
            return output_cls(
                session_id=req.session_id,
                text_result=text if text is not None else (req.input_text + '-ok'),
                is_sentence_end=True,
                session_finished=finished,
                round_number=rnd if rnd is not None else req.round_number,
            )

        def unary(req, context):
            if self.delay:
                time.sleep(self.delay)
            return _resp(req)

        def server_stream(req, context):
            for index in range(3):
                yield _resp(req, text=f'msg{index}', rnd=index + 1)

        def bidi(req_iter, context):
            for req in req_iter:
                yield _resp(req, finished=(req.input_text == 'bye'))

        handlers = {
            'Unary': grpc.unary_unary_rpc_method_handler(
                unary,
                request_deserializer=input_cls.FromString,
                response_serializer=output_cls.SerializeToString),
            'ServerStream': grpc.unary_stream_rpc_method_handler(
                server_stream,
                request_deserializer=input_cls.FromString,
                response_serializer=output_cls.SerializeToString),
            'Bidi': grpc.stream_stream_rpc_method_handler(
                bidi,
                request_deserializer=input_cls.FromString,
                response_serializer=output_cls.SerializeToString),
            # NotRegistered 故意不注册 → UNIMPLEMENTED (12)
        }
        generic = grpc.method_handlers_generic_handler(
            'int1789.EchoService', handlers)
        self.server.add_generic_rpc_handlers((generic,))
        port = self.server.add_insecure_port('127.0.0.1:0')
        self.target = f'127.0.0.1:{port}'
        self.server.start()

    def stop(self):
        self.server.stop(0)


@pytest.fixture(scope='module')
def echo_server():
    clear_proto_cache()
    server = _EchoServer(ECHO_PROTO.encode('utf-8'))
    yield server
    server.stop()
    clear_proto_cache()


def _method(server, name, kind):
    return server.compiled.find_method('int1789.EchoService', name, kind)


# ── descriptor / proto 安全面 ──────────────────────────────────────────
class TestDescriptor:

    def test_compile_and_find_method(self):
        clear_proto_cache()
        compiled = compile_proto(ECHO_PROTO.encode('utf-8'))
        method = compiled.find_method('int1789.EchoService', 'Unary', 'unary')
        assert method.kind == 'unary'
        assert method.path == '/int1789.EchoService/Unary'
        assert method.input_class.DESCRIPTOR.name == 'EchoRequest'

    def test_streaming_kinds_detected(self):
        compiled = compile_proto(ECHO_PROTO.encode('utf-8'))
        assert compiled.find_method(
            'int1789.EchoService', 'ServerStream', 'server_stream').kind == 'server_stream'
        assert compiled.find_method(
            'int1789.EchoService', 'Bidi', 'bidi').kind == 'bidi'

    def test_method_kind_mismatch_rejected(self):
        compiled = compile_proto(ECHO_PROTO.encode('utf-8'))
        with pytest.raises(GrpcMethodKindError):
            compiled.find_method('int1789.EchoService', 'Unary', 'server_stream')

    def test_missing_service_and_method_rejected(self):
        compiled = compile_proto(ECHO_PROTO.encode('utf-8'))
        with pytest.raises(GrpcProtoError):
            compiled.find_method('int1789.NoService', 'Unary', 'unary')
        with pytest.raises(GrpcProtoError):
            compiled.find_method('int1789.EchoService', 'NoMethod', 'unary')

    def test_import_whitelist(self):
        # 只允许 google/protobuf/*.proto
        validate_proto_imports('import "google/protobuf/empty.proto";')
        with pytest.raises(GrpcProtoError):
            validate_proto_imports('import "other/evil.proto";')
        with pytest.raises(GrpcProtoError):
            validate_proto_imports('import "google/protobuf/../../etc/passwd";')

    def test_size_cap(self):
        oversized = ('//' + 'x' * (256 * 1024 + 1)).encode('utf-8')
        with pytest.raises(GrpcProtoError):
            compile_proto(oversized)

    def test_compile_error_is_config_error(self):
        with pytest.raises(GrpcProtoError):
            compile_proto(b'syntax = "proto3"; message {')


# ── JSON ↔ message ─────────────────────────────────────────────────────
class TestMessageMapping:

    def test_parse_dict_and_message_to_dict_keep_snake_case(self, echo_server):
        method = _method(echo_server, 'Unary', 'unary')
        message = parse_request(
            {'session_id': 's-1', 'round_number': 2, 'input_text': '你好'}, method)
        assert message.session_id == 's-1'
        assert message.round_number == 2
        assert message.input_text == '你好'

        payload = message_to_payload(message)
        # preserving_proto_field_name=True：字段名保持 proto 里的 snake_case
        assert set(payload) == {'session_id', 'round_number', 'input_text'}

    def test_parse_dict_rejects_unknown_field(self, echo_server):
        method = _method(echo_server, 'Unary', 'unary')
        from google.protobuf.json_format import ParseError
        with pytest.raises(ParseError):
            parse_request({'no_such_field': 1}, method)


# ── 错误码映射 ─────────────────────────────────────────────────────────
class TestStatusMapping:

    @pytest.mark.parametrize('code,expected', [
        (0, 0), (1, 499), (2, 500), (3, 400), (4, 504), (5, 404), (6, 409),
        (7, 403), (8, 429), (9, 412), (10, 409), (11, 400), (12, 501),
        (13, 500), (14, 503), (15, 500), (16, 401),
    ])
    def test_all_16_status_codes(self, code, expected):
        assert grpc_status_to_biz(code)[0] == expected

    def test_status_table_covers_all_16(self):
        assert sorted(GRPC_STATUS_TO_BIZ) == list(range(17))

    def test_error_fields_keep_raw_code_out_of_business_field(self):
        fields = grpc_error_fields(14)
        assert fields['biz_code'] == 503
        assert fields['raw_code'] == 14
        assert fields['error_source'] == 'grpc'

    def test_metadata_validation(self):
        assert validate_metadata({'authorization': 'Bearer x'}) == [
            ('authorization', 'Bearer x')]
        with pytest.raises(GrpcProtoError):
            validate_metadata({'Authorization': 'Bearer x'})
        with pytest.raises(GrpcProtoError):
            validate_metadata({'authorization': 'Bearer x\r\ninjected: 1'})


# ── 真实调用：三形态 ───────────────────────────────────────────────────
class TestCalls:

    def test_unary(self, echo_server):
        client = GrpcClient(echo_server.target, _method(echo_server, 'Unary', 'unary'),
                            metadata=[('authorization', 'Bearer test')],
                            deadline_ms=5000)
        try:
            result = client.call_unary({'session_id': 's', 'round_number': 1,
                                        'input_text': 'hi'})
        finally:
            client.close()
        assert result['success'] is True
        assert result['payload']['text_result'] == 'hi-ok'
        assert result['payload']['session_id'] == 's'

    def test_server_stream_three_messages(self, echo_server):
        client = GrpcClient(echo_server.target,
                            _method(echo_server, 'ServerStream', 'server_stream'),
                            deadline_ms=5000)
        try:
            result = client.call_server_stream({'session_id': 's', 'input_text': 'hi'})
        finally:
            client.close()
        messages = result['messages']
        assert [m['text_result'] for m in messages] == ['msg0', 'msg1', 'msg2']
        assert [e['seq'] for e in result['events']] == [0, 1, 2]
        assert all(e['event_type'] == 'message' for e in result['events'])

    def test_bidi_two_rounds(self, echo_server):
        client = GrpcClient(echo_server.target, _method(echo_server, 'Bidi', 'bidi'),
                            deadline_ms=5000)
        session = client.open_bidi_session()
        try:
            session.send({'session_id': 's', 'round_number': 1, 'input_text': 'hello'})
            first = session.recv(timeout=3)
            assert first['event_type'] == 'message'
            assert first['payload']['text_result'] == 'hello-ok'
            session.send({'session_id': 's', 'round_number': 2, 'input_text': 'bye'})
            second = session.recv(timeout=3)
            assert second['event_type'] == 'message'
            assert second['payload']['session_finished'] is True
            session.close_send()
            end = session.recv(timeout=3)
            assert end['event_type'] == 'end_stream'
        finally:
            session.close()

    def test_unimplemented_status(self, echo_server):
        client = GrpcClient(echo_server.target,
                            _method(echo_server, 'NotRegistered', 'unary'),
                            deadline_ms=5000)
        try:
            with pytest.raises(GrpcCallError) as excinfo:
                client.call_unary({'session_id': 's'})
        finally:
            client.close()
        assert excinfo.value.fields['raw_code'] == 12
        assert excinfo.value.fields['biz_code'] == 501
        assert excinfo.value.fields['error_source'] == 'grpc'

    def test_deadline_exceeded(self):
        clear_proto_cache()
        slow = _EchoServer(ECHO_PROTO.encode('utf-8'), delay_seconds=1.0)
        try:
            client = GrpcClient(slow.target, slow.compiled.find_method(
                'int1789.EchoService', 'Unary', 'unary'), deadline_ms=200)
            with pytest.raises(GrpcCallError) as excinfo:
                client.call_unary({'session_id': 's'})
            client.close()
        finally:
            slow.stop()
            clear_proto_cache()
        assert excinfo.value.fields['raw_code'] == 4
        assert excinfo.value.fields['biz_code'] == 504

    def test_connection_refused_is_network_or_unavailable(self):
        clear_proto_cache()
        compiled = compile_proto(ECHO_PROTO.encode('utf-8'))
        client = GrpcClient('127.0.0.1:1', compiled.find_method(
            'int1789.EchoService', 'Unary', 'unary'), deadline_ms=500)
        with pytest.raises(GrpcCallError) as excinfo:
            client.call_unary({'session_id': 's'})
        client.close()
        fields = excinfo.value.fields
        assert fields['biz_code'] in (503,)
        assert fields['error_source'] in ('grpc', 'network')
        clear_proto_cache()


# ── 适配器配置校验 ─────────────────────────────────────────────────────
class _ApiCfg:
    def __init__(self, meta, protocol='grpc', max_timeout=30):
        self.id = 999
        self.meta = meta
        self.protocol = protocol
        self.max_timeout = max_timeout
        self.api_endpoints = [{'endpoint': '127.0.0.1:1'}]
        self.vendor = None
        self.adapter_class = None


class TestAdapterConfig:

    def test_missing_meta_grpc(self):
        from api_test_service.infrastructure.adapters.grpc_adapter import GrpcAdapter
        adapter = GrpcAdapter(_ApiCfg({}))
        with pytest.raises(GrpcProtoError):
            adapter.grpc_config()

    def test_reflection_rejected(self):
        from api_test_service.infrastructure.adapters.grpc_adapter import GrpcAdapter
        adapter = GrpcAdapter(_ApiCfg({'grpc': {
            'service': 's', 'method': 'm', 'method_kind': 'unary',
            'proto_object_key': 'local://x/y.proto', 'reflection': True}}))
        with pytest.raises(GrpcProtoError):
            adapter.grpc_config()

    def test_unknown_method_kind_rejected(self):
        from api_test_service.infrastructure.adapters.grpc_adapter import GrpcAdapter
        adapter = GrpcAdapter(_ApiCfg({'grpc': {
            'service': 's', 'method': 'm', 'method_kind': 'client_stream',
            'proto_object_key': 'local://x/y.proto'}}))
        with pytest.raises(GrpcProtoError):
            adapter.grpc_config()

    def test_proto_sha_mismatch_rejected(self, tmp_path, monkeypatch):
        from api_test_service.infrastructure.adapters.grpc_adapter import GrpcAdapter
        from shared.infrastructure import storage as storage_mod

        proto_path = tmp_path / 'echo.proto'
        proto_path.write_text(ECHO_PROTO, encoding='utf-8')
        monkeypatch.setattr(storage_mod.storage, 'load_bytes',
                            lambda path, **kw: proto_path.read_bytes())
        adapter = GrpcAdapter(_ApiCfg({'grpc': {
            'service': 'int1789.EchoService', 'method': 'Unary',
            'method_kind': 'unary', 'proto_object_key': 'local://x/echo.proto',
            'proto_sha256': '0' * 64}}))
        with pytest.raises(GrpcProtoError):
            adapter._proto_bytes(adapter.grpc_config())


# ── 路由 / 可用矩阵 ────────────────────────────────────────────────────
class TestRouting:

    def test_infer_protocol_maps_grpc(self):
        cfg = _ApiCfg({}, protocol='grpc')
        assert infer_protocol(cfg) is AdapterProtocol.GRPC

    def test_availability_matrix_allows_grpc(self):
        assert ('grpc', False) in AVAILABLE_PROTOCOL_STREAMING
        assert ('grpc', True) in AVAILABLE_PROTOCOL_STREAMING
        assert is_protocol_streaming_available('grpc', False)
        assert is_protocol_streaming_available('grpc', True)
        # A2（SSE）未上线仍拒绝
        assert not is_protocol_streaming_available('sse', True)

    def test_lane_only_by_streaming(self):
        assert lane_of(False) is ExecutionLane.NON_STREAMING
        assert lane_of(True) is ExecutionLane.STREAMING


# ── 流式道策略：轮次结构 ───────────────────────────────────────────────
class _FakeSession:
    session_id = 'sess-1789'

    def get_context(self):
        return []

    def get_context_for_request(self):
        return []


class _FakeExecutor:
    """最小执行器替身：只需 _handle_control / _log（执行器基类同形）。"""

    def __init__(self):
        self.logs = []

    def _handle_control(self, task_id):
        return None

    def _log(self, level='INFO', content='', **kwargs):
        self.logs.append((level, content))


class _FakeAlgoAcl:
    """算法 ACL 替身：不连服务，返回空 field_mappings。"""

    def get_field_mappings(self, *args, **kwargs):
        return {}


class TestStreamStrategy:

    def _executor(self):
        from api_test_service.core.grpc_stream_executor import GrpcStreamExecutor
        executor = GrpcStreamExecutor(_FakeExecutor())
        executor._algo_acl = lambda: _FakeAlgoAcl()
        return executor

    def test_event_rounds_three_messages(self, echo_server, monkeypatch):
        """server-stream：3 条消息 → rounds 3 轮，output 键为 target_param。"""
        executor = self._executor()
        captured = []

        def fake_attach(round_result, field_mappings, algorithm_type, task_id,
                        unwrap_execute_result=False):
            round_result['output'] = {'target_a': round_result['raw_response']['text_result']}
            captured.append(round_result)

        monkeypatch.setattr(executor, '_attach_api_output_fields', fake_attach)

        from api_test_service.infrastructure.adapters.grpc_adapter import GrpcAdapter
        adapter = GrpcAdapter(
            _ApiCfg({'grpc': {'service': 'int1789.EchoService',
                              'method': 'ServerStream',
                              'method_kind': 'server_stream',
                              'proto_object_key': 'local://unused'}}),
            case_config={})
        adapter._endpoint = echo_server.target
        adapter._method = _method(echo_server, 'ServerStream', 'server_stream')

        round_results = []
        ok = executor._run_event_rounds(
            1, 2, [{'round_number': 1}], adapter, _ApiCfg({}),
            _FakeSession(), {}, 'translation', round_results)
        assert ok is True
        assert [r['round_number'] for r in round_results] == [1, 2, 3]
        assert [r['output'] for r in round_results] == [
            {'target_a': 'msg0'}, {'target_a': 'msg1'}, {'target_a': 'msg2'}]
        assert all(r['success'] for r in round_results)

    def test_bidi_rounds_match_ws_shape(self, echo_server, monkeypatch):
        """bidi：2 轮会话，轮次字段与 WS realtime 同构（逐个键对照）。"""
        executor = self._executor()

        def fake_attach(round_result, field_mappings, algorithm_type, task_id,
                        unwrap_execute_result=False):
            round_result['output'] = {'target_a': round_result['raw_response'].get('text_result')}

        monkeypatch.setattr(executor, '_attach_api_output_fields', fake_attach)

        from api_test_service.infrastructure.adapters.grpc_adapter import GrpcAdapter
        adapter = GrpcAdapter(
            _ApiCfg({'grpc': {'service': 'int1789.EchoService',
                              'method': 'Bidi', 'method_kind': 'bidi',
                              'proto_object_key': 'local://unused'}}),
            case_config={'body_template': {
                'session_id': '{{session_id}}',
                'round_number': '{{round_number}}',
                'input_text': '{{input_text}}',
            }})
        adapter._endpoint = echo_server.target
        adapter._method = _method(echo_server, 'Bidi', 'bidi')

        rounds = [
            {'round_number': 1, 'algorithm_params': [
                {'field_code': 'input_text', 'field_value': 'hello'}]},
            {'round_number': 2, 'algorithm_params': [
                {'field_code': 'input_text', 'field_value': 'bye'}]},
        ]
        round_results = []
        ok = executor._run_session_rounds(
            1, 2, rounds, adapter, _ApiCfg({}), {}, _FakeSession(), {},
            'translation', round_results, {}, {})

        assert ok is True
        assert len(round_results) == 2
        ws_keys = {'round_number', 'mode', 'success', 'latency', 'answer_text',
                   'output', 'frame_count', 'error'}
        for result in round_results:
            assert ws_keys.issubset(result.keys())
        assert [r['output'] for r in round_results] == [
            {'target_a': 'hello-ok'}, {'target_a': 'bye-ok'}]

    def test_server_stream_config_error_marks_case_failed(self, monkeypatch):
        """proto 缺失等配置错误 → 用例失败（不静默降级到别的执行道）。"""
        executor = self._executor()
        from api_test_service.infrastructure.adapters import (
            vendor_adapter_registry as registry,
        )

        def boom(*args, **kwargs):
            raise GrpcProtoError('proto 文件为空: local://x/y.proto')

        monkeypatch.setattr(registry, 'create_from_config', boom)
        round_results = []
        ok = executor._run_rounds(
            1, 2, [{'round_number': 1}], _ApiCfg({}), {}, _FakeSession(),
            {}, 'translation', round_results)
        assert ok is False
        assert round_results[0]['error_source'] == 'config'
        assert round_results[0]['biz_code'] == 400
