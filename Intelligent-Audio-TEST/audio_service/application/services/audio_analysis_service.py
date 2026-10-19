# -*- coding: utf-8 -*-
"""音频特征分析 / 质量评估 / 处理（降噪/增益/剪辑）应用服务（INT-820 §3.3.2）。

计算口径（DSP，基于 pydub + numpy/scipy，栈内已有依赖）：
- 特征分析 analyze_features：
  - 频谱特征：基频范围（帧级自相关基频估计的 min/max）、主频能量峰（PSD 峰值频率）、
    谐波失真（THD%，基波 vs 谐波功率比）
  - 能量分布：平均能量（整体 RMS dBFS）、峰值能量（峰值 dBFS）、能量集中度（1 - 谱平坦度）
  - 时域特征：过零率、活跃时长占比（帧 RMS 相对峰值-50dB 门限）、起始时间（首个活跃帧）
- 质量评估 assess_quality：
  - 信噪比（谱域 SNR：信号平均功率密度 vs PSD 中位数宽带噪声底）
  - 动态范围（峰值幅度 vs 噪声底幅度）
  - 频率响应评分（-40dB 带宽覆盖可闻频带比例）
  - 整体质量评分（SNR/动态范围/频率响应加权）
- 处理 process：
  - denoise：STFT 谱减法（噪声谱估计自最低能量帧，谱底限制抑制音乐噪声）
  - gain：线性增益（gain_db → 10^(db/20)）+ 削波保护
  - trim：时间段裁剪（pydub 切片，保留原始采样参数）
  - mode=new（默认）生成新文件并创建新音频记录（原名 + 操作后缀）；
    mode=overwrite 用处理结果更新原记录 file_path/format/size/duration。
"""
from __future__ import annotations

import logging
import os
import tempfile
import uuid
from typing import Any, Dict, Optional, Tuple

import numpy as np

from shared.infrastructure.storage import storage
from audio_service.domain.repositories.audio_repository_abc import AudioRepositoryInterface
from audio_service.infrastructure.persistence.audio_repository import audio_repository

logger = logging.getLogger(__name__)

# ---- DSP 常量 ----
_DBFS_MIN = -120.0            # log10(0) 下限，避免 -inf
_FRAME_LENGTH = 2048          # STFT/帧长
_HOP_LENGTH = 512             # 帧移
_ACTIVE_THRESHOLD_OFFSET_DB = -50.0   # 活跃门限 = 峰值 dBFS + 该偏移
_PITCH_MIN_HZ = 50.0          # 基频估计下界（人声/常见音源下限）
_PITCH_MAX_HZ = 5000.0        # 基频估计上界
_AUDIBLE_BAND_LOW_HZ = 20.0   # 可闻频带下界
_AUDIBLE_BAND_HIGH_HZ = 20000.0  # 可闻频带上界
_BANDWIDTH_FALL_DB = -40.0    # 频率响应带宽判定的 PSD 跌落门限
_DENOISE_ALPHA = 1.5          # 谱减系数
_DENOISE_FLOOR_RATIO = 0.01   # 谱底比例（相对噪声谱估计）
_SNR_MAX_DB = 99.0
_DR_MAX_DB = 120.0


def _to_db(value, min_db: float = _DBFS_MIN):
    """线性幅度 → dB（相对满幅 1.0）。支持标量与数组输入。"""
    arr = np.asarray(value, dtype=np.float64)
    if arr.ndim == 0:
        v = float(arr)
        return min_db if v <= 1e-12 else 20.0 * np.log10(v)
    safe = np.maximum(arr, 1e-12)
    out = 20.0 * np.log10(safe)
    out[arr <= 1e-12] = min_db
    return out


def _load_audio(file_path: str) -> Tuple[np.ndarray, int]:
    """加载音频为 float64 单声道数组（归一化到 [-1,1]）+ 采样率。

    pydub 负责解码（mp3/flac/aac 等走 ffmpeg），多声道下混为单声道。
    """
    from pydub import AudioSegment
    seg = AudioSegment.from_file(file_path)
    sr = seg.frame_rate
    samples = np.array(seg.get_array_of_samples(), dtype=np.float64)
    if seg.channels > 1:
        samples = samples.reshape(-1, seg.channels).mean(axis=1)
    samples /= (1 << (8 * seg.sample_width - 1))
    return samples, sr


