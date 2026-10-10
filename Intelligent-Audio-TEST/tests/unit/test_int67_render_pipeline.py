# -*- coding: utf-8 -*-
"""INT-67 混音下沉管线单测 — AudioStreamOrchestrator + RenderAudioFile/Stream + Servicer

覆盖（08 设计文档 §3.1/§3.2/§3.3/§四/§五）：
- 编排路由表：http_api(±stream) / websocket_api / physical（显式拒绝）/ 未知
- 噪声合并复用 build_noise_info：executor 侧仅透传两级配置（require_devices=False）
- Step 2 格式适配（源 48k/stereo → 目标 16k/mono）、Step 3 增益（有 SPL 补偿+映射、无 SPL 原样）
- Step 4 speaker 感知时间轴复用（顺序/交叠/干扰人 delay/噪声独立混入）
- RenderAudioFile 整段混音（5A/6A）：长度、容器包装、逐样本无削波
- RenderAudioStream 逐窗混音（5B/6B）：100ms 窗口、is_last、补零、与整段输出逐字节一致
- Servicer：stream 逐 chunk 透传 / file 成功与失败收敛
"""
import base64
import json
import wave
import io
from types import SimpleNamespace

import numpy as np
import pytest

import audio_service.application.services.audio_stream_orchestrator as orch_mod
from audio_service.application.services.audio_stream_orchestrator import (
    AudioKind,
    AudioStreamOrchestrator,
)
from audio_service.application.services.render_audio_file import RenderAudioFile
from audio_service.application.services.render_audio_stream import RenderAudioStream

RATE = 16000


def _tone_pcm(seconds, rate, freq, amp, channels=1, sampwidth_bits=16):
    """合成测试音频 WAV bytes（固定幅值正弦，RMS 可预期）"""
    t = np.arange(int(rate * seconds)) / rate
    samples = amp * np.sin(2 * np.pi * freq * t)
    if channels == 2:
        samples = np.repeat(samples, 2)
    if sampwidth_bits == 16:
        return (np.clip(samples, -1, 1) * 32767).astype('<i2').tobytes()
    raise ValueError("仅 16bit 用于管线测试")


def _fake_loader(pcm_by_id):
    """替身源加载器：audio_id → (pcm bytes, 元数据)"""

    def load(self, audio_id):
        aid = int(audio_id)
        if aid not in pcm_by_id:
            raise FileNotFoundError(aid)
        pcm, rate, channels = pcm_by_id[aid]
        return pcm, {'sample_rate': rate, 'channels': channels, 'duration': 0.0}

    return load


def _patch_loader(monkeypatch, pcm_by_id):
    monkeypatch.setattr(AudioStreamOrchestrator, '_load_source_pcm', _fake_loader(pcm_by_id))


@pytest.fixture
def orchestrator():
    return AudioStreamOrchestrator()


class TestRoute:
    def test_http_api_non_stream_goes_file(self):
        assert AudioStreamOrchestrator.route('http_api', stream=False) == 'file'

    def test_http_api_stream_goes_stream(self):
        assert AudioStreamOrchestrator.route('http_api', stream=True) == 'stream'

    def test_websocket_api_goes_stream(self):
        assert AudioStreamOrchestrator.route('websocket_api') == 'stream'

    def test_physical_rejected(self):
        with pytest.raises(ValueError):
            AudioStreamOrchestrator.route('physical')

    def test_unknown_rejected(self):
        with pytest.raises(ValueError):
            AudioStreamOrchestrator.route('modem')


class TestNoiseMerge:
    """噪声合并复用 build_noise_info：两级配置透传，合并归 audio_service"""

    def test_resolve_noise_reuses_build_noise_info(self, monkeypatch):
        recorded = {}

        def fake_build_noise_info(round_config, case_config, require_devices=True):
            recorded['round'] = round_config
            recorded['case'] = case_config
            recorded['require_devices'] = require_devices
            return (({'spl': 45.0, 'audio_id': 3}, object()), [])

        monkeypatch.setattr(orch_mod, 'build_noise_info', fake_build_noise_info)
        config = {
            'round_noise': {'audio_id': 9, 'spl': 40, 'loop': True, 'delay': 500},
            'case_noise': {'audio_id': 3, 'spl': 45},
        }
        resolved = AudioStreamOrchestrator._resolve_noise(config)
        # 两级原样透传给 build_noise_info，且 API 路径不要求设备
        assert recorded['round'] == {'background_noise': config['round_noise']}
        assert recorded['case'] == {'background_noise': config['case_noise']}
        assert recorded['require_devices'] is False
        # 命中块（case 级优先，audio_id=3 命中）回填 loop/delay 透传字段
        assert resolved == {'audio_id': 3, 'spl': 45.0, 'loop': False, 'delay': 0.0}

    def test_resolve_noise_round_block_fields_when_round_wins(self, monkeypatch):
        monkeypatch.setattr(
            orch_mod, 'build_noise_info',
            lambda r, c, require_devices=True: (({'spl': 40.0, 'audio_id': 9}, object()), []))
        resolved = AudioStreamOrchestrator._resolve_noise({
            'round_noise': {'audio_id': 9, 'spl': 40, 'loop': True, 'delay': 250},
        })
        assert resolved == {'audio_id': 9, 'spl': 40.0, 'loop': True, 'delay': 250.0}

    def test_resolve_noise_empty(self):
        assert AudioStreamOrchestrator._resolve_noise({}) is None


