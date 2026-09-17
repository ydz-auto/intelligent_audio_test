# -*- coding: utf-8 -*-
"""
音频对齐模块：将 played_audios（干净信号）与 user_wav（劣化信号）做 FFT 互相关对齐，
生成一个新的音频——与 user_wav 同等时长，内容只保留 played_audios 的干净语音，
时间戳与 user_wav 原始时间线对齐。

生成的新音频用于替代原始 user_wav 进行 ASR 识别和后续评估。
"""
import logging
import os
import tempfile

import numpy as np
from scipy.io import wavfile
from scipy.signal import resample_poly

from app.services.calculators.xiaoyi_metrics.turn_taking.false_takeover import (
    _load_audio,
    _detect_speech_region,
    _coarse_to_fine_align,
    _resolve_played_audio_path,
)

logger = logging.getLogger(__name__)


def _resolve_played_audio_paths(played_audios):
    """从 played_audios 参数解析出所有音频文件路径列表。

    兼容多种形态:
    - str: wav 路径，或 JSON 字符串（list/dict）
    - list: 每项为 dict（取 audio_path）或路径字符串
    - dict: 直接取 audio_path

    Returns:
        list[str]: 解析出的音频路径列表
    """
    if not played_audios:
        return []

    data = played_audios
    if isinstance(data, str):
        s = data.strip()
        if s[:1] in ('[', '{'):
            try:
                data = json.loads(s)
            except (ValueError, TypeError):
                return [s] if s else []
        else:
            return [s] if s else []

    def _pick(obj):
        if isinstance(obj, dict):
            return obj.get('audio_path') or obj.get('path')
        if isinstance(obj, str):
            return obj or None
        return None

    if isinstance(data, list):
        return [p for item in data if (p := _pick(item))]
    if isinstance(data, dict):
        p = _pick(data)
        return [p] if p else []
    return []


def generate_aligned_clean_audio(user_wav, played_audios, output_path=None):
    """将多段 played_audios 干净语音逐段对齐到 user_wav 时间线，生成新的干净音频。

    流程：
        1. 加载 user_wav（劣化）
        2. 逐个加载 played_audios（干净），检测有效语音区间
        3. 每段干净语音独立做粗到细 FFT 互相关对齐到 user_wav
        4. 创建与 user_wav 同长度的静音数组，将每段干净语音放置到各自对齐位置
        5. 保存为 WAV 文件

    Args:
        user_wav: 用户通道录音文件路径（劣化信号）
        played_audios: 干净音源（str 路径 / list[str] / played_audios 参数对象）
        output_path: 输出 WAV 路径，None 则自动生成临时文件

    Returns:
        dict: {
            'aligned_wav': str,          # 生成的新音频路径
            'sample_rate': int,          # 采样率
            'duration_s': float,         # 新音频时长（秒）= user_wav 时长
            'segments': list[dict],      # 每段对齐信息
            'ncc': float,                # 平均互相关置信度
            'message': str,             # 状态信息
        }
    """
    result = {
        'aligned_wav': None,
        'sample_rate': None,
        'duration_s': None,
        'segments': [],
        'ncc': None,
        'message': '',
    }

    played_paths = _resolve_played_audio_paths(played_audios)
    if not played_paths or not user_wav:
        result['message'] = 'played_audios 或 user_wav 为空'
        return result

    # 1. 加载 user_wav
    sr_user, user_audio = _load_audio(user_wav)
    duration_s = len(user_audio) / sr_user

    # 创建与 user_wav 同长度的静音数组
    aligned_audio = np.zeros(len(user_audio), dtype=np.float64)

    segments = []
    ncc_list = []

    # 时序约束：后续段只能在前面段之后搜索，防止重复对齐到同一位置
    search_start_sample = 0
    # 最小 NCC 阈值，低于此值认为对齐不可靠
    MIN_NCC_THRESHOLD = 0.3

    for i, played_path in enumerate(played_paths):
        if not os.path.isfile(played_path):
            logger.warning(f"played_audio 文件不存在: {played_path}")
            continue

        # 2. 加载干净音源
        sr_clean, clean_audio = _load_audio(played_path)
        if sr_clean != sr_user:
            clean_audio = resample_poly(clean_audio, sr_user, sr_clean)

        # 3. 检测有效语音区间
        speech_start, speech_end = _detect_speech_region(clean_audio, sr_user)
        clean_speech = clean_audio[speech_start:speech_end]
        clean_duration_s = len(clean_speech) / sr_user

        if len(clean_speech) < 1:
            logger.warning(f"段{i}: 干净音源有效语音区间为空，跳过: {played_path}")
            continue

        # 4. 粗到细 FFT 互相关对齐（仅在未匹配区域搜索）
        search_region = user_audio[search_start_sample:]
        offset_samples, ncc = _coarse_to_fine_align(clean_speech, search_region)
        offset_samples += search_start_sample  # 修正为全局偏移
        offset_s = offset_samples / sr_user
        ncc_list.append(ncc)

        # 检测重复 offset
        prev_offsets = [seg['offset_samples'] for seg in segments]
        if offset_samples in prev_offsets:
            logger.warning(f"段{i}: offset={offset_s:.3f}s 与前段重复，NCC={ncc:.4f}，"
                           f"对齐可能失败")

        if ncc < MIN_NCC_THRESHOLD:
            logger.warning(f"段{i}: NCC={ncc:.4f} 低于阈值 {MIN_NCC_THRESHOLD}，"
                           f"offset={offset_s:.3f}s 对齐不可靠")

        logger.info(f"段{i}: {os.path.basename(played_path)} "
                     f"clean={speech_start / sr_user:.3f}s-{speech_end / sr_user:.3f}s "
                     f"offset={offset_s:.3f}s NCC={ncc:.4f}")

        # 5. 放置干净语音到对齐位置
        end_sample = min(offset_samples + len(clean_speech), len(user_audio))
        actual_len = end_sample - offset_samples
        if actual_len > 0:
            aligned_audio[offset_samples:end_sample] = clean_speech[:actual_len]

        # 更新搜索起点：下一段只能在本段之后搜索
        search_start_sample = end_sample

        segments.append({
            'index': i,
            'source': os.path.basename(played_path),
            'offset_samples': offset_samples,
            'offset_s': offset_s,
            'clean_duration_s': clean_duration_s,
            'ncc': ncc,
        })

    if not segments:
        result['message'] = '所有干净音源有效语音区间均为空'
        return result

    avg_ncc = float(np.mean(ncc_list))
    logger.info(f"共 {len(segments)} 段干净语音对齐完成, 平均NCC={avg_ncc:.4f}")

    # 6. 保存为 WAV
    if output_path is None:
        output_path = os.path.join(
            tempfile.gettempdir(),
            f"aligned_clean_{os.path.basename(user_wav)}",
        )

    aligned_int16 = (np.clip(aligned_audio, -1.0, 1.0) * 32767).astype(np.int16)
    wavfile.write(output_path, sr_user, aligned_int16)
    logger.info(f"已保存对齐音频: {output_path} (时长 {duration_s:.3f}s)")

    result.update({
        'aligned_wav': output_path,
        'sample_rate': sr_user,
        'duration_s': duration_s,
        'segments': segments,
        'ncc': avg_ncc,
        'message': 'OK',
    })
    return result
