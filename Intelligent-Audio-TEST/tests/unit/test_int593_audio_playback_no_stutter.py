# -*- coding: utf-8 -*-
"""INT-593 微服务音频播放链路无卡顿保障 — 代码级回归防线

对应审计结论三 1-6 项（开发工程师B 修复输入）：
- P1 回调实时性：_predecode_audio_buffers 预解码+预乘增益；_create_multi_callback
  预解码路径与每回调解析路径逐帧输出一致；overflow 计数/回调最大耗时量化采集；
  死代码 effective_gain_db = 20*log10(...) 已移除（回调不再逐文件重复计算）。
- P1 播放启动阻塞：calculate_gain_compensation 按文件签名（path+mtime+size）缓存，
  同一文件重复播放不再整文件分块 RMS 全扫。
- P1 流式混音 CPU：RenderAudioStream 切片后乘（每窗只乘所需段），输出与整段混音逐字节一致。
- P2 线程池容量/配置化：audio_engine._get_audio_pool 读取
  execution_engine.audio_playback_max_workers（默认 12），拒绝硬编码 10；
  audio_pool_queue_depth 队列深度打点。
- P2 量化采集：play_multi 起播延迟（started_monotonic 含线程池排队）、
  overflows、callback_max_ms 指标打点。

测试环境：无音频硬件，stub pyaudio/pydub/shared.infrastructure.storage；
真实 numpy 可用则用真实（回调混音/缓存签名依赖 numpy）。
"""
import importlib
import importlib.util
import os
import struct
import sys
import types
import wave
from unittest import mock

import pytest

# audio_driver → shared.infrastructure.storage → BaseConfig 要求 OSS 凭据环境变量，
# 测试环境仅需可导入（不真正访问 OSS），缺省占位
os.environ.setdefault('OSS_ACCESS_KEY', 'test-access')
os.environ.setdefault('OSS_SECRET_KEY', 'test-secret')


def _make_wav(path, rate, channels=1, frames=1600, amp=1000):
    """写入一个单声道/双声道 PCM wav（恒定直流/正弦无需，用直流便于幅度断言）。"""
    if channels == 1:
        samples = struct.pack('<' + 'h' * frames, *([amp] * frames))
    else:
        samples = struct.pack('<' + 'h' * (frames * channels), *([amp] * (frames * channels)))
    with wave.open(str(path), 'wb') as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(samples)
    return str(path)


# NumPy 2.x 扩展模块每进程只允许动态加载一次；driver_env 复用
# test_path_b_pre_resample 的进程级缓存模式，避免跨用例重载报错。
_REAL_MODULES: dict = {}


def _get_real_module(name: str):
    if name in _REAL_MODULES:
        return _REAL_MODULES[name]
    try:
        mod = importlib.import_module(name)
    except Exception:
        mod = None
    _REAL_MODULES[name] = mod
    return mod


@pytest.fixture
def driver_env(monkeypatch, tmp_path):
    """提供可实例化的 PyAudioDriver（stub pyaudio/pydub/storage；numpy 真实可用则用真实）。"""
    stubs = {}

    pa = types.ModuleType('pyaudio')
    pa.PyAudio = lambda: mock.MagicMock()
    # 与真实 portaudio 常量一致（回调比较语义不变）
    pa.paFloat32 = 1
    pa.paInt32 = 2
    pa.paInt16 = 8
    pa.paInt24 = 0x8000
    pa.paInt8 = 16
    pa.paUInt8 = 32
    pa.paContinue = 0
    pa.paComplete = 1
    pa.paAbort = 2
    pa.paOutputOverflow = 8
    stubs['pyaudio'] = pa

    pd = types.ModuleType('pydub')

    class _AS:
        @staticmethod
        def from_file(*a, **k):
            raise RuntimeError('pydub stub')
    pd.AudioSegment = _AS
    stubs['pydub'] = pd

    st = types.ModuleType('shared.infrastructure.storage')

    class _S:
        def load_file(self, key):
            raise AssertionError('storage.load_file 不应用于本地文件用例')
    st.storage = _S()
    stubs['shared.infrastructure.storage'] = st

    real_numpy = _get_real_module('numpy')
    if real_numpy is not None:
        stubs['numpy'] = real_numpy
    else:
        stubs['numpy'] = types.ModuleType('numpy')

    real_scipy = _get_real_module('scipy')
    if real_scipy is not None:
        stubs['scipy'] = real_scipy
    else:
        sc = types.ModuleType('scipy')
        sc.signal = types.ModuleType('signal')
        stubs['scipy'] = sc

    monkeypatch.setenv('RESAMPLE_TEMP_PATH', str(tmp_path))
    sys.modules.pop('audio_service.infrastructure.audio.audio_driver', None)
    with mock.patch.dict(sys.modules, stubs, clear=False):
        drv_mod = importlib.import_module('audio_service.infrastructure.audio.audio_driver')
        with mock.patch.object(drv_mod, 'log_and_emit', lambda *a, **k: None):
            drv = drv_mod.PyAudioDriver()
            yield drv_mod, drv
    sys.modules.pop('audio_service.infrastructure.audio.audio_driver', None)


