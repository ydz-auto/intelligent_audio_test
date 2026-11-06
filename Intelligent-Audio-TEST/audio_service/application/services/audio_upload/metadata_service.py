# -*- coding: utf-8 -*-
"""音频元数据提取服务（原 audio_upload_service.py 提取产物，P4-2；P4-6 重组入 audio_upload 子包）。

从 audio_upload_service.py 中提取的元数据提取相关逻辑：
- 从 OSS 下载临时文件并提取时长/采样率/声道/比特率
- 读取 WAV 头部信息（采样率/位深）
- 读取 WAV 时长

INT-2202：探测失败或时长 ≤ 0 一律抛 InvalidAudioContentError，不再用默认值兜底——
兜底会让 0 字节 / 纯文本改名的 .wav 以 duration=0 入库。
"""
import os
import logging

from audio_service.application.services.audio_file_utils import _read_wav_header
from audio_service.domain.exceptions import InvalidAudioContentError

logger = logging.getLogger(__name__)


class AudioMetadataService:
    """音频元数据提取服务"""

    def extract_from_local_file(self, file_path):
        """从本地音频文件提取元数据（时长/采样率/声道/比特率）

        用 pydub 真实解码探测参数；文件为空、无法解码或时长 ≤ 0 时抛
        InvalidAudioContentError，调用方据此判该文件失败、不落库。

        :param file_path: 本地音频文件路径
        :return: dict，包含 duration/sample_rate/channels/bitrate/file_size
        """
        if not file_path or not os.path.isfile(file_path):
            raise InvalidAudioContentError('音频文件不存在或无法读取')
        file_size = os.path.getsize(file_path)
        if file_size <= 0:
            raise InvalidAudioContentError('文件内容为空（0 字节）')

        try:
            from pydub import AudioSegment
            audio_seg = AudioSegment.from_file(file_path)
        except Exception as e:
            logger.info("音频内容无法解码: path=%s err=%s", file_path, e)
            raise InvalidAudioContentError('无法解码，可能不是音频文件或已损坏') from e

        duration = len(audio_seg) / 1000.0
        sample_rate = audio_seg.frame_rate
        channels = audio_seg.channels
        if duration <= 0 or not sample_rate or not channels:
            raise InvalidAudioContentError(
                f'探测到时长 {duration:.3f}s / 采样率 {sample_rate} / 声道 {channels}')
        bitrate = audio_seg.sample_width * 8 * sample_rate

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
