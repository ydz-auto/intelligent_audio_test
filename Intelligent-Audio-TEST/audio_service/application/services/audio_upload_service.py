# -*- coding: utf-8 -*-
"""音频上传应用服务

从 audio_crud_service.py 中提取的上传相关逻辑：
- presign_upload / presign_part / complete_direct_upload
- init_upload_task / register_upload_file / upload_chunk / merge_chunks
- get_upload_progress / url_import
- 以及内部辅助方法
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
from audio_service.infrastructure.persistence.audio_repository import audio_repository
from audio_service.application.services.audio_file_utils import (
    _retry_file_operation,
    _safe_makedirs,
    _read_wav_header,
    _convert_to_wav,
)
from audio_service.application.services.audio_annotation_service import audio_annotation_service
from audio_service.application.services.audio_convert_service import _get_source_language_from_algorithm_params
from audio_service.application.services.audio_testcase_creation_service import audio_testcase_creation_service

logger = logging.getLogger(__name__)


def _get_unique_filename(directory, original_filename):
    from werkzeug.utils import secure_filename
    safe_filename = secure_filename(original_filename)
    if not safe_filename:
        safe_filename = f"audio_{uuid.uuid4().hex[:8]}"
    base_name, ext = os.path.splitext(safe_filename)
    counter = 1
    unique_filename = safe_filename
    while os.path.exists(os.path.join(directory, unique_filename)):
        unique_filename = f"{base_name}_{counter}{ext}"
        counter += 1
    return unique_filename


def _persist_file_content(file, file_path):
    """保存文件内容到磁盘"""
    content = file.read()
    with open(file_path, 'wb') as f:
        f.write(content)


def _generate_audio_storage_path(filename, dirs, filename_prefix="", relative_path=""):
    """生成音频存储路径"""
    base_upload_dir = dirs if isinstance(dirs, str) else dirs.get('base')

    if relative_path:
        temp_file_path = os.path.join(base_upload_dir, relative_path)
        os.makedirs(os.path.dirname(temp_file_path), exist_ok=True)
        if os.path.exists(temp_file_path):
            base_name, ext = os.path.splitext(temp_file_path)
            counter = 1
            while os.path.exists(temp_file_path):
                temp_file_path = f"{base_name}_{counter}{ext}"
                counter += 1
    else:
        if filename_prefix:
            prefixed_filename = f"{filename_prefix}{filename}"
        else:
            prefixed_filename = filename
        if not os.path.exists(base_upload_dir):
            os.makedirs(base_upload_dir, exist_ok=True)
        safe_filename = _get_unique_filename(base_upload_dir, prefixed_filename)
        temp_file_path = os.path.join(base_upload_dir, safe_filename)

    return temp_file_path


def _create_audio_db_record(temp_file_path, filename, relative_path=""):
    """转换音频为WAV，上传到OSS，提取元数据，返回音频记录数据"""
    original_filename = filename
    try:
        wav_file_path, wav_filename, sample_rate, bits_per_sample = _convert_to_wav(temp_file_path)
        if os.path.exists(temp_file_path) and temp_file_path != wav_file_path:
            _retry_file_operation(os.remove, temp_file_path)

        if relative_path:
            safe_path = relative_path.replace('\\', '/').lstrip('/')
            safe_path = '/'.join(p for p in safe_path.split('/') if p and p != '..')
            oss_key = f"direct/{safe_path}"
        else:
            oss_key = f"direct/{wav_filename}"

        if storage.exists(f'audios/{oss_key}'):
            base, ext_part = os.path.splitext(oss_key)
            counter = 1
            while storage.exists(f'audios/{base}_{counter}{ext_part}'):
                counter += 1
            oss_key = f"{base}_{counter}{ext_part}"
        file_path = storage.save_file(wav_file_path, 'audios', oss_key)
        if os.path.exists(wav_file_path):
            _retry_file_operation(os.remove, wav_file_path)
        original_filename = wav_filename
    except Exception as e:
        if os.path.exists(temp_file_path):
            _retry_file_operation(os.remove, temp_file_path)
        raise ValueError(f"音频转换/上传OSS失败: {str(e)}")

    meta_tmp_path = None
    try:
        import tempfile
        meta_tmp_path = tempfile.NamedTemporaryFile(delete=False, suffix='.wav').name
        storage.load_file(f'audios/{oss_key}', meta_tmp_path)
        file_size = os.path.getsize(meta_tmp_path)
        from pydub import AudioSegment
        audio_seg = AudioSegment.from_file(meta_tmp_path)
        duration = len(audio_seg) / 1000.0
        channels = audio_seg.channels
        bitrate = bits_per_sample * sample_rate * channels
        if duration <= 0:
            raise ValueError("音频时长为0，可能是无效的音频文件")
    except Exception as e:
        try:
            storage.delete(f'audios/{oss_key}')
        except Exception:
            logger.debug("解析音频元数据失败后清理OSS文件失败: oss_key=%s", oss_key, exc_info=True)
        raise ValueError(f"无法识别的音频格式或文件已损坏: {str(e)}")
    finally:
        if meta_tmp_path and os.path.exists(meta_tmp_path):
            try:
                os.remove(meta_tmp_path)
            except Exception:
                logger.debug("清理音频元数据临时文件失败: %s", meta_tmp_path, exc_info=True)

    return {
        'name': original_filename,
        'original_filename': original_filename,
        'file_path': file_path,
        'size': file_size,
        'duration': duration,
        'sample_rate': sample_rate,
        'channels': channels,
        'bitrate': bitrate,
        'format': 'wav',
    }


class AudioUploadService:
    """音频上传应用服务"""

    def __init__(self, repo: AudioRepositoryInterface = None):
        self.repo = repo or audio_repository
        self._annotation_service = audio_annotation_service
        self._testcase_creation_service = audio_testcase_creation_service

    def presign_upload(self, data: dict) -> dict:
        """生成 S3 Multipart Upload 初始化信息和第一批分片预签名 URL"""
        try:
            filename = data.get('filename', '')
            file_size = data.get('file_size', data.get('fileSize', 0))
            md5 = data.get('md5')
            chunk_size = data.get('chunk_size', data.get('chunkSize', 5 * 1024 * 1024))
            is_wav = data.get('is_wav', data.get('isWav', False))
            relative_path = data.get('relative_path', data.get('relativePath'))

            if md5:
                existing = self.repo.get_audio_by_md5(md5)
                if existing:
                    return {
                        'success': True, 'message': '秒传成功',
                        'data': {
                            'instantUpload': True,
                            'audioId': existing.id,
                            'name': existing.name,
                        },
                        'code': 200,
                    }

            ext = os.path.splitext(filename)[1].lower()
            category = 'audios' if is_wav else 'raw_chunks'
            if relative_path:
                safe_path = relative_path.replace('\\', '/').lstrip('/')
                safe_path = '/'.join(p for p in safe_path.split('/') if p and p != '..')
                oss_key = f"direct/{safe_path}"
            else:
                oss_key = f"direct/{filename}"

            if storage.exists(f'{category}/{oss_key}'):
                base, ext_part = os.path.splitext(oss_key)
                counter = 1
                while storage.exists(f'{category}/{base}_{counter}{ext_part}'):
                    counter += 1
                oss_key = f"{base}_{counter}{ext_part}"

            upload_id = oss.create_multipart_upload(category, oss_key)
            chunk_size = chunk_size or (5 * 1024 * 1024)
            total_parts = max(1, (file_size + chunk_size - 1) // chunk_size)
            parts_to_presign = min(total_parts, 100)
            presigned_parts = []
            for part_num in range(1, parts_to_presign + 1):
                url = oss.get_part_upload_presigned_url(
                    category, oss_key, upload_id, part_num, expires=3600
                )
                presigned_parts.append({"partNumber": part_num, "url": url})

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
            oss_key = data.get('oss_key') or data.get('ossKey', '')
            upload_id = data.get('upload_id') or data.get('uploadId')
            parts = data.get('parts', [])
            filename = data.get('filename', '')
            md5 = data.get('md5')
            file_size = data.get('file_size', data.get('fileSize', 0))
            sample_rate = data.get('sample_rate', data.get('sampleRate', 44100))
            bits_per_sample = data.get('bits_per_sample', data.get('bitsPerSample', 16))
            duration = data.get('duration', 0.0)
            tags = data.get('tags', [])
            audio_type = data.get('audio_type', data.get('audioType', 'dry'))
            asr_text = data.get('asr_text', data.get('asrText', ''))

            # 1. 完成 OSS 端分片合并
            normalized_parts = []
            for p in (parts or []):
                if isinstance(p, dict):
                    normalized_parts.append({
                        'PartNumber': int(p.get('PartNumber') or p.get('partNumber') or 0),
                        'ETag': p.get('ETag') or p.get('etag') or p.get('Etag') or '',
                    })
            if upload_id and normalized_parts:
                oss.complete_multipart_upload('audios', oss_key, upload_id, normalized_parts)

            # 2. 下载到临时文件提取元数据
            import tempfile as _tmp2
            temp_file = _tmp2.NamedTemporaryFile(delete=False, suffix='.wav').name
            storage.load_file(f'audios/{oss_key}', temp_file)
            actual_file_size = os.path.getsize(temp_file)

            try:
                sr, bps = _read_wav_header(temp_file)
                sample_rate = sr
                bits_per_sample = bps
            except Exception:
                logger.debug("解析WAV头部信息失败: temp_file=%s", temp_file, exc_info=True)

            try:
                import wave
                with wave.open(temp_file, 'rb') as wf:
                    duration = wf.getnframes() / wf.getframerate() if wf.getframerate() else 0.0
            except Exception:
                logger.debug("解析音频时长失败: temp_file=%s", temp_file, exc_info=True)

            # 3. 创建 Audio 记录
            audio = self.repo.create_audio({
                'name': filename,
                'original_filename': filename,
                'file_path': f'oss://audios/{oss_key}',
                'format': 'wav',
                'size': actual_file_size,
                'duration': duration,
                'sample_rate': sample_rate,
                'md5': md5,
                'audio_type': audio_type,
                'asr_text': asr_text,
            })

            # 4. 处理标签
            if tags:
                for tag_name in tags:
                    tag = self.repo.get_or_create_tag(tag_name)
                    self.repo.add_audio_tag(audio.id, tag.id)

            self.repo.commit()

            return {
                'success': True, 'message': '直传完成',
                'data': {
                    'audio_id': audio.id,
                    'name': audio.name,
                    'oss_key': oss_key,
                    'size': actual_file_size,
                    'duration': duration,
                    'sample_rate': sample_rate,
                    'bits_per_sample': bits_per_sample,
                },
                'code': 200,
            }
        except Exception as e:
            self.repo.rollback()
            logger.error(f"complete_direct_upload failed: {e}", exc_info=True)
            return {'success': False, 'message': str(e), 'data': None, 'code': 400}
        finally:
            if temp_file and os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except Exception:
                    logger.debug("清理直传临时文件失败: %s", temp_file, exc_info=True)

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

            registered_files = []
            with self.repo.no_autoflush:
                for file_info in files:
                    record = self._create_upload_file_record(file_info, task_id)
                    if record is None:
                        continue
                    registered_files.append({
                        'file_id': record['file_id'],
                        'filename': record['filename'],
                        'total_chunks': record['total_chunks'],
                        'chunk_size': record['chunk_size'],
                        'status': record['status'],
                    })
                    task.total_files += 1
                    task.total_size += record['file_size']
                    if record['status'] == 'completed':
                        task.completed_files += 1
                        task.uploaded_size += record['file_size']

                if task.completed_files >= task.total_files and task.total_files > 0:
                    task.status = 'completed'
                else:
                    task.status = 'uploading'

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
            file_size if status == 'completed' else 0,
            total_chunks if status == 'completed' else 0,
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
            file_id = data.get('file_id') or data.get('fileId')
            chunk_index = data.get('chunk_index', data.get('chunkIndex'))
            total_chunks = data.get('total_chunks', data.get('totalChunks'))
            task_id = data.get('task_id') or data.get('taskId')
            chunk_content_b64 = data.get('chunk_content', data.get('chunkContent'))
            chunk_size = data.get('chunk_size', data.get('chunkSize', 0))

            if not file_id or chunk_index is None or not total_chunks or not task_id:
                return {'success': False, 'message': '缺少分片信息', 'data': None, 'code': 400}

            upload_file = self.repo.get_upload_file(file_id)
            if not upload_file:
                return {'success': False, 'message': '文件不存在', 'data': None, 'code': 404}

            task = self.repo.get_upload_task(task_id)
            if not task:
                return {'success': False, 'message': '任务不存在', 'data': None, 'code': 404}

            # 保存分片到磁盘
            import base64
            from audio_service.config.config import Config
            base_upload_dir = getattr(Config, 'AUDIO_STORAGE_PATH',
                                     os.path.join(os.environ.get('LOCAL_STORAGE_ROOT', './storage'), 'audios'))
            chunk_dir = os.path.join(base_upload_dir, 'chunks', file_id)
            _safe_makedirs(chunk_dir)
            chunk_path = os.path.join(chunk_dir, f"chunk_{chunk_index}")

            if chunk_content_b64:
                chunk_data = base64.b64decode(chunk_content_b64)
                with open(chunk_path, 'wb') as f:
                    f.write(chunk_data)
                actual_chunk_size = os.path.getsize(chunk_path)
            else:
                actual_chunk_size = chunk_size

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

            self.repo.commit()
            return {
                'success': True, 'message': '分片上传成功',
                'data': {
                    'file_id': file_id,
                    'chunk_index': chunk_index,
                    'completed_chunks': upload_file.completed_chunks,
                    'total_chunks': total_chunks,
                    'uploaded_size': upload_file.uploaded_size,
                    'file_size': upload_file.size,
                    'task_progress': {
                        'uploaded_size': task.uploaded_size,
                        'total_size': task.total_size,
                        'completed_files': task.completed_files,
                        'total_files': task.total_files,
                        'status': task.status,
                    },
                },
                'code': 200,
            }
        except Exception as e:
            self.repo.rollback()
            import traceback
            log_and_emit(
                level='error', module='audio_controller',
                content=f'分片上传失败: {str(e)}', category='audio', source='backend',
            )
            return {'success': False, 'message': str(e), 'data': None, 'code': 400}

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

            params = self._extract_merge_params(data)

            # 检查秒传
            instant_result = self._check_instant_upload(upload_file, data, params)
            if instant_result is not None:
                return instant_result

            # 合并分片
            final_path = self._merge_file_parts(upload_file, data)

            # 转码并提取元数据
            audio_meta = self._transcode_and_extract_metadata(final_path, upload_file, data)

            # 创建音频记录
            new_audio, audio_tags, raw_annotations_data = self._create_audio_record(
                audio_meta, upload_file, data, params
            )

            # 创建测试用例（如果需要）
            tc_result = self._create_test_case_if_needed(
                new_audio, params, audio_tags, raw_annotations_data
            )

            self.repo.commit()

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

        except Exception as e:
            self.repo.rollback()
            logger.error(f"合并分片失败: {str(e)}", exc_info=True)
            return {'success': False, 'message': f'合并分片失败: {str(e)}', 'data': None, 'code': 400}

    def _extract_merge_params(self, data):
        """从 data 中提取合并参数"""
        tc_config = data.get('test_case_config') or data.get('testCaseConfig')
        rounds_config = None
        if tc_config and isinstance(tc_config, dict):
            rounds_config = tc_config.get('rounds')

        tc_group_name = tc_config.get('group_name') if tc_config else None
        tc_inherit_tags = tc_config.get('inherit_tags', True) if tc_config else True

        test_case_group_name = data.get('test_case_group_name') or data.get('testCaseGroupName')
        if tc_group_name:
            test_case_group_name = tc_group_name

        algorithm_params = data.get('algorithm_params') or data.get('algorithmParams')
        algorithm_params_dict = None
        if isinstance(algorithm_params, list):
            algorithm_params_dict = algorithm_params
        elif isinstance(algorithm_params, dict):
            algorithm_params_dict = [{'field_code': k, 'field_value': v} for k, v in algorithm_params.items()]

        if tc_config and tc_config.get('algorithm_params') and not algorithm_params_dict:
            # 通过 ACL 仓储规范化算法参数
            from audio_service.infrastructure.acl.algorithm_acl_repository import (
                AlgorithmACLRepositoryImpl,
            )
            algorithm_params_dict = AlgorithmACLRepositoryImpl().normalize_algorithm_params_to_list(
                tc_config.get('algorithm_params')
            )

        dimensions_data = data.get('dimensions')
        if tc_config and tc_config.get('dimensions') and not dimensions_data:
            dimensions_data = tc_config.get('dimensions')

        return {
            'create_test_case': data.get('create_test_case', data.get('createTestCase', False)),
            'test_types': data.get('test_types', data.get('testTypes', ['api'])),
            'dimensions_data': dimensions_data,
            'default_playback_device_id': data.get('default_playback_device_id') or data.get('defaultPlaybackDeviceId'),
            'default_spl': data.get('default_spl', data.get('defaultSpl', 65.0)),
            'noise_spl': data.get('noise_spl', data.get('noiseSpl', 60.0)),
            'noise_audio_id': data.get('noise_audio_id') or data.get('noiseAudioId'),
            'noise_device_ids': data.get('noise_device_ids') or data.get('noiseDeviceIds') or [],
            'test_case_group_name': test_case_group_name,
            'algorithm_type': data.get('algorithm_type') or data.get('algorithmType'),
            'algorithm_params': algorithm_params,
            'algorithm_params_dict': algorithm_params_dict,
            'description': data.get('description', ''),
            'user_tags': data.get('tags', []),
            'rounds_config': rounds_config,
            'tc_inherit_tags': tc_inherit_tags,
        }

    def _check_instant_upload(self, upload_file, data, params):
        """检查秒传场景"""
        is_instant_upload = upload_file.total_chunks == 0 and upload_file.status == 'completed'

        if not is_instant_upload and upload_file.md5:
            existing_audio = self.repo.get_audio_by_md5(upload_file.md5)
            if existing_audio:
                is_instant_upload = True

        if not is_instant_upload:
            if upload_file.completed_chunks < upload_file.total_chunks:
                return {'success': False, 'message': '还有分片未上传完成', 'data': None, 'code': 400}
            return None

        existing_audio_id = None
        audio_tags = []
        if upload_file.md5:
            existing_audio = self.repo.get_audio_by_md5(upload_file.md5)
            if existing_audio:
                existing_audio_id = existing_audio.id
                audio_tags = self.repo.get_audio_tag_names(existing_audio.id)

                if params['create_test_case']:
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
                else:
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
        return None

    def _merge_file_parts(self, upload_file, data):
        """合并分片，返回 final_path"""
        from audio_service.config.config import Config
        base_upload_dir = getattr(Config, 'AUDIO_STORAGE_PATH',
                                  os.path.join(os.environ.get('LOCAL_STORAGE_ROOT', './storage'), 'audios'))
        chunk_base = os.path.join(base_upload_dir, 'chunks')

        is_direct_oss = data.get('is_direct_oss', data.get('isDirectOss', False))
        oss_key = data.get('oss_key', data.get('ossKey'))
        oss_upload_id = data.get('oss_upload_id', data.get('ossUploadId'))
        oss_parts = data.get('oss_parts', data.get('ossParts'))
        file_id = data.get('file_id') or data.get('fileId')

        if is_direct_oss and oss_key and oss_upload_id:
            normalized_oss_parts = []
            for p in (oss_parts or []):
                if isinstance(p, dict):
                    normalized_oss_parts.append({
                        'PartNumber': int(p.get('PartNumber') or p.get('partNumber') or 0),
                        'ETag': p.get('ETag') or p.get('etag') or p.get('Etag') or '',
                    })
            if normalized_oss_parts:
                oss.complete_multipart_upload('raw_chunks', oss_key, oss_upload_id, normalized_oss_parts)
            ext = os.path.splitext(oss_key)[1].lower() or '.tmp'
            import tempfile as _tmp3
            final_path = _tmp3.NamedTemporaryFile(delete=False, suffix=ext).name
            storage.load_file(f'raw_chunks/{oss_key}', final_path)
            try:
                storage.delete(f'raw_chunks/{oss_key}')
            except Exception as e:
                logger.warning(f"清理 raw-chunks 失败: {e}")
        else:
            chunk_dir = os.path.join(chunk_base, file_id)
            if upload_file.relative_path:
                final_path = os.path.join(base_upload_dir, upload_file.relative_path)
                os.makedirs(os.path.dirname(final_path), exist_ok=True)
            else:
                safe_filename = _get_unique_filename(base_upload_dir, upload_file.filename)
                final_path = os.path.join(base_upload_dir, safe_filename)

            def perform_merge():
                os.makedirs(os.path.dirname(final_path), exist_ok=True)
                if os.path.exists(final_path):
                    _retry_file_operation(os.remove, final_path)
                with open(final_path, 'wb') as final_file:
                    for i in range(upload_file.total_chunks):
                        chunk_path = os.path.join(chunk_dir, f"chunk_{i}")
                        if os.path.exists(chunk_path):
                            with open(chunk_path, 'rb') as chunk_file:
                                final_file.write(chunk_file.read())

            _retry_file_operation(perform_merge)
            final_path = os.path.normpath(final_path)

        return final_path

    def _transcode_and_extract_metadata(self, final_path, upload_file, data):
        """转码为 WAV 并提取音频元数据"""
        wav_file_path = None
        oss_key = None
        meta_tmp_path = None

        try:
            orig_ext = os.path.splitext(final_path)[1].lower()
            if orig_ext == '.wav':
                wav_file_path = final_path
                wav_filename = os.path.basename(final_path)
                sample_rate, bits_per_sample = _read_wav_header(final_path)
            else:
                wav_file_path, wav_filename, sample_rate, bits_per_sample = _convert_to_wav(final_path)
                if os.path.exists(final_path) and final_path != wav_file_path:
                    _retry_file_operation(os.remove, final_path)

            if upload_file.relative_path:
                safe_path = upload_file.relative_path.replace('\\', '/').lstrip('/')
                safe_path = '/'.join(p for p in safe_path.split('/') if p and p != '..')
                stem = os.path.splitext(safe_path)[0]
                oss_key = f"direct/{stem}.wav"
            else:
                stem = os.path.splitext(upload_file.filename)[0]
                oss_key = f"direct/{stem}.wav"

            if storage.exists(f'audios/{oss_key}'):
                base, ext_part = os.path.splitext(oss_key)
                counter = 1
                while storage.exists(f'audios/{base}_{counter}{ext_part}'):
                    counter += 1
                oss_key = f"{base}_{counter}{ext_part}"

            final_path = storage.save_file(wav_file_path, 'audios', oss_key)
            if os.path.exists(wav_file_path):
                _retry_file_operation(os.remove, wav_file_path)

            upload_file.filename = wav_filename
            upload_file.original_filename = wav_filename
            self.repo.flush()

        except Exception as e:
            logger.warning(f"音频转换/上传OSS失败，将保留原始格式: {str(e)}")
            if wav_file_path and os.path.exists(wav_file_path):
                try:
                    os.remove(wav_file_path)
                except Exception:
                    logger.debug("清理WAV转换临时文件失败: %s", wav_file_path, exc_info=True)
            if oss_key:
                try:
                    storage.delete(f'audios/{oss_key}')
                except Exception:
                    logger.debug("音频转换失败后清理OSS文件失败: oss_key=%s", oss_key, exc_info=True)
            sample_rate = 44100
            bits_per_sample = 16

        meta_source_path = final_path
        if oss_key:
            import tempfile as _tmp
            meta_tmp_path = _tmp.NamedTemporaryFile(delete=False, suffix='.wav').name
            storage.load_file(f'audios/{oss_key}', meta_tmp_path)
            meta_source_path = meta_tmp_path

        file_size = os.path.getsize(meta_source_path)
        duration = 0.0
        sample_rate = 44100
        channels = 2
        bitrate = 128000

        try:
            from pydub import AudioSegment
            audio_seg = AudioSegment.from_file(meta_source_path)
            duration = len(audio_seg) / 1000.0
            sample_rate = audio_seg.frame_rate
            channels = audio_seg.channels
            bitrate = audio_seg.frame_width * 8 * sample_rate
            if duration <= 0:
                raise ValueError("音频时长为0，可能是无效的音频文件")
        except Exception as e:
            logger.info(f"音频元数据提取失败，使用默认值: {str(e)}")
        finally:
            if meta_tmp_path and os.path.exists(meta_tmp_path):
                try:
                    os.remove(meta_tmp_path)
                except Exception:
                    logger.debug("清理音频元数据临时文件失败: %s", meta_tmp_path, exc_info=True)

        return {
            'final_path': final_path,
            'file_size': file_size,
            'duration': duration,
            'sample_rate': sample_rate,
            'channels': channels,
            'bitrate': bitrate,
        }

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
        )

        if isinstance(tc_ids, list):
            tc_id = tc_ids[0] if tc_ids else None
            tc_count = len(tc_ids)
        else:
            tc_id = tc_ids
            tc_count = 1 if tc_ids else 0

        return {'tc_id': tc_id, 'tc_count': tc_count}

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
            file_progress = []
            for file in files:
                file_progress.append({
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
                })

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

            if relative_path:
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

            return {
                'success': True, 'message': 'URL 导入成功',
                'data': {'id': new_audio.id, 'name': new_audio.name},
                'code': 201,
            }
        except Exception as e:
            self.repo.rollback()
            return {'success': False, 'message': str(e), 'data': None, 'code': 400}

    def _save_audio(self, file, filename_prefix="", relative_path=""):
        """保存音频文件并提取元数据"""
        from audio_service.config.config import Config
        original_filename = file.filename
        base_upload_dir = getattr(Config, 'AUDIO_STORAGE_PATH',
                                  os.path.join(os.environ.get('LOCAL_STORAGE_ROOT', './storage'), 'audios'))
        temp_file_path = _generate_audio_storage_path(original_filename, base_upload_dir, filename_prefix, relative_path)
        _retry_file_operation(_persist_file_content, file, temp_file_path)
        return _create_audio_db_record(temp_file_path, original_filename, relative_path)


# 模块级实例
audio_upload_service = AudioUploadService()
