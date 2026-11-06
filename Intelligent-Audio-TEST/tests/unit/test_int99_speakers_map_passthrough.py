# -*- coding: utf-8 -*-
"""INT-99 API 侧多源时间轴 speakers_map 透传单测

覆盖（验收标准）：
1. 存在音频标注时混音时间轴与 E2E 同语义（按标注而非 play_order）
   - RoundRenderService 组装请求经标注查询端口构建并透传 speakers_map
   - 跨边界语义：API 侧组装的 render_config 喂给 AudioStreamOrchestrator，
     共同 speaker 顺序 / 无共同 speaker 交叠（与 E2E build_audio_timelines 同判定）
2. 无标注时行为与 INT-82 现状一致（回退 play_order，render_config 不携带 speakers_map）
   - 未注入 audio_acl / 无 speaker 源 / 查询为空 / 查询失败 → 均不携带
3. audio_service 标注查询 gRPC 能力（handler 提取口径与 E2E extract_speakers_from_annotations
   同源）+ servicer 委托 + 消费端 ACL gRPC 实现（失败收敛空映射）
4. 源级守卫延续：执行器/应用层不直触 proto 与 stub 工厂
"""
import inspect
import json
import os
from unittest import mock

import numpy as np
import pytest

os.environ.setdefault('OSS_ACCESS_KEY', 'test-access')
os.environ.setdefault('OSS_SECRET_KEY', 'test-secret')

from api_test_service.application.round_render_service import RoundRenderService
from api_test_service.domain.repositories.acl.audio_render_acl_repository import (
    RenderedAudioDTO,
)


# ── 替身 ──────────────────────────────────────────────────

class RenderAclCapture:
    """ACL 端口桩：捕获 build_render_config 入参，回显组装产物"""

    def __init__(self):
        self.calls = []

    def build_render_config(self, round_config, case_config, target_format=None,
                            api_id=None, spl_mapping=None, speakers_map=None,
                            overlap_rate=0.0, overlap_time=0.0):
        self.calls.append({'speakers_map': speakers_map})
        config = {
            'audios': round_config.get('audios') or [],
            'round_noise': round_config.get('background_noise') or None,
            'case_noise': case_config.get('background_noise') or None,
            'overlap_rate': overlap_rate,
            'overlap_time': overlap_time,
        }
        if speakers_map:
            config['speakers_map'] = speakers_map
        return config

    def render_audio_file(self, render_config, task_id=''):
        return None

    def render_audio_stream(self, render_config, task_id=''):
        return iter([])


class SpeakersAclStub:
    """标注查询端口桩：预置 speakers_map，支持注入异常"""

    def __init__(self, speakers_map=None, error=None):
        self._speakers_map = speakers_map or {}
        self._error = error
        self.calls = []

    def get_audio_speakers(self, audio_ids):
        self.calls.append(list(audio_ids))
        if self._error:
            raise self._error
        return {str(k): list(v) for k, v in self._speakers_map.items()
                if str(k) in {str(a) for a in audio_ids}}

    def get_audio(self, audio_id):
        return None


class ApiConfigStub:
    def __init__(self, api_id=7, meta=None):
        self.id = api_id
        self.meta = meta or {}


# ── RoundRenderService：speakers_map 组装与透传 ───────────

ROUND = {
    'audios': [
        {'audio_id': 2, 'type': 'speaker', 'play_order': 1},
        {'audio_id': 1, 'type': 'speaker', 'play_order': 0},
        {'audio_id': 3, 'type': 'interferer', 'delay': 2000},
    ],
}


