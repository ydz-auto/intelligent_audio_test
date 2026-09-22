# -*- coding: utf-8 -*-
"""env_response_latency.py
环境声回复时延计算：模型在听到环境声后多久开始回复

原理:
    1. played_audios 为原始环境声音频（干净音源）
    2. 用 FFT 互相关在 user_wav（录制音频）中定位该环境声的起止时间戳
    3. 从 ai_wav 提取 ASR 词级时间戳，找到环境声结束后的模型首字时间戳
    4. 回复时延 = model_first_word_start_ms - env_sound_end_ms

输出: {response_latency_ms, env_sound_start_ms, env_sound_end_ms, model_first_word_start_ms, ncc, message}
"""
import json
import os
import logging
from typing import Any, Dict, Optional

import numpy as np
from scipy.io import wavfile
from scipy.signal import fftconvolve, resample_poly

from app.services.calculators.xiaoyi_metrics.shared.llm_client import (
    get_asr_chunks,
)

logger = logging.getLogger(__name__)


# ─────────── 音频处理工具（移植自 false_takeover.py）───────────

def _load_audio(filepath):
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


def _detect_speech_region(audio, sr, frame_ms=20, hop_ms=10, threshold_factor=0.1):
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


def _fft_xcorr(reference, signal):
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


def _coarse_to_fine_align(clean, noisy, factors=None):
    """按 coarse-to-fine 互相关策略对齐音频。"""
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
            offset_ds, ncc = _fft_xcorr(clean_ds, noisy_ds)
            approx_offset = offset_ds * factor
        else:
            estimate = int(approx_offset / factor)
            margin = ref_len
            search_start = max(0, estimate - margin)
            search_end = min(len(noisy_ds), estimate + margin + ref_len)
            offset_ds, ncc = _fft_xcorr(clean_ds, noisy_ds[search_start:search_end])
            approx_offset = (offset_ds + search_start) * factor
    return max(0, approx_offset), ncc


def _resolve_played_audio_path(played_audios):
    """从 played_audios 参数解析出实际音频文件路径。

    兼容多种形态:
    - str: wav 路径，或 JSON 字符串（list/dict，平台 played_audios 参数）
    - list: 每项为 dict（取 audio_path）或路径字符串，取第一个非空
    - dict: 直接取 audio_path
    """
    if not played_audios:
        return None

    data = played_audios
    if isinstance(data, str):
        s = data.strip()
        if s[:1] in ('[', '{'):
            try:
                data = json.loads(s)
            except (ValueError, TypeError):
                return s or None
        else:
            return s or None

    def _pick(obj):
        if isinstance(obj, dict):
            return obj.get('audio_path') or obj.get('path')
        if isinstance(obj, str):
            return obj or None
        return None

    if isinstance(data, dict):
        return _pick(data)

    if isinstance(data, list):
        for item in data:
            p = _pick(item)
            if p:
                return p

    return None


def _locate_env_sound(played_audios, user_wav):
    """将 played_audios 的有效语料对齐到 user_wav，返回环境声在录制中的起止时间戳。

    Returns:
        (start_s, end_s, ncc): 起止时间（秒）+ 互相关峰值
    """
    sr_clean, clean = _load_audio(played_audios)
    sr_user, user_audio = _load_audio(user_wav)
    if sr_clean != sr_user:
        clean = resample_poly(clean, sr_user, sr_clean)
    start, end = _detect_speech_region(clean, sr_user)
    clean_speech = clean[start:end]
    if len(clean_speech) < 1:
        return None, None, None
    offset, ncc = _coarse_to_fine_align(clean_speech, user_audio)
    return offset / sr_user, (offset + len(clean_speech)) / sr_user, ncc


# ─────────── 主入口 ───────────