def _samples_to_segment(samples: np.ndarray, sr: int, sample_width: int = 2) -> Any:
    """float 数组 → pydub AudioSegment（单声道 PCM）。"""
    from pydub import AudioSegment
    scale = (1 << (8 * sample_width - 1)) - 1
    pcm = np.clip(samples * scale, -scale, scale).astype(np.int16)
    return AudioSegment(pcm.tobytes(), frame_rate=int(sr), sample_width=sample_width, channels=1)


def _frame_rms(samples: np.ndarray, sr: int,
               frame_length: int = _FRAME_LENGTH,
               hop_length: int = _HOP_LENGTH) -> np.ndarray:
    """按帧计算 RMS 能量。"""
    if samples.size < frame_length:
        samples = np.pad(samples, (0, frame_length - samples.size))
    n_frames = 1 + (samples.size - frame_length) // hop_length
    frames = np.array([
        samples[i * hop_length: i * hop_length + frame_length]
        for i in range(n_frames)
    ])
    return np.sqrt(np.mean(frames ** 2, axis=1))


def _power_spectrum(samples: np.ndarray, sr: int) -> Tuple[np.ndarray, np.ndarray]:
    """Welch 功率谱密度（单边），返回 (freqs, psd)。"""
    from scipy.signal import welch
    freqs, psd = welch(samples, fs=sr, nperseg=_FRAME_LENGTH, noverlap=_HOP_LENGTH)
    return freqs, psd


def _estimate_pitch_frame(frame: np.ndarray, sr: int) -> Optional[float]:
    """帧级基频估计（归一化自相关峰值）。

    在 [_PITCH_MIN_HZ, _PITCH_MAX_HZ] 区间内找自相关首峰，返回基频 Hz；
    能量过低或无峰返回 None。
    """
    frame = frame - frame.mean()
    n = frame.size
    energy = np.dot(frame, frame)
    if energy <= 1e-12:
        return None
    r = np.correlate(frame, frame, mode='full')[n - 1:] / energy
    lag_min = max(1, int(sr / _PITCH_MAX_HZ))
    lag_max = min(n - 1, int(sr / _PITCH_MIN_HZ))
    if lag_max <= lag_min:
        return None
    segment = r[lag_min:lag_max + 1]
    peak_idx = lag_min + int(np.argmax(segment))
    # 简单三点二次插值，提升子采样精度
    if 0 < peak_idx < n - 1:
        left, mid, right = r[peak_idx - 1], r[peak_idx], r[peak_idx + 1]
        denom = left - 2 * mid + right
        if abs(denom) > 1e-12:
            delta = 0.5 * (left - right) / denom
            peak_idx_f = peak_idx + float(np.clip(delta, -1.0, 1.0))
            return sr / peak_idx_f
    return sr / peak_idx if peak_idx > 0 else None


def _thd_percent(psd: np.ndarray, freqs: np.ndarray, f0: Optional[float]) -> float:
    """谐波失真 THD%（基波功率 vs 2×..N× 谐波功率）。

    f0 取主频；谐波带宽按 f0 比例（默认 ±10%，下限 5Hz）聚合 PSD。
    """
    if f0 is None or f0 <= 0 or float(np.sum(psd)) <= 1e-12:
        return 0.0

    def _band_power(fc: float) -> float:
        width = max(fc * 0.1, 5.0)
        mask = (freqs >= fc - width) & (freqs <= fc + width)
        return float(np.sum(psd[mask]))

    fund_power = _band_power(f0)
    if fund_power <= 1e-12:
        return 0.0
    harmonic_power = 0.0
    h = 2
    while h * f0 < freqs[-1] * 0.95:
        harmonic_power += _band_power(h * f0)
        h += 1
    thd = 100.0 * np.sqrt(harmonic_power) / np.sqrt(fund_power)
    return float(min(thd, 100.0))


