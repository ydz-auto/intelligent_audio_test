# -*- coding: utf-8 -*-
"""WAV 直传 OSS Mixin（原 audio_upload_service.py 拆分产物，P4-5；P4-6 重组入 audio_upload 子包）。

职责：直传完成后的分片合并、元数据提取、Audio 记录创建、标签附加。
依赖 self.repo / self._metadata_service。
"""
import os
import logging

from shared.infrastructure.storage import storage
from shared.clients.oss_client import oss

logger = logging.getLogger(__name__)


class AudioDirectUploadMixin:
    """WAV 直传 OSS（依赖 self.repo / self._metadata_service）"""

    def complete_direct_upload(self, data: dict) -> dict:
        """WAV 文件直传 OSS 完成后，合并分片 + 登记 DB"""
        temp_file = None
        try:
            oss_key, upload_id, parts = self._extract_direct_upload_params(data)
            filename, md5, audio_type, asr_text, tags = self._extract_direct_upload_meta(data)

            # 1. 完成 OSS 端分片合并
            self._complete_oss_multipart(oss_key, upload_id, parts)

            # 2. 下载到临时文件提取元数据
            temp_file, actual_file_size, sample_rate, bits_per_sample, duration = (
                self._download_and_extract_direct_meta(oss_key)
            )

            # 3. 创建 Audio 记录
            audio = self.repo.create_audio({
                'name': filename, 'original_filename': filename,
                'file_path': f'oss://audios/{oss_key}', 'format': 'wav',
                'size': actual_file_size, 'duration': duration,
                'sample_rate': sample_rate, 'md5': md5,
                'audio_type': audio_type, 'asr_text': asr_text,
            })

            # 4. 处理标签
            self._attach_direct_upload_tags(audio, tags)
            self.repo.commit()

            return self._build_direct_upload_response(
                audio, oss_key, actual_file_size, duration, sample_rate, bits_per_sample
            )
        except Exception as e:
            self.repo.rollback()
            logger.error(f"complete_direct_upload failed: {e}", exc_info=True)
            return {'success': False, 'message': str(e), 'data': None, 'code': 400}
        finally:
            self._cleanup_temp_file(temp_file)

    def _extract_direct_upload_params(self, data):
        """提取直传 OSS 参数：oss_key/upload_id/parts"""
        oss_key = data.get('oss_key') or data.get('ossKey', '')
        upload_id = data.get('upload_id') or data.get('uploadId')
        parts = data.get('parts', [])
        return oss_key, upload_id, parts

    def _extract_direct_upload_meta(self, data):
        """提取直传音频元数据：filename/md5/audio_type/asr_text/tags"""
        filename = data.get('filename', '')
        md5 = data.get('md5')
        audio_type = data.get('audio_type', data.get('audioType', 'dry'))
        asr_text = data.get('asr_text', data.get('asrText', ''))
        tags = data.get('tags', [])
        return filename, md5, audio_type, asr_text, tags

    def _build_direct_upload_response(self, audio, oss_key, actual_file_size, duration, sample_rate, bits_per_sample):
        """构建直传完成响应"""
        return {
            'success': True, 'message': '直传完成',
            'data': {
                'audio_id': audio.id, 'name': audio.name, 'oss_key': oss_key,
                'size': actual_file_size, 'duration': duration,
                'sample_rate': sample_rate, 'bits_per_sample': bits_per_sample,
            },
            'code': 200,
        }

    def _complete_oss_multipart(self, oss_key, upload_id, parts):
        """完成 OSS 端分片合并"""
        normalized_parts = []
        for p in (parts or []):
            if isinstance(p, dict):
                normalized_parts.append({
                    'PartNumber': int(p.get('PartNumber') or p.get('partNumber') or 0),
                    'ETag': p.get('ETag') or p.get('etag') or p.get('Etag') or '',
                })
        if upload_id and normalized_parts:
            oss.complete_multipart_upload('audios', oss_key, upload_id, normalized_parts)

    def _download_and_extract_direct_meta(self, oss_key):
        """下载 OSS 文件到临时文件并提取元数据，返回 (temp_file, size, sr, bps, duration)"""
        import tempfile as _tmp2
        temp_file = _tmp2.NamedTemporaryFile(delete=False, suffix='.wav').name
        storage.load_file(f'audios/{oss_key}', temp_file)
        actual_file_size = os.path.getsize(temp_file)

        sample_rate = 44100
        bits_per_sample = 16
        duration = 0.0

        sr = self._metadata_service.extract_wav_header(temp_file)
        if sr:
            sample_rate, bits_per_sample = sr

        dur = self._metadata_service.extract_wav_duration(temp_file)
        if dur is not None:
            duration = dur

        return temp_file, actual_file_size, sample_rate, bits_per_sample, duration

    def _attach_direct_upload_tags(self, audio, tags):
        """为直传音频附加标签"""
        if not tags:
            return
        for tag_name in tags:
            tag = self.repo.get_or_create_tag(tag_name)
            self.repo.add_audio_tag(audio.id, tag.id)

    def _cleanup_temp_file(self, temp_file):
        """清理临时文件"""
        if temp_file and os.path.exists(temp_file):
            try:
                os.remove(temp_file)
            except Exception:
                logger.debug("清理直传临时文件失败: %s", temp_file, exc_info=True)
