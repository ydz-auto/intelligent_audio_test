# -*- coding: utf-8 -*-
"""上传任务 Mixin（原 audio_upload_service.py 拆分产物，P4-5；P4-6 重组入 audio_upload 子包）。

职责：上传任务初始化、文件注册、分片上传、进度查询。
依赖 self.repo。
"""
import os
import uuid
import logging
from datetime import timedelta

from shared.utils.query_utils import now_cst
from shared.utils.log_handler import log_and_emit
from audio_service.domain.entities import UploadStatus
from audio_service.application.services.audio_file_utils import (
    _safe_makedirs,
)

logger = logging.getLogger(__name__)


class AudioUploadTaskMixin:
    """上传任务（依赖 self.repo）"""

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

    # ===== 查询 =====

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
