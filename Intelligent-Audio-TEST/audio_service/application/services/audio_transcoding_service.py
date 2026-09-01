# -*- coding: utf-8 -*-
"""音频转码服务

从 audio_upload_service.py 中提取的转码/OSS/文件路径相关逻辑：
- 文件名清理与去重（_sanitize_filename/_get_unique_filename）
- 文件内容持久化（_persist_file_content）
- 音频存储路径生成（_generate_audio_storage_path）
- 直传/分片合并的 OSS 分片归一化
- 转码为 WAV 并上传 OSS（transcode_and_extract_metadata）
- 直传 OSS 分片合并（merge_direct_oss_parts）
- 本地分片合并（merge_local_chunks）
"""
import os
import re
import uuid
import logging

from shared.infrastructure.storage import storage
from shared.clients.oss_client import oss
from audio_service.application.services.audio_file_utils import (
    _retry_file_operation,
    _read_wav_header,
    _convert_to_wav,
)
from audio_service.application.services.audio_metadata_service import audio_metadata_service

logger = logging.getLogger(__name__)


def _sanitize_filename(filename):
    """清理文件名，防止路径穿越，同时保留中文等非ASCII字符。

    与 werkzeug.secure_filename 不同，不会将中文替换为下划线。
    仅移除/替换路径穿越危险字符（.., /, \\, 空字符等）。
    """
    if not filename:
        return ''
    # 去掉路径分隔符和父目录引用，防止路径穿越
    # 先把 \\ 转为 / 统一处理
    cleaned = filename.replace('\\', '/').replace('\x00', '')
    # 取 basename，去掉任何目录部分
    cleaned = cleaned.split('/')[-1]
    # 把路径穿越用的点序列中危险的部分替换掉（如 .. 变为 _）
    # 但保留文件名中正常的点（扩展名分隔符）
    # 替换 Windows 不允许的字符: < > : " | ? *
    cleaned = re.sub(r'[<>:"|?*]', '_', cleaned)
    # 去掉开头/结尾的点和空格（Windows 下不允许）
    cleaned = cleaned.strip('. ')
    return cleaned


def _get_unique_filename(directory, original_filename):
    safe_filename = _sanitize_filename(original_filename)
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


def _normalize_oss_parts(parts):
    """归一化 OSS 分片列表，统一为 {PartNumber, ETag} 字典"""
    normalized = []
    for p in (parts or []):
        if isinstance(p, dict):
            normalized.append({
                'PartNumber': int(p.get('PartNumber') or p.get('partNumber') or 0),
                'ETag': p.get('ETag') or p.get('etag') or p.get('Etag') or '',
            })
    return normalized