def evaluate_env_response_latency(
    played_audios: str,
    user_wav: str,
    ai_wav: str,
) -> Dict[str, Any]:
    """环境声回复时延计算

    通过 FFT 互相关在 user_wav 中定位环境声（played_audios）的起止时间戳，
    再从 ai_wav 的 ASR 词级时间戳中找到环境声结束后的模型首字时间戳，
    计算回复时延 = model_first_word_start_ms - env_sound_end_ms。

    Args:
        played_audios: 原始环境声音频路径（干净音源）
        user_wav:      录制音频路径（包含环境声的 user 通道音频）
        ai_wav:        模型回复音频路径（从中提取 ASR 词级时间戳）

    Returns:
        dict: {response_latency_ms, env_sound_start_ms, env_sound_end_ms,
               model_first_word_start_ms, ncc, message}
    """
    result: Dict[str, Any] = {
        'response_latency_ms': None,
        'env_sound_start_ms': None,
        'env_sound_end_ms': None,
        'model_first_word_start_ms': None,
        'ncc': None,
        'message': '',
    }

    # 解析 played_audios 路径
    played_audio_path = _resolve_played_audio_path(played_audios)
    if not played_audio_path or not os.path.isfile(played_audio_path):
        result['message'] = f'played_audios 文件不存在: {played_audios!r}'
        logger.error(result['message'])
        return result

    if not user_wav or not os.path.isfile(user_wav):
        result['message'] = f'user_wav 文件不存在: {user_wav!r}'
        logger.error(result['message'])
        return result

    if not ai_wav or not os.path.isfile(ai_wav):
        result['message'] = f'ai_wav 文件不存在: {ai_wav!r}'
        logger.error(result['message'])
        return result

    # 1. FFT 互相关定位环境声在 user_wav 中的起止时间
    try:
        start_s, end_s, ncc = _locate_env_sound(played_audio_path, user_wav)
    except Exception as exc:
        logger.exception('[env_latency] 音频对齐失败')
        result['message'] = f'音频对齐失败: {exc}'
        return result

    if start_s is None or end_s is None:
        result['message'] = '环境声有效语料区间为空，无法对齐'
        logger.error(result['message'])
        return result

    result['env_sound_start_ms'] = round(start_s * 1000.0, 1)
    result['env_sound_end_ms'] = round(end_s * 1000.0, 1)
    result['ncc'] = round(ncc, 4)

    logger.info(
        f'[env_latency] 环境声定位: start={result["env_sound_start_ms"]}ms '
        f'end={result["env_sound_end_ms"]}ms ncc={result["ncc"]}'
    )

    # 2. 从 ai_wav 提取 ASR 词级时间戳
    ai_chunks = get_asr_chunks(ai_wav)
    if not ai_chunks:
        result['message'] = 'ai_wav ASR chunks 为空，无法获取模型首字时间戳'
        logger.error(result['message'])
        return result

    # 3. 找到环境声结束后的模型首字
    env_end_s = end_s
    valid_chunks = [
        c for c in ai_chunks
        if isinstance(c, dict) and c.get('timestamp')
        and c['timestamp'][0] is not None
        and c['timestamp'][0] >= env_end_s
    ]

    if not valid_chunks:
        result['message'] = (
            f'未找到环境声结束后的模型回复 chunk '
            f'(env_sound_end={env_end_s:.3f}s, ai_chunks={len(ai_chunks)})'
        )
        logger.error(result['message'])
        return result

    first_start_s = min(c['timestamp'][0] for c in valid_chunks)
    result['model_first_word_start_ms'] = round(first_start_s * 1000.0, 1)

    # 4. 回复时延 = 模型首字时间 - 环境声结束时间
    result['response_latency_ms'] = round(
        result['model_first_word_start_ms'] - result['env_sound_end_ms'], 1
    )
    result['message'] = 'OK'

    first_chunk = valid_chunks[0]
    logger.info(
        f'[env_latency] 回复时延: {result["response_latency_ms"]}ms '
        f'(model_first_word={result["model_first_word_start_ms"]}ms - '
        f'env_sound_end={result["env_sound_end_ms"]}ms, '
        f'首字="{first_chunk.get("text", "")}")'
    )

    return result


if __name__ == '__main__':
    import argparse
    from pathlib import Path

    # 独立运行时加载 eval_server/.env
    _env_path = Path(__file__).resolve().parents[4] / '.env'
    if _env_path.exists():
        with open(_env_path, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    os.environ.setdefault(k.strip(), v.strip())

    parser = argparse.ArgumentParser(
        description='环境声回复时延：FFT 互相关定位环境声在录制中的时间戳，计算模型回复时延'
    )
    parser.add_argument('played_audios', help='原始环境声音频路径')
    parser.add_argument('user_wav', help='录制音频路径（包含环境声）')
    parser.add_argument('ai_wav', help='模型回复音频路径')
    args = parser.parse_args()

    r = evaluate_env_response_latency(
        played_audios=args.played_audios,
        user_wav=args.user_wav,
        ai_wav=args.ai_wav,
    )

    print('=' * 60)
    print(f'message: {r["message"]}')
    print(f'  环境声起始: {r["env_sound_start_ms"]}ms')
    print(f'  环境声结束: {r["env_sound_end_ms"]}ms')
    print(f'  模型首字:   {r["model_first_word_start_ms"]}ms')
    print(f'  回复时延:   {r["response_latency_ms"]}ms')
    print(f'  NCC:        {r["ncc"]}')
    print('=' * 60)
    print(json.dumps(r, ensure_ascii=False, indent=2))
