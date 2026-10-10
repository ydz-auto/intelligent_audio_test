# -*- coding: utf-8 -*-
"""INT-67 双端冒烟（验收补充）：消费端 ACL → 真实 gRPC 传输 → RenderServiceServicer → 双出口。

补开发卡自测缺口（未起真实双端联调）：进程内起真实 gRPC server（注册真实
RenderServiceServicer，与 audio_service/interfaces/grpc/server.py 注册方式一致），
消费端经真实 AudioRenderACLRepositoryImpl 出站，全链路走真实 proto 序列化与
网络回环；仅「音频库存储读取」以替身承载（存储/DB 基础设施非本卡改动范围）。

覆盖：
- RenderAudioFile：24bit/44.1k/stereo 源 → 16k/s16/mono/wav（24bit 防误解析过线验证，
  与 16bit 同幅度源输出幅度一致）
- RenderAudioStream：chunk 契约（整窗恒定 = rate×ch×bytes×0.1s、序号连续、is_last 终帧）
- 强不变量：流式逐窗拼接 == 整段混音输出（真实传输下逐字节一致）
- ApiRmsSplService 校准点插值经线生效（映射倍增 → 输出 RMS 精确翻倍；clamp 边界）
- 失败收敛：file success=False → ACL 返回 None；stream 终止帧 message 不抛裸异常
- 消费端路由镜像 route_render_mode

打回项复现锁定（验收不通过，2026-10-10）：标注 xfail(strict=True) 的 3 例即
P1 缺陷「WAV 容器头按 PCM 解析」的复现锁——开发修复后这 3 例会通过，
strict xfail 将令套件翻红，届时必须移除标记。
"""
import base64
import io
import os
import wave
from concurrent import futures

import grpc
import numpy as np
import pytest

# gRPC stub 工厂链导入 BaseConfig，测试环境仅需可导入（不真正访问 OSS）
os.environ.setdefault('OSS_ACCESS_KEY', 'test-access')
os.environ.setdefault('OSS_SECRET_KEY', 'test-secret')

import shared.clients.grpc_clients as grpc_clients
from api_test_service.domain.repositories.acl.audio_render_acl_repository import (
    route_render_mode,
)
from api_test_service.infrastructure.acl.audio_render_acl_repository import (
    AudioRenderACLRepositoryImpl,
)
from audio_service.application.services.audio_stream_orchestrator import (
    AudioStreamOrchestrator,
    audio_stream_orchestrator,
)
from shared.proto import audio_service_pb2_grpc as audio_grpc

RATE = 16000
CHUNK_MS = 100
WINDOW_FRAMES = RATE * CHUNK_MS // 1000


def _sine(seconds, rate, freq, amp, channels=1):
    t = np.arange(int(rate * seconds)) / rate
    samples = amp * np.sin(2 * np.pi * freq * t)
    if channels == 2:
        samples = np.repeat(samples, 2)
    return samples.astype(np.float32)


def _wav_bytes(samples_f32, rate, channels, sampwidth):
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as w:
        w.setnchannels(channels)
        w.setsampwidth(sampwidth)
        w.setframerate(rate)
        if sampwidth == 2:
            w.writeframes((np.clip(samples_f32, -1, 1) * 32767).astype('<i2').tobytes())
        else:
            vals = (np.clip(samples_f32, -1, 1) * 8388607).astype('<i4')
            w.writeframes(vals.view(np.uint8).reshape(-1, 4)[:, :3].tobytes())
    return buf.getvalue()


def _patch_storage(monkeypatch, pcm_by_id):
    def load(self, audio_id):
        aid = int(audio_id)
        if aid not in pcm_by_id:
            raise FileNotFoundError(f"音频 {aid} 不存在或缺少 file_path")
        return pcm_by_id[aid]

    monkeypatch.setattr(AudioStreamOrchestrator, '_load_from_storage', load)


@pytest.fixture(autouse=True)
def _isolated_cache():
    audio_stream_orchestrator._pcm_cache.clear()
    yield
    audio_stream_orchestrator._pcm_cache.clear()


@pytest.fixture()
def render_server():
    from audio_service.interfaces.grpc.servicers import RenderServiceServicer
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=4))
    audio_grpc.add_RenderServiceServicer_to_server(RenderServiceServicer(), server)
    port = server.add_insecure_port('127.0.0.1:0')
    server.start()
    yield port
    server.stop(0)


@pytest.fixture()
def acl(render_server, monkeypatch):
    """消费端 ACL 出站经真实 gRPC 回环到本进程 server（替换 stub 工厂端口解析）"""
    channel = grpc.insecure_channel(f'127.0.0.1:{render_server}')
    monkeypatch.setattr(
        grpc_clients, 'get_render_service_stub',
        lambda: audio_grpc.RenderServiceStub(channel))
    yield AudioRenderACLRepositoryImpl()
    channel.close()