# --------------------------------------------------------------------------- #
#  P2 线程池容量/配置化：读取 audio_playback_max_workers（默认 12）             #
# --------------------------------------------------------------------------- #
class TestAudioPoolConfig:
    def _service(self):
        from audio_service.infrastructure.audio.audio_engine import AudioService
        svc = AudioService()
        svc._audio_pool = None
        return svc

    def test_pool_reads_config_max_workers(self, monkeypatch):
        from shared.utils.config_manager import config_manager
        monkeypatch.setattr(
            config_manager, 'get_value',
            lambda *a, **k: 12)
        svc = self._service()
        pool = svc._get_audio_pool()
        assert pool._max_workers == 12

    def test_pool_defaults_12_when_config_missing(self, monkeypatch):
        from shared.utils.config_manager import config_manager
        # 模拟配置文件中无该项 → config_manager 回落调用方默认（12）
        monkeypatch.setattr(
            config_manager, 'get_value',
            lambda service, key, default=None: default)
        svc = self._service()
        pool = svc._get_audio_pool()
        # 配置缺失回落默认 12（V9.7.10 语义：每声道/每设备 1 worker），拒绝硬编码 10
        assert pool._max_workers == 12

    def test_pool_respects_configured_value(self, monkeypatch):
        from shared.utils.config_manager import config_manager
        monkeypatch.setattr(
            config_manager, 'get_value',
            lambda *a, **k: 16)
        svc = self._service()
        assert svc._get_audio_pool()._max_workers == 16

    def test_queue_depth_zero_fresh_and_int(self):
        from audio_service.infrastructure.audio.audio_engine import AudioService
        svc = AudioService()
        svc._audio_pool = None
        assert svc.audio_pool_queue_depth() == 0


# --------------------------------------------------------------------------- #
#  P1 播放启动阻塞：增益补偿按文件签名缓存                                      #
# --------------------------------------------------------------------------- #
class TestGainCompensationCache:
    def test_second_call_hits_cache(self, driver_env, tmp_path, monkeypatch):
        drv_mod, drv = driver_env
        wav = _make_wav(tmp_path / 'a.wav', 16000)
        calls = []
        monkeypatch.setattr(
            drv, '_compute_gain_compensation',
            lambda p: (calls.append(p) or 1.0))
        drv_mod.clear_gain_compensation_cache()
        assert drv.calculate_gain_compensation(wav) == 1.0
        assert drv.calculate_gain_compensation(wav) == 1.0
        assert len(calls) == 1, '第二次调用应命中缓存（不再整文件 RMS 全扫）'

    def test_file_replaced_invalidates_cache(self, driver_env, tmp_path, monkeypatch):
        drv_mod, drv = driver_env
        wav = tmp_path / 'a.wav'
        _make_wav(str(wav), 16000, frames=1600)
        calls = []
        monkeypatch.setattr(
            drv, '_compute_gain_compensation',
            lambda p: (calls.append(p) or 1.0))
        drv_mod.clear_gain_compensation_cache()
        drv.calculate_gain_compensation(str(wav))
        # 文件内容/大小变化 → 签名失效 → 重算
        _make_wav(str(wav), 16000, frames=3200)
        drv.calculate_gain_compensation(str(wav))
        assert len(calls) == 2

    def test_cache_survives_other_file(self, driver_env, tmp_path, monkeypatch):
        """不同文件互不串扰（签名含绝对路径）。"""
        drv_mod, drv = driver_env
        wav1 = _make_wav(tmp_path / 'a1.wav', 16000)
        wav2 = _make_wav(tmp_path / 'a2.wav', 16000)
        calls = []
        monkeypatch.setattr(
            drv, '_compute_gain_compensation',
            lambda p: (calls.append(p) or 1.0))
        drv_mod.clear_gain_compensation_cache()
        drv.calculate_gain_compensation(wav1)
        drv.calculate_gain_compensation(wav1)
        drv.calculate_gain_compensation(wav2)
        assert len(calls) == 2


