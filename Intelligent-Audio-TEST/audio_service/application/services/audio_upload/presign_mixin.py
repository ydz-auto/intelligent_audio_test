# -*- coding: utf-8 -*-
"""音频预签名 Mixin（原 audio_upload_service.py 拆分产物，P4-5；P4-6 重组入 audio_upload 子包）。

职责：S3 Multipart Upload 预签名（初始化 / 分片 URL / MD5 秒传检查 / OSS key 去重）。
依赖 self.repo（AudioRepositoryInterface）。
"""
import os
import logging

from shared.infrastructure.storage import storage
from shared.clients.oss_client import oss

logger = logging.getLogger(__name__)


class AudioPresignMixin:
    """音频预签名（依赖 self.repo）"""

    def presign_upload(self, data: dict) -> dict:
        """生成 S3 Multipart Upload 初始化信息和第一批分片预签名 URL"""
        try:
            filename = data.get('filename', '')
            file_size = data.get('file_size', data.get('fileSize', 0))
            md5 = data.get('md5')
            chunk_size = data.get('chunk_size', data.get('chunkSize', 5 * 1024 * 1024))
            is_wav = data.get('is_wav', data.get('isWav', False))
            relative_path = data.get('relative_path', data.get('relativePath'))

            # 秒传检查
            instant = self._check_md5_instant_upload(md5)
            if instant:
                return instant

            oss_key = self._build_presign_oss_key(filename, relative_path)
            category = 'audios' if is_wav else 'raw_chunks'
            oss_key = self._dedupe_presign_oss_key(category, oss_key)

            upload_id = oss.create_multipart_upload(category, oss_key)
            chunk_size = chunk_size or (5 * 1024 * 1024)
            total_parts = max(1, (file_size + chunk_size - 1) // chunk_size)
            parts_to_presign = min(total_parts, 100)
            presigned_parts = self._presign_parts(
                category, oss_key, upload_id, parts_to_presign
            )

            return {
                'success': True, 'message': '预签名 URL 生成成功',
                'data': {
                    'uploadId': upload_id,
                    'ossKey': oss_key,
                    'category': category,
                    'chunkSize': chunk_size,
                    'totalParts': total_parts,
                    'parts': presigned_parts,
                    'presignedRemaining': total_parts > parts_to_presign,
                },
                'code': 200,
            }
        except Exception as e:
            logger.error(f"presign_upload failed: {e}", exc_info=True)
            return {'success': False, 'message': str(e), 'data': None, 'code': 400}

    def _check_md5_instant_upload(self, md5):
        """检查 MD5 秒传，命中则返回秒传响应，否则返回 None"""
        if not md5:
            return None
        existing = self.repo.get_audio_by_md5(md5)
        if not existing:
            return None
        return {
            'success': True, 'message': '秒传成功',
            'data': {
                'instantUpload': True,
                'audioId': existing.id,
                'name': existing.name,
            },
            'code': 200,
        }

    def _build_presign_oss_key(self, filename, relative_path):
        """构建预签名用的 OSS key"""
        if relative_path:
            safe_path = relative_path.replace('\\', '/').lstrip('/')
            safe_path = '/'.join(p for p in safe_path.split('/') if p and p != '..')
            return f"direct/{safe_path}"
        return f"direct/{filename}"

    def _dedupe_presign_oss_key(self, category, oss_key):
        """OSS key 去重，若已存在则追加序号"""
        if storage.exists(f'{category}/{oss_key}'):
            base, ext_part = os.path.splitext(oss_key)
            counter = 1
            while storage.exists(f'{category}/{base}_{counter}{ext_part}'):
                counter += 1
            oss_key = f"{base}_{counter}{ext_part}"
        return oss_key

    def _presign_parts(self, category, oss_key, upload_id, parts_to_presign):
        """生成前 N 个分片的预签名 URL"""
        presigned_parts = []
        for part_num in range(1, parts_to_presign + 1):
            url = oss.get_part_upload_presigned_url(
                category, oss_key, upload_id, part_num, expires=3600
            )
            presigned_parts.append({"partNumber": part_num, "url": url})
        return presigned_parts

    def presign_part(self, data: dict) -> dict:
        """请求更多分片的预签名 URL"""
        try:
            upload_id = data.get('upload_id') or data.get('uploadId')
            part_number = data.get('part_number') or data.get('partNumber')
            oss_key = data.get('oss_key') or data.get('ossKey', '')
            category = data.get('category', 'raw_chunks')

            if not upload_id or not part_number:
                return {'success': False, 'message': '参数验证失败: 缺少 upload_id 或 part_number', 'data': None, 'code': 400}
            if not oss_key:
                return {'success': False, 'message': '缺少 oss_key 参数', 'data': None, 'code': 400}

            url = oss.get_part_upload_presigned_url(
                category, oss_key, upload_id, part_number, expires=3600
            )
            return {
                'success': True, 'message': 'Success',
                'data': {'partNumber': part_number, 'url': url},
                'code': 200,
            }
        except Exception as e:
            logger.error(f"presign_part failed: {e}", exc_info=True)
            return {'success': False, 'message': str(e), 'data': None, 'code': 400}
