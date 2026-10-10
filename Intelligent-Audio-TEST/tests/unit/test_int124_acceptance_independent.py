# -*- coding: utf-8 -*-
"""INT-124 测试工程师独立验收：get_audios_by_ids 契约对齐 + 静默失败显式化。

事故（INT-95 主链实机复验）：algorithm_service 参考参数生成全空——
消费侧按 data.get('items') 解析，而 audio_service.GetAudiosByIds 真实契约是
data 为 JSON 裸数组（_ok(data=results) 无 items 包装）→ 每次调用必抛
'list' object has no attribute 'get'，异常被吞只打 ERROR、返回空结果，
三轮 Preloaded 0 audios / Generated 0 reference params，参考参数落库恒为空。

开发修复（commit 4900ac94）两处消费端 + 一处告警：
- shared/clients/_grpc_algo_audio.get_audios_by_ids（实机日志中的调用路径，
  logger=grpc_clients）：兼容裸数组 / 历史 {"items":[...]} 双形态；
  resp.success=False 显式 WARNING（原静默）；成功但解析出 0 条时 WARNING；
  请求构造修正为 proto 仅有的 data 字段（JSON {"ids":[...]}）
- algorithm_service/infrastructure/acl/algorithm_acl_gateway.get_audios_by_ids
  （issue 指认文件）：同款解析容错 + 请求构造修复 + 同款告警
- algorithm_service/application/queries/reference_params_queries.py：
  generate_for_round 在 audio_ids 非空但预加载 audio_map 为空时显式 WARNING
  （0/M audios，参考参数将为空——对齐 INT-107「静默失败显式化」口径）

本验收文件与开发侧 monkeypatch 自测互补，重点钉死：
1. 对端真实契约形态（audio_service/_audio_to_dict → _wrap → data=裸数组）
   下消费端正确出 map——即原 bug 的必然复现输入不再是失败；
2. 原始双 bug 形态回归锚：裸数组 data.get('items') 的 AttributeError 必然死法 +
   proto 无 audio_ids 字段（老 kwargs 构造 ValueError）——修复一旦回退立即爆红；
3. success=False / 0 条 / 传输异常三类失败全部有显式日志（不再静默吞掉）；
4. 真实链路（不 mock 消费函数本体，只替换 gRPC stub 工厂与 DB 仓储）：
   audio_acl_repository.preload_audio_data → grpc_clients.get_audios_by_ids →
   _grpc_algo_audio，以及 ReferenceParamsQueryHandler.generate_for_round 在裸数组
   契约下参考参数非空生成、0 音频时 0/M 显式告警。
"""
import json
import logging
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from shared.proto import audio_service_pb2 as e2e_pb
from shared.clients import _grpc_algo_audio
from shared.clients import grpc_clients
from algorithm_service.infrastructure.acl import algorithm_acl_gateway
from algorithm_service.infrastructure.acl.audio_acl_repository import audio_acl_repository
from algorithm_service.application.queries.reference_params_queries import ReferenceParamsQueryHandler
from algorithm_service.infrastructure.persistence.param_repository import reference_param_repository
from shared.utils.log_handler import _api as log_api


# ==================== 测试基建 ====================

class _CaptureHandler:
    """替代 DatabaseLogHandler：log_not_emit 的 record 全部内存捕获。"""

    def __init__(self):
        self.records = []

    def emit(self, record):
        self.records.append(record)

    @property
    def warnings(self):
        return [r for r in self.records if r.levelno >= logging.WARNING]

    def messages(self, level=None):
        return [r.msg for r in self.records
                if level is None or r.levelno == level]


@pytest.fixture
def capture_logs(monkeypatch):
    cap = _CaptureHandler()
    monkeypatch.setattr(log_api, 'get_db_handler', lambda: cap)
    return cap


class _FakeStub:
    """AudioConfigServiceStub 替身：记录请求、按配置返回响应或抛异常。

    outcome 为 e2e_pb.AudioConfigResponse 实例（正常返回）或 Exception 实例（抛出）。
    """

    def __init__(self, outcome):
        self.outcome = outcome
        self.requests = []

    def GetAudiosByIds(self, request, timeout=None):
        self.requests.append(request)
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


def _stub_response(data_obj):
    """按 audio_service 真实序列化方式（_wrap → _dumps(result['data'])）构造响应。"""
    return e2e_pb.AudioConfigResponse(
        success=True, message='', data=json.dumps(data_obj, ensure_ascii=False))


@pytest.fixture
def patch_client_stub(monkeypatch):
    """替换 _grpc_algo_audio 模块级 stub 工厂（实机路径），返回 stub 装配器。"""
    holder = {}

    def _install(outcome):
        stub = _FakeStub(outcome)
        holder['stub'] = stub
        monkeypatch.setattr(_grpc_algo_audio, 'get_audio_config_service_stub',
                            lambda: stub)
        return stub

    return _install


