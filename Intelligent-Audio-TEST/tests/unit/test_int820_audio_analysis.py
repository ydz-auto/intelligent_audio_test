# -*- coding: utf-8 -*-
"""INT-820 音频特征分析 / 质量评估 / 处理（降噪/增益/剪辑）单测。

覆盖：
1. compute_features 纯函数：正弦波频谱特征（主频≈440Hz、THD≈0）、能量分布、时域特征
2. compute_quality 纯函数：正弦波 SNR/动态范围高、白噪声 SNR 低、频率响应覆盖、评分区间
3. denoise_samples / apply_gain 纯函数：谱减降噪提升 SNR、增益倍率与削波保护
4. AudioAnalysisService 服务层：analyze_features / assess_quality / process
   （mode=new 建记录、mode=overwrite 更新原记录、参数校验失败分支）
"""
import os
import types
import wave
from unittest import mock

import numpy as np
import pytest

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from shared.infrastructure.storage import storage

from audio_service.application.services.audio_analysis_service import (
    AudioAnalysisService,
    apply_gain,
    compute_features,
    compute_quality,
    denoise_samples,
)


# ── 合成音频工具 ─────────────────────────────────────────────

def _write_wav(path, samples, sr=44100):
    """float64 样本 → 16-bit 单声道 WAV。"""
    pcm = np.clip(samples * 32767, -32768, 32767).astype(np.int16)
    with wave.open(str(path), 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())
    return str(path)


def _make_sine(path, freq=440.0, duration=1.0, sr=44100, amplitude=0.5,
               offset_s=0.0):
    t = np.arange(int(sr * duration)) / sr
    samples = amplitude * np.sin(2 * np.pi * freq * (t - offset_s))
    if offset_s > 0:
        samples[: int(sr * offset_s)] = 0.0
    return _write_wav(path, samples, sr)


def _make_noise(path, duration=1.0, sr=44100, amplitude=0.1, seed=42):
    rng = np.random.default_rng(seed)
    samples = rng.uniform(-amplitude, amplitude, int(sr * duration))
    return _write_wav(path, samples, sr)


def _load(path):
    """复用服务的加载口径（pydub 解码 → 单声道 float）。"""
    from audio_service.application.services.audio_analysis_service import _load_audio
    return _load_audio(str(path))


def _fake_audio(**overrides):
    base = dict(
        id=1, filename='test_audio', original_filename='test_audio.wav',
        file_path='local://audios/test.wav', sample_rate=44100, channels=1,
        audio_type='dry', asr_text='', description='', source_language='',
    )
    base.update(overrides)
    return types.SimpleNamespace(**base)


# ── 纯函数：特征分析 ─────────────────────────────────────────

class TestComputeFeatures:

    def test_sine_wave_spectral(self, tmp_path):
        """440Hz 正弦：主频≈440、THD≈0、基频范围收窄到 440 附近。"""
        wav = _make_sine(tmp_path / 'sine.wav')
        samples, sr = _load(wav)
        features = compute_features(samples, sr)
        spectral = features['spectral']
        assert 380 < spectral['dominant_frequency'] < 500
        assert spectral['harmonic_distortion'] < 5.0
        assert 400 < spectral['fundamental_range_low'] < 480
        assert 400 < spectral['fundamental_range_high'] < 480
        assert spectral['fundamental_range_low'] <= spectral['fundamental_range_high']

    def test_sine_wave_energy_time(self, tmp_path):
        wav = _make_sine(tmp_path / 'sine.wav', amplitude=0.5)
        samples, sr = _load(wav)
        features = compute_features(samples, sr)
        energy = features['energy']
        td = features['time_domain']
        # 0.5 正弦：RMS ≈ -9 dBFS、峰值 ≈ -6 dBFS
        assert -12 < energy['average_energy_db'] < -6
        assert -8 < energy['peak_energy_db'] < -4
        # 纯音能量集中（谱平坦度低 → 集中度接近 1）
        assert energy['energy_concentration'] > 0.5
        # 440Hz@44.1k 过零率 ≈ 2*440/44100 ≈ 0.02
        assert 0.01 < td['zero_crossing_rate'] < 0.03
        # 稳态正弦：全程活跃、起始 ≈ 0
        assert td['active_duration_ratio'] > 0.9
        assert td['onset_time'] < 0.1

    def test_silence_leading_onset(self, tmp_path):
        """前 0.2s 静音：起始时间 ≈ 0.2s。"""
        wav = _make_sine(tmp_path / 'sine_offset.wav', offset_s=0.2)
        samples, sr = _load(wav)
        features = compute_features(samples, sr)
        assert 0.1 < features['time_domain']['onset_time'] < 0.3