class AudioTranscodingService:
    """音频转码服务：处理转码、OSS 上传、元数据提取"""

    def transcode_and_extract_metadata(self, final_path, upload_file):
        """转码为 WAV 并提取音频元数据

        :param final_path: 合并后的原始文件路径
        :param upload_file: UploadFile 记录（含 filename/relative_path）
        :return: dict，含 final_path/file_size/duration/sample_rate/channels/bitrate
        """
        wav_file_path = None
        oss_key = None

        try:
            wav_file_path, wav_filename, sample_rate, bits_per_sample = self._transcode_to_wav(
                final_path, upload_file
            )
            oss_key = self._build_oss_key(upload_file)
            oss_key = self._dedupe_oss_key(oss_key)
            final_path = storage.save_file(wav_file_path, 'audios', oss_key)
            if os.path.exists(wav_file_path):
                _retry_file_operation(os.remove, wav_file_path)
            # 更新文件名为WAV文件名（转换后存储用的文件名）
            # original_filename 保留注册时记录的原始上传名，不覆盖
            upload_file.filename = wav_filename
        except Exception as e:
            logger.warning(f"音频转换/上传OSS失败，将保留原始格式: {str(e)}")
            self._cleanup_transcode_failure(wav_file_path, oss_key)
            sample_rate = 44100
            bits_per_sample = 16

        meta_source_path, meta_tmp_path = self._prepare_meta_source(final_path, oss_key)
        meta = audio_metadata_service.extract_from_local_file(meta_source_path)
        self._cleanup_meta_tmp(meta_tmp_path)

        return {
            'final_path': final_path,
            'file_size': meta['file_size'],
            'duration': meta['duration'],
            'sample_rate': meta['sample_rate'],
            'channels': meta['channels'],
            'bitrate': meta['bitrate'],
        }

    def _transcode_to_wav(self, final_path, upload_file):
        """将音频转码为 WAV，返回 (wav_file_path, wav_filename, sample_rate, bits_per_sample)"""
        orig_ext = os.path.splitext(final_path)[1].lower()
        if orig_ext == '.wav':
            wav_file_path = final_path
            wav_filename = os.path.basename(final_path)
            sample_rate, bits_per_sample = _read_wav_header(final_path)
        else:
            wav_file_path, wav_filename, sample_rate, bits_per_sample = _convert_to_wav(final_path)
            if os.path.exists(final_path) and final_path != wav_file_path:
                _retry_file_operation(os.remove, final_path)
        return wav_file_path, wav_filename, sample_rate, bits_per_sample

    def _build_oss_key(self, upload_file):
        """根据 relative_path/filename 构建 OSS key"""
        if upload_file.relative_path:
            safe_path = upload_file.relative_path.replace('\\', '/').lstrip('/')
            safe_path = '/'.join(p for p in safe_path.split('/') if p and p != '..')
            stem = os.path.splitext(safe_path)[0]
        else:
            stem = os.path.splitext(upload_file.filename)[0]
        return f"direct/{stem}.wav"

    def _dedupe_oss_key(self, oss_key):
        """OSS key 去重，若已存在则追加序号"""
        if storage.exists(f'audios/{oss_key}'):
            base, ext_part = os.path.splitext(oss_key)
            counter = 1
            while storage.exists(f'audios/{base}_{counter}{ext_part}'):
                counter += 1
            oss_key = f"{base}_{counter}{ext_part}"
        return oss_key

    def _cleanup_transcode_failure(self, wav_file_path, oss_key):
        """转码失败后清理临时文件和 OSS 文件"""
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

    def _prepare_meta_source(self, final_path, oss_key):
        """准备元数据提取的源文件路径，返回 (meta_source_path, meta_tmp_path)"""
        if not oss_key:
            return final_path, None
        import tempfile as _tmp
        meta_tmp_path = _tmp.NamedTemporaryFile(delete=False, suffix='.wav').name
        storage.load_file(f'audios/{oss_key}', meta_tmp_path)
        return meta_tmp_path, meta_tmp_path

    def _cleanup_meta_tmp(self, meta_tmp_path):
        """清理元数据临时文件"""
        if meta_tmp_path and os.path.exists(meta_tmp_path):
            try:
                os.remove(meta_tmp_path)
            except Exception:
                logger.debug("清理音频元数据临时文件失败: %s", meta_tmp_path, exc_info=True)

    def create_record_from_file(self, temp_file_path, filename, relative_path=""):
        """转换音频为WAV，上传到OSS，提取元数据，返回音频记录数据

        用于 url_import 路径。与 transcode_and_extract_metadata 不同：
        失败时抛出 ValueError 而非使用默认值。
        """
        original_filename = filename
        try:
            wav_file_path, wav_filename, sample_rate, bits_per_sample = _convert_to_wav(temp_file_path)
            if os.path.exists(temp_file_path) and temp_file_path != wav_file_path:
                _retry_file_operation(os.remove, temp_file_path)
            oss_key = self._build_record_oss_key(relative_path, wav_filename)
            oss_key = self._dedupe_oss_key(oss_key)
            file_path = storage.save_file(wav_file_path, 'audios', oss_key)
            if os.path.exists(wav_file_path):
                _retry_file_operation(os.remove, wav_file_path)
            original_filename = wav_filename
        except Exception as e:
            if os.path.exists(temp_file_path):
                _retry_file_operation(os.remove, temp_file_path)
            raise ValueError(f"音频转换/上传OSS失败: {str(e)}")

        meta = self._extract_record_metadata(oss_key, sample_rate, bits_per_sample)
        return {
            'name': original_filename,
            'original_filename': original_filename,
            'file_path': file_path,
            'size': meta['file_size'],
            'duration': meta['duration'],
            'sample_rate': sample_rate,
            'channels': meta['channels'],
            'bitrate': meta['bitrate'],
            'format': 'wav',
        }

    def _build_record_oss_key(self, relative_path, wav_filename):
        """构建 url_import 路径的 OSS key"""
        if relative_path:
            safe_path = relative_path.replace('\\', '/').lstrip('/')
            safe_path = '/'.join(p for p in safe_path.split('/') if p and p != '..')
            return f"direct/{safe_path}"
        return f"direct/{wav_filename}"

    def _extract_record_metadata(self, oss_key, sample_rate, bits_per_sample):
        """从 OSS 下载并提取元数据（url_import 路径，失败抛异常并清理 OSS）"""
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
        return {'file_size': file_size, 'duration': duration, 'channels': channels, 'bitrate': bitrate}

    def merge_direct_oss_parts(self, oss_key, oss_upload_id, oss_parts):
        """完成 OSS 直传分片合并，返回临时文件路径"""
        normalized_oss_parts = _normalize_oss_parts(oss_parts)
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
        return final_path

    def merge_local_chunks(self, upload_file, base_upload_dir, chunk_base):
        """合并本地分片，返回 final_path"""
        file_id = upload_file.id
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
        return os.path.normpath(final_path)


# 模块级实例
audio_transcoding_service = AudioTranscodingService()