def _spectral_flatness(psd: np.ndarray) -> float:
    """谱平坦度（几何均值/算术均值），能量集中度 = 1 - 平坦度。"""
    mask = psd > 1e-12
    if int(mask.sum()) < 2:
        return 0.0
    p = psd[mask]
    arith = float(np.mean(p))
    if arith <= 1e-12:
        return 1.0
    geo = float(np.exp(np.mean(np.log(p))))
    return float(np.clip(geo / arith, 0.0, 1.0))


def _spectral_noise_floor(psd: np.ndarray, sr: int) -> float:
    """宽带噪声底 RMS 估计：PSD 中位数密度 × 单边带宽（≈ sr/2）→ sqrt。

    纯音/窄带信号的 PSD 能量集中在少数 bin，中位数逼近背景噪声密度；
    宽带噪声（白噪）中位数 ≈ 均值 → 噪声底 ≈ 信号 RMS。
    """
    density = float(np.median(psd))
    return float(np.sqrt(max(density, 0.0) * (sr / 2.0)))


def _bandwidth_coverage(psd_db: np.ndarray, freqs: np.ndarray, sr: int) -> float:
    """-40dB 带宽覆盖可闻频带比例 [0,1]。"""
    # 全频谱均为对数下限（数字静音，全部 bin 被 _to_db 钳制到下限）时无带宽可言；
    # 真实低电平信号（如白噪声 PSD 密度整体 < -120dB）仍有未钳制的实际值，不能误判
    if psd_db.size and bool(np.all(psd_db == _DBFS_MIN)):
        return 0.0
    peak_db = float(np.max(psd_db))
    mask = psd_db >= peak_db + _BANDWIDTH_FALL_DB
    band_low = _AUDIBLE_BAND_LOW_HZ
    band_high = min(float(sr) / 2.0, _AUDIBLE_BAND_HIGH_HZ)
    if band_high <= band_low or not np.any(mask):
        return 0.0
    f_low = float(freqs[mask].min())
    f_high = float(freqs[mask].max())
    return float(np.clip((f_high - f_low) / (band_high - band_low), 0.0, 1.0))


def compute_features(samples: np.ndarray, sr: int) -> Dict[str, Any]:
    """纯函数：特征分析计算（频谱/能量/时域三组）。"""
    freqs, psd = _power_spectrum(samples, sr)
    psd_db = _to_db(psd)

    # ---- 频谱特征 ----
    dominant_idx = int(np.argmax(psd))
    dominant_frequency = float(freqs[dominant_idx])

    frame_len = min(_FRAME_LENGTH, samples.size) if samples.size else 0
    hop = min(_HOP_LENGTH, frame_len) if frame_len else 1
    rms = _frame_rms(samples, sr, frame_length=frame_len, hop_length=hop)
    active_mask = rms > (float(np.max(rms)) * 10 ** (_ACTIVE_THRESHOLD_OFFSET_DB / 20.0))
    pitch_estimates = []
    step = max(1, int(rms.size / 200.0))  # 长文件抽帧，控制计算量
    for i in range(0, rms.size, step):
        if not active_mask[i]:
            continue
        start = i * hop
        frame = samples[start:start + frame_len]
        if frame.size < frame_len:
            frame = np.pad(frame, (0, frame_len - frame.size))
        f0 = _estimate_pitch_frame(frame, sr)
        if f0 is not None:
            pitch_estimates.append(f0)
    if pitch_estimates:
        fundamental_low = float(np.min(pitch_estimates))
        fundamental_high = float(np.max(pitch_estimates))
    else:
        fundamental_low = fundamental_high = dominant_frequency

    thd = _thd_percent(psd, freqs, dominant_frequency)

    # ---- 能量分布 ----
    peak = float(np.max(np.abs(samples))) if samples.size else 0.0
    average_energy_db = _to_db(float(np.sqrt(np.mean(samples ** 2)))) if samples.size else _DBFS_MIN
    peak_energy_db = _to_db(peak)
    concentration = 1.0 - _spectral_flatness(psd)

    # ---- 时域特征 ----
    if samples.size > 1:
        zcr = float(np.sum(np.abs(np.diff(np.sign(samples))) > 0) / (samples.size - 1))
    else:
        zcr = 0.0
    active_ratio = float(np.mean(active_mask)) if rms.size else 0.0
    active_indices = np.nonzero(active_mask)[0]
    onset_time = float(active_indices[0] * hop / sr) if active_indices.size else 0.0

    return {
        'spectral': {
            'fundamental_range_low': round(fundamental_low, 2),
            'fundamental_range_high': round(fundamental_high, 2),
            'dominant_frequency': round(dominant_frequency, 2),
            'harmonic_distortion': round(thd, 2),
        },
        'energy': {
            'average_energy_db': round(average_energy_db, 2),
            'peak_energy_db': round(peak_energy_db, 2),
            'energy_concentration': round(concentration, 4),
        },
        'time_domain': {
            'zero_crossing_rate': round(zcr, 4),
            'active_duration_ratio': round(active_ratio, 4),
            'onset_time': round(onset_time, 3),
        },
    }