def _build_config(monkeypatch, pcm_by_id, **overrides):
    _patch_storage(monkeypatch, pcm_by_id)
    repo = AudioRenderACLRepositoryImpl
    defaults = dict(
        round_config={'audios': [{'audio_id': 10, 'type': 'speaker', 'spl': None}]},
        case_config={},
        target_format={'sample_rate': RATE, 'bit_depth': 's16', 'channels': 1,
                       'container': 'pcm'},
    )
    defaults.update(overrides)
    return repo.build_render_config(**defaults)


class TestFileExitOverRealGrpc:
    @pytest.mark.xfail(strict=True, reason=(
        'INT-67 打回项 P1：源加载把 WAV 容器整文件（含 44B RIFF 头）当 PCM 解析——'
        '头部变垃圾样本且时间轴整体偏移，24bit 因 44%3=2 持续 1 字节错位全样本损毁；'
        '修复后本用例翻红，需移除标记'))
    def test_24bit_stereo_44k_source_to_16k_mono_wav(self, acl, monkeypatch):
        src = _wav_bytes(_sine(1.0, 44100, 440, 0.5, channels=2), 44100, 2, 3)
        config = _build_config(
            monkeypatch, {10: (src, {'sample_rate': 44100, 'channels': 2})},
            target_format={'sample_rate': RATE, 'bit_depth': 's16', 'channels': 1,
                           'container': 'wav'})
        dto = acl.render_audio_file(config, task_id='SMOKE-1')
        assert dto is not None and dto.container == 'wav'
        assert (dto.sample_rate, dto.channels, dto.bit_depth) == (RATE, 1, 's16')
        assert dto.duration_ms == 1000
        with wave.open(io.BytesIO(dto.audio_bytes), 'rb') as w:
            assert w.getframerate() == RATE and w.getnchannels() == 1
            assert w.getsampwidth() == 2 and w.getnframes() == RATE
            raw = w.readframes(w.getnframes())
        vals = np.frombuffer(raw, dtype='<i2').astype(np.float64) / 32768.0
        # 24bit 误解析为 int16 会产生幅度/波形畸变：同幅度正弦下混后 RMS ≈ 0.5/√2
        assert np.sqrt(np.mean(vals ** 2)) == pytest.approx(0.5 / np.sqrt(2), rel=0.1)

    def test_24bit_and_16bit_same_amplitude_sources_render_equal_level(self, acl, monkeypatch):
        """同幅度正弦 24bit vs 16bit 源经同一适配链路 → 输出幅度一致（防误解析回归）"""
        mono = _sine(1.0, 44100, 440, 0.5, channels=1)
        stereo = np.repeat(mono, 2)
        config = _build_config(
            monkeypatch, {
                10: (_wav_bytes(stereo, 44100, 2, 3), {'sample_rate': 44100, 'channels': 2}),
                11: (_wav_bytes(stereo, 44100, 2, 2), {'sample_rate': 44100, 'channels': 2}),
            })
        r24 = acl.render_audio_file(config, task_id='SMOKE-2A')
        config2 = _build_config(
            monkeypatch, {10: (_wav_bytes(stereo, 44100, 2, 2), {'sample_rate': 44100, 'channels': 2})})
        r16 = acl.render_audio_file(config2, task_id='SMOKE-2B')
        rms24 = np.sqrt(np.mean((np.frombuffer(r24.audio_bytes, dtype='<i2').astype(np.float64)) ** 2))
        rms16 = np.sqrt(np.mean((np.frombuffer(r16.audio_bytes, dtype='<i2').astype(np.float64)) ** 2))
        assert rms24 == pytest.approx(rms16, rel=5e-3)