# --------------------------------------------------------------------------- #
#  P1 回调实时性：预解码缓冲 + 回调输出一致性 + 量化采集                          #
# --------------------------------------------------------------------------- #
class TestCallbackPredecode:
    def _open_wav(self, path, channels, rate):
        return wave.open(path, 'rb')

    def test_predecode_output_matches_reference_mix(self, driver_env, tmp_path, monkeypatch):
        """预解码路径输出 == 每回调解析参考实现（逐字节一致）。"""
        drv_mod, drv = driver_env
        if not callable(getattr(getattr(drv_mod, 'np', None), 'frombuffer', None)):
            pytest.skip('回调混音需要 numpy，当前环境缺失')
        wav = _make_wav(tmp_path / 'tone.wav', 16000, channels=1, frames=1600, amp=4000)
        wf = self._open_wav(wav, 1, 16000)
        effective_gains = [2.0]
        # 量化采集：回调最大耗时需可观测（真实耗时可能为 0ms，打桩单调钟制造 0.5ms 间隔）
        counter = {'n': 0}

        def _fake_monotonic():
            counter['n'] += 1
            return 1000.0 + counter['n'] * 0.5
        monkeypatch.setattr(drv_mod.time, 'monotonic', _fake_monotonic)

        bufs = drv._predecode_audio_buffers([wf], effective_gains)
        assert bufs is not None and len(bufs) == 1

        metrics = {'overflows': 0, 'callback_max_ms': 0.0, 'start_latency_ms': None}
        cb = drv._create_multi_callback(
            stream_channels=2, stream_rate=16000,
            audio_gains=[1.0], gain_compensations=[2.0],
            file_channels_list=[1], file_rates_list=[16000],
            channel_indices=[0], wave_files=[wf],
            parent_stop_event=None, loop=False,
            audio_is_noise_list=[False], audio_delays=[0.0], audio_loops_list=[False],
            effective_gains=effective_gains, decoded_buffers=bufs,
            play_metrics=metrics,
        )
        out_bytes, flag = cb(None, 1600, None, None)
        assert flag == drv_mod.pyaudio.paContinue

        # 参考实现：逐帧解析 + 增益乘（旧回调数学）
        wf.rewind()
        ref = drv_mod.AudioFormatAdapter.to_int16_scale(wf.readframes(1600), 2) * 2.0
        out_ref = drv_mod.np.zeros(1600 * 2, dtype='float32')
        out_ref[0:1600 * 2:2] += ref[:1600]
        out_ref = drv_mod.np.clip(out_ref, -32768, 32767).astype('<i2')
        assert out_bytes == out_ref.tobytes()
        # 直流 amp=4000 × 增益2 → 8000（int16 幅度约定，取通道 0 偶数下标样本）
        vals = drv_mod.np.frombuffer(out_bytes, dtype='<i2')[0::2]
        assert abs(int(vals[0]) - 8000) <= 1
        assert metrics['callback_max_ms'] > 0.0, '回调最大耗时已采集'

    def test_callback_counts_output_overflow(self, driver_env, tmp_path):
        """PortAudio callback status paOutputOverflow → overflow 计数（量化采集）。"""
        drv_mod, drv = driver_env
        wav = _make_wav(tmp_path / 't.wav', 16000, frames=1600)
        wf = wave.open(wav, 'rb')
        bufs = drv._predecode_audio_buffers([wf], [1.0])
        metrics = {'overflows': 0, 'callback_max_ms': 0.0, 'start_latency_ms': None}
        cb = drv._create_multi_callback(
            stream_channels=1, stream_rate=16000,
            audio_gains=[1.0], gain_compensations=[1.0],
            file_channels_list=[1], file_rates_list=[16000],
            channel_indices=[0], wave_files=[wf],
            parent_stop_event=None, loop=False,
            audio_is_noise_list=[False], audio_delays=[0.0], audio_loops_list=[False],
            effective_gains=[1.0], decoded_buffers=bufs,
            play_metrics=metrics,
        )
        cb(None, 1600, None, drv_mod.pyaudio.paOutputOverflow)
        assert metrics['overflows'] == 1
        cb(None, 1600, None, 0)
        assert metrics['overflows'] == 1

    def test_predecode_memory_fallback(self, driver_env, tmp_path):
        """总内存超限 → 返回 None（回退每回调解析），不 OOM。"""
        drv_mod, drv = driver_env
        wav = _make_wav(tmp_path / 't.wav', 16000, frames=1600)
        wf = wave.open(wav, 'rb')
        bufs = drv._predecode_audio_buffers([wf], [1.0], max_total_bytes=1)
        assert bufs is None

    def test_callback_fallback_path_without_predecode(self, driver_env, tmp_path):
        """未传入 effective_gains/decoded_buffers 时回退每回调解析（旧语义，兼容兜底）。"""
        drv_mod, drv = driver_env
        wav = _make_wav(tmp_path / 't.wav', 16000, frames=1600, amp=1000)
        wf = wave.open(wav, 'rb')
        metrics = {'overflows': 0, 'callback_max_ms': 0.0, 'start_latency_ms': None}
        cb = drv._create_multi_callback(
            stream_channels=1, stream_rate=16000,
            audio_gains=[1.0], gain_compensations=[1.0],
            file_channels_list=[1], file_rates_list=[16000],
            channel_indices=[0], wave_files=[wf],
            parent_stop_event=None, loop=False,
            audio_is_noise_list=[False], audio_delays=[0.0], audio_loops_list=[False],
            play_metrics=metrics,
        )
        out_bytes, flag = cb(None, 1600, None, None)
        assert flag == drv_mod.pyaudio.paContinue
        vals = drv_mod.np.frombuffer(out_bytes, dtype='<i2')
        assert abs(int(vals[0]) - 1000) <= 1

    def test_predecode_restores_wave_position(self, driver_env, tmp_path):
        """预解码后 wave 句柄位置复位（回退路径/复用安全）。"""
        drv_mod, drv = driver_env
        wav = _make_wav(tmp_path / 't.wav', 16000, frames=3200)
        wf = wave.open(wav, 'rb')
        wf.setpos(800)
        before = wf.tell()
        bufs = drv._predecode_audio_buffers([wf], [1.0])
        assert bufs is not None
        assert wf.tell() == before


