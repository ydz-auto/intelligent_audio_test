"""音频路径正则化工具"""
import os
from typing import Optional


def normalize_audio_path(audio_path: str, static_base_path: str) -> str:
    """将绝对音频路径转为相对 STATIC_BASE_PATH 的相对路径。

    解析符号链接后比较，不在基目录下则原样返回。
    """
    if not audio_path or not static_base_path:
        return audio_path
    if not os.path.isabs(audio_path):
        return audio_path
    real_abs = os.path.realpath(audio_path)
    real_base = os.path.realpath(static_base_path)
    try:
        common = os.path.commonpath([real_abs, real_base])
        if common == real_base:
            return os.path.relpath(real_abs, real_base).replace('\\', '/')
    except ValueError:
        pass
    return audio_path