class TestStreamExitOverRealGrpc:
    @pytest.mark.xfail(strict=True, reason=(
        'INT-67 打回项 P1：同上——WAV 头按 PCM 解析使 duration/总帧数虚增'
        '（22 样本/源），流式拼接==整段强不变量失配；修复后本用例翻红，需移除标记'))
    def test_chunk_contract_and_strong_invariant(self, acl, monkeypatch):
        """整窗恒定 0.1s；序号连续；is_last 仅终帧；流式拼接 == 整段输出（逐字节）"""
        pcm_by_id = {
            10: (_wav_bytes(_sine(1.0, RATE, 440, 0.5), RATE, 1, 2), {'sample_rate': RATE, 'channels': 1}),
            11: (_wav_bytes(_sine(0.5, RATE, 880, 0.3), RATE, 1, 2), {'sample_rate': RATE, 'channels': 1}),
            12: (_wav_bytes(_sine(0.3, RATE, 990, 0.2), RATE, 1, 2), {'sample_rate': RATE, 'channels': 1}),
        }
        config = _build_config(
            monkeypatch, pcm_by_id,
            round_config={'audios': [
                {'audio_id': 10, 'type': 'speaker', 'spl': None, 'play_order': 0},
                {'audio_id': 11, 'type': 'speaker', 'spl': None, 'play_order': 1},
                {'audio_id': 12, 'type': 'interferer', 'spl': None, 'delay': 700},
            ]})
        file_dto = acl.render_audio_file(config, task_id='SMOKE-3')
        # 总长 1.5s = 24000 帧 = 15 整窗
        assert file_dto.duration_ms == 1500
        chunks = list(acl.render_audio_stream(config, task_id='SMOKE-3'))
        assert len(chunks) == 15
        assert all(c.message == '' for c in chunks)
        assert [c.sequence for c in chunks] == list(range(15))
        assert all(not c.is_last for c in chunks[:-1]) and chunks[-1].is_last
        # 整窗恒定：rate×ch×bytes×0.1s = 1600×1×2 = 3200B
        assert all(len(base64.b64decode(c.data_b64)) == 3200 for c in chunks)
        stream_raw = b''.join(base64.b64decode(c.data_b64) for c in chunks)
        assert stream_raw == file_dto.audio_bytes

    @pytest.mark.xfail(strict=True, reason=(
        'INT-67 打回项 P1：同上——WAV 头按 PCM 解析使 total_frames 虚增，'
        '尾窗长度失配；修复后本用例翻红，需移除标记'))
    def test_partial_tail_window_is_terminal_and_short(self, acl, monkeypatch):
        """1.55s（非整窗倍数）→ 16 chunk，末窗短且 is_last=True（恒定窗仅覆盖整窗）"""
        src = _wav_bytes(_sine(1.55, RATE, 440, 0.5), RATE, 1, 2)
        config = _build_config(monkeypatch, {10: (src, {'sample_rate': RATE, 'channels': 1})})
        chunks = list(acl.render_audio_stream(config, task_id='SMOKE-4'))
        assert len(chunks) == 16
        tail = base64.b64decode(chunks[-1].data_b64)
        # 总帧 24800 = 15 整窗 + 800 帧尾窗
        assert len(tail) == (24800 - 15 * WINDOW_FRAMES) * 2
        assert chunks[-1].is_last is True


class TestSplInterpolationOverRealGrpc:
    def _source(self, monkeypatch):
        src = _wav_bytes(_sine(0.5, RATE, 440, 0.5), RATE, 1, 2)
        _patch_storage(monkeypatch, {10: (src, {'sample_rate': RATE, 'channels': 1})})

    def _render_rms(self, acl, monkeypatch, spl, mapping):
        self._source(monkeypatch)
        config = AudioRenderACLRepositoryImpl.build_render_config(
            round_config={'audios': [{'audio_id': 10, 'type': 'speaker', 'spl': spl}]},
            case_config={}, spl_mapping=mapping,
            target_format={'sample_rate': RATE, 'bit_depth': 's16', 'channels': 1,
                           'container': 'pcm'})
        dto = acl.render_audio_file(config, task_id='SMOKE-5')
        return np.sqrt(np.mean((np.frombuffer(dto.audio_bytes, dtype='<i2').astype(np.float64)) ** 2))

    def test_calibrated_mapping_interpolates_through_wire(self, acl, monkeypatch):
        base = {'calibration_status': 'calibrated', 'calibration_points': [
            {'target_spl': 50.0, 'gain_linear': 0.5}, {'target_spl': 70.0, 'gain_linear': 2.0}]}
        doubled = {'calibration_status': 'calibrated', 'calibration_points': [
            {'target_spl': 50.0, 'gain_linear': 1.0}, {'target_spl': 70.0, 'gain_linear': 4.0}]}
        rms_a = self._render_rms(acl, monkeypatch, 60.0, base)      # 插值 1.25
        rms_b = self._render_rms(acl, monkeypatch, 60.0, doubled)   # 插值 2.50
        assert rms_b == pytest.approx(rms_a * 2.0, rel=2e-3)

    def test_clamp_boundary_below_min_point(self, acl, monkeypatch):
        mapping = {'calibration_status': 'calibrated', 'calibration_points': [
            {'target_spl': 50.0, 'gain_linear': 0.5}, {'target_spl': 70.0, 'gain_linear': 2.0}]}
        rms_below = self._render_rms(acl, monkeypatch, 40.0, mapping)
        rms_at_min = self._render_rms(acl, monkeypatch, 50.0, mapping)
        assert rms_below == pytest.approx(rms_at_min, rel=1e-6)


class TestFailureConvergenceOverRealGrpc:
    def test_file_missing_audio_returns_none(self, acl, monkeypatch):
        _patch_storage(monkeypatch, {})
        config = _build_config(monkeypatch, {})
        assert acl.render_audio_file(config, task_id='SMOKE-6') is None

    def test_stream_failure_converges_to_terminal_chunk(self, acl, monkeypatch):
        _patch_storage(monkeypatch, {})
        config = _build_config(monkeypatch, {})
        chunks = list(acl.render_audio_stream(config, task_id='SMOKE-7'))
        assert len(chunks) == 1
        assert chunks[0].is_last is True
        assert chunks[0].data_b64 == ''
        assert chunks[0].message


class TestConsumerRouteMirror:
    def test_route_render_mode(self):
        assert route_render_mode('http_api', stream=False) == 'file'
        assert route_render_mode('http_api', stream=True) == 'stream'
        assert route_render_mode('websocket_api') == 'stream'
        with pytest.raises(ValueError):
            route_render_mode('physical')
        with pytest.raises(ValueError):
            route_render_mode('modem')