# --------------------------------------------------------------------------- #
#  P2 量化采集：play_multi 起播延迟/overflow 打点端到端                          #
# --------------------------------------------------------------------------- #
class TestPlayMultiMetrics:
    def test_play_multi_logs_start_latency_and_metrics(self, driver_env, tmp_path, monkeypatch):
        drv_mod, drv = driver_env
        wav = _make_wav(tmp_path / 't.wav', 16000, frames=1600)

        # stub 设备信息与流（is_active 第一次 True 后 False，自然结束）
        pa = drv.pa
        pa.get_device_info_by_index = lambda idx: {
            'maxOutputChannels': 2, 'defaultSampleRate': 16000, 'name': 'stub'}
        stream = mock.MagicMock()
        state = {'active': True}

        def _is_active():
            cur = state['active']
            state['active'] = False
            return cur
        stream.is_active = _is_active
        pa.open = mock.MagicMock(return_value=stream)

        captured = []
        monkeypatch.setattr(drv_mod, 'log_and_emit', lambda *a, **k: captured.append((a[0], a[1], a[2])))

        import time as _t
        t0 = _t.monotonic()
        drv.play_multi(
            [{'file': wav, 'channel': 0, 'gain': 1.0, 'is_noise': False}],
            device_index=0,
            started_monotonic=t0,
        )

        metric_lines = [m for m in captured if m[2].startswith('[play_metrics]')]
        assert metric_lines, f'应输出 play_metrics 打点，实际: {captured}'
        start_line = [m for m in metric_lines if 'start_latency_ms=' in m[2]]
        assert start_line, f'应含 start_latency_ms 打点: {metric_lines}'
        assert float(start_line[0][2].split('start_latency_ms=')[1].split(',')[0]) >= 0.0
        # overflows=0、callback_max_ms 存在
        final_line = [m for m in metric_lines if 'overflows=' in m[2]]
        assert final_line and 'callback_max_ms=' in final_line[-1][2]

    def test_play_multi_fallback_when_no_predecode(self, driver_env, tmp_path, monkeypatch):
        """预解码超限仍能正常播放（回退路径不破坏 play_multi）。"""
        drv_mod, drv = driver_env
        wav = _make_wav(tmp_path / 't.wav', 16000, frames=1600)
        pa = drv.pa
        pa.get_device_info_by_index = lambda idx: {
            'maxOutputChannels': 2, 'defaultSampleRate': 16000, 'name': 'stub'}
        stream = mock.MagicMock()
        state = {'active': True}

        def _is_active():
            cur = state['active']
            state['active'] = False
            return cur
        stream.is_active = _is_active
        pa.open = mock.MagicMock(return_value=stream)

        captured = []
        monkeypatch.setattr(drv_mod, 'log_and_emit', lambda *a, **k: captured.append((a[0], a[1], a[2])))
        monkeypatch.setattr(drv, '_predecode_audio_buffers', lambda *a, **k: None)

        import time as _t
        drv.play_multi(
            [{'file': wav, 'channel': 0, 'gain': 1.0, 'is_noise': False}],
            device_index=0,
            started_monotonic=_t.monotonic(),
        )
        assert any('[play_metrics]' in m[2] for m in captured)


