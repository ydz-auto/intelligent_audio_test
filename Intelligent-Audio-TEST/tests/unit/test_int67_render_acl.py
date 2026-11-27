# -*- coding: utf-8 -*-
"""INT-67 api_test_service 消费端混音单测 — AudioRenderACLRepositoryImpl（进程内）

覆盖（验收标准：混音已并入 api_test_service 进程，执行器不经 gRPC）：
- build_render_config：audios 透传 + 两级噪声透传 + 目标格式/SPL 映射
- route_render_mode：08 设计文档 §3.1 路由表（file/stream/physical 拒绝）
- render_audio_file：进程内整段混音 + DTO 还原（base64 → bytes / 元数据）
- render_audio_stream：逐 chunk 迭代 + 失败收敛（message + is_last 终止帧）
- 失败收敛：混音异常 → None / 终止帧
"""
import base64
import os

import pytest

# gRPC stub 工厂链导入 BaseConfig，测试环境仅需可导入（不真正访问 OSS）
os.environ.setdefault('OSS_ACCESS_KEY', 'test-access')
os.environ.setdefault('OSS_SECRET_KEY', 'test-secret')

import api_test_service.infrastructure.acl.audio_render_acl_repository as acl_mod
from api_test_service.domain.repositories.acl.audio_render_acl_repository import (
    RenderChunkDTO,
    RenderedAudioDTO,
    route_render_mode,
)
from api_test_service.infrastructure.acl.audio_render_acl_repository import (
    AudioRenderACLRepositoryImpl,
)


def _patch_render(monkeypatch, file_result=None, stream_chunks=(), error=None):
    """替身进程内混音：记录入参，按 mode 返回整段结果或逐 chunk 迭代。"""
    calls = {}

    def fake_render(render_config, mode):
        calls['mode'] = mode
        calls['config'] = render_config
        if error is not None:
            raise error
        if mode == 'file':
            return file_result
        return iter(stream_chunks)

    monkeypatch.setattr(acl_mod._orchestrator, 'render', fake_render)
    return calls


class TestBuildRenderConfig:
    def test_two_level_noise_passthrough_only(self):
        round_config = {
            'audios': [{'audio_id': 1, 'type': 'speaker', 'spl': 65}],
            'background_noise': {'audio_id': 3, 'spl': 45, 'loop': True, 'delay': 200},
        }
        case_config = {'background_noise': {'audio_id': 99, 'spl': 50}}
        config = AudioRenderACLRepositoryImpl.build_render_config(
            round_config, case_config)
        # 执行器侧只透传，不合并：round_noise / case_noise 原样携带
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
        """INT-1799：混音出口只由 streaming 决定（协议不参与）"""
        assert route_render_mode(False) == 'file'
        assert route_render_mode(True) == 'stream'
        # 历史 device_type 调用（确定性映射，仍可用）
        assert route_render_mode('http_api') == 'file'
        assert route_render_mode('websocket_api') == 'stream'
        with pytest.raises(ValueError):
            route_render_mode('physical')
        with pytest.raises(ValueError):
            route_render_mode('modem')


class TestRenderAudioFile:
    def test_in_process_returns_dto(self, monkeypatch):
        payload = {
            'container': 'wav',
            'audio_base64': base64.b64encode(b'RIFF....').decode('ascii'),
            'sample_rate': 16000, 'bit_depth': 's16', 'channels': 1,
            'duration_ms': 1000,
        }
        calls = _patch_render(monkeypatch, file_result=payload)

        repo = AudioRenderACLRepositoryImpl()
        config = {'audios': []}
        dto = repo.render_audio_file(config, task_id='T1')
        assert isinstance(dto, RenderedAudioDTO)
        assert dto.audio_bytes == b'RIFF....'
        assert (dto.container, dto.sample_rate, dto.bit_depth,
                dto.channels, dto.duration_ms) == ('wav', 16000, 's16', 1, 1000)
        assert calls['mode'] == 'file'
        assert calls['config'] is config

    def test_empty_audio_returns_none(self, monkeypatch):
        _patch_render(monkeypatch, file_result={'audio_base64': ''})
        assert AudioRenderACLRepositoryImpl().render_audio_file({}, 'T1') is None

    def test_mix_error_returns_none(self, monkeypatch):
        _patch_render(monkeypatch, error=ConnectionError('混音失败'))
        assert AudioRenderACLRepositoryImpl().render_audio_file({}, 'T1') is None


class TestRenderAudioStream:
    def test_stream_iterates_chunks(self, monkeypatch):
        chunks = [
            {'sequence': 0, 'data': 'AAA=', 'is_last': False, 'message': ''},
            {'sequence': 1, 'data': 'BBB=', 'is_last': True, 'message': ''},
        ]
        calls = _patch_render(monkeypatch, stream_chunks=chunks)
        repo = AudioRenderACLRepositoryImpl()
        config = {'audios': []}
        out = list(repo.render_audio_stream(config, task_id='T2'))
        assert [(c.sequence, c.data_b64, c.is_last) for c in out] == \
            [(0, 'AAA=', False), (1, 'BBB=', True)]
        assert calls['mode'] == 'stream'
        assert calls['config'] is config

    def test_stream_error_converges_to_terminal_chunk(self, monkeypatch):
        _patch_render(monkeypatch, error=ConnectionError('断流'))
        out = list(AudioRenderACLRepositoryImpl().render_audio_stream({}, task_id='T2'))
        assert len(out) == 1
        assert out[0].is_last is True
        assert out[0].sequence == -1
        assert '断流' in out[0].message

    def test_stream_chunk_dto_defaults(self):
        dto = RenderChunkDTO()
        assert (dto.sequence, dto.data_b64, dto.is_last, dto.message) == (0, '', False, '')
