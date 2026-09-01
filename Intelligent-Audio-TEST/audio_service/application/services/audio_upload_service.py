# -*- coding: utf-8 -*-
"""音频上传应用服务（编排器）

重构后仅保留上传流程编排，具体子能力委托给：
- audio_transcoding_service: 转码/OSS/文件路径/分片合并
- audio_metadata_service: 音频元数据提取
- audio_round_config_service: 轮次配置/合并参数提取
- audio_annotation_service: 标注持久化
- audio_testcase_creation_service: 测试用例创建

公共 API（AudioUploadService 的方法签名）保持不变，调用方无需修改。
"""
import os
import uuid
import logging
from datetime import timedelta

from shared.utils.query_utils import now_cst
from shared.utils.log_handler import log_and_emit
from api_gateway.application.services.stats_cache import refresh_stats_cache
from shared.infrastructure.storage import storage
from shared.clients.oss_client import oss
from audio_service.domain.repositories.audio_repository_abc import AudioRepositoryInterface
from audio_service.domain.entities import UploadStatus
from audio_service.infrastructure.persistence.audio_repository import audio_repository
from audio_service.application.services.audio_file_utils import (
    _retry_file_operation,
    _safe_makedirs,
)
from audio_service.application.services.audio_annotation_service import audio_annotation_service
from audio_service.application.services.audio_convert_service import _get_source_language_from_algorithm_params
from audio_service.application.services.audio_testcase_creation_service import audio_testcase_creation_service
from audio_service.application.services.audio_metadata_service import audio_metadata_service
from audio_service.application.services.audio_transcoding_service import (
    audio_transcoding_service,
    _generate_audio_storage_path,
    _persist_file_content,
    _get_unique_filename,
)
from audio_service.application.services.audio_round_config_service import audio_round_config_service

logger = logging.getLogger(__name__)