class TestPrepare:
    def test_prepare_adapts_and_gains(self, monkeypatch, orchestrator):
        # 源 48k/stereo；目标 16k/mono；speaker spl=65（线性近似基准 → spl_gain=1.0），
        # 干扰人 spl=None（原样不动）
        _patch_loader(monkeypatch, {
            1: (_tone_pcm(1.0, 48000, 440, 0.5, channels=2), 48000, 2),
            2: (_tone_pcm(0.5, 48000, 880, 0.25, channels=2), 48000, 2),
        })
        config = {
            'task_id': 'T1',
            'target_format': {'sample_rate': RATE, 'bit_depth': 's16', 'channels': 1},
            'audios': [
                {'audio_id': 1, 'type': 'speaker', 'spl': 65, 'play_order': 0},
                {'audio_id': 2, 'type': 'speaker', 'spl': None, 'play_order': 1},
            ],
        }
        context = orchestrator.prepare(config)
        assert context.target_format.sample_rate == RATE
        assert len(context.sources) == 2
        s1, s2 = context.sources
        assert s1.kind == AudioKind.SPEAKER and s2.kind == AudioKind.SPEAKER
        # 适配到 16k mono：1s → 16000 帧
        assert s1.samples.size == RATE
        assert s2.samples.size == RATE // 2
        # spl=65 → rms_comp × linear_approx(65)=1.0 → 幅值 0.5 的正弦 RMS ≈ 0.5/√2（≈ -6dB）
        assert s1.gain_linear == pytest.approx(10 ** ((-30.0 - 20 * np.log10(0.5 / np.sqrt(2))) / 20), rel=1e-3)
        # spl=None → 原样 1.0
        assert s2.gain_linear == 1.0

    def test_prepare_noise_from_two_level_config(self, monkeypatch, orchestrator):
        _patch_loader(monkeypatch, {
            1: (_tone_pcm(0.5, RATE, 440, 0.5), RATE, 1),
            3: (_tone_pcm(0.2, RATE, 100, 0.3), RATE, 1),
        })
        monkeypatch.setattr(
            orch_mod, 'build_noise_info',
            lambda r, c, require_devices=True: (({'spl': 45.0, 'audio_id': 3}, object()), []))
        config = {
            'audios': [{'audio_id': 1, 'type': 'speaker', 'spl': None}],
            'round_noise': {'audio_id': 3, 'spl': 45, 'loop': True, 'delay': 100},
            'target_format': {'sample_rate': RATE, 'bit_depth': 's16', 'channels': 1},
        }
        context = orchestrator.prepare(config)
        kinds = [s.kind for s in context.sources]
        assert kinds == [AudioKind.SPEAKER, AudioKind.NOISE]
        noise = context.sources[1]
        assert noise.loop is True
        assert noise.delay_frames == int(0.1 * RATE)
        # loop 噪声铺满整缓冲
        assert context.total_frames >= len(noise.samples)

    def test_prepare_empty_rejected(self, monkeypatch, orchestrator):
        with pytest.raises(ValueError):
            orchestrator.prepare({'audios': []})

    def test_prepare_unknown_type_rejected(self, monkeypatch, orchestrator):
        _patch_loader(monkeypatch, {1: (_tone_pcm(0.1, RATE, 440, 0.5), RATE, 1)})
        with pytest.raises(ValueError):
            orchestrator.prepare({'audios': [{'audio_id': 1, 'type': 'alien'}]})