# --------------------------------------------------------------------------- #
#  并发隔离（验收 #4）：render 流式混音 与 物理播放 同进程并发不互相破坏          #
# --------------------------------------------------------------------------- #
class TestConcurrentIsolation:
    """播放期间并发发起 render 流式混音：两条链路各自输出正确、互不阻塞。

    INT-593 的 GIL 竞争缓解（回调轻量化/混音切片后乘）后，同一 audio_service
    进程内 render 混音（CPU 密集）与物理实时播放可并发承载。
    """

    def test_render_stream_runs_concurrently_with_play_multi(self, driver_env, tmp_path, monkeypatch):
        import base64
        import threading
        import numpy as np
        from audio_service.application.services.audio_stream_orchestrator import (
            AudioStreamOrchestrator,
        )
        from audio_service.application.services.render_audio_file import RenderAudioFile
        from audio_service.application.services.render_audio_stream import RenderAudioStream

        rate = 16000

        def _tone_pcm(seconds, freq=440, amp=0.5):
            t = np.arange(int(rate * seconds)) / rate
            samples = amp * np.sin(2 * np.pi * freq * t)
            return (np.clip(samples, -1, 1) * 32767).astype('<i2').tobytes()

        # 1) render 流式混音上下文（真实 orchestration 管线）
        pcm_by_id = {1: (_tone_pcm(1.0), rate, 1)}

        def fake_loader(self, audio_id):
            pcm, sr, ch = pcm_by_id[int(audio_id)]
            return pcm, {'sample_rate': sr, 'channels': ch, 'duration': 0.0}

        monkeypatch.setattr(AudioStreamOrchestrator, '_load_source_pcm', fake_loader)
        ctx = AudioStreamOrchestrator().prepare({
            'task_id': 'T593c',
            'target_format': {'sample_rate': rate, 'bit_depth': 's16', 'channels': 1},
            'audios': [{'audio_id': 1, 'type': 'speaker', 'spl': None}],
        })
        file_raw = base64.b64decode(RenderAudioFile.render(ctx)['audio_base64'])

        # 2) 物理播放 stub（is_active 撑 3 拍 ≈ 0.3s，与 render 流式重叠）
        drv_mod, drv = driver_env
        wav = _make_wav(tmp_path / 'c.wav', rate, frames=1600)
        drv.pa.get_device_info_by_index = lambda idx: {
            'maxOutputChannels': 2, 'defaultSampleRate': rate, 'name': 'stub'}
        stream = mock.MagicMock()
        state = {'active': 3}

        def _is_active():
            if state['active'] > 0:
                state['active'] -= 1
                return True
            return False
        stream.is_active = _is_active
        drv.pa.open = mock.MagicMock(return_value=stream)

        render_chunks = []
        play_result = {}

        def _render_worker():
            render_chunks.append(list(RenderAudioStream.render(ctx)))

        def _play_worker():
            try:
                drv.play_multi(
                    [{'file': wav, 'channel': 0, 'gain': 1.0, 'is_noise': False}],
                    device_index=0,
                )
                play_result['ok'] = True
            except Exception as e:  # noqa: BLE001
                play_result['err'] = repr(e)

        tr = threading.Thread(target=_render_worker)
        tp = threading.Thread(target=_play_worker)
        tr.start()
        tp.start()
        tr.join(timeout=30)
        tp.join(timeout=30)
        assert not tr.is_alive() and not tp.is_alive()
        assert play_result.get('ok') is True, f'播放链路并发异常: {play_result.get("err")}'
        assert render_chunks, 'render 流式未产出 chunk'
        stream_raw = b''.join(base64.b64decode(c['data']) for c in render_chunks[0])
        assert stream_raw[:len(file_raw)] == file_raw, '并发期间 render 输出逐字节正确'

