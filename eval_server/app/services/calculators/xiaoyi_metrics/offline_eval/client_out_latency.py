# -*- coding: utf-8 -*-
"""基于干净音源与 client_out 的互相关对齐计算模型回复时延。"""
import logging

import numpy as np
from scipy.io import wavfile
from scipy.signal import fftconvolve, resample_poly

logger = logging.getLogger(__name__)


def load_audio(filepath):
    """加载 WAV 文件，转为 mono float64，返回 (sr, data)。"""
    sr, data = wavfile.read(filepath)
    if data.ndim > 1:
        data = data.mean(axis=1)
    dt = data.dtype
    if dt == np.int16:
        data = data.astype(np.float64) / 32768.0
    elif dt == np.int32:
        data = data.astype(np.float64) / 2147483648.0
    elif dt == np.uint8:
        data = (data.astype(np.float64) - 128.0) / 128.0
    elif dt in (np.float32, np.float64):
        data = data.astype(np.float64)
    else:
        data = data.astype(np.float64)
        peak = np.max(np.abs(data))
        if peak > 0:
            data /= peak
    return sr, data


def detect_speech_region(audio, sr, frame_ms=20, hop_ms=10, threshold_factor=0.1):
    """使用 RMS 能量获取干净音源有效语料区间。"""
    frame_len = int(sr * frame_ms / 1000)
    hop_len = int(sr * hop_ms / 1000)
    n_frames = max(1, (len(audio) - frame_len) // hop_len + 1)
    rms = np.zeros(n_frames)
    for i in range(n_frames):
        segment = audio[i * hop_len:i * hop_len + frame_len]
        if len(segment) > 0:
            rms[i] = np.sqrt(np.mean(segment ** 2))
    max_rms = np.max(rms)
    if max_rms <= 0:
        return 0, len(audio)
    active_frames = np.where(rms > max_rms * threshold_factor)[0]
    if len(active_frames) == 0:
        return 0, len(audio)
    start = int(active_frames[0] * hop_len)
    end = min(len(audio), int(active_frames[-1] * hop_len + frame_len))
    return start, end


def fft_xcorr(reference, signal):
    """FFT 互相关，返回 reference 在 signal 中的起始样本偏移。"""
    if len(signal) < len(reference):
        return -1, 0.0
    corr = fftconvolve(signal, reference[::-1], mode='full')
    valid_corr = corr[len(reference) - 1:len(signal)]
    peak_idx = int(np.argmax(np.abs(valid_corr)))
    ref_energy = float(np.sum(reference ** 2))
    segment = signal[peak_idx:peak_idx + len(reference)]
    segment_energy = float(np.sum(segment ** 2))
    if ref_energy > 0 and segment_energy > 0:
        ncc = float(valid_corr[peak_idx]) / np.sqrt(ref_energy * segment_energy)
    else:
        ncc = 0.0
    return peak_idx, ncc


def coarse_to_fine_align(clean, noisy, factors=None):
    """按 batch_align.py 的 coarse-to-fine 互相关策略对齐音频。"""
    factors = factors or [16, 4, 1]
    approx_offset = 0
    ncc = 0.0
    for level, factor in enumerate(factors):
        if factor > 1:
            clean_ds = resample_poly(clean, 1, factor)
            noisy_ds = resample_poly(noisy, 1, factor)
        else:
            clean_ds = clean
            noisy_ds = noisy
        ref_len = len(clean_ds)
        if level == 0:
            offset_ds, ncc = fft_xcorr(clean_ds, noisy_ds)
            approx_offset = offset_ds * factor
        else:
            estimate = int(approx_offset / factor)
            margin = ref_len
            search_start = max(0, estimate - margin)
            search_end = min(len(noisy_ds), estimate + margin + ref_len)
            offset_ds, ncc = fft_xcorr(clean_ds, noisy_ds[search_start:search_end])
            approx_offset = (offset_ds + search_start) * factor
    return max(0, approx_offset), ncc


def locate_client_out(case_wav, client_out_wav):
    """将 case_wav 的有效语料对齐到 client_out_wav，返回 client_out 时间戳。"""
    sr_clean, clean = load_audio(case_wav)
    sr_out, client_out = load_audio(client_out_wav)
    if sr_clean != sr_out:
        clean = resample_poly(clean, sr_out, sr_clean)
    start, end = detect_speech_region(clean, sr_out)
    clean_speech = clean[start:end]
    if len(clean_speech) < 1:
        return None, None, None
    offset, ncc = coarse_to_fine_align(clean_speech, client_out)
    return offset / sr_out, (offset + len(clean_speech)) / sr_out, ncc


def compute_client_out_latency(case_wav, client_out_wav, model_chunks):
    """计算 client_out 结束到模型回复首字之间的时延。"""
    result = {
        'client_out_start_ms': None,
        'client_out_end_ms': None,
        'model_first_word_start_ms': None,
        'client_out_latency_ms': None,
        'ncc': None,
        'message': '',
    }
    if not case_wav or not client_out_wav:
        result['message'] = 'case_wav 或 client_out_wav 为空，无法对齐'
        return result
    try:
        start_s, end_s, ncc = locate_client_out(case_wav, client_out_wav)
    except Exception as exc:
        logger.exception('[client_out时延] 音频对齐失败')
        result['message'] = f'音频对齐失败: {exc}'
        return result
    if start_s is None or end_s is None:
        result['message'] = '干净音源有效语料区间为空，无法对齐'
        return result
    result['client_out_start_ms'] = start_s * 1000.0
    result['client_out_end_ms'] = end_s * 1000.0
    result['ncc'] = ncc

    valid_chunks = [
        c for c in (model_chunks or [])
        if isinstance(c, dict) and c.get('timestamp')
        and c['timestamp'][0] is not None
    ]
    if not valid_chunks:
        result['message'] = 'model_chunks 没有有效首字时间戳'
        return result
    first_start_s = min(c['timestamp'][0] for c in valid_chunks)
    result['model_first_word_start_ms'] = first_start_s * 1000.0
    result['client_out_latency_ms'] = (
        result['model_first_word_start_ms'] - result['client_out_end_ms']
    )
    result['message'] = 'OK'
    return result