# ── 纯函数：质量评估 ─────────────────────────────────────────

class TestComputeQuality:

    def test_sine_quality(self, tmp_path):
        """正弦波：SNR/动态范围高、带宽窄→频率响应评分低、整体评分中上。"""
        wav = _make_sine(tmp_path / 'sine.wav')
        samples, sr = _load(wav)
        quality = compute_quality(samples, sr)
        assert quality['snr_db'] > 30
        assert quality['dynamic_range_db'] > 40
        assert quality['frequency_response_score'] < 40
        assert 30 < quality['quality_score'] <= 100

    def test_noise_quality(self, tmp_path):
        """白噪声：SNR≈0、带宽全覆盖→频率响应评分高、整体评分低。"""
        wav = _make_noise(tmp_path / 'noise.wav')
        samples, sr = _load(wav)
        quality = compute_quality(samples, sr)
        assert quality['snr_db'] < 15
        assert quality['frequency_response_score'] > 50
        assert quality['quality_score'] < 60

    def test_quality_ranges(self, tmp_path):
        """质量指标均在有界区间内。"""
        wav = _make_sine(tmp_path / 'sine.wav')
        samples, sr = _load(wav)
        quality = compute_quality(samples, sr)
        assert 0 <= quality['snr_db'] <= 99
        assert 0 <= quality['dynamic_range_db'] <= 120
        assert 0 <= quality['frequency_response_score'] <= 100
        assert 0 <= quality['quality_score'] <= 100


# ── 纯函数：处理 ─────────────────────────────────────────────

class TestProcessingFunctions:

    def test_denoise_improves_snr(self, tmp_path):
        """谱减法降噪：含噪信号处理后 SNR 提升（≥3dB）。"""
        sr = 44100
        n = sr
        t = np.arange(n) / sr
        tone = 0.5 * np.sin(2 * np.pi * 440 * t)
        rng = np.random.default_rng(7)
        noise = rng.uniform(-0.05, 0.05, n)
        noisy = tone + noise
        before = compute_quality(noisy, sr)
        cleaned = denoise_samples(noisy.copy(), sr)
        after = compute_quality(cleaned, sr)
        assert after['snr_db'] > before['snr_db'] + 3

    def test_denoise_preserves_clean_tone(self):
        """谱门降噪不应把稳态主频误判为噪声：纯音处理前后幅度/SNR 基本不变。"""
        sr = 44100
        t = np.arange(sr) / sr
        tone = 0.4 * np.sin(2 * np.pi * 440 * t)
        out = denoise_samples(tone.copy(), sr)
        # 峰值与输入一致（响度保持）
        assert abs(float(np.max(np.abs(out))) - 0.4) < 0.01
        # 稳态纯音 SNR 保持高位
        assert compute_quality(out, sr)['snr_db'] > 50
        # RMS 接近原值 0.4/√2
        assert abs(float(np.sqrt(np.mean(out ** 2))) - 0.4 / np.sqrt(2)) < 0.02

    def test_apply_gain_multiplies(self):
        samples = np.full(100, 0.25)
        out = apply_gain(samples, 6.0)
        # 6dB → 幅度 × 10^(6/20)（≈1.9953）
        assert float(out[0]) == pytest.approx(0.25 * 10 ** (6.0 / 20.0), abs=1e-9)

    def test_apply_gain_clips_at_full_scale(self):
        samples = np.full(100, 0.9)
        out = apply_gain(samples, 12.0)  # 0.9*4=3.6 → 削波到 1.0
        assert float(np.max(out)) == pytest.approx(1.0, abs=1e-12)
        assert float(np.min(out)) >= -1.0

    def test_apply_gain_zero_db_unchanged(self):
        samples = np.array([0.1, -0.2, 0.3])
        out = apply_gain(samples, 0.0)
        np.testing.assert_allclose(out, samples)


# ── 服务层 ───────────────────────────────────────────────────

