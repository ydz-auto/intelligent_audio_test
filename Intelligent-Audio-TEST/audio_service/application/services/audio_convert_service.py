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
            upload_dir = os.path.dirname(old_path)
            new_filename = f"conv_{uuid.uuid4().hex}.{target_format}"
            new_path = os.path.join(upload_dir, new_filename)

            local_old = old_path
            if old_path.startswith(('oss://', 'local://')):
                import tempfile
                local_old = tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(old_path)[1]).name
                storage.load_file(old_path, local_old)

            audio_seg = AudioSegment.from_file(local_old)
            audio_seg.export(new_path, format=target_format)

            new_storage_path = storage.save_file(new_path, 'audios', f'conv/{new_filename}')
            if os.path.exists(new_path):
                _retry_file_operation(os.remove, new_path)
            if local_old != old_path and os.path.exists(local_old):
                _retry_file_operation(os.remove, local_old)

            self.repo.update_audio(audio_id, {
                'file_path': new_storage_path,
                'format': target_format,
                'size': os.path.getsize(new_path) if os.path.exists(new_path) else audio.size,
            })
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


# 模块级实例
audio_convert_service = AudioConvertService()