class TestTimeline:
    def test_sequential_and_interferer_and_noise(self, monkeypatch, orchestrator):
        _patch_loader(monkeypatch, {
            1: (_tone_pcm(1.0, RATE, 440, 0.5), RATE, 1),
            2: (_tone_pcm(1.0, RATE, 440, 0.5), RATE, 1),
            4: (_tone_pcm(0.5, RATE, 880, 0.3), RATE, 1),
            3: (_tone_pcm(0.1, RATE, 100, 0.2), RATE, 1),
        })
        config = {
            'target_format': {'sample_rate': RATE, 'bit_depth': 's16', 'channels': 1},
            'audios': [
                {'audio_id': 2, 'type': 'speaker', 'spl': None, 'play_order': 1},
                {'audio_id': 1, 'type': 'speaker', 'spl': None, 'play_order': 0},
                {'audio_id': 4, 'type': 'interferer', 'spl': None, 'delay': 2000},
            ],
            'round_noise': {'audio_id': 3, 'spl': 40, 'loop': False},
        }
        monkeypatch.setattr(
            orch_mod, 'build_noise_info',
            lambda r, c, require_devices=True: (({'spl': 40.0, 'audio_id': 3}, object()), []))
        context = orchestrator.prepare(config)
        placement_by_id = {
            context.sources[idx].audio_id: start for idx, start in context.placements
        }
        # speaker 按 play_order 顺序：0 → 0；1 → 第一条结束（1s = 16000 帧）
        assert placement_by_id[1] == 0
        assert placement_by_id[2] == RATE
        # 干扰人不参与时间轴：startDelay 2s
        assert placement_by_id[4] == 2 * RATE
        # 噪声独立混入：start 0
        assert placement_by_id[3] == 0
        # 总长 = max(2s, 2.5s, 2s+0.5s, 0.1s) = 2.5s
        assert context.total_frames == int(2.5 * RATE)

    def test_speaker_aware_overlap_reuses_timeline(self, monkeypatch, orchestrator):
        """共同 speaker → 顺序；无共同 speaker + overlap_time → 交叠（复用 E2E 计算）"""
        _patch_loader(monkeypatch, {
            1: (_tone_pcm(1.0, RATE, 440, 0.5), RATE, 1),
            2: (_tone_pcm(1.0, RATE, 440, 0.5), RATE, 1),
        })
        config = {
            'target_format': {'sample_rate': RATE, 'bit_depth': 's16', 'channels': 1},
            'audios': [
                {'audio_id': 1, 'type': 'speaker', 'spl': None, 'play_order': 0},
                {'audio_id': 2, 'type': 'speaker', 'spl': None, 'play_order': 1},
            ],
            'speakers_map': {'1': ['spk9'], '2': ['spk8']},
            'overlap_time': 0.5,   # 秒（与 E2E 时间轴函数口径一致）：无共同 speaker → 交叠 0.5s
        }
        context = orchestrator.prepare(config)
        placement_by_id = {
            context.sources[idx].audio_id: start for idx, start in context.placements
        }
        # 无共同 speaker → start = prev_end - 0.5s = 0.5s
        assert placement_by_id[1] == 0
        assert placement_by_id[2] == RATE // 2

    def test_common_speaker_sequential(self, monkeypatch, orchestrator):
        """相邻音频有共同 speaker → 顺序播放（复用 E2E speaker 感知判定的正向用例）"""
        _patch_loader(monkeypatch, {
            1: (_tone_pcm(1.0, RATE, 440, 0.5), RATE, 1),
            2: (_tone_pcm(1.0, RATE, 440, 0.5), RATE, 1),
        })
        config = {
            'target_format': {'sample_rate': RATE, 'bit_depth': 's16', 'channels': 1},
            'audios': [
                {'audio_id': 1, 'type': 'speaker', 'spl': None, 'play_order': 0},
                {'audio_id': 2, 'type': 'speaker', 'spl': None, 'play_order': 1},
            ],
            'speakers_map': {'1': ['spk9'], '2': ['spk9']},
            'overlap_time': 0.5,
        }
        context = orchestrator.prepare(config)
        placement_by_id = {
            context.sources[idx].audio_id: start for idx, start in context.placements
        }
        # 共同 speaker → 顺序：start = prev_end（交叠参数不生效）
        assert placement_by_id[1] == 0
        assert placement_by_id[2] == RATE