class TestAudioAnalysisService:

    def _service(self, repo):
        return AudioAnalysisService(repo=repo)

    @mock.patch.object(storage, 'load_file')
    def test_analyze_features_ok(self, load_file, tmp_path):
        wav = _make_sine(tmp_path / 'sine.wav')
        load_file.return_value = str(wav)
        repo = mock.MagicMock()
        repo.get_audio.return_value = _fake_audio()
        result = self._service(repo).analyze_features(1)
        assert result['success'] is True
        data = result['data']
        assert data['audio_id'] == 1
        assert 'spectral' in data and 'energy' in data and 'time_domain' in data

    @mock.patch.object(storage, 'load_file')
    def test_assess_quality_ok(self, load_file, tmp_path):
        wav = _make_sine(tmp_path / 'sine.wav')
        load_file.return_value = str(wav)
        repo = mock.MagicMock()
        repo.get_audio.return_value = _fake_audio()
        result = self._service(repo).assess_quality(1)
        assert result['success'] is True
        data = result['data']
        assert data['audio_id'] == 1
        assert 'snr_db' in data and 'quality_score' in data

    def test_audio_not_found(self):
        repo = mock.MagicMock()
        repo.get_audio.return_value = None
        svc = self._service(repo)
        for call in (svc.analyze_features, svc.assess_quality):
            result = call(999)
            assert result['success'] is False
            assert result['code'] == 404

    @mock.patch.object(storage, 'load_file')
    @mock.patch.object(storage, 'save_file')
    def test_process_new_creates_record(self, save_file, load_file, tmp_path):
        wav = _make_sine(tmp_path / 'sine.wav')
        load_file.return_value = str(wav)
        save_file.return_value = 'local://audios/processed/x.wav'
        repo = mock.MagicMock()
        repo.get_audio.return_value = _fake_audio()
        new_audio = _fake_audio(id=99)
        repo.create_audio.return_value = new_audio
        result = self._service(repo).process(1, {'operation': 'gain', 'gain_db': 6.0})
        assert result['success'] is True
        data = result['data']
        assert data['mode'] == 'new'
        assert data['new_audio_id'] == 99
        assert data['format'] == 'wav'
        assert data['file_path'] == 'local://audios/processed/x.wav'
        repo.create_audio.assert_called_once()
        repo.update_audio.assert_not_called()
        create_kwargs = repo.create_audio.call_args[0][0]
        assert create_kwargs['name'] == 'test_audio_gain'

    @mock.patch.object(storage, 'load_file')
    @mock.patch.object(storage, 'save_file')
    def test_process_overwrite_updates_record(self, save_file, load_file, tmp_path):
        wav = _make_sine(tmp_path / 'sine.wav')
        load_file.return_value = str(wav)
        save_file.return_value = 'local://audios/processed/y.wav'
        repo = mock.MagicMock()
        repo.get_audio.return_value = _fake_audio()
        result = self._service(repo).process(
            1, {'operation': 'denoise', 'mode': 'overwrite'})
        assert result['success'] is True
        assert result['data']['mode'] == 'overwrite'
        assert result['data']['audio_id'] == 1
        repo.update_audio.assert_called_once()
        repo.create_audio.assert_not_called()
        update_fields = repo.update_audio.call_args[0][1]
        assert update_fields['file_path'] == 'local://audios/processed/y.wav'
        assert update_fields['format'] == 'wav'

    @mock.patch.object(storage, 'load_file')
    def test_process_trim_ok(self, load_file, tmp_path):
        wav = _make_sine(tmp_path / 'sine.wav', duration=2.0)
        load_file.return_value = str(wav)
        repo = mock.MagicMock()
        repo.get_audio.return_value = _fake_audio()
        new_audio = _fake_audio(id=100)
        repo.create_audio.return_value = new_audio
        result = self._service(repo).process(
            1, {'operation': 'trim', 'start_ms': 500, 'end_ms': 1500})
        assert result['success'] is True
        assert result['data']['new_audio_id'] == 100
        assert abs(result['data']['duration'] - 1.0) < 0.1

    @mock.patch.object(storage, 'load_file')
    def test_process_trim_only_start_ms(self, load_file, tmp_path):
        """仅给 start_ms（省略 end_ms）：裁去开头、保留到音频末尾。"""
        wav = _make_sine(tmp_path / 'sine.wav', duration=2.0)
        load_file.return_value = str(wav)
        repo = mock.MagicMock()
        repo.get_audio.return_value = _fake_audio()
        new_audio = _fake_audio(id=101)
        repo.create_audio.return_value = new_audio
        result = self._service(repo).process(
            1, {'operation': 'trim', 'start_ms': 500})
        assert result['success'] is True
        assert abs(result['data']['duration'] - 1.5) < 0.1

    @mock.patch.object(storage, 'load_file')
    def test_process_trim_only_end_ms(self, load_file, tmp_path):
        """仅给 end_ms（省略 start_ms）：保留开头到 end_ms。"""
        wav = _make_sine(tmp_path / 'sine.wav', duration=2.0)
        load_file.return_value = str(wav)
        repo = mock.MagicMock()
        repo.get_audio.return_value = _fake_audio()
        new_audio = _fake_audio(id=102)
        repo.create_audio.return_value = new_audio
        result = self._service(repo).process(
            1, {'operation': 'trim', 'end_ms': 500})
        assert result['success'] is True
        assert abs(result['data']['duration'] - 0.5) < 0.1

    @mock.patch.object(storage, 'load_file')
    def test_process_trim_null_end_ms_defaults_full(self, load_file, tmp_path):
        """网关透传形态（end_ms 键存在但为 None）：默认取全长，不再 400。"""
        wav = _make_sine(tmp_path / 'sine.wav', duration=2.0)
        load_file.return_value = str(wav)
        repo = mock.MagicMock()
        repo.get_audio.return_value = _fake_audio()
        new_audio = _fake_audio(id=103)
        repo.create_audio.return_value = new_audio
        result = self._service(repo).process(
            1, {'operation': 'trim', 'start_ms': 500, 'end_ms': None})
        assert result['success'] is True
        assert abs(result['data']['duration'] - 1.5) < 0.1

    @mock.patch.object(storage, 'load_file')
    def test_process_gain_non_finite_rejected(self, load_file, tmp_path):
        """gain_db 非有限值（JSON 1e999 → inf）：拒绝，不产出垃圾音频。"""
        wav = _make_sine(tmp_path / 'sine.wav', duration=1.0)
        load_file.return_value = str(wav)
        repo = mock.MagicMock()
        repo.get_audio.return_value = _fake_audio()
        result = self._service(repo).process(
            1, {'operation': 'gain', 'gain_db': 1e999})
        assert result['success'] is False
        assert result['code'] == 400
        repo.create_audio.assert_not_called()

    def test_process_invalid_operation(self):
        repo = mock.MagicMock()
        repo.get_audio.return_value = _fake_audio()
        result = self._service(repo).process(1, {'operation': 'bogus'})
        assert result['success'] is False
        assert result['code'] == 400

    def test_process_invalid_mode(self):
        repo = mock.MagicMock()
        repo.get_audio.return_value = _fake_audio()
        result = self._service(repo).process(
            1, {'operation': 'gain', 'mode': 'both'})
        assert result['success'] is False
        assert result['code'] == 400

    @mock.patch.object(storage, 'load_file')
    def test_process_trim_invalid_interval(self, load_file, tmp_path):
        wav = _make_sine(tmp_path / 'sine.wav', duration=1.0)
        load_file.return_value = str(wav)
        repo = mock.MagicMock()
        repo.get_audio.return_value = _fake_audio()
        result = self._service(repo).process(
            1, {'operation': 'trim', 'start_ms': 800, 'end_ms': 500})
        assert result['success'] is False
        assert result['code'] == 400


