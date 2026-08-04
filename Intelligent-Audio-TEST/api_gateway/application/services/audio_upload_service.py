import os
import uuid
import logging
from datetime import timedelta
from pydantic import ValidationError
from werkzeug.utils import secure_filename
from api_gateway.infrastructure.request_adapter import request
from api_gateway.config.config import Config
from shared.models.models import Audio, Tag, AudioAnnotation, AudioTag, UploadTask, UploadFile, UploadChunk
from shared.models.database import db
from shared.utils.response import success_response, error_response
from shared.utils.query_utils import now_cst
from shared.clients.oss_client import oss  # 仅用于 Multipart Upload 等 OSS 专有操作
from shared.infrastructure.storage import storage
from shared.algorithm.case_parameter_extractor import _normalize_algorithm_params_to_list
from api_gateway.schemas.audio import (
    CompleteDirectUploadRequest,
    InitUploadTaskRequest,
    MergeChunksRequest,
    PresignPartRequest,
    PresignUploadRequest,
    RegisterUploadFileRequest,
    URLImportRequest,
)
from pydub import AudioSegment
from api_gateway.application.services.audio_common import (
    retry_file_operation, safe_makedirs, safe_rmtree, _read_wav_header, convert_to_wav,
)
from api_gateway.application.services.audio_convert_service import AudioConvertService

logger = logging.getLogger(__name__)