class TestFileExit:
    def _prepare(self, monkeypatch, orchestrator):
        _patch_loader(monkeypatch, {
            1: (_tone_pcm(1.0, RATE, 440, 0.5), RATE, 1),
        })
        return orchestrator.prepare({
            'task_id': 'T2',
            'target_format': {'sample_rate': RATE, 'bit_depth': 's16',
                              'channels': 1, 'container': 'wav'},
            'audios': [{'audio_id': 1, 'type': 'speaker', 'spl': None}],
        })

    def test_render_file_wav_container(self, monkeypatch, orchestrator):
        context = self._prepare(monkeypatch, orchestrator)
        result = RenderAudioFile.render(context)
        assert result['container'] == 'wav'
        assert result['sample_rate'] == RATE
        assert result['bit_depth'] == 's16'
        assert result['channels'] == 1
        assert result['duration_ms'] == 1000
        raw = base64.b64decode(result['audio_base64'])
        with wave.open(io.BytesIO(raw), 'rb') as w:
            assert w.getframerate() == RATE
            assert w.getnchannels() == 1
            assert w.getsampwidth() == 2
            assert w.getnframes() == RATE

    def test_render_file_pcm_container(self, monkeypatch, orchestrator):
        context = self._prepare(monkeypatch, orchestrator)
        context.target_format = type(context.target_format)(
            sample_rate=RATE, bit_depth='s16', channels=1, container='pcm')
        result = RenderAudioFile.render(context)
        raw = base64.b64decode(result['audio_base64'])
        assert len(raw) == RATE * 2

    def test_render_file_no_clipping_with_gains(self, monkeypatch, orchestrator):
        # 三源同相叠加经增益后仍被 clip 防削波
        _patch_loader(monkeypatch, {
            1: (_tone_pcm(0.5, RATE, 440, 0.9), RATE, 1),
            2: (_tone_pcm(0.5, RATE, 440, 0.9), RATE, 1),
            3: (_tone_pcm(0.5, RATE, 440, 0.9), RATE, 1),
        })
        context = orchestrator.prepare({
            'target_format': {'sample_rate': RATE, 'bit_depth': 's16', 'channels': 1},
            'audios': [
                {'audio_id': 1, 'type': 'speaker', 'spl': None},
                {'audio_id': 2, 'type': 'speaker', 'spl': None, 'play_order': 1, 'delay': 0},
                {'audio_id': 3, 'type': 'interferer', 'spl': None},
            ],
        })
        result = RenderAudioFile.render(context)
        raw = base64.b64decode(result['audio_base64'])
        vals = np.frombuffer(raw, dtype='<i2')
        assert vals.min() >= -32768 and vals.max() <= 32767