class TestRoundRenderSpeakersMap:
    def test_speakers_map_built_and_passed(self):
        acl = RenderAclCapture()
        annotation = SpeakersAclStub({'1': ['spk9'], '2': ['spk8']})
        service = RoundRenderService(acl, audio_acl=annotation)
        config = service.build_round_render_config(ApiConfigStub(), dict(ROUND), {})
        assert config['speakers_map'] == {'1': ['spk9'], '2': ['spk8']}
        # 仅干声（speaker 源）参与查询，interferer 不查
        assert annotation.calls == [[2, 1]]

    def test_speaker_type_filter_dedup_and_order(self):
        acl = RenderAclCapture()
        annotation = SpeakersAclStub({})
        service = RoundRenderService(acl, audio_acl=annotation)
        round_cfg = {
            'audios': [
                {'audio_id': 1, 'type': 'speaker'},
                {'audio_id': 2, 'type': 'speaker'},
                {'audio_id': 1, 'type': 'speaker'},   # 重复 audio_id 只查一次
                {'audio_id': 3, 'type': 'noise'},
                {'audio_id': 4},                       # 缺 type 默认 speaker 源
            ],
        }
        service.build_round_render_config(ApiConfigStub(), round_cfg, {})
        assert annotation.calls == [[1, 2, 4]]

    def test_no_audio_acl_omits_speakers_map(self):
        """未注入标注端口：不携带 speakers_map（INT-82 组装现状）"""
        acl = RenderAclCapture()
        service = RoundRenderService(acl)
        config = service.build_round_render_config(ApiConfigStub(), dict(ROUND), {})
        assert 'speakers_map' not in config
        assert acl.calls[0]['speakers_map'] is None

    def test_no_annotations_omits_speakers_map(self):
        """标注为空（无 diarization）：不携带，行为与 INT-82 一致"""
        acl = RenderAclCapture()
        annotation = SpeakersAclStub({})
        service = RoundRenderService(acl, audio_acl=annotation)
        config = service.build_round_render_config(ApiConfigStub(), dict(ROUND), {})
        assert 'speakers_map' not in config

    def test_query_failure_falls_back_to_play_order(self):
        """标注查询失败：收敛为不携带（时间轴回退 play_order），不阻断渲染"""
        acl = RenderAclCapture()
        annotation = SpeakersAclStub(error=ConnectionError('audio_service 不可达'))
        service = RoundRenderService(acl, audio_acl=annotation)
        config = service.build_round_render_config(ApiConfigStub(), dict(ROUND), {})
        assert 'speakers_map' not in config
        assert [a['audio_id'] for a in config['audios']] == [2, 1, 3]

    def test_stream_path_also_carries_speakers_map(self):
        acl = RenderAclCapture()
        annotation = SpeakersAclStub({'1': ['spk9'], '2': ['spk9']})
        service = RoundRenderService(acl, audio_acl=annotation)
        config = service.build_round_render_config(
            ApiConfigStub(), dict(ROUND), {}, stream=True)
        assert config['speakers_map'] == {'1': ['spk9'], '2': ['spk9']}


# ── 跨边界语义：API 组装的 render_config → 编排器时间轴同 E2E ──

RATE = 16000


def _tone_pcm(seconds, freq, amp):
    t = np.arange(int(RATE * seconds)) / RATE
    samples = amp * np.sin(2 * np.pi * freq * t)
    return (np.clip(samples, -1, 1) * 32767).astype('<i2').tobytes()


class TestTimelineSemanticParity:
    """验收 1：API 侧多源轮次按标注构建时间轴（同 E2E 语义）"""

    def _prepare(self, monkeypatch, render_config):
        from audio_service.application.services.audio_stream_orchestrator import (
            AudioStreamOrchestrator,
        )
        pcm = _tone_pcm(1.0, 440, 0.5)
        monkeypatch.setattr(
            AudioStreamOrchestrator, '_load_source_pcm',
            lambda self, audio_id: (pcm, {'sample_rate': RATE, 'channels': 1,
                                          'duration': 1.0}))
        orchestrator = AudioStreamOrchestrator()
        return orchestrator.prepare(dict(render_config, task_id='T99',
                                         target_format={'sample_rate': RATE,
                                                        'bit_depth': 's16',
                                                        'channels': 1}))

    def test_api_assembled_config_yields_speaker_aware_timeline(self, monkeypatch):
        """共同 speaker → 顺序；无共同 speaker → 按 overlap 交叠（非 play_order 链式）"""
        acl = RenderAclCapture()
        annotation = SpeakersAclStub({'1': ['spk9'], '2': ['spk8']})
        service = RoundRenderService(acl, audio_acl=annotation)
        render_config = service.build_round_render_config(
            ApiConfigStub(),
            {'audios': [
                {'audio_id': 1, 'type': 'speaker', 'play_order': 0},
                {'audio_id': 2, 'type': 'speaker', 'play_order': 1},
            ], 'algorithm_params': {'overlap_time': 0.5}},
            {})
        context = self._prepare(monkeypatch, render_config)
        placement = {context.sources[i].audio_id: s for i, s in context.placements}
        # 无共同 speaker → start = prev_end - 0.5s（交叠），而非顺序（= play_order 回退）
        assert placement[1] == 0
        assert placement[2] == RATE // 2

        # 同一 audios 换成共同 speaker 标注 → 顺序播放（start = prev_end）
        annotation2 = SpeakersAclStub({'1': ['spk9'], '2': ['spk9']})
        service2 = RoundRenderService(acl, audio_acl=annotation2)
        render_config2 = service2.build_round_render_config(
            ApiConfigStub(),
            {'audios': [
                {'audio_id': 1, 'type': 'speaker', 'play_order': 0},
                {'audio_id': 2, 'type': 'speaker', 'play_order': 1},
            ], 'algorithm_params': {'overlap_time': 0.5}},
            {})
        context2 = self._prepare(monkeypatch, render_config2)
        placement2 = {context2.sources[i].audio_id: s for i, s in context2.placements}
        assert placement2[2] == RATE

    def test_without_annotations_timeline_falls_back_to_play_order(self, monkeypatch):
        """验收 2：无标注 → speakers_map 不携带 → 交叠链式回退（INT-82 现状）"""
        acl = RenderAclCapture()
        annotation = SpeakersAclStub({})
        service = RoundRenderService(acl, audio_acl=annotation)
        render_config = service.build_round_render_config(
            ApiConfigStub(),
            {'audios': [
                {'audio_id': 1, 'type': 'speaker', 'play_order': 0},
                {'audio_id': 2, 'type': 'speaker', 'play_order': 1},
            ], 'algorithm_params': {'overlap_time': 0.5}},
            {})
        assert 'speakers_map' not in render_config
        context = self._prepare(monkeypatch, render_config)
        placement = {context.sources[i].audio_id: s for i, s in context.placements}
        # 无 speakers_map 时 speaker 感知判定退化为 False → 仍按 overlap 链式
        assert placement[1] == 0
        assert placement[2] == RATE // 2