class AudioUploadService:
    # 内部辅助方法：处理文件名冲突
    @staticmethod
    def _get_unique_filename(directory, original_filename):
        # 去除文件名中的特殊字符，保留基本字符和扩展名
        safe_filename = secure_filename(original_filename)
        if not safe_filename:
            # 如果文件名被完全清理为空，使用默认名
            safe_filename = f"audio_{uuid.uuid4().hex[:8]}"

        # 检查文件是否已存在，如果存在则添加数字后缀
        base_name, ext = os.path.splitext(safe_filename)
        counter = 1
        unique_filename = safe_filename

        while os.path.exists(os.path.join(directory, unique_filename)):
            unique_filename = f"{base_name}_{counter}{ext}"
            counter += 1

        return unique_filename

    # 内部辅助方法：保存音频文件并提取元数据
    @staticmethod
    def _save_audio(file, filename_prefix="", relative_path=""):
        original_filename = file.filename

        # 确定基础上传目录 - 使用配置文件中的 AUDIO_STORAGE_PATH
        base_upload_dir = Config.AUDIO_STORAGE_PATH

        # 确定最终的文件路径（先保存为临时文件，后续会转换为WAV）
        if relative_path:
            # 有相对路径，保持原文件结构
            temp_file_path = os.path.join(base_upload_dir, relative_path)

            # 确保目录存在（创建所有必要的父目录）
            os.makedirs(os.path.dirname(temp_file_path), exist_ok=True)

            # 检查文件是否已存在，如果存在则添加数字后缀
            if os.path.exists(temp_file_path):
                base_name, ext = os.path.splitext(temp_file_path)
                counter = 1
                while os.path.exists(temp_file_path):
                    temp_file_path = f"{base_name}_{counter}{ext}"
                    counter += 1
        else:
            # 没有相对路径，直接保存在基础目录
            # 处理带前缀的文件名
            if filename_prefix:
                prefixed_filename = f"{filename_prefix}{original_filename}"
            else:
                prefixed_filename = original_filename

            # 确保基础目录存在
            if not os.path.exists(base_upload_dir):
                os.makedirs(base_upload_dir, exist_ok=True)

            # 使用唯一文件名（临时文件）
            safe_filename = AudioUploadService._get_unique_filename(base_upload_dir, prefixed_filename)
            temp_file_path = os.path.join(base_upload_dir, safe_filename)

        # 先保存原始文件
        retry_file_operation(file.save, temp_file_path)

        try:
            # 转换为WAV格式（生成临时 WAV 文件，返回临时路径）
            wav_file_path, wav_filename, sample_rate, bits_per_sample = convert_to_wav(temp_file_path)

            # 删除原始临时文件
            if os.path.exists(temp_file_path) and temp_file_path != wav_file_path:
                retry_file_operation(os.remove, temp_file_path)

            # 上传规整后的 WAV 到 OSS（audios bucket），DB 记录 OSS key 而非本地路径
            # 保留用户本地目录结构
            if relative_path:
                safe_path = relative_path.replace('\\', '/').lstrip('/')
                safe_path = '/'.join(p for p in safe_path.split('/') if p and p != '..')
                oss_key = f"direct/{safe_path}"
            else:
                oss_key = f"direct/{wav_filename}"
            # 同名去重
            if storage.exists(f'audios/{oss_key}'):
                base, ext_part = os.path.splitext(oss_key)
                counter = 1
                while storage.exists(f'audios/{base}_{counter}{ext_part}'):
                    counter += 1
                oss_key = f"{base}_{counter}{ext_part}"
            file_path = storage.save_file(wav_file_path, 'audios', oss_key)
            # 上传完成后删除本地临时 WAV
            if os.path.exists(wav_file_path):
                retry_file_operation(os.remove, wav_file_path)

            # DB 记录存储路径（复用 file_path 字段，带 scheme 前缀）
            # file_path 已由 save_file 返回带前缀的路径
            # 更新文件名为WAV文件名
            original_filename = wav_filename

        except Exception as e:
            # 如果转换/上传失败，删除临时文件并抛出异常
            if os.path.exists(temp_file_path):
                retry_file_operation(os.remove, temp_file_path)
            if 'wav_file_path' in dir() and os.path.exists(wav_file_path):
                retry_file_operation(os.remove, wav_file_path)
            raise ValueError(f"音频转换/上传OSS失败: {str(e)}")

        # 提取WAV文件元数据（从存储下载到临时后解析，避免依赖本地持久文件）
        # 先下载到临时用于元数据提取，提取后删除
        meta_tmp_path = None
        try:
            import tempfile
            meta_tmp_path = tempfile.NamedTemporaryFile(delete=False, suffix='.wav').name
            storage.load_file(f'audios/{oss_key}', meta_tmp_path)
            file_size = os.path.getsize(meta_tmp_path)
            audio_seg = AudioSegment.from_file(meta_tmp_path)
            duration = len(audio_seg) / 1000.0
            channels = audio_seg.channels
            # 使用实际的位深计算比特率
            bitrate = bits_per_sample * sample_rate * channels

            # 严格校验：如果时长为0，通常意味着不是有效的音频文件
            if duration <= 0:
                raise ValueError("音频时长为0，可能是无效的音频文件")

        except Exception as e:
            # 如果元数据提取失败，说明不是有效的音频文件
            # 删除已上传到存储的对象，避免残留无效数据
            try:
                storage.delete(f'audios/{oss_key}')
            except Exception:
                pass
            raise ValueError(f"无法识别的音频格式或文件已损坏: {str(e)}")
        finally:
            if meta_tmp_path and os.path.exists(meta_tmp_path):
                try:
                    os.remove(meta_tmp_path)
                except Exception:
                    pass

        return {
            "name": original_filename,
            "original_filename": original_filename,
            "file_path": file_path,
            "size": file_size,
            "duration": duration,
            "sample_rate": sample_rate,
            "channels": channels,
            "bitrate": bitrate,
            "format": "wav"
        }

    # 内部辅助方法：初始化上传目录
    @staticmethod
    def _init_upload_dirs():
        """
        初始化上传相关目录
        """
        base_upload_dir = Config.AUDIO_STORAGE_PATH
        chunk_dir = os.path.join(base_upload_dir, 'chunks')
        temp_dir = os.path.join(base_upload_dir, 'temp')

        # 确保目录存在
        for dir_path in [base_upload_dir, chunk_dir, temp_dir]:
            safe_makedirs(dir_path)

        return {
            'base': base_upload_dir,
            'chunk': chunk_dir,
            'temp': temp_dir
        }

    # ========== 前端直传 OSS 接口 ==========

    @staticmethod
    def presign_upload():
        """生成 S3 Multipart Upload 初始化信息和第一批分片预签名 URL

        前端调用此接口获取 upload_id 和分片预签名 URL，直接 PUT 分片到 OSS。
        - WAV 文件：直传 audios bucket（最终文件，无需后端转码）
        - 非 WAV 文件：直传 raw-chunks bucket（临时，后端 merge 时拉取转码）
        """
        try:
            data = request.get_json() or {}
            try:
                validated = PresignUploadRequest.model_validate(data)
            except ValidationError as e:
                return error_response(f"参数验证失败: {e}")

            # 秒传判断：MD5 命中直接返回
            if validated.md5:
                existing = Audio.query.filter_by(md5=validated.md5, deleted=False).first()
                if existing:
                    return success_response({
                        "instantUpload": True,
                        "audioId": existing.id,
                        "name": existing.name,
                    }, "秒传成功")

            # 生成 OSS key：保留用户本地目录结构
            ext = os.path.splitext(validated.filename)[1].lower()
            # WAV 直传 audios，非 WAV 传 raw-chunks
            category = 'audios' if validated.is_wav else 'raw_chunks'
            if validated.relative_path:
                # 浏览器 webkitRelativePath，如 "test_data/noise/sample.wav"
                # OSS key: "direct/test_data/noise/sample.wav"
                # 清理路径，防止 ../ 和 绝对路径注入
                safe_path = validated.relative_path.replace('\\', '/').lstrip('/')
                safe_path = '/'.join(p for p in safe_path.split('/') if p and p != '..')
                oss_key = f"direct/{safe_path}"
            else:
                # 没有目录信息（单文件上传），用原始文件名
                oss_key = f"direct/{validated.filename}"

            # 同名去重：如果 key 已存在，加序号后缀（如 sample_1.wav, sample_2.wav）
            if storage.exists(f'{category}/{oss_key}'):
                base, ext_part = os.path.splitext(oss_key)
                counter = 1
                while storage.exists(f'{category}/{base}_{counter}{ext_part}'):
                    counter += 1
                oss_key = f"{base}_{counter}{ext_part}"

            # 初始化 S3 Multipart Upload
            upload_id = oss.create_multipart_upload(category, oss_key)

            # 计算分片数
            chunk_size = validated.chunk_size or (5 * 1024 * 1024)
            total_parts = max(1, (validated.file_size + chunk_size - 1) // chunk_size)

            # 生成前几个分片的预签名 URL（前端按需请求更多）
            # 一次性生成最多 100 个分片 URL（覆盖 500MB 以内文件）
            parts_to_presign = min(total_parts, 100)
            presigned_parts = []
            for part_num in range(1, parts_to_presign + 1):
                url = oss.get_part_upload_presigned_url(
                    category, oss_key, upload_id, part_num, expires=3600
                )
                presigned_parts.append({
                    "partNumber": part_num,
                    "url": url,
                })

            return success_response({
                "uploadId": upload_id,
                "ossKey": oss_key,
                "category": category,
                "chunkSize": chunk_size,
                "totalParts": total_parts,
                "parts": presigned_parts,
                "presignedRemaining": total_parts > parts_to_presign,
            }, "预签名 URL 生成成功")

        except Exception as e:
            logger.error(f"presign_upload failed: {e}", exc_info=True)
            return error_response(str(e))

    @staticmethod
    def presign_part():
        """请求更多分片的预签名 URL（大文件场景，超过初始 100 个分片）"""
        try:
            data = request.get_json() or {}
            try:
                validated = PresignPartRequest.model_validate(data)
            except ValidationError as e:
                return error_response(f"参数验证失败: {e}")

            # 从 query params 获取 oss_key 和 category
            oss_key = request.args.get('oss_key')
            category = request.args.get('category', 'raw_chunks')
            if not oss_key:
                return error_response("缺少 oss_key 参数")

            url = oss.get_part_upload_presigned_url(
                category, oss_key, validated.upload_id, validated.part_number, expires=3600
            )
            return success_response({
                "partNumber": validated.part_number,
                "url": url,
            })
        except Exception as e:
            logger.error(f"presign_part failed: {e}", exc_info=True)
            return error_response(str(e))

    @staticmethod
    def complete_direct_upload():
        """WAV 文件直传 OSS 完成后，合并分片 + 登记 DB

        前端直传 WAV 到 audios bucket 后调用此接口：
        1. 调 OSS CompleteMultipartUpload 合并分片
        2. 从 OSS 下载到临时文件提取元数据（采样率/位深/时长）
        3. 创建 Audio 记录
        4. 可选创建 TestCase
        """
        temp_file = None
        try:
            data = request.get_json() or {}
            try:
                validated = CompleteDirectUploadRequest.model_validate(data)
            except ValidationError as e:
                return error_response(f"参数验证失败: {e}")

            # 1. 完成 OSS 端分片合并
            # 归一化 parts 字段：前端传 partNumber/etag（驼峰），boto3 要 PartNumber/ETag
            normalized_parts = []
            for p in (validated.parts or []):
                if isinstance(p, dict):
                    normalized_parts.append({
                        'PartNumber': int(p.get('PartNumber') or p.get('partNumber') or 0),
                        'ETag': p.get('ETag') or p.get('etag') or p.get('Etag') or '',
                    })
            if validated.upload_id and normalized_parts:
                oss.complete_multipart_upload(
                    'audios', validated.oss_key, validated.upload_id, normalized_parts
                )

            # 2. 下载到临时文件提取元数据
            import tempfile as _tmp2
            temp_file = _tmp2.NamedTemporaryFile(delete=False, suffix='.wav').name
            storage.load_file(f'audios/{validated.oss_key}', temp_file)
            file_size = os.path.getsize(temp_file)

            # 从 WAV 头读采样率/位深
            try:
                sample_rate, bits_per_sample = _read_wav_header(temp_file)
            except Exception:
                sample_rate = validated.sample_rate or 44100
                bits_per_sample = validated.bits_per_sample or 16

            # 提取时长（不依赖 ffmpeg）
            try:
                import wave
                with wave.open(temp_file, 'rb') as wf:
                    duration = wf.getnframes() / wf.getframerate() if wf.getframerate() else 0.0
            except Exception:
                duration = validated.duration or 0.0

            # 3. 创建 Audio 记录
            audio = Audio(
                name=validated.filename,
                original_filename=validated.filename,
                file_path=validated.oss_key,  # OSS key
                format='wav',
                size=file_size,
                duration=duration,
                sample_rate=sample_rate,
                md5=validated.md5,
                audio_type=validated.audio_type or 'dry',
                asr_text=validated.asr_text or '',
                deleted=False,
            )
            db.session.add(audio)
            db.session.commit()

            # 4. 处理标签
            if validated.tags:
                for tag_name in validated.tags:
                    tag = Tag.query.filter_by(name=tag_name).first()
                    if not tag:
                        tag = Tag(name=tag_name)
                        db.session.add(tag)
                        db.session.flush()
                    db.session.add(AudioTag(audio_id=audio.id, tag_id=tag.id))
                db.session.commit()

            return success_response({
                "audio_id": audio.id,
                "name": audio.name,
                "oss_key": validated.oss_key,
                "size": file_size,
                "duration": duration,
                "sample_rate": sample_rate,
                "bits_per_sample": bits_per_sample,
            }, "直传完成")

        except Exception as e:
            db.session.rollback()
            logger.error(f"complete_direct_upload failed: {e}", exc_info=True)
            return error_response(str(e))
        finally:
            # 清理临时文件
            if temp_file and os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                except Exception:
                    pass

    # 初始化上传任务
    @staticmethod
    def init_upload_task():
        try:
            data = request.get_json() or {}
            try:
                validated = InitUploadTaskRequest.model_validate(data)
            except ValidationError as e:
                return error_response(f"参数验证失败: {e}")

            # 初始化上传目录
            AudioUploadService._init_upload_dirs()

            # 生成任务ID
            task_id = str(uuid.uuid4())

            # 创建上传任务
            task = UploadTask(
                id=task_id,
                total_files=0,
                completed_files=0,
                failed_files=0,
                total_size=0,
                uploaded_size=0,
                status='preparing',
                # 7天后过期
                expired_at=now_cst() + timedelta(days=7)
            )
            db.session.add(task)
            db.session.commit()

            return success_response({
                "task_id": task_id,
                "message": "任务初始化成功"
            })
        except Exception as e:
            import traceback
            from shared.utils.log_handler import log_and_emit
            log_and_emit(
                level='error',
                module='audio_controller',
                content=f'音频入库失败: {str(e)}',
                category='audio',
                source='backend'
            )
            db.session.rollback()
            return error_response(str(e))

    # 注册上传文件
    @staticmethod
    def register_upload_file():
        try:
            data = request.get_json() or {}
            try:
                validated = RegisterUploadFileRequest.model_validate(data)
            except ValidationError as e:
                return error_response(f"参数验证失败: {e}")

            task_id = validated.task_id
            files = validated.files

            if not task_id:
                return error_response("缺少任务ID", code=400)

            # 验证任务存在
            task = db.session.get(UploadTask, task_id)
            if not task:
                return error_response(f"任务不存在: {task_id}", code=404)

            if not files:
                return error_response("缺少文件信息", code=400)

            # 初始化上传目录
            dirs = AudioUploadService._init_upload_dirs()

            # 注册文件
            registered_files = []
            # 使用 no_autoflush 批量处理，减少中间 flush 导致的锁定
            with db.session.no_autoflush:
                for file_info in files:
                    file_name = file_info.get('name', '')
                    file_size = file_info.get('size', 0)
                    md5 = file_info.get('md5', '')
                    relative_path = file_info.get('relative_path', '')

                    if not file_name:
                        continue

                    # 检查MD5是否已存在
                    status = 'pending'
                    file_id = str(uuid.uuid4())

                    # 计算总分片数 (10MB/片)
                    chunk_size = 10 * 1024 * 1024  # 10MB
                    total_chunks = max(1, (file_size + chunk_size - 1) // chunk_size)

                    if md5:
                        try:
                            existing_audio = Audio.query.filter_by(md5=md5, deleted=False).first()
                            if existing_audio:
                                # 如果已存在，标记为已完成，无需上传
                                status = 'completed'
                                total_chunks = 0
                        except Exception as e:
                            logger.warning(f"MD5查询失败: {str(e)}")

                    # 创建上传文件记录
                    upload_file = UploadFile(
                        id=file_id,
                        task_id=task_id,
                        filename=file_name,
                        original_filename=file_name,
                        relative_path=relative_path,
                        size=file_size,
                        md5=md5,
                        status=status,
                        uploaded_size=file_size if status == 'completed' else 0,
                        completed_chunks=total_chunks if status == 'completed' else 0,
                        total_chunks=total_chunks
                    )
                    db.session.add(upload_file)

                    registered_files.append({
                        "file_id": file_id,
                        "filename": file_name,
                        "total_chunks": total_chunks,
                        "chunk_size": chunk_size,
                        "status": status
                    })

                    # 更新任务统计
                    task.total_files += 1
                    task.total_size += file_size
                    if status == 'completed':
                        task.completed_files += 1
                        task.uploaded_size += file_size

                # 检查任务状态
                if task.completed_files >= task.total_files and task.total_files > 0:
                    task.status = 'completed'
                else:
                    task.status = 'uploading'

            db.session.commit()

            return success_response({
                "task_id": task_id,
                "files": registered_files,
                "message": f"成功注册 {len(registered_files)} 个文件"
            })
        except Exception as e:
            db.session.rollback()
            import traceback
            from shared.utils.log_handler import log_and_emit
            log_and_emit(
                level='error',
                module='audio_controller',
                content=f'音频注册失败: {str(e)}\n{traceback.format_exc()}',
                category='audio',
                source='backend'
            )
            return error_response(f"音频注册失败: {str(e)}")

    # 上传分片
    @staticmethod
    def upload_chunk():
        try:
            # 获取分片信息
            file_id = request.form.get('file_id')
            chunk_index = request.form.get('chunk_index', type=int)
            total_chunks = request.form.get('total_chunks', type=int)
            task_id = request.form.get('task_id')

            if not file_id or chunk_index is None or not total_chunks or not task_id:
                return error_response("缺少分片信息")

            # 验证文件存在
            upload_file = db.session.get(UploadFile, file_id)
            if not upload_file:
                return error_response("文件不存在")

            # 验证任务存在
            task = db.session.get(UploadTask, task_id)
            if not task:
                return error_response("任务不存在")

            # 检查文件
            if 'chunk' not in request.files:
                return error_response("缺少分片文件")

            chunk_file = request.files['chunk']

            # 初始化上传目录
            dirs = AudioUploadService._init_upload_dirs()

            # 生成分片存储路径
            chunk_dir = os.path.join(dirs['chunk'], file_id)
            safe_makedirs(chunk_dir)

            chunk_path = os.path.join(chunk_dir, f"chunk_{chunk_index}")

            # 保存分片
            retry_file_operation(chunk_file.save, chunk_path)

            # 更新分片状态
            chunk_size = os.path.getsize(chunk_path)

            # 使用 no_autoflush 避免在更新过程中触发不必要的查询
            with db.session.no_autoflush:
                # 检查是否已存在该分片
                existing_chunk = UploadChunk.query.filter_by(
                    file_id=file_id,
                    chunk_index=chunk_index
                ).first()

                if existing_chunk:
                    # 更新现有分片
                    existing_chunk.chunk_size = chunk_size
                    existing_chunk.status = 'completed'
                    existing_chunk.updated_at = now_cst()
                else:
                    # 创建新分片记录
                    new_chunk = UploadChunk(
                        file_id=file_id,
                        chunk_index=chunk_index,
                        chunk_size=chunk_size,
                        stored_path=chunk_path,
                        status='completed'
                    )
                    db.session.add(new_chunk)

                # 更新文件上传进度
                upload_file.completed_chunks += 1
                upload_file.uploaded_size += chunk_size

                # 如果所有分片都已上传，更新文件状态
                if upload_file.completed_chunks >= total_chunks:
                    upload_file.status = 'completed'
                    task.completed_files += 1

                # 更新任务进度
                task.uploaded_size += chunk_size
                task.status = 'uploading'

                # 检查是否所有文件都已上传
                if task.completed_files >= task.total_files:
                    task.status = 'completed'

            db.session.commit()

            return success_response({
                "file_id": file_id,
                "chunk_index": chunk_index,
                "completed_chunks": upload_file.completed_chunks,
                "total_chunks": total_chunks,
                "uploaded_size": upload_file.uploaded_size,
                "file_size": upload_file.size,
                "task_progress": {
                    "uploaded_size": task.uploaded_size,
                    "total_size": task.total_size,
                    "completed_files": task.completed_files,
                    "total_files": task.total_files,
                    "status": task.status
                }
            }, "分片上传成功")
        except Exception as e:
            import traceback
            from shared.utils.log_handler import log_and_emit
            log_and_emit(
                level='error',
                module='audio_controller',
                content=f'分片上传失败: {str(e)}',
                category='audio',
                source='backend'
            )
            db.session.rollback()
            return error_response(str(e))

    # 合并分片
    @staticmethod
    def merge_chunks():
        try:
            data = request.get_json() or {}
            try:
                validated = MergeChunksRequest.model_validate(data)
            except ValidationError as e:
                return error_response(f"参数验证失败: {e}")

            file_id = validated.file_id
            task_id = validated.task_id

            if not file_id or not task_id:
                return error_response("缺少文件或任务ID")

            create_test_case = validated.create_test_case
            test_types = validated.test_types
            dimensions_data = validated.dimensions
            default_playback_device_id = validated.default_playback_device_id
            default_spl = validated.default_spl
            noise_spl = validated.noise_spl
            noise_audio_id = validated.noise_audio_id
            test_case_group_name = validated.test_case_group_name
            algorithm_type = validated.algorithm_type
            algorithm_params = validated.algorithm_params
            algorithm_params_dict = validated.get_algorithm_params_dict()
            description = validated.description
            user_tags = validated.tags

            prompt_device_id = validated.prompt_device_id
            prompt_source_language = validated.prompt_source_language
            prompt_target_language = validated.prompt_target_language
            prompt_algorithm_type = validated.prompt_algorithm_type

            # 多轮上传配置
            tc_config = validated.test_case_config
            # rounds 经 pydantic RoundConfigItem 归一化 key 后转回 dict，
            # 保证后端代码拿到的 rounds 是蛇形 key 的 dict 列表
            rounds_config = None
            if tc_config and tc_config.rounds:
                rounds_config = [
                    r.model_dump(exclude_none=True, by_alias=False)
                    for r in tc_config.rounds
                ]
            tc_group_name = tc_config.group_name if tc_config else None
            tc_inherit_tags = tc_config.inherit_tags if tc_config is not None else True
            # test_case_config 优先级高于顶层 test_case_group_name / inherit_tags
            if tc_group_name:
                test_case_group_name = tc_group_name
            # 如果 tc_config 有 algorithm_params 且顶层没有，则用 tc_config 的
            if tc_config and tc_config.algorithm_params and not algorithm_params_dict:
                algorithm_params_dict = _normalize_algorithm_params_to_list(tc_config.algorithm_params)
            # 如果 tc_config 有 dimensions 且顶层没有，则用 tc_config 的
            if tc_config and tc_config.dimensions and not dimensions_data:
                dimensions_data = tc_config.dimensions

            # 验证文件存在
            upload_file = db.session.get(UploadFile, file_id)
            if not upload_file:
                return error_response("文件不存在")

            # 验证任务存在
            task = db.session.get(UploadTask, task_id)
            if not task:
                return error_response("任务不存在")

            # 初始化上传目录
            dirs = AudioUploadService._init_upload_dirs()

            # 检查是否是秒传文件（total_chunks = 0 且状态为 completed）
            is_instant_upload = upload_file.total_chunks == 0 and upload_file.status == 'completed'

            # WAV 直传场景：complete-direct 已把音频入库，但 UploadFile 分片状态未更新。
            # 若 md5 已对应 Audio 记录，则视为已入库，跳过分片检查。
            if not is_instant_upload and upload_file.md5:
                existing_audio_check = Audio.query.filter_by(md5=upload_file.md5, deleted=False).first()
                if existing_audio_check:
                    is_instant_upload = True

            if not is_instant_upload:
                # 普通上传：检查所有分片是否已上传
                if upload_file.completed_chunks < upload_file.total_chunks:
                    return error_response("还有分片未上传完成")

            # 秒传场景：直接获取已有音频信息
            existing_audio_id = None
            audio_tags = []
            if is_instant_upload and upload_file.md5:
                existing_audio = Audio.query.filter_by(md5=upload_file.md5, deleted=False).first()
                if existing_audio:
                    existing_audio_id = existing_audio.id

                    # 获取已有音频的标签
                    audio_tags = []
                    audio_tags_relations = AudioTag.query.filter_by(audio_id=existing_audio.id).all()
                    for at in audio_tags_relations:
                        if at and at.tag_id:
                            tag = db.session.get(Tag, at.tag_id)
                            if tag:
                                audio_tags.append(tag.name)

                    # 如果是秒传且需要创建测试用例
                    if create_test_case:
                        # 秒传场景也要持久化标注（同 code 覆盖旧记录），并构造 raw_annotations 供用例参数提取
                        raw_annotations_data = AudioConvertService._persist_annotations_and_raw(
                            existing_audio.id,
                            validated.annotations,
                            algorithm_type,
                        )
                        tc_ids = AudioConvertService._create_test_case_from_audio(
                            existing_audio.id,
                            test_types,
                            audio_tags,
                            default_playback_device_id,
                            default_spl,
                            noise_spl,
                            noise_audio_id,
                            test_case_group_name,
                            dimensions_data,
                            algorithm_type,
                            algorithm_params_dict,
                            rounds_config=rounds_config,
                            inherit_tags=tc_inherit_tags,
                            raw_annotations=raw_annotations_data,
                        )

                        # 提交测试用例创建
                        db.session.commit()

                        return success_response({
                            "file_id": file_id,
                            "audio_id": existing_audio.id,
                            "name": existing_audio.name,
                            "status": "completed",
                            "test_case_id": tc_ids[0] if tc_ids else None,
                            "test_case_count": len(tc_ids) if isinstance(tc_ids, list) else (1 if tc_ids else 0),
                            "instant_upload": True
                        }, "秒传成功，测试用例已创建")
                    else:
                        # 秒传但不需要创建测试用例，也要持久化标注（同 code 覆盖旧记录）
                        AudioConvertService._persist_annotations_and_raw(
                            existing_audio.id,
                            validated.annotations,
                            algorithm_type,
                        )
                        db.session.commit()
                        return success_response({
                            "file_id": file_id,
                            "audio_id": existing_audio.id,
                            "name": existing_audio.name,
                            "status": "completed",
                            "instant_upload": True
                        }, "秒传成功")

            # 以下是普通合并流程（非秒传）
            # OSS 直传模式：前端已分片直传 OSS，后端从 OSS 拉取合并转码
            if validated.is_direct_oss and validated.oss_key and validated.oss_upload_id:
                # 完成 OSS 端分片合并（raw-chunks bucket）
                # 归一化 parts 字段：前端传 partNumber/etag（驼峰），boto3 要 PartNumber/ETag
                normalized_oss_parts = []
                for p in (validated.oss_parts or []):
                    if isinstance(p, dict):
                        normalized_oss_parts.append({
                            'PartNumber': int(p.get('PartNumber') or p.get('partNumber') or 0),
                            'ETag': p.get('ETag') or p.get('etag') or p.get('Etag') or '',
                        })
                if normalized_oss_parts:
                    oss.complete_multipart_upload(
                        'raw_chunks', validated.oss_key,
                        validated.oss_upload_id, normalized_oss_parts
                    )
                # 从存储下载到本地临时文件（用于转码）
                dirs = AudioUploadService._init_upload_dirs()
                ext = os.path.splitext(validated.oss_key)[1].lower() or '.tmp'
                import tempfile as _tmp3
                final_path = _tmp3.NamedTemporaryFile(delete=False, suffix=ext).name
                storage.load_file(f'raw_chunks/{validated.oss_key}', final_path)
                # 下载后清理 raw-chunks 中的源文件
                try:
                    storage.delete(f'raw_chunks/{validated.oss_key}')
                except Exception as e:
                    logger.warning(f"清理 raw-chunks 失败: {e}")
            else:
                # 本地分片模式（兼容旧前端）
                chunk_dir = os.path.join(dirs['chunk'], file_id)
                # 生成最终文件路径
                if upload_file.relative_path:
                    final_path = os.path.join(dirs['base'], upload_file.relative_path)
                    os.makedirs(os.path.dirname(final_path), exist_ok=True)
                else:
                    safe_filename = AudioUploadService._get_unique_filename(dirs['base'], upload_file.filename)
                    final_path = os.path.join(dirs['base'], safe_filename)

                # 合并所有分片
                def perform_merge():
                    os.makedirs(os.path.dirname(final_path), exist_ok=True)
                    if os.path.exists(final_path):
                        retry_file_operation(os.remove, final_path)
                    with open(final_path, 'wb') as final_file:
                        for i in range(upload_file.total_chunks):
                            chunk_path = os.path.join(chunk_dir, f"chunk_{i}")
                            if os.path.exists(chunk_path):
                                with open(chunk_path, 'rb') as chunk_file:
                                    final_file.write(chunk_file.read())

                retry_file_operation(perform_merge)
                final_path = os.path.normpath(final_path)

            # 转换为WAV格式（已是 WAV 的跳过转码，直接上传 OSS）
            wav_file_path = None
            oss_key = None
            meta_tmp_path = None
            try:
                # 判断原始文件是否已经是 WAV
                orig_ext = os.path.splitext(final_path)[1].lower()
                if orig_ext == '.wav':
                    # WAV 文件无需转码，直接用原文件
                    wav_file_path = final_path
                    wav_filename = os.path.basename(final_path)
                    # 从 WAV 头读取采样率/位深（不依赖 ffmpeg）
                    sample_rate, bits_per_sample = _read_wav_header(final_path)
                else:
                    # 非 WAV 需要转码
                    wav_file_path, wav_filename, sample_rate, bits_per_sample = convert_to_wav(final_path)
                    # 删除原始合并文件
                    if os.path.exists(final_path) and final_path != wav_file_path:
                        retry_file_operation(os.remove, final_path)

                # 上传规整后的 WAV 到 OSS（audios bucket），DB 记录 OSS key
                # 保留用户本地目录结构：从 upload_file.relative_path 或原始 oss_key 推导
                if upload_file.relative_path:
                    safe_path = upload_file.relative_path.replace('\\', '/').lstrip('/')
                    safe_path = '/'.join(p for p in safe_path.split('/') if p and p != '..')
                    # 把扩展名换成 .wav（转码后的格式）
                    stem = os.path.splitext(safe_path)[0]
                    oss_key = f"direct/{stem}.wav"
                else:
                    stem = os.path.splitext(upload_file.filename)[0]
                    oss_key = f"direct/{stem}.wav"
                # 同名去重
                if storage.exists(f'audios/{oss_key}'):
                    base, ext_part = os.path.splitext(oss_key)
                    counter = 1
                    while storage.exists(f'audios/{base}_{counter}{ext_part}'):
                        counter += 1
                    oss_key = f"{base}_{counter}{ext_part}"
                final_path = storage.save_file(wav_file_path, 'audios', oss_key)
                # 上传完成后删除本地临时 WAV
                if os.path.exists(wav_file_path):
                    retry_file_operation(os.remove, wav_file_path)

                # DB 记录存储路径（复用 file_path 字段，带 scheme 前缀）
                # final_path 已由 save_file 返回带前缀的路径
                # 更新文件名为WAV文件名
                upload_file.filename = wav_filename
                upload_file.original_filename = wav_filename

            except Exception as e:
                # 如果转换/上传失败，保留原始文件但标记格式
                logger.warning(f"音频转换/上传OSS失败，将保留原始格式: {str(e)}")
                # 清理可能残留的临时文件
                if wav_file_path and os.path.exists(wav_file_path):
                    try:
                        os.remove(wav_file_path)
                    except Exception:
                        pass
                if oss_key:
                    try:
                        storage.delete(f'audios/{oss_key}')
                    except Exception:
                        pass
                sample_rate = 44100
                bits_per_sample = 16

            # 提取音频元数据：若已上传存储，从存储下载到临时提取；否则用本地 final_path
            meta_source_path = final_path
            if oss_key:
                import tempfile as _tmp
                meta_tmp_path = _tmp.NamedTemporaryFile(delete=False, suffix='.wav').name
                storage.load_file(f'audios/{oss_key}', meta_tmp_path)
                meta_source_path = meta_tmp_path
            file_size = os.path.getsize(meta_source_path)

            # 初始化元数据默认值（不依赖ffmpeg）
            duration = 0.0
            sample_rate = 44100  # 默认采样率
            channels = 2  # 默认双声道
            bitrate = 128000  # 默认比特率

            # 尝试提取详细元数据，但不依赖ffmpeg可用性
            try:
                # 尝试提取详细元数据
                audio_seg = AudioSegment.from_file(meta_source_path)
                duration = len(audio_seg) / 1000.0
                sample_rate = audio_seg.frame_rate
                channels = audio_seg.channels
                bitrate = audio_seg.frame_width * 8 * sample_rate  # 估算比特率

                # 严格校验：如果时长为0，通常意味着不是有效的音频文件
                if duration <= 0:
                    raise ValueError("音频时长为0，可能是无效的音频文件")

            except Exception as e:
                # ffmpeg不可用或元数据提取失败，使用默认值继续
                logger.info(f"音频元数据提取失败，使用默认值: {str(e)}")
            finally:
                # 清理用于元数据提取的临时文件（若从 OSS 下载的）
                if meta_tmp_path and os.path.exists(meta_tmp_path):
                    try:
                        os.remove(meta_tmp_path)
                    except Exception:
                        pass

            # 获取源语言（从算法参数中提取）
            source_language = AudioConvertService._get_source_language_from_algorithm_params(algorithm_params)

            # 获取ASR文本
            asr_text = validated.asr_text

            # 保存到音频数据库
            audio_meta = {
                "name": upload_file.filename,
                "original_filename": upload_file.original_filename,
                "file_path": final_path,
                "size": file_size,
                "duration": duration,
                "sample_rate": sample_rate,
                "channels": channels,
                "bitrate": bitrate,
                "format": "wav",
                "audio_type": validated.audio_type,
                "md5": upload_file.md5,
                "source_language": source_language,
                "asr_text": asr_text,
                "description": description
            }

            # 开启 no_autoflush 避免在多表操作中频繁触发 session flush
            with db.session.no_autoflush:
                new_audio = Audio(**audio_meta)
                db.session.add(new_audio)
                db.session.flush()  # 获取音频ID用于后续关联

                # 处理标签 (目录结构 + 用户自定义)
                audio_tags = []

                # 1. 用户自定义标签
                all_tag_names = list(user_tags)

                # 2. 目录结构作为标签
                relative_path = upload_file.relative_path
                if relative_path:
                    # 提取目录结构作为标签
                    path_parts = relative_path.split('/')
                    directory_parts = path_parts[:-1]
                    for part in directory_parts:
                        if part and part not in all_tag_names:
                            all_tag_names.append(part)

                # 批量应用标签
                for tag_name in all_tag_names:
                    if not tag_name: continue
                    # 查找或创建标签
                    tag = Tag.query.filter_by(name=tag_name).first()
                    if not tag:
                        tag = Tag(name=tag_name)
                        db.session.add(tag)
                        db.session.flush()

                    # 检查标签是否已关联
                    existing_tag = AudioTag.query.filter_by(audio_id=new_audio.id, tag_id=tag.id).first()
                    if not existing_tag:
                        audio_tag = AudioTag(audio_id=new_audio.id, tag_id=tag.id)
                        db.session.add(audio_tag)

                    audio_tags.append(tag.name)

                # 处理标注信息（支持 JSON/RTTM/STM 格式），持久化并构造 raw_annotations
                raw_annotations_data = AudioConvertService._persist_annotations_and_raw(
                    new_audio.id,
                    validated.annotations,
                    algorithm_type,
                )

                # 处理音频算法关联
                algorithm_relations = validated.algorithm_relations
                if algorithm_relations:
                    from shared.models.models import AudioAlgorithmRelation
                    for item in algorithm_relations:
                        relation = AudioAlgorithmRelation(
                            audio_id=new_audio.id,
                            algorithm_type=item.algorithm_type,
                            is_primary=item.is_primary,
                            weight=item.weight,
                            params=item.params
                        )
                        db.session.add(relation)
                elif algorithm_type:
                    from shared.models.models import AudioAlgorithmRelation
                    relation = AudioAlgorithmRelation(
                        audio_id=new_audio.id,
                        algorithm_type=algorithm_type,
                        is_primary=True,
                        weight=1.0
                    )
                    db.session.add(relation)

                # 统一提交前面的所有变更（包括音频、标签、翻译）
                db.session.flush()

            # 如果需要创建测试用例
            created_test_case_id = None
            created_test_case_count = 0
            if create_test_case:
                tc_ids = AudioConvertService._create_test_case_from_audio(
                    new_audio.id,
                    test_types,
                    audio_tags,
                    default_playback_device_id,
                    default_spl,
                    noise_spl,
                    noise_audio_id,
                    test_case_group_name,
                    dimensions_data,
                    algorithm_type,
                    algorithm_params_dict,
                    rounds_config=rounds_config,
                    inherit_tags=tc_inherit_tags,
                    raw_annotations=raw_annotations_data or None,
                )
                if isinstance(tc_ids, list):
                    created_test_case_id = tc_ids[0] if tc_ids else None
                    created_test_case_count = len(tc_ids)
                else:
                    created_test_case_id = tc_ids
                    created_test_case_count = 1 if tc_ids else 0

            # 最终统一提交所有数据库变更
            db.session.commit()

            # 返回结果
            response_data = {
                "file_id": file_id,
                "audio_id": new_audio.id,
                "name": new_audio.name,
                "status": "completed"
            }

            if created_test_case_id:
                response_data["test_case_id"] = created_test_case_id
                response_data["test_case_count"] = created_test_case_count

            return success_response(response_data, "文件合并成功")
        except Exception as e:
            db.session.rollback()
            import traceback
            from shared.utils.log_handler import log_and_emit
            log_and_emit(
                level='error',
                module='audio_controller',
                content=f'分片合并失败: {str(e)}',
                category='audio',
                source='backend'
            )
            db.session.rollback()
            return error_response(str(e))
        finally:
            # 无论成功/失败，都清理本地临时分片和中间文件
            # 1. 清理分片目录（仅本地分片模式有 chunk_dir）
            try:
                if 'chunk_dir' in dir() and chunk_dir and os.path.exists(chunk_dir):
                    safe_rmtree(chunk_dir)
            except Exception:
                pass
            # 2. 清理转码失败的 fallback 残留文件（final_path 在异常分支可能是本地路径）
            try:
                if 'final_path' in dir() and os.path.exists(final_path):
                    # 如果 final_path 是 OSS key（已成功上传），跳过；本地路径才删
                    if os.path.isabs(final_path) or not final_path.replace('/', os.sep).startswith('audio_'):
                        retry_file_operation(os.remove, final_path)
            except Exception:
                pass
            # 3. 清理元数据提取临时文件
            try:
                if 'meta_tmp_path' in dir() and meta_tmp_path and os.path.exists(meta_tmp_path):
                    retry_file_operation(os.remove, meta_tmp_path)
            except Exception:
                pass

    # 获取上传任务进度
    @staticmethod
    def get_upload_progress():
        try:
            task_id = request.args.get('task_id')

            if not task_id:
                return error_response("缺少任务ID")

            # 查询任务
            task = db.session.get(UploadTask, task_id)
            if not task:
                return error_response("任务不存在")

            # 查询任务下的所有文件
            files = UploadFile.query.filter_by(task_id=task_id).all()

            # 构建文件进度列表
            file_progress = []
            for file in files:
                file_progress.append({
                    "file_id": file.id,
                    "filename": file.filename,
                    "original_filename": file.original_filename,
                    "relative_path": file.relative_path,
                    "size": file.size,
                    "uploaded_size": file.uploaded_size,
                    "completed_chunks": file.completed_chunks,
                    "total_chunks": file.total_chunks,
                    "status": file.status,
                    "md5": file.md5
                })

            return success_response({
                "task": {
                    "task_id": task.id,
                    "status": task.status,
                    "total_files": task.total_files,
                    "completed_files": task.completed_files,
                    "failed_files": task.failed_files,
                    "total_size": task.total_size,
                    "uploaded_size": task.uploaded_size,
                    "created_at": task.created_at.isoformat()
                },
                "files": file_progress
            })
        except Exception as e:
            return error_response(str(e))

    # URL 远程导入
    @staticmethod
    def url_import():
        import requests
        from io import BytesIO
        data = request.get_json()
        if not data:
            return error_response("请求体不能为空")

        try:
            validated = URLImportRequest.model_validate(data)
        except ValidationError as e:
            return error_response(f"参数验证失败: {e}")

        url = validated.url
        relative_path = validated.relative_path or ''
        audio_type = validated.audio_type

        try:
            response = requests.get(url, stream=True)
            if response.status_code != 200:
                return error_response(f"下载失败，状态码: {response.status_code}")

            original_filename = url.split('/')[-1] or "downloaded_audio"
            file_content = BytesIO(response.content)
            file_content.filename = original_filename

            meta = AudioUploadService._save_audio(file_content, "url_", relative_path=relative_path)
            meta['audio_type'] = audio_type

            new_audio = Audio(**meta)
            db.session.add(new_audio)
            db.session.commit()

            # 将相对路径转换为标签
            if relative_path:
                # 提取目录结构作为标签，包括根文件夹名
                path_parts = relative_path.split('/')
                # 移除文件名，只保留目录部分
                directory_parts = path_parts[:-1]

                # 为每个目录创建标签，包括根文件夹名
                for tag_name in directory_parts:
                    if tag_name:
                        # 查找或创建标签
                        tag = Tag.query.filter_by(name=tag_name).first()
                        if not tag:
                            tag = Tag(name=tag_name)
                            db.session.add(tag)
                            db.session.commit()

                        # 检查标签是否已关联
                        existing_tag = AudioTag.query.filter_by(audio_id=new_audio.id, tag_id=tag.id).first()
                        if not existing_tag:
                            audio_tag = AudioTag(audio_id=new_audio.id, tag_id=tag.id)
                            db.session.add(audio_tag)

                db.session.commit()

                from shared.utils.report.stats_cache import refresh_stats_cache
                refresh_stats_cache()

            return success_response({"id": new_audio.id, "name": new_audio.name}, "URL 导入成功", http_code=201)
        except Exception as e:
            db.session.rollback()
            return error_response(str(e))