class TestStreamExit:
    def test_stream_matches_file_concatenation(self, monkeypatch, orchestrator):
        """强不变量：流式逐窗输出拼接 == 整段混音输出（补零尾窗对齐）"""
        _patch_loader(monkeypatch, {
            1: (_tone_pcm(1.0, 48000, 440, 0.5, channels=2), 48000, 2),
            2: (_tone_pcm(0.3, 48000, 880, 0.2, channels=2), 48000, 2),
            3: (_tone_pcm(0.25, RATE, 100, 0.1), RATE, 1),
        })
        monkeypatch.setattr(
            orch_mod, 'build_noise_info',
            lambda r, c, require_devices=True: (({'spl': 45.0, 'audio_id': 3}, object()), []))
        config = {
            'target_format': {'sample_rate': RATE, 'bit_depth': 's16', 'channels': 1},
            'audios': [
                {'audio_id': 1, 'type': 'speaker', 'spl': 65, 'play_order': 0},
                {'audio_id': 2, 'type': 'speaker', 'spl': None, 'play_order': 1,
                 'delay': 700},
            ],
            'round_noise': {'audio_id': 3, 'spl': 45, 'loop': True},
        }
        context = orchestrator.prepare(config)
        file_result = RenderAudioFile.render(context)
        file_raw = base64.b64decode(file_result['audio_base64'])

        chunks = list(RenderAudioStream.render(context))
        assert chunks
        window_frames = int(RATE * AudioStreamOrchestrator.chunk_duration_ms() / 1000)
        assert len(chunks) == -(-context.total_frames // window_frames)
        stream_raw = b''.join(base64.b64decode(c['data']) for c in chunks)
        # 除最后一窗补零外逐字节一致
        assert stream_raw[:len(file_raw)] == file_raw
        tail = stream_raw[len(file_raw):]
        decoded_tail = np.frombuffer(tail, dtype='<i2') if tail else np.array([])
        assert np.all(decoded_tail == 0)
        # 终帧标记
        assert chunks[-1]['is_last'] is True
        assert all(c['is_last'] is False for c in chunks[:-1])
        # chunk 序号连续
        assert [c['sequence'] for c in chunks] == list(range(len(chunks)))
        # 恒定窗口大小（Realtime 按恒定 chunk 时长推送）
        assert all(len(base64.b64decode(c['data'])) == window_frames * 2 for c in chunks)

    def test_stream_noise_loop_wraps_windows(self, monkeypatch, orchestrator):
        """loop 噪声跨窗口环绕平铺：窗口拼接与整段平铺一致"""
        noise = _tone_pcm(0.3, RATE, 100, 0.4)   # 0.3s 循环体，跨多窗
        _patch_loader(monkeypatch, {3: (noise, RATE, 1)})
        monkeypatch.setattr(
            orch_mod, 'build_noise_info',
            lambda r, c, require_devices=True: (({'spl': 50.0, 'audio_id': 3}, object()), []))
        context = orchestrator.prepare({
            'audios': [],
            'round_noise': {'audio_id': 3, 'spl': 50, 'loop': True, 'delay': 200},
            'target_format': {'sample_rate': RATE, 'bit_depth': 's16', 'channels': 1},
        })
        file_raw = base64.b64decode(RenderAudioFile.render(context)['audio_base64'])
        stream_raw = b''.join(
            base64.b64decode(c['data']) for c in RenderAudioStream.render(context))
        assert stream_raw[:len(file_raw)] == file_raw


class TestOrchestratorRenderDispatch:
    def test_render_dispatches_by_mode(self, monkeypatch, orchestrator):
        sentinel = object()
        captured = {}

        def fake_render_file(context):
            captured['file'] = True
            return sentinel

        def fake_render_stream(context):
            captured['stream'] = True
            return iter([sentinel])

        monkeypatch.setattr(RenderAudioFile, 'render', staticmethod(fake_render_file))
        monkeypatch.setattr(RenderAudioStream, 'render', staticmethod(fake_render_stream))
        monkeypatch.setattr(AudioStreamOrchestrator, 'prepare',
                            lambda self, cfg: SimpleNamespace())
        assert orchestrator.render({}, mode='file') is sentinel
        assert captured.get('file') is True
        assert list(orchestrator.render({}, mode='stream')) == [sentinel]
        assert captured.get('stream') is True
        with pytest.raises(ValueError):
            orchestrator.render({}, mode='bogus')


class TestRenderServicer:
    def _servicer_with_stub_orchestrator(self, monkeypatch, render_result):
        from audio_service.interfaces.grpc.servicers import RenderServiceServicer
        servicer = RenderServiceServicer()
        render_fn = render_result if callable(render_result) \
            else (lambda cfg, mode: render_result)
        fake_orch = SimpleNamespace(render=render_fn)
        monkeypatch.setattr(type(servicer), 'orchestrator',
                            property(lambda self: fake_orch))
        return servicer

    def test_stream_yields_chunks(self, monkeypatch):
        chunks = [
            {'sequence': 0, 'data': 'AAA=', 'is_last': False},
            {'sequence': 1, 'data': 'BBB=', 'is_last': True},
        ]
        servicer = self._servicer_with_stub_orchestrator(monkeypatch, chunks)
        from shared.proto import audio_service_pb2 as e2e_pb
        req = e2e_pb.RenderAudioStreamRequest(
            task_id='T9', render_config=json.dumps({'audios': []}))
        out = list(servicer.RenderAudioStream(req))
        assert len(out) == 2
        assert out[0].sequence == 0 and out[0].data == 'AAA=' and out[0].is_last is False
        assert out[1].sequence == 1 and out[1].is_last is True and out[1].message == ''

    def test_stream_failure_converges_to_error_chunk(self, monkeypatch):
        def boom(cfg, mode):
            raise RuntimeError('混音失败')
        servicer = self._servicer_with_stub_orchestrator(monkeypatch, boom)
        from shared.proto import audio_service_pb2 as e2e_pb
        req = e2e_pb.RenderAudioStreamRequest(task_id='T9', render_config='{}')
        out = list(servicer.RenderAudioStream(req))
        assert len(out) == 1
        assert out[0].is_last is True
        assert '混音失败' in out[0].message

    def test_file_success_and_failure(self, monkeypatch):
        from shared.proto import audio_service_pb2 as e2e_pb
        ok = self._servicer_with_stub_orchestrator(
            monkeypatch, lambda cfg, mode: {'container': 'wav', 'audio_base64': 'AAA='})
        resp = ok.RenderAudioFile(e2e_pb.RenderAudioFileRequest(
            task_id='T9', render_config='{}'))
        assert resp.success is True
        assert json.loads(resp.data)['container'] == 'wav'

        bad = self._servicer_with_stub_orchestrator(
            monkeypatch, lambda cfg, mode: (_ for _ in ()).throw(ValueError('bad config')))
        resp = bad.RenderAudioFile(e2e_pb.RenderAudioFileRequest(
            task_id='T9', render_config='{}'))
        assert resp.success is False
        assert 'bad config' in resp.message
