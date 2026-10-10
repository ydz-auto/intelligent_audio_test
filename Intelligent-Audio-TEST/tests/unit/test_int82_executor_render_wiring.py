# -*- coding: utf-8 -*-
"""INT-82 执行器 RenderService 消费链路接线单测

覆盖（验收标准）：
1. 执行器混音渲染实际走 RenderService 消费链路（组装请求 + 消费 chunk，经 ACL）
   - RoundRenderService.build_round_render_config：audios 归一化（旧 audio_id 回退 +
     SPL 缺省回填）+ 两级噪声透传 + 目标格式（api.audio_config / stream 强制 s16 单声道）
     + SPL 映射预载 + overlap 透传
   - RealtimeSessionExecutor：正常轮/打断轮逐 chunk 推送 + commit；失败终止帧定轮次失败
   - APISessionExecutor：轮次音频经 render_round_file_to_storage 引用混音产物；
     渲染失败收敛为轮次失败；纯文本轮不经混音链路
2. 执行器不存在直调 gRPC stub 的路径（源级守卫：executor/service 零 stub 触达）
3. 接线点 pytest 覆盖
"""
import base64
import inspect
import os
from types import SimpleNamespace
from unittest import mock

import pytest

os.environ.setdefault('OSS_ACCESS_KEY', 'test-access')
os.environ.setdefault('OSS_SECRET_KEY', 'test-secret')

from api_test_service.application.round_render_service import RoundRenderService
from api_test_service.domain.entities.api_rms_spl_mapping import (
    ApiRmsSplMapping,
    CalibrationPoint,
)
from api_test_service.domain.repositories.acl.audio_render_acl_repository import (
    RenderChunkDTO,
    RenderedAudioDTO,
)


# ── 替身 ──────────────────────────────────────────────────

class RenderAclStub:
    """ACL 端口桩：捕获组装的 render_config，按预置产物返回"""

    def __init__(self, file_dto=None, stream_chunks=()):
        self.file_dto = file_dto
        self.stream_chunks = list(stream_chunks)
        self.file_calls = []
        self.stream_calls = []

    def build_render_config(self, round_config, case_config, target_format=None,
                            api_id=None, spl_mapping=None, speakers_map=None,
                            overlap_rate=0.0, overlap_time=0.0):
        config = {
            'audios': round_config.get('audios') or [],
            'round_noise': round_config.get('background_noise') or None,
            'case_noise': case_config.get('background_noise') or None,
            'overlap_rate': overlap_rate,
            'overlap_time': overlap_time,
        }
        if target_format:
            config['target_format'] = target_format
        if api_id is not None:
            config['api_id'] = api_id
        if spl_mapping:
            config['spl_mapping'] = spl_mapping
        return config

    def render_audio_file(self, render_config, task_id=''):
        self.file_calls.append({'render_config': render_config, 'task_id': task_id})
        return self.file_dto

    def render_audio_stream(self, render_config, task_id=''):
        self.stream_calls.append({'render_config': render_config, 'task_id': task_id})
        return iter(self.stream_chunks)


class SplRepoStub:
    def __init__(self, mapping=None):
        self._mapping = mapping

    def get_default_mapping(self, api_id):
        return self._mapping


class StorageStub:
    def __init__(self):
        self.calls = []

    def save_bytes(self, data, category, key, content_type=None):
        self.calls.append({'data': data, 'category': category, 'key': key,
                           'content_type': content_type})
        return f'local://{category}/{key}'


class ApiConfigStub:
    def __init__(self, api_id=7, meta=None):
        self.id = api_id
        self.meta = meta or {}


def _file_dto(**overrides):
    fields = dict(audio_bytes=b'MIXED', container='wav', sample_rate=16000,
                  bit_depth='s16', channels=1, duration_ms=1500)
    fields.update(overrides)
    return RenderedAudioDTO(**fields)


# ── RoundRenderService：请求组装 ─────────────────────────

