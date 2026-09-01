# -*- coding: utf-8 -*-
"""URL 导入 Mixin（原 audio_upload_service.py 拆分产物，P4-5；P4-6 重组入 audio_upload 子包）。

职责：远程 URL 音频导入、目录标签附加、统计缓存刷新。
依赖 self.repo。
"""
import logging

from api_gateway.application.services.stats_cache import refresh_stats_cache
from audio_service.application.services.audio_file_utils import (
    _retry_file_operation,
)
from audio_service.application.services.audio_upload.transcoding_service import (
    _generate_audio_storage_path,
    _persist_file_content,
)

logger = logging.getLogger(__name__)


class AudioUrlImportMixin:
    """URL 远程导入（依赖 self.repo）"""

    def url_import(self, data: dict) -> dict:
        """URL 远程导入"""
        import requests
        from io import BytesIO

        if not data:
            return {'success': False, 'message': '请求体不能为空', 'data': None, 'code': 400}

        url = data.get('url')
        relative_path = data.get('relative_path', '') or ''
        audio_type = data.get('audio_type', data.get('audioType', 'dry'))

        if not url:
            return {'success': False, 'message': '缺少 url 参数', 'data': None, 'code': 400}

        try:
            response = requests.get(url, stream=True)
            if response.status_code != 200:
                return {'success': False, 'message': f'下载失败，状态码: {response.status_code}', 'data': None, 'code': 400}

            original_filename = url.split('/')[-1] or "downloaded_audio"
            file_content = BytesIO(response.content)
            file_content.filename = original_filename

            meta = self._save_audio(file_content, "url_", relative_path)
            meta['audio_type'] = audio_type

            new_audio = self.repo.create_audio(meta)
            self.repo.commit()

            self._attach_url_import_tags(new_audio, relative_path)

            return {
                'success': True, 'message': 'URL 导入成功',
                'data': {'id': new_audio.id, 'name': new_audio.name},
                'code': 201,
            }
        except Exception as e:
            self.repo.rollback()
            return {'success': False, 'message': str(e), 'data': None, 'code': 400}

    def _attach_url_import_tags(self, new_audio, relative_path):
        """URL 导入：根据相对路径附加目录标签并刷新统计缓存"""
        if not relative_path:
            return
        path_parts = relative_path.split('/')
        directory_parts = path_parts[:-1]
        for tag_name in directory_parts:
            if tag_name:
                tag = self.repo.get_or_create_tag(tag_name)
                self.repo.add_audio_tag(new_audio.id, tag.id)
        self.repo.commit()

        try:
            refresh_stats_cache()
        except Exception:
            logger.debug("URL导入后刷新统计缓存失败: audio_id=%s", new_audio.id, exc_info=True)

    def _save_audio(self, file, filename_prefix="", relative_path=""):
        """保存音频文件并提取元数据（委托转码服务）"""
        base_upload_dir = self._get_base_upload_dir()
        original_filename = file.filename
        temp_file_path = _generate_audio_storage_path(
            original_filename, base_upload_dir, filename_prefix, relative_path
        )
        _retry_file_operation(_persist_file_content, file, temp_file_path)
        return self._transcoding_service.create_record_from_file(
            temp_file_path, original_filename, relative_path
        )
