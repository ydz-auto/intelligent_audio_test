# -*- coding: utf-8 -*-
"""INT-593 验收#2 的自动化双轨证据：≥12 声道（PlaybackDevice）并发播放模型。

无真机声卡的自动化环境按卡内风险章节走「pyaudio stub + 真机人工复核」双轨：
本文件验证**单进程承载 ≥12 声道并发的资源模型**成立——
- audio_play_ 线程池读配置容量 = 12（每设备/每声道 1 worker，V9.7.10 语义）；
- 16 个并发 play_multi（模拟 16 台设备/声道）全部成功、无死锁；
- 同时活跃流数峰值 = 12（= 池容量），即 12 声道真正并行而非排队串行；
- 池饱和时多余任务排队但最终全部完成（无起播永久阻塞）。

60s 真机连续播放、0 underrun/爆音 属真机复核项（需真实多声道声卡），
本文件不替代真机，只证明自动化侧可达到的并发承载能力。
"""
import importlib
import importlib.util
import os
import struct
import sys
import threading
import time
import types
import wave
from unittest import mock

import pytest


def _make_wav(path, rate=16000, channels=1, frames=1600, amp=1000):
    samples = struct.pack('<' + 'h' * (frames * channels), *([amp] * (frames * channels)))
    with wave.open(str(path), 'wb') as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(samples)
    return str(path)


def _get_real_module(name):
    try:
        return importlib.import_module(name)
    except Exception:
        return None


@pytest.fixture
def concurrent_driver(monkeypatch, tmp_path):
    """可实例化 PyAudioDriver + 可观测并发的 stub 设备层。

    StubStream 在 open 时登记「活跃」，close/is_active 结束登记「非活跃」，
    测试通过峰值活跃数断言并发承载能力。
    """
    stubs = {}
    pa = types.ModuleType('pyaudio')
    pa.PyAudio = lambda: mock.MagicMock()
    for k, v in {
        'paFloat32': 1, 'paInt32': 2, 'paInt16': 8, 'paInt24': 0x8000,
        'paInt8': 16, 'paUInt8': 32, 'paContinue': 0, 'paComplete': 1,
        'paAbort': 2, 'paOutputOverflow': 8,
    }.items():
        setattr(pa, k, v)
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
    stubs['numpy'] = _get_real_module('numpy')

    sys.modules.pop('audio_service.infrastructure.audio.audio_driver', None)
    sys.modules.pop('audio_service.infrastructure.audio.audio_engine', None)
    with mock.patch.dict(sys.modules, stubs, clear=False):
        drv_mod = importlib.import_module('audio_service.infrastructure.audio.audio_driver')
        with mock.patch.object(drv_mod, 'log_and_emit', lambda *a, **k: None):
            drv = drv_mod.PyAudioDriver()
            drv.pa.get_device_info_by_index = lambda idx: {
                'maxOutputChannels': 2, 'defaultSampleRate': 16000, 'name': f'dev{idx}'}

            state = {'active': 0, 'max_active': 0, 'opened': []}

            def _track_inc():
                with threading.Lock():
                    state['active'] += 1
                    if state['active'] > state['max_active']:
                        state['max_active'] = state['active']

            def _track_dec():
                with threading.Lock():
                    state['active'] -= 1

            class StubStream:
                def __init__(self, idx):
                    self.idx = idx
                    self._left = 8  # is_active 返回 True 8 次 ≈ 0.8s 播放窗
                    with threading.Lock():
                        state['opened'].append(idx)
                    _track_inc()

                def is_active(self):
                    if self._left > 0:
                        self._left -= 1
                        return True
                    return False

                def stop_stream(self):
                    pass

                def close(self):
                    _track_dec()

            drv.pa.open = mock.MagicMock(side_effect=lambda **kw: StubStream(
                kw.get('output_device_index', 0)))

            wav = _make_wav(tmp_path / 'c.wav')

            yield drv, state, wav
    sys.modules.pop('audio_service.infrastructure.audio.audio_driver', None)
    sys.modules.pop('audio_service.infrastructure.audio.audio_engine', None)


class TestTwelveChannelConcurrentPlayback:
    """验收#2 自动化双轨：≥12 声道并发播放资源模型。"""

    def test_pool_is_12_workers_from_config(self):
        from audio_service.infrastructure.audio.audio_engine import AudioService
        svc = AudioService()
        svc._audio_pool = None
        assert svc._get_audio_pool()._max_workers == 12

    def test_sixteen_concurrent_devices_peak_active_12(self, concurrent_driver):
        """16 台设备/声道并发 play_multi：同时活跃流峰值 = 池容量 12。

        若播放被串行化（GIL/流锁），峰值会接近 1；若 12 声道无法承载，
        16 任务会有失败/死锁。峰值 12 证明每设备 play_multi 在独立 worker
        上并行执行（单进程内等价「每声道 1 worker」）。
        """
        drv, state, wav = concurrent_driver
        from audio_service.infrastructure.audio.audio_engine import AudioService
        svc = AudioService()
        pool = svc._get_audio_pool()

        results = {}

        def _run(i):
            try:
                drv.play_multi(
                    [{'file': wav, 'channel': 0, 'gain': 1.0, 'is_noise': False}],
                    device_index=i,
                    started_monotonic=time.monotonic(),
                )
                results[i] = 'ok'
            except Exception as e:  # noqa: BLE001
                results[i] = repr(e)

        futures = [pool.submit(_run, i) for i in range(16)]
        for f in futures:
            f.result(timeout=60)

        assert all(v == 'ok' for v in results.values()), f'并发播放失败: {results}'
        assert len(state['opened']) == 16, f'应打开 16 个设备流，实际 {state["opened"]}'
        assert state['max_active'] >= 12, (
            f'同时活跃流峰值 {state["max_active"]} < 12：播放被串行化，'
            f'不满足「≥12 声道并发承载」')
        assert state['active'] == 0, '播放结束后仍有流未释放（泄漏）'

    def test_saturation_queues_but_completes(self, concurrent_driver):
        """池饱和（16 > 12 worker）时多余任务排队，但最终全部完成、无死锁。

        对应「第 11/12 声道起播延迟」风险：队列等待可观测（排队深度打点），
        但不会永久阻塞或失败。
        """
        drv, state, wav = concurrent_driver
        from audio_service.infrastructure.audio.audio_engine import AudioService
        svc = AudioService()
        pool = svc._get_audio_pool()

        results = {}
        queue_depths_seen = set()

        def _run(i):
            try:
                q = svc.audio_pool_queue_depth()
                queue_depths_seen.add(q)
                drv.play_multi(
                    [{'file': wav, 'channel': 0, 'gain': 1.0, 'is_noise': False}],
                    device_index=i,
                    started_monotonic=time.monotonic(),
                )
                results[i] = 'ok'
            except Exception as e:  # noqa: BLE001
                results[i] = repr(e)

        futures = [pool.submit(_run, i) for i in range(16)]
        for f in futures:
            f.result(timeout=60)

        assert all(v == 'ok' for v in results.values()), f'饱和下播放失败: {results}'
        assert state['max_active'] >= 12
        # 至少观测到队列深度 > 0（16 任务 > 12 worker，必然有排队时刻）
        assert any(q > 0 for q in queue_depths_seen), (
            f'饱和场景未观测到排队深度打点: {queue_depths_seen}')