class TestBuildRoundRenderConfig:
    def test_audios_passthrough_and_two_level_noise(self):
        acl = RenderAclStub()
        service = RoundRenderService(acl)
        round_config = {
            'audios': [{'audio_id': 1, 'type': 'speaker', 'spl': 65},
                       {'audio_id': 2, 'type': 'interferer', 'spl': 55}],
            'background_noise': {'audio_id': 3, 'spl': 45, 'loop': True},
        }
        case_config = {'background_noise': {'audio_id': 99, 'spl': 50}}
        config = service.build_round_render_config(ApiConfigStub(), round_config,
                                                   case_config)
        assert config['audios'] == round_config['audios']
        assert config['round_noise'] == round_config['background_noise']
        assert config['case_noise'] == case_config['background_noise']

    def test_legacy_audio_id_synthesized_as_speaker_with_default_spl(self):
        acl = RenderAclStub()
        service = RoundRenderService(acl)
        config = service.build_round_render_config(
            ApiConfigStub(), {'audio_id': 9, 'spl': 70}, {})
        assert config['audios'] == [{'audio_id': 9, 'type': 'speaker', 'spl': 70.0}]

    def test_missing_spl_filled_with_reference_default(self):
        acl = RenderAclStub()
        service = RoundRenderService(acl)
        config = service.build_round_render_config(
            ApiConfigStub(), {'audios': [{'audio_id': 1, 'type': 'speaker'}]}, {})
        # 未配 SPL 回填参考基准 65 dB（保持 INT-61 单源目标语义）
        assert config['audios'][0]['spl'] == 65.0

    def test_target_format_from_api_meta(self):
        acl = RenderAclStub()
        service = RoundRenderService(acl)
        api = ApiConfigStub(meta={'audio_config': {'sample_rate': 16000,
                                                   'bit_depth': 's16',
                                                   'channels': 1,
                                                   'container': 'wav'}})
        config = service.build_round_render_config(api, {'audio_id': 1}, {})
        assert config['target_format'] == {'sample_rate': 16000, 'bit_depth': 's16',
                                           'channels': 1, 'container': 'wav'}

    def test_stream_forces_s16_mono(self):
        acl = RenderAclStub()
        service = RoundRenderService(acl)
        api = ApiConfigStub(meta={'audio_config': {'sample_rate': 16000,
                                                   'bit_depth': 's24',
                                                   'channels': 2}})
        config = service.build_round_render_config(api, {'audio_id': 1}, {},
                                                   stream=True)
        assert config['target_format'] == {'sample_rate': 16000, 'bit_depth': 's16',
                                           'channels': 1}

    def test_spl_mapping_preloaded_from_repo(self):
        mapping = ApiRmsSplMapping(
            id=5, api_id=7, calibration_status='calibrated',
            calibration_points=[CalibrationPoint(target_spl=65.0, gain_linear=1.0,
                                                 rms_dbfs=-30.0)],
            reference_spl=65.0, reference_gain_linear=1.0,
            min_gain_linear=0.01, max_gain_linear=8.0)
        acl = RenderAclStub()
        service = RoundRenderService(acl, spl_repo=SplRepoStub(mapping))
        config = service.build_round_render_config(ApiConfigStub(api_id=7),
                                                   {'audio_id': 1}, {})
        assert config['spl_mapping'] == {
            'calibration_status': 'calibrated',
            'calibration_points': [{'target_spl': 65.0, 'gain_linear': 1.0,
                                    'rms_dbfs': -30.0}],
            'reference_spl': 65.0, 'reference_gain_linear': 1.0,
            'min_gain_linear': 0.01, 'max_gain_linear': 8.0,
        }
        assert config['api_id'] == 7

    def test_no_mapping_omits_spl_mapping(self):
        acl = RenderAclStub()
        service = RoundRenderService(acl, spl_repo=SplRepoStub(None))
        config = service.build_round_render_config(ApiConfigStub(), {'audio_id': 1}, {})
        assert 'spl_mapping' not in config

    def test_overlap_from_round_then_case_params(self):
        acl = RenderAclStub()
        service = RoundRenderService(acl)
        round_config = {
            'audio_id': 1,
            'algorithm_params': [{'field_code': 'overlap_rate', 'field_value': 0.5}],
        }
        case_config = {
            'algorithm_params': {'overlap_rate': 0.9, 'overlap_time': 0.3},
        }
        config = service.build_round_render_config(ApiConfigStub(), round_config,
                                                   case_config)
        assert config['overlap_rate'] == 0.5      # 轮次级优先
        assert config['overlap_time'] == 0.3      # 轮次缺失回退用例级

    def test_overlap_rate_clamped_to_one(self):
        acl = RenderAclStub()
        service = RoundRenderService(acl)
        config = service.build_round_render_config(
            ApiConfigStub(),
            {'audio_id': 1, 'algorithm_params': {'overlap_rate': 1.7}}, {})
        assert config['overlap_rate'] == 1.0
        assert config['overlap_time'] == 0.0


# ── RoundRenderService：整文件产物落存储 ─────────────────