# ── audio_service：标注查询 gRPC 能力 ─────────────────────

class RepoStub:
    def __init__(self, annotations_map):
        self._map = annotations_map

    def get_annotations_map(self, audio_ids):
        return {k: v for k, v in self._map.items() if k in set(audio_ids)}


def _ann(segments):
    return {'format': 'json', 'code': 'diarization', 'data': segments,
            'source_language': '', 'target_language': ''}


class TestHandleGetAudioSpeakers:
    def _handler(self, annotations_map):
        from audio_service.application.handlers.audio_query_handler import (
            AudioQueryHandler,
        )
        return AudioQueryHandler(repository=RepoStub(annotations_map))

    def _query(self, audio_ids):
        from audio_service.application.queries import GetAudioSpeakersQuery
        return GetAudioSpeakersQuery(audio_ids=audio_ids)

    def test_extract_from_dict_segments_and_list_data(self):
        handler = self._handler({
            1: [_ann({'segments': [{'speaker': 'spk9', 'start': 0},
                                    {'speaker': 'spk8', 'start': 1},
                                    {'start': 2}]}),          # dict + segments
                _ann([{'speaker': 'spk9'}]),                   # list 形态
                _ann({'transcript': 'no speakers here'})],
        })
        result = handler.handle_get_audio_speakers(self._query([1, 2]))
        assert result['success'] is True
        # 键字符串化 + 排序列表；无标注音频返回空列表
        assert result['data']['speakers_map'] == {'1': ['spk8', 'spk9'], '2': []}

    def test_empty_ids_return_empty_map(self):
        handler = self._handler({})
        result = handler.handle_get_audio_speakers(self._query([]))
        assert result['data']['speakers_map'] == {}

    def test_invalid_ids_skipped_and_deduped(self):
        handler = self._handler({3: [_ann({'segments': [{'speaker': 'spk1'}]})]})
        result = handler.handle_get_audio_speakers(self._query([3, '3', 'x', None]))
        assert result['data']['speakers_map'] == {'3': ['spk1']}

    def test_extraction_aligned_with_e2e_pure_function(self):
        """提取口径与 E2E extract_speakers_from_annotations 同源（纯函数复用）"""
        from audio_service.infrastructure.audio.audio_timeline import (
            speakers_from_annotation_data,
        )
        shapes = [
            {'segments': [{'speaker': 'spk9'}, {'speaker': 'spk8'}, {}]},
            [{'speaker': 'spk9'}, {'speaker': 'spk7'}],
            {'transcript': 'x'},
            None,
        ]
        handler = self._handler({
            i: [_ann(s)] for i, s in enumerate(shapes, start=1)
        })
        result = handler.handle_get_audio_speakers(
            self._query(range(1, len(shapes) + 1)))
        for i, shape in enumerate(shapes, start=1):
            assert result['data']['speakers_map'][str(i)] == \
                sorted(speakers_from_annotation_data(shape))