class TestRenderStreamSliceMultiply:
    """RenderAudioStream 切片后乘（每窗只乘所需段）不改变输出。"""

    def test_stream_matches_file_with_gain(self, monkeypatch):
        import base64
        import numpy as np
        import audio_service.application.services.audio_stream_orchestrator as orch_mod
        from audio_service.application.services.audio_stream_orchestrator import AudioStreamOrchestrator
        from audio_service.application.services.render_audio_file import RenderAudioFile
        from audio_service.application.services.render_audio_stream import RenderAudioStream

        rate = 16000

        def _tone_pcm(seconds, freq=440, amp=0.5, channels=1):
            t = np.arange(int(rate * seconds)) / rate
            samples = amp * np.sin(2 * np.pi * freq * t)
            if channels == 2:
                samples = np.repeat(samples, 2)
            return (np.clip(samples, -1, 1) * 32767).astype('<i2').tobytes()

        pcm_by_id = {
            1: (_tone_pcm(1.0), rate, 1),
            2: (_tone_pcm(0.5, freq=880, amp=0.25), rate, 1),
        }

        def fake_loader(self, audio_id):
            aid = int(audio_id)
            pcm, sr, ch = pcm_by_id[aid]
            return pcm, {'sample_rate': sr, 'channels': ch, 'duration': 0.0}

        monkeypatch.setattr(AudioStreamOrchestrator, '_load_source_pcm', fake_loader)
        config = {
            'task_id': 'T593',
            'target_format': {'sample_rate': rate, 'bit_depth': 's16', 'channels': 1},
            'audios': [
                {'audio_id': 1, 'type': 'speaker', 'spl': None, 'play_order': 0},
                {'audio_id': 2, 'type': 'speaker', 'spl': None, 'play_order': 1},
            ],
        }
        ctx = AudioStreamOrchestrator().prepare(config)
        file_raw = base64.b64decode(RenderAudioFile.render(ctx)['audio_base64'])
        stream_raw = b''.join(
            base64.b64decode(c['data']) for c in RenderAudioStream.render(ctx))
        assert stream_raw[:len(file_raw)] == file_raw