@pytest.fixture
def patch_gateway_stub(monkeypatch):
    """替换 gateway 懒导入路径（shared.clients.grpc_clients）的 stub 工厂。"""
    holder = {}

    def _install(outcome):
        stub = _FakeStub(outcome)
        holder['stub'] = stub
        monkeypatch.setattr(grpc_clients, 'get_audio_config_service_stub',
                            lambda: stub)
        return stub

    return _install


def _audio_payload(audio_id=2235, annotations=None, **overrides):
    """复刻 audio_service._audio_to_dict 输出形态。"""
    d = {
        'id': audio_id,
        'name': f'audio_{audio_id}.wav',
        'file_path': f'/oss/audio/{audio_id}.wav',
        'duration': 3.2,
        'audio_type': 'main',
        'sample_rate': 16000,
        'annotations': annotations if annotations is not None else [],
    }
    d.update(overrides)
    return d


# ==================== Part 1：_grpc_algo_audio.get_audios_by_ids（实机路径） ====================

class TestGrpcAlgoAudioGetAudiosByIds:

    def test_bare_array_contract_returns_audio_map(self, patch_client_stub):
        """对端真实契约（裸数组）下正确出 map；请求构造为 {"ids":[...]}（kwarg bug 锚点）。"""
        stub = patch_client_stub(_stub_response([_audio_payload(2235), _audio_payload(718)]))

        result = _grpc_algo_audio.get_audios_by_ids([2235, 718])

        assert set(result.keys()) == {2235, 718}
        assert result[2235]['name'] == 'audio_2235.wav'
        assert result[718]['duration'] == 3.2
        assert len(stub.requests) == 1
        assert json.loads(stub.requests[0].data) == {'ids': [2235, 718]}

    def test_legacy_items_wrapper_still_supported(self, patch_client_stub):
        """历史 {"items":[...]} 包装兼容（task_service 同款容错）。"""
        patch_client_stub(_stub_response({'items': [_audio_payload(2235)]}))

        result = _grpc_algo_audio.get_audios_by_ids([2235])

        assert set(result.keys()) == {2235}

    def test_success_false_logs_warning_not_silent(self, patch_client_stub, capture_logs):
        """success=False 显式 WARNING（原静默吞掉）+ 空结果。"""
        patch_client_stub(e2e_pb.AudioConfigResponse(
            success=False, message='db down', data=''))

        result = _grpc_algo_audio.get_audios_by_ids([2235])

        assert result == {}
        warns = [m for m in capture_logs.messages(logging.WARNING)
                 if 'get_audios_by_ids failed' in m]
        assert len(warns) == 1
        assert 'db down' in warns[0]

    def test_zero_rows_logs_warning_with_ratio(self, patch_client_stub, capture_logs):
        """成功但解析出 0 条：WARNING 带 请求 N/实得 0 比例。"""
        patch_client_stub(_stub_response([]))

        result = _grpc_algo_audio.get_audios_by_ids([2235, 718])

        assert result == {}
        warns = [m for m in capture_logs.messages(logging.WARNING)
                 if '0/2' in m and 'get_audios_by_ids' in m]
        assert len(warns) == 1

    def test_transport_exception_logs_error(self, patch_client_stub, capture_logs):
        """传输异常保留 ERROR 且不向上炸。"""
        patch_client_stub(RuntimeError('channel unavailable'))

        result = _grpc_algo_audio.get_audios_by_ids([2235])

        assert result == {}
        errors = [m for m in capture_logs.messages(logging.ERROR)
                  if 'get_audios_by_ids failed' in m]
        assert len(errors) == 1
        assert 'channel unavailable' in errors[0]

    def test_malformed_payload_does_not_crash(self, patch_client_stub, capture_logs):
        """非法 JSON 载荷：ERROR + 空结果，不炸调用方。"""
        patch_client_stub(e2e_pb.AudioConfigResponse(
            success=True, message='', data='not-json{{'))

        result = _grpc_algo_audio.get_audios_by_ids([2235])

        assert result == {}
        assert any(m for m in capture_logs.messages(logging.ERROR)
                   if 'get_audios_by_ids' in m)

    def test_empty_data_zero_rows_warning(self, patch_client_stub, capture_logs):
        """空 data（loads 兜底 {}）→ 0 条 WARNING 而非静默。"""
        patch_client_stub(e2e_pb.AudioConfigResponse(success=True, message='', data=''))

        result = _grpc_algo_audio.get_audios_by_ids([2235])

        assert result == {}
        assert any('0/1' in m for m in capture_logs.messages(logging.WARNING))

    def test_entries_without_id_are_skipped(self, patch_client_stub):
        """无 id / 非 dict 条目跳过，其余正常收录。"""
        patch_client_stub(_stub_response([
            {'name': 'no-id-entry'},
            _audio_payload(718),
            'garbage-string',
        ]))

        result = _grpc_algo_audio.get_audios_by_ids([718, 999])

        assert set(result.keys()) == {718}

    def test_empty_ids_short_circuit(self, patch_client_stub):
        """空 id 列表不发调用。"""
        stub = patch_client_stub(_stub_response([]))

        assert _grpc_algo_audio.get_audios_by_ids([]) == {}
        assert stub.requests == []


