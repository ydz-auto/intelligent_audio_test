# -*- coding: utf-8 -*-
"""INT-67 api_test_service 消费端 ACL 单测 — AudioRenderACLRepositoryImpl

覆盖（验收标准：api_test_service 仅「组装请求 + 消费 chunk」，执行器不得直调 stub）：
- build_render_config：audios 透传 + 两级噪声透传（合并归 audio_service）+ 目标格式/SPL 映射
- route_render_mode：08 设计文档 §3.1 路由表（file/stream/physical 拒绝）
- render_audio_file：unary 调用 + DTO 还原（base64 → bytes / 元数据）
- render_audio_stream：逐 chunk 迭代 + 失败收敛（message + is_last 终止帧）
- 失败收敛：unary success=False → None；gRPC 异常 → None / 终止帧
"""
import base64
import json
import os
from unittest import mock

import pytest

# gRPC stub 工厂链导入 BaseConfig，测试环境仅需可导入（不真正访问 OSS）
os.environ.setdefault('OSS_ACCESS_KEY', 'test-access')
os.environ.setdefault('OSS_SECRET_KEY', 'test-secret')

from api_test_service.domain.repositories.acl.audio_render_acl_repository import (
    RenderChunkDTO,
    RenderedAudioDTO,
    route_render_mode,
)
from api_test_service.infrastructure.acl.audio_render_acl_repository import (
    AudioRenderACLRepositoryImpl,
)


def _fake_stub(file_response=None, stream_chunks=()):
    stub = mock.Mock()
    stub.RenderAudioFile.return_value = file_response
    stub.RenderAudioStream.return_value = iter(stream_chunks)
    return stub


def _patch_stub(monkeypatch, stub):
    import shared.clients.grpc_clients as gc
    monkeypatch.setattr(gc, 'get_render_service_stub', lambda: stub)


class TestBuildRenderConfig:
    def test_two_level_noise_passthrough_only(self):
        round_config = {
            'audios': [{'audio_id': 1, 'type': 'speaker', 'spl': 65}],
            'background_noise': {'audio_id': 3, 'spl': 45, 'loop': True, 'delay': 200},
        }
        case_config = {'background_noise': {'audio_id': 99, 'spl': 50}}
        config = AudioRenderACLRepositoryImpl.build_render_config(
            round_config, case_config)
        # 执行器侧只透传，不合并：round_noise / case_noise 原样出站
        assert config['audios'] == round_config['audios']
        assert config['round_noise'] == round_config['background_noise']
        assert config['case_noise'] == case_config['background_noise']
        assert 'background_noise' not in config
        assert config['overlap_rate'] == 0.0 and config['overlap_time'] == 0.0

    def test_optional_fields_omitted_when_absent(self):
        config = AudioRenderACLRepositoryImpl.build_render_config({}, {})
        assert 'target_format' not in config
        assert 'api_id' not in config
        assert 'spl_mapping' not in config
        assert 'speakers_map' not in config

    def test_full_fields_assembled(self):
        spl_mapping = {'calibration_status': 'calibrated',
                       'calibration_points': [{'target_spl': 65, 'gain_linear': 1.0}]}
        config = AudioRenderACLRepositoryImpl.build_render_config(
            {'audios': [{'audio_id': 1}]}, {},
            target_format={'sample_rate': 16000, 'bit_depth': 's16', 'channels': 1},
            api_id=7, spl_mapping=spl_mapping,
            speakers_map={'1': ['spk9']}, overlap_rate=0.2, overlap_time=0.5)
        assert config['target_format'] == {'sample_rate': 16000, 'bit_depth': 's16',
                                           'channels': 1}
        assert config['api_id'] == 7
        assert config['spl_mapping'] == spl_mapping
        assert config['speakers_map'] == {'1': ['spk9']}
        assert config['overlap_rate'] == 0.2
        assert config['overlap_time'] == 0.5


class TestRouteRenderMode:
    def test_route_table(self):
        assert route_render_mode('http_api', stream=False) == 'file'
        assert route_render_mode('http_api', stream=True) == 'stream'
        assert route_render_mode('websocket_api') == 'stream'
        with pytest.raises(ValueError):
            route_render_mode('physical')
        with pytest.raises(ValueError):
            route_render_mode('modem')


class TestRenderAudioFile:
    def test_unary_returns_dto(self, monkeypatch):
        payload = {
            'container': 'wav',
            'audio_base64': base64.b64encode(b'RIFF....').decode('ascii'),
            'sample_rate': 16000, 'bit_depth': 's16', 'channels': 1,
            'duration_ms': 1000,
        }
        resp = mock.Mock(success=True, message='ok',
                         data=json.dumps(payload))
        stub = _fake_stub(file_response=resp)
        _patch_stub(monkeypatch, stub)

        repo = AudioRenderACLRepositoryImpl()
        dto = repo.render_audio_file({'audios': []}, task_id='T1')
        assert isinstance(dto, RenderedAudioDTO)
        assert dto.audio_bytes == b'RIFF....'
        assert (dto.container, dto.sample_rate, dto.bit_depth,
                dto.channels, dto.duration_ms) == ('wav', 16000, 's16', 1, 1000)
        # 请求参数：task_id + render_config JSON
        req = stub.RenderAudioFile.call_args[0][0]
        assert req.task_id == 'T1'
        assert json.loads(req.render_config) == {'audios': []}

    def test_unary_success_false_returns_none(self, monkeypatch):
        resp = mock.Mock(success=False, message='mix failed', data='')
        _patch_stub(monkeypatch, _fake_stub(file_response=resp))
        assert AudioRenderACLRepositoryImpl().render_audio_file({}, 'T1') is None

    def test_grpc_error_returns_none(self, monkeypatch):
        stub = _fake_stub()
        stub.RenderAudioFile.side_effect = ConnectionError('服务不可达')
        _patch_stub(monkeypatch, stub)
        assert AudioRenderACLRepositoryImpl().render_audio_file({}, 'T1') is None


class TestRenderAudioStream:
    def test_stream_iterates_chunks(self, monkeypatch):
        chunks = [
            mock.Mock(sequence=0, data='AAA=', is_last=False, message=''),
            mock.Mock(sequence=1, data='BBB=', is_last=True, message=''),
        ]
        stub = _fake_stub(stream_chunks=chunks)
        _patch_stub(monkeypatch, stub)
        repo = AudioRenderACLRepositoryImpl()
        out = list(repo.render_audio_stream({'audios': []}, task_id='T2'))
        assert [(c.sequence, c.data_b64, c.is_last) for c in out] == \
            [(0, 'AAA=', False), (1, 'BBB=', True)]
        req = stub.RenderAudioStream.call_args[0][0]
        assert req.task_id == 'T2'
        assert json.loads(req.render_config) == {'audios': []}

    def test_stream_error_converges_to_terminal_chunk(self, monkeypatch):
        stub = _fake_stub()
        stub.RenderAudioStream.side_effect = ConnectionError('断流')
        _patch_stub(monkeypatch, stub)
        out = list(AudioRenderACLRepositoryImpl().render_audio_stream({}, task_id='T2'))
        assert len(out) == 1
        assert out[0].is_last is True
        assert out[0].sequence == -1
        assert '断流' in out[0].message

    def test_stream_chunk_dto_defaults(self):
        dto = RenderChunkDTO()
        assert (dto.sequence, dto.data_b64, dto.is_last, dto.message) == (0, '', False, '')
