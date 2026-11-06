# -*- coding: utf-8 -*-
"""INT-511 块 4：混音/SPL 测试 — mock 音频缓冲验证（不依赖真声卡/真设备）

覆盖（验收标准）：
- 混音引擎：speakers_map 交叠并行、噪声合并轮次级、多轨 play_multi、
  压缩增益 RMS 补偿 —— mock 音频缓冲/驱动验证（不真出声）
- SPL 映射双路径：SPLMappingService（audio_service 物理设备域）/ ApiRmsSplService
  （数字域）双实现、无映射 _linear_approx 回退、校准逻辑 —— mock 表数据验证
- 混音顺序契约（位深→float32→重采样→声道）+ SPL 增益计算正确
"""
import io
import math
import os
import threading
import wave
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import numpy as np
import pytest

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from audio_service.infrastructure.audio.audio_timeline import (
    build_audio_timelines,
    calculate_audio_delays,
    calculate_overlap_time,
    calculate_speaker_aware_audio_delays,
    get_audio_configs_for_offset,
    is_overlap_playback,
)
from audio_service.infrastructure.audio._engine_playback_mixin import (
    EnginePlaybackMixin,
)
from audio_service.domain.services.api_rms_spl_service import ApiRmsSplService as AudioApiRmsSplService
from audio_service.infrastructure.audio import spl_service as spl_service_module


