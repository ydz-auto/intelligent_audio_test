# -*- coding: utf-8 -*-
"""音频元数据提取服务

从 audio_upload_service.py 中提取的元数据提取相关逻辑：
- 从 OSS 下载临时文件并提取时长/采样率/声道/比特率
- 读取 WAV 头部信息（采样率/位深）
- 读取 WAV 时长
- 解析失败时使用默认值兜底
"""
import os
import logging

from audio_service.application.services.audio_file_utils import _read_wav_header

logger = logging.getLogger(__name__)


class AudioMetadataService:
    """音频元数据提取服务"""

    def extract_from_local_file(self, file_path):
        """从本地音频文件提取元数据（时长/采样率/声道/比特率）

        :param file_path: 本地音频文件路径
        :return: dict，包含 duration/sample_rate/channels/bitrate/file_size
        """
        file_size = os.path.getsize(file_path)
        duration = 0.0
        sample_rate = 44100
        channels = 1  # 默认单声道
        bitrate = 128000

        try:
            from pydub import AudioSegment
            audio_seg = AudioSegment.from_file(file_path)
            duration = len(audio_seg) / 1000.0
            sample_rate = audio_seg.frame_rate
            channels = audio_seg.channels
            bitrate = audio_seg.sample_width * 8 * sample_rate
            if duration <= 0:
                raise ValueError("音频时长为0，可能是无效的音频文件")
        except Exception as e:
            logger.info(f"音频元数据提取失败，使用默认值: {str(e)}")

        return {
            'file_size': file_size,
            'duration': duration,
            'sample_rate': sample_rate,
            'channels': channels,
            'bitrate': bitrate,
        }

    def extract_wav_header(self, file_path):
        """读取 WAV 头部信息（采样率/位深）

        :param file_path: 本地 WAV 文件路径
        :return: (sample_rate, bits_per_sample) 元组，失败时返回 None
        """
        try:
            return _read_wav_header(file_path)
        except Exception:
            logger.debug("解析WAV头部信息失败: file_path=%s", file_path, exc_info=True)
            return None

    def extract_wav_duration(self, file_path):
        """读取 WAV 文件时长

        :param file_path: 本地 WAV 文件路径
        :return: 时长（秒），失败返回 None
        """
        try:
            import wave
            with wave.open(file_path, 'rb') as wf:
                return wf.getnframes() / wf.getframerate() if wf.getframerate() else 0.0
        except Exception:
            logger.debug("解析音频时长失败: file_path=%s", file_path, exc_info=True)
            return None


# 模块级实例
audio_metadata_service = AudioMetadataService()
