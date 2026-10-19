# -*- coding: utf-8 -*-
"""音频格式转换应用服务

从 audio_crud_service.py 中提取的转换相关逻辑：
- convert_audio
- _get_source_language_from_algorithm_params（静态方法 → 模块级函数）
"""
import os
import uuid
import logging

from shared.infrastructure.storage import storage
from audio_service.domain.repositories.audio_repository_abc import AudioRepositoryInterface
from audio_service.infrastructure.persistence.audio_repository import audio_repository
from audio_service.application.services.audio_file_utils import (
    _retry_file_operation,
    _get_relative_path,
)

logger = logging.getLogger(__name__)

# 格式转换附加参数（INT-782）：无损失格式支持位深，有损格式支持比特率
LOSSLESS_FORMATS = {'wav', 'flac'}
LOSSY_FORMATS = {'mp3', 'aac', 'ogg', 'wma', 'm4a'}
# WAV 位深 (bit) → PCM codec（与 audio_file_utils._convert_to_wav 同口径）
WAV_PCM_CODEC = {8: 'pcm_s8', 16: 'pcm_s16le', 24: 'pcm_s24le', 32: 'pcm_s32le'}
# FLAC 位深 (bit) → sample_fmt（ffmpeg flac 编码器仅接受 s16/s32，24 位以 s32 承载）
FLAC_SAMPLE_FMT = {16: 's16', 24: 's32', 32: 's32'}


def _get_source_language_from_algorithm_params(algorithm_params):
    """从算法参数中提取源语言"""
    if not algorithm_params:
        return None
    for param in algorithm_params:
        if isinstance(param, dict):
            if param.get('field_code') == 'source_language':
                return param.get('field_value')
        elif hasattr(param, 'field_code') and param.field_code == 'source_language':
            return param.field_value
    return None


class AudioConvertService:
    """音频格式转换应用服务"""

    def __init__(self, repo: AudioRepositoryInterface = None):
        self.repo = repo or audio_repository

    def convert_audio(self, audio_id: int, data: dict) -> dict:
        """音频格式转换"""
        from pydub import AudioSegment
        audio = self.repo.get_audio(audio_id)
        if not audio:
            return {'success': False, 'message': '未找到音频文件', 'data': None, 'code': 404}

        target_format = (data.get('format') or 'wav').lower()

        try:
            old_path = audio.file_path
            new_filename = f"conv_{uuid.uuid4().hex}.{target_format}"
            # 转换产物先落本地临时文件：源文件可能在 OSS（oss://...），沿用其目录
            # 构造输出路径会产生非法本地路径（INT-817 实测发现）
            import tempfile
            new_path = os.path.join(tempfile.gettempdir(), new_filename)

            local_old = old_path
            if old_path.startswith(('oss://', 'local://')):
                local_old = tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(old_path)[1]).name
                storage.load_file(old_path, local_old)

            audio_seg = AudioSegment.from_file(local_old)
            export_params = self._build_export_params(data, target_format)
            if export_params:
                audio_seg.export(new_path, format=target_format, parameters=export_params)
            else:
                audio_seg.export(new_path, format=target_format)

            new_size = os.path.getsize(new_path)
            new_storage_path = storage.save_file(new_path, 'audios', f'conv/{new_filename}')
            if os.path.exists(new_path):
                _retry_file_operation(os.remove, new_path)
            if local_old != old_path and os.path.exists(local_old):
                _retry_file_operation(os.remove, local_old)

            update_fields = {
                'file_path': new_storage_path,
                'format': target_format,
                'size': new_size,
            }
            # 转换后刷新元数据（接口实现文档 AudioImport §1.5：更新数据库中的元数据信息）
            sample_rate = data.get('sample_rate', data.get('sampleRate'))
            channels = data.get('channels')
            bitrate = data.get('bitrate')
            if sample_rate is not None:
                update_fields['sample_rate'] = int(sample_rate)
            if channels is not None:
                update_fields['channels'] = int(channels)
            if bitrate is not None:
                update_fields['bitrate'] = self._bitrate_to_bps(bitrate)

            self.repo.update_audio(audio_id, update_fields)
            self.repo.commit()

            return {
                'success': True, 'message': f'音频已成功转换为 {target_format}',
                'data': {
                    'id': audio.id,
                    'format': target_format,
                    'file_path': _get_relative_path(new_storage_path),
                },
                'code': 200,
            }
        except Exception as e:
            return {'success': False, 'message': f'转换失败: {str(e)}', 'data': None, 'code': 400}

    def _build_export_params(self, data: dict, target_format: str) -> list:
        """根据请求附加参数构建 ffmpeg export 参数。

        - 采样率 → -ar；声道数 → -ac（对所有格式生效）
        - 位深 → WAV 用 PCM codec、FLAC 用 sample_fmt（仅无损失格式）
        - 比特率 → -b:a（仅有损格式 mp3/aac/ogg 等支持）
        """
        params = []
        sample_rate = data.get('sample_rate', data.get('sampleRate'))
        channels = data.get('channels')
        bit_depth = data.get('bit_depth', data.get('bitDepth'))
        bitrate = data.get('bitrate')

        if sample_rate is not None:
            params += ['-ar', str(int(sample_rate))]
        if channels is not None:
            params += ['-ac', str(int(channels))]
        if bit_depth is not None and target_format in LOSSLESS_FORMATS:
            if target_format == 'wav':
                codec = WAV_PCM_CODEC.get(int(bit_depth))
                if codec:
                    params += ['-acodec', codec]
            elif target_format == 'flac':
                sample_fmt = FLAC_SAMPLE_FMT.get(int(bit_depth))
                if sample_fmt:
                    params += ['-sample_fmt', sample_fmt]
        if bitrate is not None and target_format in LOSSY_FORMATS:
            params += ['-b:a', self._normalize_bitrate(bitrate)]
        return params

    @staticmethod
    def _normalize_bitrate(bitrate) -> str:
        """归一化比特率到 ffmpeg -b:a 形式（kbps）。"""
        if isinstance(bitrate, (int, float)):
            return f'{int(bitrate)}k'
        s = str(bitrate).strip().lower()
        if s and s[-1] in 'km':
            return s
        return f'{s}k'

    @staticmethod
    def _bitrate_to_bps(bitrate) -> int:
        """目标比特率转换为 bps 存入 DB（bitrate 列口径为 bps）。"""
        if isinstance(bitrate, (int, float)):
            return int(bitrate) * 1000
        s = str(bitrate).strip().lower()
        if s.endswith('k'):
            return int(float(s[:-1]) * 1000)
        if s.endswith('m'):
            return int(float(s[:-1]) * 1000000)
        return int(float(s)) * 1000


# 模块级实例
audio_convert_service = AudioConvertService()