class AudioUploadService:
    """音频上传应用服务（编排器）"""

    def __init__(self, repo: AudioRepositoryInterface = None):
        self.repo = repo or audio_repository
        self._annotation_service = audio_annotation_service
        self._testcase_creation_service = audio_testcase_creation_service
        self._transcoding_service = audio_transcoding_service
        self._metadata_service = audio_metadata_service
        self._round_config_service = audio_round_config_service

    # ===== 预签名相关 =====

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

    # ===== 上传任务相关 =====

    def init_upload_task(self, data: dict = None) -> dict:
        """初始化上传任务"""
        try:
            task_id = str(uuid.uuid4())
            task = self.repo.create_upload_task(
                task_id, total_files=0, total_size=0,
                status='preparing', expired_at=now_cst() + timedelta(days=7),
            )
            self.repo.commit()
            return {
                'success': True, 'message': '任务初始化成功',
                'data': {'task_id': task_id, 'message': '任务初始化成功'},
                'code': 200,
            }
        except Exception as e:
            self.repo.rollback()
            log_and_emit(
                level='error', module='audio_controller',
                content=f'音频入库失败: {str(e)}', category='audio', source='backend',
            )
            return {'success': False, 'message': str(e), 'data': None, 'code': 400}

    def register_upload_file(self, data: dict) -> dict:
        """注册上传文件"""
        try:
            task_id = data.get('task_id') or data.get('taskId')
            files = data.get('files', [])

            if not task_id:
                return {'success': False, 'message': '缺少任务ID', 'data': None, 'code': 400}

            task = self.repo.get_upload_task(task_id)
            if not task:
                return {'success': False, 'message': f'任务不存在: {task_id}', 'data': None, 'code': 404}

            if not files:
                return {'success': False, 'message': '缺少文件信息', 'data': None, 'code': 400}

            registered_files = self._register_files_batch(task, files, task_id)

            self.repo.commit()
            return {
                'success': True, 'message': f'成功注册 {len(registered_files)} 个文件',
                'data': {'task_id': task_id, 'files': registered_files},
                'code': 200,
            }
        except Exception as e:
            self.repo.rollback()
            import traceback
            log_and_emit(
                level='error', module='audio_controller',
                content=f'音频注册失败: {str(e)}\n{traceback.format_exc()}',
                category='audio', source='backend',
            )
            return {'success': False, 'message': f'音频注册失败: {str(e)}', 'data': None, 'code': 400}

    def _register_files_batch(self, task, files, task_id):
        """批量注册文件，返回 registered_files 列表"""
        registered_files = []
        with self.repo.no_autoflush:
            for file_info in files:
                record = self._create_upload_file_record(file_info, task_id)
                if record is None:
                    continue
                registered_files.append(self._format_registered_file(record))
                self._accumulate_task_stats(task, record)

            if task.completed_files >= task.total_files and task.total_files > 0:
                task.status = 'completed'
            else:
                task.status = 'uploading'
        return registered_files

    def _format_registered_file(self, record):
        """格式化注册文件响应"""
        return {
            'file_id': record['file_id'],
            'filename': record['filename'],
            'total_chunks': record['total_chunks'],
            'chunk_size': record['chunk_size'],
            'status': record['status'],
        }

    def _accumulate_task_stats(self, task, record):
        """累加任务统计（文件数/大小/已完成）"""
        task.total_files += 1
        task.total_size += record['file_size']
        if record['status'] == UploadStatus.completed.value:
            task.completed_files += 1
            task.uploaded_size += record['file_size']

    def _create_upload_file_record(self, file_info, task_id):
        """创建 UploadFile 记录"""
        file_name = file_info.get('name', '')
        file_size = file_info.get('size', 0)
        md5 = file_info.get('md5', '')
        relative_path = file_info.get('relative_path', file_info.get('relativePath', ''))

        if not file_name:
            return None

        status = 'pending'
        file_id = str(uuid.uuid4())
        chunk_size = 10 * 1024 * 1024
        total_chunks = max(1, (file_size + chunk_size - 1) // chunk_size)

        if md5:
            try:
                existing_audio = self.repo.get_audio_by_md5(md5)
                if existing_audio:
                    status = 'completed'
                    total_chunks = 0
            except Exception as e:
                logger.warning(f"MD5查询失败: {str(e)}")

        self.repo.create_upload_file(
            file_id, task_id, file_name, file_name, relative_path,
            file_size, md5, status,
            file_size if status == UploadStatus.completed.value else 0,
            total_chunks if status == UploadStatus.completed.value else 0,
            total_chunks,
        )

        return {
            'file_id': file_id, 'filename': file_name,
            'total_chunks': total_chunks, 'chunk_size': chunk_size,
            'status': status, 'file_size': file_size,
        }

    def upload_chunk(self, data: dict) -> dict:
        """上传分片"""
        try:
            file_id, chunk_index, total_chunks, task_id, chunk_content_b64, chunk_size = (
                self._extract_chunk_params(data)
            )

            if not file_id or chunk_index is None or not total_chunks or not task_id:
                return {'success': False, 'message': '缺少分片信息', 'data': None, 'code': 400}

            upload_file = self.repo.get_upload_file(file_id)
            if not upload_file:
                return {'success': False, 'message': '文件不存在', 'data': None, 'code': 404}

            task = self.repo.get_upload_task(task_id)
            if not task:
                return {'success': False, 'message': '任务不存在', 'data': None, 'code': 404}

            # 保存分片到磁盘
            chunk_path, actual_chunk_size = self._save_chunk_to_disk(
                file_id, chunk_index, chunk_content_b64, chunk_size
            )

            # 更新分片与任务进度
            self._update_chunk_progress(
                upload_file, task, file_id, chunk_index, actual_chunk_size, total_chunks, chunk_path
            )

            self.repo.commit()
            return self._build_chunk_upload_response(
                file_id, chunk_index, total_chunks, upload_file, task
            )
        except Exception as e:
            self.repo.rollback()
            import traceback
            log_and_emit(
                level='error', module='audio_controller',
                content=f'分片上传失败: {str(e)}', category='audio', source='backend',
            )
            return {'success': False, 'message': str(e), 'data': None, 'code': 400}

    def _extract_chunk_params(self, data):
        """提取分片上传参数"""
        file_id = data.get('file_id') or data.get('fileId')
        chunk_index = data.get('chunk_index', data.get('chunkIndex'))
        total_chunks = data.get('total_chunks', data.get('totalChunks'))
        task_id = data.get('task_id') or data.get('taskId')
        chunk_content_b64 = data.get('chunk_content', data.get('chunkContent'))
        chunk_size = data.get('chunk_size', data.get('chunkSize', 0))
        return file_id, chunk_index, total_chunks, task_id, chunk_content_b64, chunk_size

    def _build_chunk_upload_response(self, file_id, chunk_index, total_chunks, upload_file, task):
        """构建分片上传成功响应"""
        return {
            'success': True, 'message': '分片上传成功',
            'data': {
                'file_id': file_id,
                'chunk_index': chunk_index,
                'completed_chunks': upload_file.completed_chunks,
                'total_chunks': total_chunks,
                'uploaded_size': upload_file.uploaded_size,
                'file_size': upload_file.size,
                'task_progress': self._build_task_progress(task),
            },
            'code': 200,
        }

    def _build_task_progress(self, task):
        """构建任务进度数据"""
        return {
            'uploaded_size': task.uploaded_size,
            'total_size': task.total_size,
            'completed_files': task.completed_files,
            'total_files': task.total_files,
            'status': task.status,
        }

    def _save_chunk_to_disk(self, file_id, chunk_index, chunk_content_b64, chunk_size):
        """保存分片到磁盘，返回 (chunk_path, 实际分片大小)"""
        base_upload_dir = self._get_base_upload_dir()
        chunk_dir = os.path.join(base_upload_dir, 'chunks', file_id)
        _safe_makedirs(chunk_dir)
        chunk_path = os.path.join(chunk_dir, f"chunk_{chunk_index}")

        if chunk_content_b64:
            import base64
            chunk_data = base64.b64decode(chunk_content_b64)
            with open(chunk_path, 'wb') as f:
                f.write(chunk_data)
            return chunk_path, os.path.getsize(chunk_path)
        return chunk_path, chunk_size

    def _update_chunk_progress(self, upload_file, task, file_id, chunk_index, actual_chunk_size, total_chunks, chunk_path):
        """更新分片与任务进度"""
        with self.repo.no_autoflush:
            existing_chunk = self.repo.get_upload_chunk(file_id, chunk_index)
            if existing_chunk:
                self.repo.update_upload_file(existing_chunk, chunk_size=actual_chunk_size, status='completed')
            else:
                self.repo.create_upload_chunk(file_id, chunk_index, actual_chunk_size, chunk_path)

            upload_file.completed_chunks += 1
            upload_file.uploaded_size += actual_chunk_size

            if upload_file.completed_chunks >= total_chunks:
                upload_file.status = 'completed'
                task.completed_files += 1

            task.uploaded_size += actual_chunk_size
            task.status = 'uploading'

            if task.completed_files >= task.total_files:
                task.status = 'completed'

    def _get_base_upload_dir(self):
        """获取音频存储根目录"""
        from audio_service.config.config import Config
        return getattr(Config, 'AUDIO_STORAGE_PATH',
                       os.path.join(os.environ.get('LOCAL_STORAGE_ROOT', './storage'), 'audios'))

    # ===== 合并分片相关 =====

    def merge_chunks(self, data: dict) -> dict:
        """合并分片"""
        try:
            file_id = data.get('file_id') or data.get('fileId')
            task_id = data.get('task_id') or data.get('taskId')
            if not file_id or not task_id:
                return {'success': False, 'message': '缺少文件或任务ID', 'data': None, 'code': 400}

            upload_file = self.repo.get_upload_file(file_id)
            if not upload_file:
                return {'success': False, 'message': '文件不存在', 'data': None, 'code': 404}
            task = self.repo.get_upload_task(task_id)
            if not task:
                return {'success': False, 'message': '任务不存在', 'data': None, 'code': 404}

            params = self._round_config_service.extract_merge_params(data)

            # 检查秒传
            instant_result = self._check_instant_upload(upload_file, data, params)
            if instant_result is not None:
                return instant_result

            # 合并分片
            final_path = self._merge_file_parts(upload_file, data)

            # 转码并提取元数据
            audio_meta = self._transcoding_service.transcode_and_extract_metadata(
                final_path, upload_file
            )

            # 创建音频记录
            new_audio, audio_tags, raw_annotations_data = self._create_audio_record(
                audio_meta, upload_file, data, params
            )

            # 创建测试用例（如果需要）
            tc_result = self._create_test_case_if_needed(
                new_audio, params, audio_tags, raw_annotations_data
            )

            self.repo.commit()
            return self._build_merge_response(file_id, new_audio, tc_result)
        except Exception as e:
            self.repo.rollback()
            logger.error(f"合并分片失败: {str(e)}", exc_info=True)
            return {'success': False, 'message': f'合并分片失败: {str(e)}', 'data': None, 'code': 400}

    def _build_merge_response(self, file_id, new_audio, tc_result):
        """构建合并完成响应"""
        response_data = {
            'file_id': file_id,
            'audio_id': new_audio.id,
            'name': new_audio.name,
            'status': 'completed',
        }
        if tc_result:
            response_data['test_case_id'] = tc_result.get('tc_id')
            response_data['test_case_count'] = tc_result.get('tc_count')
        return {'success': True, 'message': '合并完成', 'data': response_data, 'code': 200}

    def _check_instant_upload(self, upload_file, data, params):
        """检查秒传场景：返回响应 dict 表示已处理，返回 None 表示继续合并流程"""
        is_instant_upload = upload_file.total_chunks == 0 and upload_file.status == UploadStatus.completed

        if not is_instant_upload and upload_file.md5:
            existing_audio = self.repo.get_audio_by_md5(upload_file.md5)
            if existing_audio:
                is_instant_upload = True

        if not is_instant_upload:
            if upload_file.completed_chunks < upload_file.total_chunks:
                return {'success': False, 'message': '还有分片未上传完成', 'data': None, 'code': 400}
            return None

        return self._handle_instant_upload(upload_file, data, params)

    def _handle_instant_upload(self, upload_file, data, params):
        """处理秒传：查找已有音频并按是否创建测试用例分支"""
        if not upload_file.md5:
            return None

        existing_audio = self.repo.get_audio_by_md5(upload_file.md5)
        if not existing_audio:
            return None

        audio_tags = self.repo.get_audio_tag_names(existing_audio.id)

        if params['create_test_case']:
            return self._instant_upload_with_testcase(existing_audio, data, params, audio_tags)
        return self._instant_upload_without_testcase(existing_audio, data, params)

    def _instant_upload_with_testcase(self, existing_audio, data, params, audio_tags):
        """秒传 + 创建测试用例：匹配轮次、创建用例、返回响应"""
        self._round_config_service.match_existing_audio_in_rounds(
            params['rounds_config'], existing_audio
        )
        raw_annotations_data = self._annotation_service.persist_annotations_and_raw(
            existing_audio.id,
            data.get('annotations', []),
            params['algorithm_type'],
        )
        tc_ids = self._testcase_creation_service.create_test_case_from_audio(
            existing_audio.id,
            params['test_types'],
            audio_tags,
            params['default_playback_device_id'],
            params['default_spl'],
            params['noise_spl'],
            params['noise_audio_id'],
            params['test_case_group_name'],
            params['dimensions_data'],
            params['algorithm_type'],
            params['algorithm_params_dict'],
            rounds_config=params['rounds_config'],
            inherit_tags=params['tc_inherit_tags'],
            raw_annotations=raw_annotations_data,
            noise_device_ids=params.get('noise_device_ids'),
            case_background_noise=params.get('case_background_noise'),
        )
        self.repo.commit()
        return {
            'success': True, 'message': '秒传成功，测试用例已创建',
            'data': {
                'file_id': data.get('file_id') or data.get('fileId'),
                'audio_id': existing_audio.id,
                'name': existing_audio.name,
                'status': 'completed',
                'test_case_id': tc_ids[0] if tc_ids else None,
                'test_case_count': len(tc_ids) if isinstance(tc_ids, list) else (1 if tc_ids else 0),
                'instant_upload': True,
            },
            'code': 200,
        }

    def _instant_upload_without_testcase(self, existing_audio, data, params):
        """秒传不创建测试用例：仅持久化标注并返回响应"""
        self._annotation_service.persist_annotations_and_raw(
            existing_audio.id,
            data.get('annotations', []),
            params['algorithm_type'],
        )
        self.repo.commit()
        return {
            'success': True, 'message': '秒传成功',
            'data': {
                'file_id': data.get('file_id') or data.get('fileId'),
                'audio_id': existing_audio.id,
                'name': existing_audio.name,
                'status': 'completed',
                'instant_upload': True,
            },
            'code': 200,
        }

    def _merge_file_parts(self, upload_file, data):
        """合并分片，返回 final_path（委托转码服务）"""
        base_upload_dir = self._get_base_upload_dir()
        chunk_base = os.path.join(base_upload_dir, 'chunks')

        is_direct_oss = data.get('is_direct_oss', data.get('isDirectOss', False))
        oss_key = data.get('oss_key', data.get('ossKey'))
        oss_upload_id = data.get('oss_upload_id', data.get('ossUploadId'))
        oss_parts = data.get('oss_parts', data.get('ossParts'))

        if is_direct_oss and oss_key and oss_upload_id:
            return self._transcoding_service.merge_direct_oss_parts(
                oss_key, oss_upload_id, oss_parts
            )
        return self._transcoding_service.merge_local_chunks(
            upload_file, base_upload_dir, chunk_base
        )

    def _create_audio_record(self, audio_meta, upload_file, data, params):
        """创建音频数据库记录，处理标签和算法关联"""
        source_language = _get_source_language_from_algorithm_params(
            params['algorithm_params']
        )

        audio_record = self.repo.create_audio({
            'name': upload_file.filename,
            'original_filename': upload_file.original_filename,
            'file_path': audio_meta['final_path'],
            'size': audio_meta['file_size'],
            'duration': audio_meta['duration'],
            'sample_rate': audio_meta['sample_rate'],
            'channels': audio_meta['channels'],
            'bitrate': audio_meta['bitrate'],
            'format': 'wav',
            'audio_type': data.get('audio_type', data.get('audioType', 'dry')),
            'md5': upload_file.md5,
            'source_language': source_language,
            'asr_text': data.get('asr_text', data.get('asrText', '')),
            'description': params['description'],
        })

        audio_tags = self._process_audio_tags(audio_record, params['user_tags'], upload_file)

        raw_annotations_data = self._annotation_service.persist_annotations_and_raw(
            audio_record.id,
            data.get('annotations', []),
            params['algorithm_type'],
        )

        self._process_algorithm_relations(audio_record, data, params['algorithm_type'])
        self.repo.flush()

        return audio_record, audio_tags, raw_annotations_data

    def _process_audio_tags(self, audio_record, user_tags, upload_file):
        """处理音频标签关联"""
        audio_tags = []
        all_tag_names = list(user_tags)

        relative_path = upload_file.relative_path
        if relative_path:
            path_parts = relative_path.split('/')
            directory_parts = path_parts[:-1]
            for part in directory_parts:
                if part and part not in all_tag_names:
                    all_tag_names.append(part)

        for tag_name in all_tag_names:
            if not tag_name:
                continue
            tag = self.repo.get_or_create_tag(tag_name)
            self.repo.add_audio_tag(audio_record.id, tag.id)
            audio_tags.append(tag.name)

        return audio_tags

    def _process_algorithm_relations(self, audio_record, data, algorithm_type):
        """处理音频算法关联"""
        algorithm_relations = data.get('algorithm_relations', data.get('algorithmRelations'))
        if algorithm_relations:
            for item in algorithm_relations:
                if isinstance(item, dict):
                    self.repo.create_audio_algorithm_relation(audio_record.id, item)
        elif algorithm_type:
            self.repo.create_audio_algorithm_relation(audio_record.id, {
                'algorithm_type': algorithm_type,
                'is_primary': True,
                'weight': 1.0,
                'params': None,
            })

    def _create_test_case_if_needed(self, new_audio, params, audio_tags, raw_annotations_data):
        """如果需要，创建测试用例"""
        if not params['create_test_case']:
            return None

        tc_ids = self._testcase_creation_service.create_test_case_from_audio(
            new_audio.id,
            params['test_types'],
            audio_tags,
            params['default_playback_device_id'],
            params['default_spl'],
            params['noise_spl'],
            params['noise_audio_id'],
            params['test_case_group_name'],
            params['dimensions_data'],
            params['algorithm_type'],
            params['algorithm_params_dict'],
            rounds_config=params['rounds_config'],
            inherit_tags=params['tc_inherit_tags'],
            raw_annotations=raw_annotations_data or None,
            noise_device_ids=params.get('noise_device_ids'),
            case_background_noise=params.get('case_background_noise'),
        )

        if isinstance(tc_ids, list):
            tc_id = tc_ids[0] if tc_ids else None
            tc_count = len(tc_ids)
        else:
            tc_id = tc_ids
            tc_count = 1 if tc_ids else 0

        return {'tc_id': tc_id, 'tc_count': tc_count}

    # ===== 查询与导入 =====

    def get_upload_progress(self, data: dict) -> dict:
        """获取上传任务进度"""
        try:
            task_id = data.get('task_id') or data.get('taskId')
            if not task_id:
                return {'success': False, 'message': '缺少任务ID', 'data': None, 'code': 400}

            task = self.repo.get_upload_task(task_id)
            if not task:
                return {'success': False, 'message': '任务不存在', 'data': None, 'code': 404}

            files = self.repo.list_upload_files(task_id)
            file_progress = [self._format_file_progress(f) for f in files]

            return {
                'success': True, 'message': 'Success',
                'data': {
                    'task': {
                        'task_id': task.id,
                        'status': task.status,
                        'total_files': task.total_files,
                        'completed_files': task.completed_files,
                        'failed_files': task.failed_files,
                        'total_size': task.total_size,
                        'uploaded_size': task.uploaded_size,
                        'created_at': task.created_at.isoformat() if task.created_at else None,
                    },
                    'files': file_progress,
                },
                'code': 200,
            }
        except Exception as e:
            return {'success': False, 'message': str(e), 'data': None, 'code': 400}

    def _format_file_progress(self, file):
        """格式化单文件进度"""
        return {
            'file_id': file.id,
            'filename': file.filename,
            'original_filename': file.original_filename,
            'relative_path': file.relative_path,
            'size': file.size,
            'uploaded_size': file.uploaded_size,
            'completed_chunks': file.completed_chunks,
            'total_chunks': file.total_chunks,
            'status': file.status,
            'md5': file.md5,
        }

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


# 模块级实例
audio_upload_service = AudioUploadService()