class TestGetAudioSpeakersServicer:
    def test_delegates_to_query_handler(self):
        from audio_service.interfaces.grpc.servicers import AudioConfigServiceServicer
        servicer = AudioConfigServiceServicer()
        handler = mock.Mock()
        handler.handle_get_audio_speakers.return_value = {
            'success': True, 'message': 'ok',
            'data': {'speakers_map': {'1': ['spk9']}},
        }
        servicer._query_handler = handler
        resp = servicer.GetAudioSpeakers(
            mock.Mock(data=json.dumps({'audio_ids': [1]})))
        assert resp.success is True
        assert json.loads(resp.data)['speakers_map'] == {'1': ['spk9']}
        query = handler.handle_get_audio_speakers.call_args[0][0]
        assert query.audio_ids == [1]

    def test_handler_error_converges_to_failed_response(self):
        from audio_service.interfaces.grpc.servicers import AudioConfigServiceServicer
        servicer = AudioConfigServiceServicer()
        handler = mock.Mock()
        handler.handle_get_audio_speakers.side_effect = RuntimeError('boom')
        servicer._query_handler = handler
        resp = servicer.GetAudioSpeakers(mock.Mock(data='{"audio_ids": [1]}'))
        assert resp.success is False


# ── api_test_service 消费端 ACL：GetAudioSpeakers gRPC 实现 ──

def _patch_speakers_stub(monkeypatch, stub):
    import shared.clients.grpc_clients as gc
    monkeypatch.setattr(gc, 'get_audio_config_service_stub', lambda: stub)


class TestAudioSpeakersAclImpl:
    def test_success_returns_speakers_map(self, monkeypatch):
        from api_test_service.infrastructure.acl.audio_acl_repository import (
            AudioConfigAclRepositoryImpl,
        )
        from shared.proto import audio_service_pb2 as e2e_pb
        resp = e2e_pb.AudioConfigResponse(
            success=True, message='ok',
            data=json.dumps({'speakers_map': {'1': ['spk9'], '2': []}}))
        stub = mock.Mock()
        stub.GetAudioSpeakers.return_value = resp
        _patch_speakers_stub(monkeypatch, stub)
        result = AudioConfigAclRepositoryImpl().get_audio_speakers([1, 2])
        assert result == {'1': ['spk9'], '2': []}
        req = stub.GetAudioSpeakers.call_args[0][0]
        assert json.loads(req.data) == {'audio_ids': [1, 2]}

    def test_empty_ids_skips_grpc(self, monkeypatch):
        from api_test_service.infrastructure.acl.audio_acl_repository import (
            AudioConfigAclRepositoryImpl,
        )
        stub = mock.Mock()
        _patch_speakers_stub(monkeypatch, stub)
        assert AudioConfigAclRepositoryImpl().get_audio_speakers([]) == {}
        stub.GetAudioSpeakers.assert_not_called()

    def test_success_false_converges_empty(self, monkeypatch):
        from api_test_service.infrastructure.acl.audio_acl_repository import (
            AudioConfigAclRepositoryImpl,
        )
        from shared.proto import audio_service_pb2 as e2e_pb
        resp = e2e_pb.AudioConfigResponse(success=False, message='db down', data='')
        stub = mock.Mock()
        stub.GetAudioSpeakers.return_value = resp
        _patch_speakers_stub(monkeypatch, stub)
        assert AudioConfigAclRepositoryImpl().get_audio_speakers([1]) == {}

    def test_grpc_error_converges_empty(self, monkeypatch):
        from api_test_service.infrastructure.acl.audio_acl_repository import (
            AudioConfigAclRepositoryImpl,
        )
        stub = mock.Mock()
        stub.GetAudioSpeakers.side_effect = ConnectionError('不可达')
        _patch_speakers_stub(monkeypatch, stub)
        assert AudioConfigAclRepositoryImpl().get_audio_speakers([1]) == {}


# ── 验收 3：源级守卫延续（执行器/应用层不直触 proto 与 stub 工厂）──

class TestNoDirectAnnotationStubAccess:
    _MODULES = [
        'api_test_service.core.realtime_session_executor',
        'api_test_service.core.api_session_executor',
        'api_test_service.core.api_executor',
        'api_test_service.application.round_render_service',
    ]
    _FORBIDDEN = [
        'get_audio_config_service_stub',
        'audio_service_pb2',
        'GetAudioSpeakersRequest',
    ]

    def test_executors_and_service_never_touch_annotation_stub(self):
        import importlib
        for name in self._MODULES:
            module = importlib.import_module(name)
            source = inspect.getsource(module)
            for token in self._FORBIDDEN:
                assert token not in source, \
                    f"{name} 直触了 {token}（标注查询必须经 ACL 端口出站）"
