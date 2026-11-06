# -*- coding: utf-8 -*-
"""音频文件操作工具函数

从 audio_crud_service.py 中提取的模块级工具函数：
- _retry_file_operation
- _safe_makedirs
- _read_wav_header
- _convert_to_wav
- _get_relative_path
"""
import os


def _retry_file_operation(func, *args, **kwargs):
    max_retries = 5
    retry_delay = 0.2
    for i in range(max_retries):
        try:
            return func(*args, **kwargs)
        except (PermissionError, OSError):
            if i == max_retries - 1:
                raise
            import time
            time.sleep(retry_delay)


def _safe_makedirs(dir_path):
    if os.path.exists(dir_path):
        return
    max_retries = 3
    for i in range(max_retries):
        try:
            os.makedirs(dir_path, exist_ok=True)
            return
        except (PermissionError, OSError):
            if i == max_retries - 1:
                raise
            import time
            time.sleep(0.2)


def _read_wav_header(file_path):
    import wave
    with wave.open(file_path, 'rb') as wf:
        return wf.getframerate(), wf.getsampwidth() * 8


def _convert_to_wav(file_path):
    from pydub import AudioSegment
    file_path = os.path.normpath(file_path)
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"文件不存在: {file_path}")

    audio_seg = AudioSegment.from_file(file_path)
    original_sample_rate = audio_seg.frame_rate
    original_channels = audio_seg.channels

    # 多声道只保留第一个声道（转为单声道）
    if original_channels > 1:
        audio_seg = audio_seg.split_to_mono()[0]
        original_channels = 1

    # 位深信息通过 sample_width 获取（bytes per sample per channel）
    original_bits_per_sample = audio_seg.sample_width * 8

    directory = os.path.dirname(file_path)
    filename = os.path.splitext(os.path.basename(file_path))[0]
    new_wav_path = os.path.join(directory, f"{filename}.wav")

    codec_map = {16: 'pcm_s16le', 24: 'pcm_s24le', 32: 'pcm_s32le'}
    codec = codec_map.get(original_bits_per_sample, 'pcm_s16le')

    audio_seg.export(
        new_wav_path,
        format='wav',
        parameters=['-ar', str(int(original_sample_rate)),
                    '-ac', str(original_channels),
                    '-acodec', codec]
    )
    new_filename = f"{filename}.wav"
    return new_wav_path, new_filename, original_sample_rate, original_bits_per_sample


def _get_relative_path(file_path):
    """计算相对路径（简化版，网关侧 _format_audio_list 会再做一次）"""
    if not file_path:
        return file_path
    return file_path.replace('\\', '/')