# ── gRPC servicer 路径（INT-1662 回归：Query 缺 @dataclass 导致实例化即 TypeError） ──

class TestAnalyzeAudioFeaturesServicerPath:
    """servicer 必须能把 request.audio_id 构造成 Query 再进 handler。

    INT-1662：AnalyzeAudioFeaturesQuery 曾漏 @dataclass(frozen=True)，
    `AnalyzeAudioFeaturesQuery(audio_id=...)` 直接 TypeError，被 servicer 的
    try/except 吞成 success=false，前端恒 400。此用例只打 servicer → query → handler
    的装配链路，不依赖真实音频与数据库。
    """

    def _servicer(self, query_handler):
        from audio_service.interfaces.grpc.servicers import AudioConfigServiceServicer
        servicer = AudioConfigServiceServicer()
        servicer._query_handler = query_handler
        return servicer

    def test_query_is_frozen_dataclass(self):
        from dataclasses import is_dataclass
        from audio_service.application.queries import AnalyzeAudioFeaturesQuery

        assert is_dataclass(AnalyzeAudioFeaturesQuery)
        assert AnalyzeAudioFeaturesQuery(audio_id=7).audio_id == 7
        with pytest.raises(Exception):
            AnalyzeAudioFeaturesQuery(audio_id=7).audio_id = 8  # frozen

    def test_servicer_passes_query_to_handler(self):
        from shared.proto import audio_service_pb2 as audio_pb

        handler = mock.MagicMock()
        handler.handle_analyze_audio_features.return_value = {
            'success': True, 'message': '特征分析成功', 'code': 200,
            'data': {'audio_id': 7, 'spectral': {}},
        }
        servicer = self._servicer(handler)

        resp = servicer.AnalyzeAudioFeatures(
            audio_pb.AnalyzeAudioFeaturesRequest(audio_id=7))

        assert resp.success is True
        query = handler.handle_analyze_audio_features.call_args[0][0]
        from audio_service.application.queries import AnalyzeAudioFeaturesQuery
        assert isinstance(query, AnalyzeAudioFeaturesQuery)
        assert query.audio_id == 7