def _wav_file(path, seconds, rate=16000, amp=0.5):
    """生成 s16 单声道 wav 测试文件"""
    t = np.arange(int(rate * seconds)) / rate
    samples = (amp * np.sin(2 * np.pi * 440 * t) * 32767).astype('<i2')
    with wave.open(str(path), 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(samples.tobytes())


@pytest.fixture
def wav_a(tmp_path):
    p = tmp_path / 'a.wav'
    _wav_file(p, 1.0)
    return str(p)


@pytest.fixture
def wav_b(tmp_path):
    p = tmp_path / 'b.wav'
    _wav_file(p, 0.5)
    return str(p)


# ──────────────────────────── 混音时间轴（纯函数） ────────────────────────────

def _cfg(file, **kw):
    base = {'file': file, 'channel': 0, 'gain': 1.0, 'is_noise': False}
    base.update(kw)
    return base


class TestTimelineDelays:
    def test_noise_merged_at_round_level_and_interferer_delay(self, wav_a, wav_b):
        """噪声合并轮次级：noise 恒 delay=0（随首干声起播）；interferer 用自身 delay"""
        configs = [
            _cfg(wav_a, play_order=0, duration=1.0),
            _cfg(wav_b, play_order=1, duration=0.5),
            _cfg(wav_a, is_noise=True),
            _cfg(wav_b, type='interferer', delay=1.5),
        ]
        result = calculate_audio_delays(configs, overlap_rate=0, is_overlap=False,
                                        overlap_time=0)
        # 顺序：干声按 play_order → 噪声（delay 0）→ interferer（自身 delay）
        assert result[0][1] == 0.0
        assert result[2][1] == 0.0          # 噪声并入轮次级
        assert result[3][0]['type'] == 'interferer'
        assert result[3][1] == 1.5

    def test_overlap_rate_formula(self, wav_a, wav_b):
        """overlap_rate 链式交叠：start = prev_end × (1 - overlap_rate)"""
        configs = [_cfg(wav_a, play_order=0, duration=1.0),
                   _cfg(wav_b, play_order=1, duration=0.5)]
        result = calculate_audio_delays(configs, overlap_rate=0.5, is_overlap=True)
        assert result[0][1] == 0.0
        assert result[1][1] == pytest.approx(0.5)   # 1.0 × (1-0.5)

    def test_speaker_aware_common_speaker_sequential(self, wav_a, wav_b):
        """speakers_map：相邻共同 speaker → 顺序播放（start = prev_end）"""
        configs = [
            _cfg(wav_a, play_order=0, duration=1.0, audio_id=1),
            _cfg(wav_b, play_order=1, duration=0.5, audio_id=2),
        ]
        speakers_map = {1: {'spkA'}, 2: {'spkA'}}   # 共同 speaker
        result = calculate_speaker_aware_audio_delays(
            configs, 0.5, True, speakers_map=speakers_map)
        assert result[0][1] == 0.0
        assert result[1][1] == pytest.approx(1.0)    # prev_end，顺序非交叠

    def test_speaker_aware_no_common_speaker_overlap(self, wav_a, wav_b):
        """speakers_map：无共同 speaker → 按 overlap_time 交叠"""
        configs = [
            _cfg(wav_a, play_order=0, duration=1.0, audio_id=1),
            _cfg(wav_b, play_order=1, duration=0.5, audio_id=2),
        ]
        speakers_map = {1: {'spkA'}, 2: {'spkB'}}    # 无共同 speaker
        result = calculate_speaker_aware_audio_delays(
            configs, 0.5, True, overlap_time=0.3, speakers_map=speakers_map)
        assert result[1][1] == pytest.approx(1.0 - 0.3)

    def test_build_audio_timelines_speaker_aware(self, wav_a, wav_b):
        """build_audio_timelines：speaker 感知 end 时间（共同 speaker → 顺序 end）"""
        audios = [
            (_cfg(wav_a, play_order=0, audio_id=1), SimpleNamespace(duration=1.0, file_path=wav_a)),
            (_cfg(wav_b, play_order=1, audio_id=2), SimpleNamespace(duration=0.5, file_path=wav_b)),
        ]
        timelines = build_audio_timelines(audios, overlap_rate=0.5, speakers_map={
            1: {'spkA'}, 2: {'spkA'}})
        assert timelines[0]['start'] == 0.0
        assert timelines[1]['start'] == pytest.approx(1.0)
        assert timelines[1]['end'] == pytest.approx(1.5)

    def test_is_overlap_playback(self):
        assert is_overlap_playback(0.3, 0) is True
        assert is_overlap_playback(0, 0.5) is True
        assert is_overlap_playback(0, 0) is False
        assert is_overlap_playback(None, None) is False

    def test_calculate_overlap_time_priority(self, wav_a):
        assert calculate_overlap_time(wav_a, overlap_time=0.3, overlap_rate=0.5) == 0.3
        assert calculate_overlap_time(wav_a, overlap_time=0, overlap_rate=0.5) == 0.5
        assert calculate_overlap_time(wav_a, overlap_time=0, overlap_rate=0) == 0.0


class TestOffsetSlicing:
    def _timelines(self, wav_a, wav_b):
        audios = [
            (_cfg(wav_a, play_order=0, audio_id=1, playback_device_id=1),
             SimpleNamespace(duration=1.0, file_path=wav_a)),
            (_cfg(wav_b, play_order=1, audio_id=2, playback_device_id=1),
             SimpleNamespace(duration=0.5, file_path=wav_b)),
        ]
        return build_audio_timelines(audios, overlap_rate=0, speakers_map={})

    def test_offset_skips_elapsed_and_sets_local_offset(self, wav_a, wav_b, monkeypatch):
        """get_audio_configs_for_offset：越过结束时间的音频跳过；落入窗口者裁 local_offset"""
        timelines = self._timelines(wav_a, wav_b)
        devices = {1: {'device_index': 2, 'channel_index': 0, 'gain': 1.0}}
        out = get_audio_configs_for_offset(timelines, global_offset=0.2,
                                           playback_devices_map=devices)
        assert [c['audio_id'] for c in out] == [1, 2]   # 两条都在窗口内
        assert out[0]['offset'] == pytest.approx(0.2)   # 首条已播 0.2s
        assert out[1]['offset'] == 0.0

        # global_offset 越过第二条结束 → 全部跳过
        out2 = get_audio_configs_for_offset(timelines, global_offset=2.0,
                                            playback_devices_map=devices)
        assert out2 == []

    def test_offset_applies_spl_gain_from_mapping(self, wav_a, wav_b, monkeypatch):
        """offset 切片经 SPL 映射求增益（mock spl_service.spl_to_gain 表数据）"""
        timelines = self._timelines(wav_a, wav_b)
        # 设备带 current_spl_mapping_id → 走 spl_service
        device = SimpleNamespace(current_spl_mapping_id=42)
        devices = {1: {'device_index': 2, 'channel_index': 0, 'gain': 1.0,
                       'device_obj': device}}
        monkeypatch.setattr(
            spl_service_module.spl_service, 'spl_to_gain',
            lambda mapping_id, target_spl, app=None: 0.5)
        out = get_audio_configs_for_offset(timelines, global_offset=0.1,
                                           playback_devices_map=devices)
        assert out[0]['gain'] == pytest.approx(0.5)
        # 无 SPL 映射设备 → 回退 device gain
        devices2 = {1: {'device_index': 2, 'channel_index': 0, 'gain': 0.8}}
        out2 = get_audio_configs_for_offset(timelines, global_offset=0.1,
                                            playback_devices_map=devices2)
        assert out2[0]['gain'] == pytest.approx(0.8)


# ──────────────────────────── 多轨 play_multi（mock 驱动，不真出声） ────────────────────────────

class _PlaybackHarness(EnginePlaybackMixin):
    """EnginePlaybackMixin 组合：mock 音频驱动 + 线程池，验证多轨配置透传"""

    def __init__(self, driver):
        self.active_players = {}
        self._audio_pool = ThreadPoolExecutor(max_workers=4)
        self._driver = driver

    def _get_driver(self):
        return self._driver

    def _get_audio_pool(self):
        return self._audio_pool

    def audio_pool_queue_depth(self):
        """线程池排队深度（INT-593 打点，与 audio_engine.AudioService 同实现）"""
        queue = getattr(self._audio_pool, '_work_queue', None)
        return queue.qsize() if queue is not None else 0


class TestPlayMulti:
    def test_play_overlap_passes_multi_track_configs_with_delays(self, wav_a, wav_b):
        """多轨 play_multi：干声+噪声+interferer 按时间轴 delay 组装后交驱动（不真出声）"""
        from audio_service.infrastructure.audio._engine_playback_mixin import (
            EnginePlaybackMixin,
        )
        driver = type('MockDriver', (), {'seen_configs': None})()
        driver.play_multi = lambda configs, device_index, stop_event, loop=False, **kw: (
            setattr(driver, 'seen_configs', list(configs)) or True)

        harness = _PlaybackHarness(driver)
        configs = [
            _cfg(wav_a, device_index=0, play_order=0, duration=1.0),
            _cfg(wav_b, device_index=0, play_order=1, duration=0.5),
            _cfg(wav_a, device_index=0, is_noise=True),
            _cfg(wav_b, device_index=0, type='interferer', delay=1.5),
        ]
        futures, _, _ = harness.play_overlap(1, configs, overlap_rate=0,
                                             speakers_map=None)
        for f in futures:
            f.result(timeout=3)

        seen = driver.seen_configs
        assert seen is not None
        # 4 条配置全部透传至 play_multi
        assert len(seen) == 4
        # 时间轴 delay 透传：干声[0, 1.0]、噪声[0]、interferer[1.5]（驱动层只见 delay/is_noise）
        delays = [c.get('delay') for c in seen]
        assert delays == [0.0, 1.0, 0.0, 1.5]
        noise = [c for c in seen if c.get('is_noise')]
        assert noise and noise[0]['delay'] == 0.0
        # 噪声强制循环语义由 is_noise 标记承载
        assert any(c.get('is_noise') for c in seen)

    def test_play_overlap_no_dry_returns_empty(self, wav_a):
        """无干声（纯噪声）→ 空编排（不建播放任务）"""
        from audio_service.infrastructure.audio._engine_playback_mixin import (
            EnginePlaybackMixin,
        )
        harness = _PlaybackHarness(SimpleNamespace(play_multi=lambda *a, **k: None))
        futures, _, _ = harness.play_overlap(1, [_cfg(wav_a, is_noise=True)],
                                             overlap_rate=0)
        assert futures == []


# ──────────────────────────── 压缩增益 RMS 补偿（mock 音频缓冲） ────────────────────────────

def _sine_samples(dbfs, rate=16000, seconds=0.1):
    """float32 采样序列，RMS 恰为 10^(dbfs/20)"""
    t = np.arange(int(rate * seconds)) / rate
    amp = 10.0 ** (dbfs / 20.0) * math.sqrt(2.0)
    return (amp * np.sin(2 * np.pi * 440 * t)).astype(np.float32)


class TestRmsCompensation:
    def test_rms_compensate_normalizes_to_target_dbfs(self):
        """压缩增益 RMS 补偿：-6 dBFS 缓冲 → 补偿到 -30 dBFS 目标"""
        samples = _sine_samples(-6.02)
        gain = AudioApiRmsSplService.rms_compensate(samples)
        expected = 10 ** ((-30.0 - (-6.02)) / 20.0)
        assert gain == pytest.approx(expected, rel=1e-2)

    def test_rms_compensate_silence_returns_one(self):
        assert AudioApiRmsSplService.rms_compensate(np.zeros(16, dtype=np.float32)) == 1.0
        assert AudioApiRmsSplService.rms_compensate(np.array([], dtype=np.float32)) == 1.0

    def test_compute_source_gain_no_spl_returns_one(self):
        """未配 SPL → 原始不动（不补偿，设计 §6.4）"""
        samples = _sine_samples(-6.02)
        assert AudioApiRmsSplService.compute_source_gain(samples, None) == 1.0

    def test_compute_source_gain_combines_rms_and_spl(self):
        """组合增益 effective = rms_compensate × spl_gain（与 E2E 公式同构）"""
        samples = _sine_samples(-6.02)
        gain = AudioApiRmsSplService.compute_source_gain(samples, 65.0)
        rms_comp = AudioApiRmsSplService.rms_compensate(samples)
        spl_gain = AudioApiRmsSplService._linear_approx(65.0)  # 1.0
        assert gain == pytest.approx(rms_comp * spl_gain, rel=1e-2)


# ──────────────────────────── SPL 映射双路径（mock 表数据） ────────────────────────────

class TestSplMappingServicePhysical:
    """SPLMappingService（audio_service 物理设备域）：mock gRPC 表数据"""

    def _patch(self, monkeypatch, mapping):
        monkeypatch.setattr(
            spl_service_module, '_get_spl_mapping_via_grpc', lambda mid: mapping)

    def test_calibration_points_interp(self, monkeypatch):
        """校准点插值：points[{spl, gain}] → np.interp"""
        self._patch(monkeypatch, {'calibration_data': {'points': [
            {'spl': 45, 'gainOffset': 20 * np.log10(0.1)},
            {'spl': 65, 'gainOffset': 0},
            {'spl': 85, 'gainOffset': 20 * np.log10(10.0)},
        ]}})
        gain = spl_service_module.spl_service.spl_to_gain(1, 55.0)
        # 45→0.1 与 65→1.0 中点 55 → 0.55
        assert gain == pytest.approx(0.55, rel=1e-6)

    def test_exact_target_uses_digital_gain(self, monkeypatch):
        """精确命中 target_spl → 直接返回 digital_gain（/100 换算）"""
        self._patch(monkeypatch, {'target_spl': 65.0, 'digital_gain': 123.0})
        gain = spl_service_module.spl_service.spl_to_gain(1, 65.0)
        assert gain == pytest.approx(1.23)

    def test_no_mapping_returns_one(self, monkeypatch):
        """无映射（gRPC 不可达）→ 默认增益 1.0"""
        self._patch(monkeypatch, None)
        assert spl_service_module.spl_service.spl_to_gain(1, 65.0) == 1.0

    def test_gain_limit_applied(self, monkeypatch):
        """限幅：超出 MAX_GAIN_LINEAR → 钳制"""
        self._patch(monkeypatch, {'calibration_data': {'points': [
            {'spl': 85, 'gainOffset': 20 * np.log10(1e9)},  # 荒谬大增益
        ]}})
        gain = spl_service_module.spl_service.spl_to_gain(1, 85.0)
        assert gain <= spl_service_module.SPLMappingService.MAX_GAIN_LINEAR + 1e-9


class TestApiRmsSplDualPath:
    """ApiRmsSplService（api_test_service 数字域）双路径：校准 / 无映射回退"""

    def test_calibrated_interp(self):
        from api_test_service.domain.entities.api_rms_spl_mapping import (
            ApiRmsSplMapping,
            CalibrationPoint,
        )
        from api_test_service.domain.services.api_rms_spl_service import ApiRmsSplService
        mapping = ApiRmsSplMapping(
            id=1, api_id=7, calibration_status='calibrated',
            calibration_points=[
                CalibrationPoint(target_spl=45, gain_linear=0.1),
                CalibrationPoint(target_spl=65, gain_linear=1.0),
                CalibrationPoint(target_spl=85, gain_linear=10.0),
            ])
        assert ApiRmsSplService.spl_to_gain_by_mapping(mapping, 55.0) == pytest.approx(0.55)

    def test_no_mapping_linear_approx_fallback(self):
        from api_test_service.domain.services.api_rms_spl_service import ApiRmsSplService
        service = ApiRmsSplService(repository=None)
        assert service.spl_to_gain(7, 65.0) == pytest.approx(1.0)
        assert service.spl_to_gain(7, 45.0) == pytest.approx(0.1, rel=1e-6)

    def test_rms_dbfs_to_spl_reference_shift(self):
        from api_test_service.domain.services.api_rms_spl_service import ApiRmsSplService
        # 基准 -30 dBFS ↔ 65 dB；-24 dBFS → 71 dB
        assert ApiRmsSplService.rms_dbfs_to_spl(-24.0) == pytest.approx(71.0)

    def test_compute_push_gain_anti_clip(self):
        """推送增益防削波：补偿后能量不超过 -5 dBFS 上限"""
        from api_test_service.domain.services.api_rms_spl_service import ApiRmsSplService
        service = ApiRmsSplService(repository=None)
        pcm = np.array([32767, -32767] * 500, dtype='<i2').tobytes()
        gain = service.compute_push_gain(pcm, api_id=7, target_spl=100.0)
        max_allowed = 10 ** ((-5.0 - (-30.0)) / 20.0)
        assert gain <= max_allowed + 1e-9


# ──────────────────────────── 混音顺序契约（位深→float32→重采样→声道） ────────────────────────────

class TestMixOrderContract:
    def _s24_bytes(self, int_vals):
        vals = np.asarray(int_vals, dtype='<i4')
        out = np.empty((vals.size, 3), dtype=np.uint8)
        view = vals.view(np.uint8).reshape(-1, 4)
        out[:, 0], out[:, 1], out[:, 2] = view[:, 0], view[:, 1], view[:, 2]
        return out.tobytes()

    def test_adapt_order_bitdepth_float32_resample_channels(self, monkeypatch):
        """混音顺序契约：位深→float32 解析 → 重采样（源声道布局）→ 通道转换"""
        from audio_service.domain.services.audio_format_adapter import (
            AudioFormat,
            AudioFormatAdapter,
        )
        calls = []

        def spy_resample(samples, src_rate, dst_rate, channels=1):
            calls.append((src_rate, dst_rate, channels))
            return np.zeros(len(samples) * dst_rate // src_rate, dtype=np.float32)

        monkeypatch.setattr(AudioFormatAdapter, 'resample', staticmethod(spy_resample))
        src = AudioFormat(sample_rate=48000, bit_depth='s24', channels=2)
        dst = AudioFormat(sample_rate=16000, bit_depth='s16', channels=1)
        pcm = self._s24_bytes(np.zeros(9600))   # 交织立体声 4800 帧 × 2ch
        AudioFormatAdapter.adapt(pcm, src, dst)
        assert calls, '重采样未被调用'
        # 重采样在源声道布局（channels=2）下进行 → 通道转换在其后
        assert calls[0] == (48000, 16000, 2)