class TestRenderRoundFileToStorage:
    def test_dto_materialized_to_storage(self):
        acl = RenderAclStub(file_dto=_file_dto())
        storage = StorageStub()
        service = RoundRenderService(acl, storage_client=storage)
        result = service.render_round_file_to_storage(
            ApiConfigStub(api_id=7), {'audio_id': 1}, {}, task_id='T1',
            name_hint='round_2')
        assert result['path'].startswith('local://audios/T1/7/rendered/round_2_')
        assert result['path'].endswith('.wav')
        assert result['duration_ms'] == 1500
        call = storage.calls[0]
        assert call['data'] == b'MIXED'
        assert call['category'] == 'audios'
        assert call['key'].endswith('.wav')
        assert call['content_type'] == 'audio/wav'
        # 组装的 render_config 经 ACL 出站
        assert acl.file_calls[0]['task_id'] == 'T1'

    def test_pcm_container_uses_pcm_extension(self):
        acl = RenderAclStub(file_dto=_file_dto(container='pcm'))
        storage = StorageStub()
        service = RoundRenderService(acl, storage_client=storage)
        result = service.render_round_file_to_storage(
            ApiConfigStub(), {'audio_id': 1}, {}, task_id='T1')
        assert storage.calls[0]['key'].endswith('.pcm')
        assert storage.calls[0]['content_type'] == 'audio/pcm'
        assert result['container'] == 'pcm'

    def test_render_failure_returns_none(self):
        acl = RenderAclStub(file_dto=None)   # gRPC 失败 → ACL 收敛 None
        service = RoundRenderService(acl, storage_client=StorageStub())
        assert service.render_round_file_to_storage(
            ApiConfigStub(), {'audio_id': 1}, {}, task_id='T1') is None

    def test_empty_bytes_returns_none(self):
        acl = RenderAclStub(file_dto=_file_dto(audio_bytes=b''))
        service = RoundRenderService(acl, storage_client=StorageStub())
        assert service.render_round_file_to_storage(
            ApiConfigStub(), {'audio_id': 1}, {}, task_id='T1') is None


# ── RealtimeSessionExecutor：逐 chunk 消费接线 ───────────

class _ExecutorStub:
    def _handle_control(self, task_id):
        pass

    def _log(self, level='INFO', content='', **kwargs):
        pass


class WsClientStub:
    def __init__(self):
        self.chunks = []
        self.committed = False
        self.output = {'audio': bytearray(b'\x01\x02'), 'frame_results': [1, 2],
                       'text': 'ok', 'latency_ms': 5, 'ai_complete': True,
                       'barge_in_detected': True, 'barge_in_latency_ms': 10}

    def send_audio_chunk(self, chunk_b64):
        self.chunks.append(chunk_b64)

    def commit_input(self):
        self.committed = True

    def mark_commit(self):
        pass

    def wait_ai_complete(self, start_timeout=None, end_timeout=None):
        return True

    def wait_ai_speaking(self, start_timeout=None):
        return True

    def recv(self, timeout=None):
        return {'type': 'user_speech_started'}


def _chunks(*payloads):
    return [RenderChunkDTO(sequence=i, data_b64=base64.b64encode(p).decode('ascii'),
                           is_last=i == len(payloads) - 1, message='')
            for i, p in enumerate(payloads)]


@pytest.fixture
def rt_executor(monkeypatch):
    monkeypatch.setattr('api_test_service.core.realtime_session_executor.time.sleep',
                        lambda s: None)
    from api_test_service.core.realtime_session_executor import RealtimeSessionExecutor
    executor = RealtimeSessionExecutor(_ExecutorStub())
    executor._render_service = mock.Mock()
    return executor