def compute_quality(samples: np.ndarray, sr: int) -> Dict[str, Any]:
    """纯函数：质量评估计算（SNR/动态范围/频率响应/整体评分）。"""
    freqs, psd = _power_spectrum(samples, sr)
    psd_db = _to_db(psd)

    signal_rms = float(np.sqrt(np.mean(samples ** 2))) if samples.size else 0.0
    noise_rms = _spectral_noise_floor(psd, sr)
    peak = float(np.max(np.abs(samples))) if samples.size else 0.0

    if noise_rms <= 1e-12 or signal_rms <= 1e-12:
        snr_db = 0.0
        dynamic_range_db = 0.0
    else:
        snr_db = float(np.clip(_to_db(signal_rms / noise_rms), 0.0, _SNR_MAX_DB))
        dynamic_range_db = float(np.clip(_to_db(peak / noise_rms), 0.0, _DR_MAX_DB))

    frequency_response_score = round(100.0 * _bandwidth_coverage(psd_db, freqs, sr), 2)

    snr_norm = min(snr_db / 60.0, 1.0)
    dr_norm = min(dynamic_range_db / 90.0, 1.0)
    fr_norm = frequency_response_score / 100.0
    quality_score = round(100.0 * (0.4 * snr_norm + 0.3 * dr_norm + 0.3 * fr_norm))
    quality_score = int(np.clip(quality_score, 0, 100))

    return {
        'snr_db': round(snr_db, 2),
        'dynamic_range_db': round(dynamic_range_db, 2),
        'frequency_response_score': frequency_response_score,
        'quality_score': quality_score,
    }


def denoise_samples(samples: np.ndarray, sr: int) -> np.ndarray:
    """谱门降噪（spectral gating）：宽带噪声底 + 软增益掩码。

    噪声底取全 STFT 幅度的中位数（窄带主频只占少数 bin，中位数被宽带噪声
    主导），对每个 bin 施加 1 - α·noise/mag 的软增益：主频成分（mag >> 噪声底）
    增益≈1 原样保留，噪声成分（mag≈噪声底）被压低到谱底比例，避免谱减法把
    稳态主频误判为噪声而过减。输出按输入峰值归一化保持响度一致。
    """
    from scipy.signal import istft, stft
    # 默认 boundary='zeros' / padded=True：hann 窗 + 75% 重叠满足 NOLA，可完美重建
    _, _, Zxx = stft(samples, sr, nperseg=_FRAME_LENGTH,
                     noverlap=_FRAME_LENGTH - _HOP_LENGTH)
    mag = np.abs(Zxx)
    phase = np.angle(Zxx)

    noise_floor = float(np.median(mag))
    if noise_floor <= 1e-9:
        return samples

    gain = np.maximum(
        1.0 - _DENOISE_ALPHA * noise_floor / (mag + 1e-9),
        _DENOISE_FLOOR_RATIO,
    )
    mag_clean = mag * gain
    Zxx_clean = mag_clean * np.exp(1j * phase)
    _, samples_clean = istft(Zxx_clean, sr, nperseg=_FRAME_LENGTH,
                             noverlap=_FRAME_LENGTH - _HOP_LENGTH)
    samples_clean = samples_clean[: samples.size]
    # 响度保持：输出峰值不超输入峰值，避免削波失真
    in_peak = float(np.max(np.abs(samples))) if samples.size else 0.0
    out_peak = float(np.max(np.abs(samples_clean))) if samples_clean.size else 0.0
    if in_peak > 0.0 and out_peak > in_peak:
        samples_clean = samples_clean * (in_peak / out_peak)
    return samples_clean