# ==================== Part 2：algorithm_acl_gateway.get_audios_by_ids（issue 指认文件） ====================

class TestAlgorithmAclGatewayGetAudiosByIds:

    def test_bare_array_maps_audio_dto(self, patch_gateway_stub):
        """裸数组契约 → {id: AudioDTO}，字段映射正确，未知字段被 dict_to_dto 过滤。"""
        patch_gateway_stub(_stub_response([
            _audio_payload(2235, extra_unknown_key='should-be-filtered'),
        ]))

        result = algorithm_acl_gateway.get_audios_by_ids([2235])

        dto = result[2235]
        assert dto.id == 2235
        assert dto.duration == 3.2
        assert dto.sample_rate == 16000
        assert dto.annotations == []
        assert not hasattr(dto, 'extra_unknown_key')

    def test_annotations_flow_through_dto(self, patch_gateway_stub):
        """标注列表经 AudioDTO.annotations 透传。"""
        anns = [{'code': 'asr', 'format': 'txt', 'data': {'text': '你好世界'}}]
        patch_gateway_stub(_stub_response([_audio_payload(2235, annotations=anns)]))

        result = algorithm_acl_gateway.get_audios_by_ids([2235])

        assert result[2235].annotations == anns

    def test_items_wrapper_compatible(self, patch_gateway_stub):
        patch_gateway_stub(_stub_response({'items': [_audio_payload(2235)]}))

        result = algorithm_acl_gateway.get_audios_by_ids([2235])

        assert set(result.keys()) == {2235}

    def test_request_construction_uses_ids_json(self, patch_gateway_stub):
        """请求构造修正锚点：proto 仅有的 data 字段装 {"ids":[...]}。"""
        stub = patch_gateway_stub(_stub_response([]))

        algorithm_acl_gateway.get_audios_by_ids([2235, 718])

        assert json.loads(stub.requests[0].data) == {'ids': [2235, 718]}

    def test_success_false_logs_warning(self, patch_gateway_stub, capture_logs):
        patch_gateway_stub(e2e_pb.AudioConfigResponse(
            success=False, message='audio_service unreachable', data=''))

        result = algorithm_acl_gateway.get_audios_by_ids([2235])

        assert result == {}
        warns = [m for m in capture_logs.messages(logging.WARNING)
                 if 'get_audios_by_ids failed' in m and 'audio_service unreachable' in m]
        assert len(warns) == 1

    def test_zero_rows_logs_warning(self, patch_gateway_stub, capture_logs):
        patch_gateway_stub(_stub_response([]))

        result = algorithm_acl_gateway.get_audios_by_ids([2235])

        assert result == {}
        assert any('0/1' in m for m in capture_logs.messages(logging.WARNING))

    def test_transport_exception_logs_error(self, patch_gateway_stub, capture_logs):
        patch_gateway_stub(TimeoutError('deadline exceeded'))

        result = algorithm_acl_gateway.get_audios_by_ids([2235])

        assert result == {}
        assert any('get_audios_by_ids failed' in m
                   for m in capture_logs.messages(logging.ERROR))


# ==================== Part 3：原始 bug 形态回归锚 ====================

class TestOriginalBugShapeAnchors:
    """原缺陷的两个必然死法。修复回退（任一处改回旧形态）时本组用例必爆红。"""

    def test_bare_array_under_old_parse_is_attribute_error(self):
        """原解析 data.get('items') 在裸数组输入下必然 AttributeError（事故根因）。"""
        data = json.loads(json.dumps([_audio_payload(2235)]))
        with pytest.raises(AttributeError):
            data.get('items')

    def test_proto_rejects_legacy_kwargs_construction(self):
        """proto GetAudiosByIdsRequest 仅 data 字段——老 audio_ids= kwargs 构造必 ValueError。"""
        with pytest.raises(ValueError):
            e2e_pb.GetAudiosByIdsRequest(audio_ids=[2235])