class TestRealtimeExecutorWiring:
    def test_normal_round_consumes_stream_chunks(self, rt_executor):
        rt_executor._render_service.stream_round_chunks.return_value = \
            iter(_chunks(b'a', b'b', b'c'))
        client = WsClientStub()
        result = rt_executor._execute_normal_round(
            client, ApiConfigStub(api_id=7), {'audio_id': 1}, 1, 'T1', {})

        assert result['success'] is True
        assert result['input_chunk_count'] == 3
        assert client.chunks == [base64.b64encode(p).decode('ascii')
                                 for p in (b'a', b'b', b'c')]
        assert client.committed is True
        # 消费链路：组装请求 + 逐 chunk 经 ACL（stream 强制 s16 单声道）
        args, kwargs = rt_executor._render_service.stream_round_chunks.call_args
        assert args[0].id == 7 and args[3] == 'T1'

    def test_normal_round_failure_terminal_chunk(self, rt_executor):
        rt_executor._render_service.stream_round_chunks.return_value = iter([
            RenderChunkDTO(sequence=-1, data_b64='', is_last=True,
                           message='audio_service 不可达')])
        client = WsClientStub()
        result = rt_executor._execute_normal_round(
            client, ApiConfigStub(), {'audio_id': 1}, 1, 'T1', {})
        assert result['success'] is False
        assert 'audio_service 不可达' in result['error']
        assert client.chunks == []          # 失败即止，不推送
        assert client.committed is False

    def test_interruption_round_consumes_stream_chunks(self, rt_executor):
        rt_executor._render_service.stream_round_chunks.return_value = \
            iter(_chunks(b'x', b'y'))
        client = WsClientStub()
        result = rt_executor._execute_interruption_round(
            client, ApiConfigStub(), {'audio_id': 1, 'interruption_delay_ms': 1},
            2, 'T1', {})
        assert result['success'] is True
        assert result['barge_in_detected'] is True
        assert len(client.chunks) == 2
        assert client.committed is True

    def test_interruption_round_render_failure(self, rt_executor):
        rt_executor._render_service.stream_round_chunks.return_value = iter([
            RenderChunkDTO(sequence=-1, data_b64='', is_last=True, message='断流')])
        client = WsClientStub()
        result = rt_executor._execute_interruption_round(
            client, ApiConfigStub(), {'audio_id': 1, 'interruption_delay_ms': 1},
            2, 'T1', {})
        assert result['success'] is False
        assert '断流' in result['error']
        assert client.chunks == []


# ── APISessionExecutor：整文件消费接线 ───────────────────

@pytest.fixture
def api_executor():
    from api_test_service.core.api_session_executor import APISessionExecutor
    executor = APISessionExecutor(_ExecutorStub())
    executor._render_service = mock.Mock()
    return executor


class TestApiSessionExecutorWiring:
    def test_round_audio_path_uses_rendered_product(self, api_executor):
        api_executor._render_service.render_round_file_to_storage.return_value = {
            'path': 'local://audios/T1/7/rendered/round_1_1.wav', 'duration_ms': 1500,
        }
        path = api_executor._get_round_audio_path(
            ApiConfigStub(api_id=7), {'audios': [{'audio_id': 1}]}, {}, 'T1', 1)
        assert path == 'local://audios/T1/7/rendered/round_1_1.wav'
        args, kwargs = api_executor._render_service.render_round_file_to_storage.call_args
        assert args[0].id == 7 and args[3] == 'T1'
        assert kwargs.get('name_hint') == 'round_1'

    def test_render_failure_raises_round_error(self, api_executor):
        api_executor._render_service.render_round_file_to_storage.return_value = None
        with pytest.raises(ValueError, match='混音渲染失败'):
            api_executor._get_round_audio_path(
                ApiConfigStub(), {'audios': [{'audio_id': 1}]}, {}, 'T1', 1)

    def test_text_only_round_skips_render(self, api_executor):
        path = api_executor._get_round_audio_path(
            ApiConfigStub(), {'query': '你好'}, {}, 'T1', 1)
        assert path == ''
        api_executor._render_service.render_round_file_to_storage.assert_not_called()

    def test_send_round_converges_render_failure_to_failed_round(self, api_executor,
                                                                 monkeypatch):
        """渲染失败收敛为轮次失败结果，不中断整个用例"""
        def _raise(*args, **kwargs):
            raise ValueError('第 1 轮混音渲染失败（RenderAudioFile 无产物）')
        monkeypatch.setattr(api_executor, '_build_round_context', _raise)
        session = SimpleNamespace(session_id='s1', session_timeout=5,
                                  get_context=lambda: {},
                                  get_context_for_request=lambda: {})
        result = api_executor._send_round_request(
            task_id='T1', api_config=ApiConfigStub(), api_specific_config={},
            session=session, round_number=1, round_config={'audio_id': 1},
            case_algorithm_params=None, algorithm_type='voice_llm',
            case_config={})
        assert result['success'] is False
        assert '混音渲染失败' in result['error']


# ── 验收标准 2：执行器不得直调 gRPC stub（源级守卫）──────

class TestNoDirectStubAccess:
    _MODULES = [
        'api_test_service.core.realtime_session_executor',
        'api_test_service.core.api_session_executor',
        'api_test_service.application.round_render_service',
    ]

    def test_executors_and_service_never_touch_stub_layer(self):
        import api_test_service.core.api_session_executor as api_exec
        import api_test_service.core.realtime_session_executor as rt_exec
        import api_test_service.application.round_render_service as render_svc
        for module in (rt_exec, api_exec, render_svc):
            source = inspect.getsource(module)
            assert 'get_render_service_stub' not in source, \
                f"{module.__name__} 直调了 gRPC stub 工厂"
            assert 'audio_service_pb2' not in source, \
                f"{module.__name__} 直触了 gRPC proto 层"