def apply_gain(samples: np.ndarray, gain_db: float) -> np.ndarray:
    """线性增益（dB → 幅度倍率），削波保护到满幅。"""
    gain = 10 ** (gain_db / 20.0)
    out = samples * gain
    np.clip(out, -1.0, 1.0, out=out)
    return out


class AudioAnalysisService:
    """音频特征/质量/处理应用服务（依赖仓储解析音频记录与持久化）。"""

    def __init__(self, repo: AudioRepositoryInterface = None) -> None:
        self.repo = repo or audio_repository

    # ---------- 内部工具 ----------

    def _resolve_local_path(self, file_path: str) -> Optional[str]:
        if not file_path:
            return None
        ref = file_path if file_path.startswith(('oss://', 'local://')) \
            else storage.build_path('audios', file_path)
        return storage.load_file(ref)

    def _load_audio_for(self, audio) -> Tuple[np.ndarray, int]:
        local_path = self._resolve_local_path(audio.file_path)
        if not local_path or not os.path.exists(local_path):
            raise FileNotFoundError(f'无法解析音频文件路径: {audio.file_path}')
        return _load_audio(local_path)

    # ---------- 特征分析 ----------

    def analyze_features(self, audio_id: int) -> Dict[str, Any]:
        audio = self.repo.get_audio(audio_id)
        if not audio:
            return {'success': False, 'message': '未找到音频文件', 'data': None, 'code': 404}
        if not audio.file_path:
            return {'success': False, 'message': '音频文件路径缺失', 'data': None, 'code': 404}
        try:
            samples, sr = self._load_audio_for(audio)
            features = compute_features(samples, sr)
            features['audio_id'] = audio.id
            features['duration'] = round(len(samples) / sr, 3)
            return {'success': True, 'message': '特征分析成功', 'data': features, 'code': 200}
        except Exception as e:
            logger.error("音频特征分析失败: audio_id=%s, err=%s", audio_id, e, exc_info=True)
            return {'success': False, 'message': f'特征分析失败: {e}', 'data': None, 'code': 400}

    # ---------- 质量评估 ----------

    def assess_quality(self, audio_id: int) -> Dict[str, Any]:
        audio = self.repo.get_audio(audio_id)
        if not audio:
            return {'success': False, 'message': '未找到音频文件', 'data': None, 'code': 404}
        if not audio.file_path:
            return {'success': False, 'message': '音频文件路径缺失', 'data': None, 'code': 404}
        try:
            samples, sr = self._load_audio_for(audio)
            quality = compute_quality(samples, sr)
            quality['audio_id'] = audio.id
            quality['duration'] = round(len(samples) / sr, 3)
            return {'success': True, 'message': '质量评估成功', 'data': quality, 'code': 200}
        except Exception as e:
            logger.error("音频质量评估失败: audio_id=%s, err=%s", audio_id, e, exc_info=True)
            return {'success': False, 'message': f'质量评估失败: {e}', 'data': None, 'code': 400}

    # ---------- 处理（降噪/增益/剪辑） ----------

    def process(self, audio_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
        from pydub import AudioSegment
        audio = self.repo.get_audio(audio_id)
        if not audio:
            return {'success': False, 'message': '未找到音频文件', 'data': None, 'code': 404}
        if not audio.file_path:
            return {'success': False, 'message': '音频文件路径缺失', 'data': None, 'code': 404}

        operation = (data.get('operation') or '').lower()
        if operation not in ('denoise', 'gain', 'trim'):
            return {'success': False, 'message': '不支持的处理操作，可选 denoise/gain/trim',
                    'data': None, 'code': 400}
        mode = (data.get('mode') or 'new').lower()
        if mode not in ('new', 'overwrite'):
            return {'success': False, 'message': 'mode 仅支持 new/overwrite', 'data': None, 'code': 400}

        try:
            local_path = self._resolve_local_path(audio.file_path)
            if not local_path or not os.path.exists(local_path):
                raise FileNotFoundError(f'无法解析音频文件路径: {audio.file_path}')

            seg = AudioSegment.from_file(local_path)

            if operation == 'trim':
                duration_ms = len(seg)
                start_ms = int(data.get('start_ms', 0))
                end_ms = int(data.get('end_ms', duration_ms))
                if start_ms < 0 or end_ms <= start_ms or end_ms > duration_ms:
                    return {'success': False,
                            'message': f'无效的剪辑区间 start_ms={start_ms} end_ms={end_ms}（音频时长 {duration_ms}ms）',
                            'data': None, 'code': 400}
                new_seg = seg[start_ms:end_ms]
                new_sr = seg.frame_rate
            else:
                samples, sr = _load_audio(local_path)
                if operation == 'denoise':
                    processed = denoise_samples(samples, sr)
                else:  # gain
                    gain_db = float(data.get('gain_db', 0.0))
                    processed = apply_gain(samples, gain_db)
                new_seg = _samples_to_segment(processed, sr)
                new_sr = sr

            # 导出为 wav（处理产物统一 wav），落存储
            tmp_wav = os.path.join(tempfile.gettempdir(), f'proc_{uuid.uuid4().hex}.wav')
            new_seg.export(tmp_wav, format='wav')
            try:
                new_size = os.path.getsize(tmp_wav)
            except OSError:
                new_size = len(new_seg.raw_data)
            new_storage_path = storage.save_file(tmp_wav, 'audios', f'processed/{uuid.uuid4().hex}.wav')
            try:
                os.remove(tmp_wav)
            except OSError:
                logger.debug("清理处理临时文件失败: %s", tmp_wav, exc_info=True)

            new_duration = len(new_seg) / 1000.0
            result = {
                'audio_id': audio.id,
                'operation': operation,
                'mode': mode,
                'format': 'wav',
                'file_path': new_storage_path,
                'duration': round(new_duration, 3),
                'size': new_size,
            }

            if mode == 'overwrite':
                self.repo.update_audio(audio.id, {
                    'file_path': new_storage_path,
                    'format': 'wav',
                    'size': new_size,
                    'duration': new_duration,
                    'sample_rate': new_sr,
                    'channels': new_seg.channels,
                })
                self.repo.commit()
            else:
                new_name = f"{audio.filename}_{operation}"
                new_original = f"{os.path.splitext(audio.original_filename or audio.filename)[0]}_{operation}.wav"
                new_audio = self.repo.create_audio({
                    'name': new_name,
                    'original_filename': new_original,
                    'file_path': new_storage_path,
                    'size': new_size,
                    'duration': new_duration,
                    'sample_rate': new_sr,
                    'channels': new_seg.channels,
                    'format': 'wav',
                    'audio_type': audio.audio_type,
                    'asr_text': audio.asr_text,
                    'description': audio.description,
                    'md5': '',
                    'source_language': audio.source_language,
                })
                self.repo.commit()
                result['new_audio_id'] = new_audio.id

            return {'success': True, 'message': f'音频{operation}处理成功',
                    'data': result, 'code': 200}
        except Exception as e:
            self.repo.rollback()
            logger.error("音频处理失败: audio_id=%s, op=%s, err=%s", audio_id, operation, e, exc_info=True)
            return {'success': False, 'message': f'音频处理失败: {e}', 'data': None, 'code': 400}


# 模块级单例
audio_analysis_service = AudioAnalysisService()