# ==================== Part 4：真实链路（只替换 stub 工厂与 DB 仓储） ====================

class TestRealChain:
    """消费函数本体（grpc_clients 再导出 / audio_acl_repository / generate_for_round）
    全部真实执行，仅替换 gRPC stub 工厂（对端按真实序列化形态应答）与 DB 仓储。"""

    def test_preload_audio_data_real_chain_bare_array(self, patch_client_stub, capture_logs):
        """preload_audio_data 真实穿过 grpc_clients → _grpc_algo_audio：Preloaded N audios 为实际数。"""
        anns = [{'code': 'asr', 'format': 'txt', 'data': {'text': '你好世界'}}]
        patch_client_stub(_stub_response([
            _audio_payload(2235, annotations=anns),
            _audio_payload(718),
        ]))

        ctx = audio_acl_repository.preload_audio_data([2235, 718])

        assert set(ctx['audio_map'].keys()) == {2235, 718}
        assert ctx['duration_map'][2235] == 3.2
        assert ctx['annotation_map'][2235][0]['data']['text'] == '你好世界'
        assert ctx['annotation_map'][718] == []
        # 无任何告警（正常路径不触发 0/N / failed）
        assert capture_logs.warnings == []

    def test_generate_for_round_real_chain_generates_params(self, patch_client_stub, capture_logs,
                                                            monkeypatch):
        """裸数组契约下参考参数真实生成非空（原缺陷场景：恒为空）。"""
        anns = [{'code': 'asr', 'format': 'txt',
                 'data': {'text': '你好世界', 'segments': [{'text': '你好世界'}]}}]
        patch_client_stub(_stub_response([_audio_payload(2235, annotations=anns)]))
        monkeypatch.setattr(
            reference_param_repository, 'list_by_algorithm',
            lambda algorithm_type: [
                {'code': 'asr_ref', 'param_type': 'text',
                 'field_path': 'segments[].text', 'merge_mode': 'join'},
            ])

        test_case_config = {
            'algorithm_type': 'voice_llm',
            'test_type': 'api',
            'config': {},
        }
        round_data = {'round_number': 1, 'audios': [{'audio_id': 2235}]}

        result = ReferenceParamsQueryHandler.generate_for_round(test_case_config, round_data)

        assert len(result) == 1
        param = result[0]
        assert param['code'] == 'asr_ref'
        assert param['type'] == 'text'
        assert param['value'] == '你好世界'
        # 正常路径零告警
        assert capture_logs.warnings == []

    def test_generate_for_round_zero_audio_explicit_warning(self, patch_client_stub, capture_logs,
                                                            monkeypatch):
        """负路径：对端查无此音频 → 0/M 显式 WARNING（INT-107 静默失败显式化口径），
        参考参数为空但不再无告警终态。"""
        patch_client_stub(_stub_response([]))
        monkeypatch.setattr(
            reference_param_repository, 'list_by_algorithm',
            lambda algorithm_type: [
                {'code': 'asr_ref', 'param_type': 'text',
                 'field_path': 'segments[].text', 'merge_mode': 'join'},
            ])

        test_case_config = {
            'algorithm_type': 'voice_llm',
            'test_type': 'api',
            'config': {},
        }
        round_data = {'round_number': 2, 'audios': [{'audio_id': 999999}]}

        result = ReferenceParamsQueryHandler.generate_for_round(test_case_config, round_data)

        assert result == []
        all_msgs = capture_logs.messages()
        assert any('audio preload returned 0/1 audios' in m for m in all_msgs)
        assert any('reference params will likely be empty' in m for m in all_msgs)

    def test_generate_for_round_success_false_warning(self, patch_client_stub, capture_logs,
                                                      monkeypatch):
        """负路径：audio_service 侧失败（success=False）→ 显式 WARNING 且参考参数为空。"""
        patch_client_stub(e2e_pb.AudioConfigResponse(
            success=False, message='db down', data=''))
        monkeypatch.setattr(
            reference_param_repository, 'list_by_algorithm',
            lambda algorithm_type: [
                {'code': 'asr_ref', 'param_type': 'text',
                 'field_path': 'segments[].text', 'merge_mode': 'join'},
            ])

        test_case_config = {
            'algorithm_type': 'voice_llm',
            'test_type': 'api',
            'config': {},
        }
        round_data = {'round_number': 3, 'audios': [{'audio_id': 2235}]}

        result = ReferenceParamsQueryHandler.generate_for_round(test_case_config, round_data)

        assert result == []
        assert any('get_audios_by_ids failed' in m
                   for m in capture_logs.messages(logging.WARNING))
        assert any('audio preload returned 0/1 audios' in m
                   for m in capture_logs.messages())
