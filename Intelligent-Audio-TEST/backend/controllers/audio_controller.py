import os
import re
import uuid
import requests
import time
import shutil
import logging
from flask import request, send_file, Response, current_app
from sqlalchemy.orm import joinedload
from sqlalchemy import cast, String, func
from backend.models.models import Audio, Tag, AudioAnnotation, AudioTag, TestCase, TestCaseGroup, PlaybackDevice, UploadTask, UploadFile, UploadChunk
from backend.models.database import db
from backend.utils.web.response import success_response, error_response
from backend.utils.web.log_handler import log_not_emit
from backend.utils.common.task_utils import has_running_e2e_tasks
from backend.utils.algorithm.case_parameter_extractor import _normalize_algorithm_params_to_list
from backend.schemas.audio import (
    AudioIdsData,
    AudioItem,
    AudioListData,
    AudioListStats,
    BatchActionRequest,
    BatchPlaybackRequest,
    BatchUpdateAnnotationsRequest,
    ConvertFormatRequest,
    InitUploadTaskRequest,
    MergeChunksRequest,
    RegisterUploadFileRequest,
    TagListData as AudioTagListData,
    URLImportRequest,
    UpdateMetadataRequest,
)
from pydantic import ValidationError
from datetime import datetime, timedelta, timezone
from backend.utils.common.query_utils import now_cst
from pydub import AudioSegment


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

logger = logging.getLogger(__name__)

# 辅助函数：重试文件操作，解决 Windows 下的文件占用问题
def retry_file_operation(func, *args, **kwargs):
    max_retries = 5
    retry_delay = 0.2
    for i in range(max_retries):
        try:
            return func(*args, **kwargs)
        except (PermissionError, OSError) as e:
            if i == max_retries - 1:
                raise
            time.sleep(retry_delay)

def safe_makedirs(dir_path):
    if os.path.exists(dir_path):
        return
    max_retries = 3
    for i in range(max_retries):
        try:
            os.makedirs(dir_path, exist_ok=True)
            return
        except (PermissionError, OSError) as e:
            if i == max_retries - 1:
                raise
            time.sleep(0.2)

# 辅助函数：安全删除目录
def safe_rmtree(path):
    if not os.path.exists(path):
        return
        
    def on_error(func, path, exc_info):
        import stat
        try:
            os.chmod(path, stat.S_IWUSR)
            func(path)
        except:
            pass
            
    try:
        retry_file_operation(shutil.rmtree, path, onerror=on_error)
    except:
        # 最后尝试强制删除
        time.sleep(0.5)
        shutil.rmtree(path, ignore_errors=True)

# 辅助函数：获取相对路径（只返回static路径后半部分）
def get_relative_path(file_path):
    # 获取static目录路径
    static_base_path = current_app.config.get('STATIC_BASE_PATH')
    if not static_base_path:
        return file_path
    
    # 将Windows风格路径转换为统一的斜杠格式
    normalized_file_path = file_path.replace('\\', '/')
    normalized_static_path = static_base_path.replace('\\', '/')
    
    # 查找static目录在文件路径中的位置
    static_index = normalized_file_path.find(normalized_static_path)
    if static_index != -1:
        # 返回static目录之后的部分（去掉开头的斜杠）
        relative_path = normalized_file_path[static_index + len(normalized_static_path):]
        # 去掉开头的斜杠
        while relative_path.startswith('/'):
            relative_path = relative_path[1:]
        return relative_path
    
    # 如果没有找到static目录，返回原路径
    return file_path

def convert_to_wav(file_path):
    """
    将音频转换为WAV格式（不进行归一化，增益调整在播放时实时进行）
    :param file_path: 原始音频文件路径
    :return: 转换后的WAV文件路径
    """
    # 规范化文件路径（处理混合斜杠问题）
    file_path = os.path.normpath(file_path)
    
    # 检查文件是否存在
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"文件不存在: {file_path}")
    
    # 加载原始音频
    audio_seg = AudioSegment.from_file(file_path)
    
    # 获取原始音频的采样率信息
    original_sample_rate = audio_seg.frame_rate
    original_channels = audio_seg.channels

    # 多声道只保留第一个声道（转为单声道）
    if original_channels > 1:
        audio_seg = audio_seg.split_to_mono()[0]
        original_channels = 1

    # 位深信息通过sample_width获取（bytes per sample per channel）
    original_bits_per_sample = audio_seg.sample_width * 8

    # 生成新的WAV文件路径
    directory = os.path.dirname(file_path)
    filename = os.path.splitext(os.path.basename(file_path))[0]
    new_wav_path = os.path.join(directory, f"{filename}.wav")
    
    # 导出为WAV，保持原始采样率和位深
    # 使用pcm_s<bits_per_sample>le格式（小端）保持位深
    codec_map = {
        16: 'pcm_s16le',
        24: 'pcm_s24le',
        32: 'pcm_s32le'
    }
    codec = codec_map.get(original_bits_per_sample, 'pcm_s16le')
    
    audio_seg.export(
        new_wav_path, 
        format='wav',
        parameters=['-ar', str(int(original_sample_rate)),
                   '-ac', str(original_channels),
                   '-acodec', codec]
    )
    
    # 返回新的文件名（带.wav扩展名）
    new_filename = f"{filename}.wav"
    return new_wav_path, new_filename, original_sample_rate, original_bits_per_sample


class AudioController:
    @staticmethod
    def _get_source_language_from_algorithm_params(algorithm_params):
        if not algorithm_params:
            return None
        for param in algorithm_params:
            if isinstance(param, dict):
                if param.get('field_code') == 'source_language':
                    return param.get('field_value')
            elif hasattr(param, 'field_code') and param.field_code == 'source_language':
                return param.field_value
        return None

    # 获取所有可用的音频标签
    @staticmethod
    def get_all_tags():
        # 查询所有不重复的标签
        tags = db.session.query(Tag.name).distinct().all()
        # 提取标签名称
        tag_names = [tag.name for tag in tags]
        return success_response(AudioTagListData(items=tag_names, total=len(tag_names)))

    # 获取所有音频文件列表
    @staticmethod
    def get_all():
        # 支持分页和过滤
        # 优先从 body 获取参数（POST），其次从 query 获取（GET）
        if request.method == 'POST' and request.is_json:
            data = request.get_json() or {}
            page = data.get('page', 1)
            per_page = data.get('perPage', data.get('per_page', 10))
            keyword = data.get('keyword')
            format_ = data.get('format')
            audio_type = data.get('audioType', data.get('audio_type'))
            folder = data.get('folder')
            sample_rate = data.get('sampleRate', data.get('sample_rate'))
            duration = data.get('duration')
            tags_data = data.get('tags', [])
            direction = data.get('direction')
        else:
            page = request.args.get('page', 1, type=int)
            per_page = request.args.get('per_page', 10, type=int)
            keyword = request.args.get('keyword')
            format_ = request.args.get('format')
            audio_type = request.args.get('audio_type')
            folder = request.args.get('folder')
            sample_rate = request.args.get('sample_rate')
            duration = request.args.get('duration')
            tags = request.args.getlist('tags')
            tags_data = [{'name': t, 'mode': 'and'} for t in tags] if tags else []
            direction = request.args.get('direction')

        query = Audio.query.filter_by(deleted=False)
        if keyword:
            query = query.filter(
                (Audio.name.like(f"%{keyword}%")) | 
                (Audio.original_filename.like(f"%{keyword}%"))
            )
        if format_:
            query = query.filter_by(format=format_)
        if audio_type:
            query = query.filter_by(audio_type=audio_type)
        if folder:
            query = query.filter(Audio.file_path.like(f"{folder}%"))
        if sample_rate and sample_rate != '':
            # 处理采样率参数，将字符串格式转换为数字进行比较
            try:
                # 提取采样率数值，如 "44.1 kHz" -> 44100
                rate_value = float(sample_rate.split()[0]) * 1000
                query = query.filter_by(sample_rate=rate_value)
            except (ValueError, IndexError):
                pass
        if duration:
            # 处理时长参数
            if duration == 'short':
                # 短 (<= 30秒)
                query = query.filter(Audio.duration <= 30)
            elif duration == 'medium':
                # 中 (30秒 - 5分钟)
                query = query.filter(Audio.duration.between(30, 300))
            elif duration == 'long':
                # 长 (> 5分钟)
                query = query.filter(Audio.duration > 300)

        if direction:
            query = query.join(AudioAnnotation).filter(
                (AudioAnnotation.source_language.like(f"%{direction.split('-')[0]}%")) |
                (AudioAnnotation.target_language.like(f"%{direction.split('-')[1]}%"))
            )

        if tags_data:
            # 处理标签：支持字符串数组和对象数组 [{name: 'xxx', mode: 'or'}, 'yyy']
            or_tags = []
            and_tags = []
            
            for t in tags_data:
                if isinstance(t, dict):
                    tag_name = t.get('name', '').strip()
                    tag_mode = t.get('mode', 'and')
                    if tag_name:
                        if tag_mode == 'or':
                            or_tags.append(tag_name)
                        else:
                            and_tags.append(tag_name)
                elif isinstance(t, str):
                    for part in t.split(','):
                        p = part.strip()
                        if p:
                            and_tags.append(p)
            
            # OR 模式：音频拥有任一 OR 标签即可
            if or_tags:
                or_audio_ids = (
                    db.session.query(AudioTag.audio_id)
                    .join(Tag, Tag.id == AudioTag.tag_id)
                    .filter(Tag.name.in_(or_tags))
                    .distinct()
                )
                query = query.filter(Audio.id.in_(or_audio_ids))
            
            # AND 模式：音频必须拥有所有 AND 标签
            if and_tags:
                and_tag_ids = (
                    db.session.query(Tag.id)
                    .filter(Tag.name.in_(and_tags))
                    .subquery()
                )
                audio_tag_counts = (
                    db.session.query(AudioTag.audio_id, db.func.count(AudioTag.tag_id).label('tag_count'))
                    .filter(AudioTag.tag_id.in_(db.session.query(and_tag_ids)))
                    .group_by(AudioTag.audio_id)
                    .subquery()
                )
                query = query.join(audio_tag_counts, audio_tag_counts.c.audio_id == Audio.id).filter(audio_tag_counts.c.tag_count == len(and_tags))

        pagination = query.order_by(Audio.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)
        audios = pagination.items

        audio_ids = [audio.id for audio in audios]

        audio_tags_map = {}
        if audio_ids:
            audio_tags_records = (
                db.session.query(AudioTag, Tag)
                .join(Tag, Tag.id == AudioTag.tag_id)
                .filter(AudioTag.audio_id.in_(audio_ids))
                .all()
            )
            for at, tag in audio_tags_records:
                if at.audio_id not in audio_tags_map:
                    audio_tags_map[at.audio_id] = []
                audio_tags_map[at.audio_id].append(tag.name)

        annotations_map = {}
        if audio_ids:
            annotations_records = AudioAnnotation.query.filter(
                AudioAnnotation.audio_id.in_(audio_ids),
                AudioAnnotation.deleted == False
            ).all()
            for ann in annotations_records:
                if ann.audio_id not in annotations_map:
                    annotations_map[ann.audio_id] = []
                annotations_map[ann.audio_id].append({
                    "format": ann.format,
                    "code": ann.code,
                    "data": ann.data,
                    "source_language": ann.source_language,
                    "target_language": ann.target_language
                })

        data = []
        for audio in audios:
            tags = audio_tags_map.get(audio.id, [])
            annotations = annotations_map.get(audio.id, [])
            
            data.append(
                AudioItem(
                    id=audio.id,
                    name=audio.name,
                    original_filename=audio.original_filename,
                    file_path=get_relative_path(audio.file_path),
                    duration=audio.duration,
                    size=audio.size,
                    sample_rate=audio.sample_rate,
                    channels=audio.channels,
                    bitrate=audio.bitrate,
                    format=audio.format,
                    audio_type=audio.audio_type,
                    asr_text=audio.asr_text,
                    description=audio.description,
                    source_language=audio.source_language,
                    tags=tags,
                    annotations=annotations,
                    created_at=audio.created_at.isoformat() if audio.created_at else None,
                    updated_at=audio.updated_at.isoformat() if audio.updated_at else None,
                )
            )
        
        today_start = now_cst().replace(hour=0, minute=0, second=0, microsecond=0)

        stats_result = db.session.query(
            db.func.sum(Audio.size),
            db.func.sum(Audio.duration)
        ).filter(Audio.deleted == False).first()

        total_size = stats_result[0] or 0
        total_duration = stats_result[1] or 0

        today_uploads = db.session.query(db.func.count(Audio.id)).filter(
            Audio.created_at >= today_start,
            Audio.deleted == False
        ).scalar() or 0

        # 格式化大小
        if total_size < 1024:
            size_str = f"{total_size} B"
        elif total_size < 1024 * 1024:
            size_str = f"{total_size/1024:.2f} KB"
        else:
            size_str = f"{total_size/(1024*1024):.2f} MB"

        # 格式化时长
        mins, secs = divmod(int(total_duration), 60)
        duration_str = f"{mins}:{secs:02d}"

        return success_response(
            AudioListData(
                items=data,
                total=pagination.total,
                page=pagination.page,
                per_page=pagination.per_page,
                pages=pagination.pages,
                stats=AudioListStats(
                    total_files=pagination.total,
                    total_size=size_str,
                    total_duration=duration_str,
                    today_uploads=today_uploads,
                ),
            )
        )

    # 获取单个音频文件详情
    @staticmethod
    def get_one(audio_id):
        audio = Audio.query.filter_by(id=audio_id, deleted=False).first()
        if not audio:
            return error_response("音频文件不存在", code=404)
        
        # 获取关联的标签
        audio_tags = AudioTag.query.filter_by(audio_id=audio.id).all()
        tags = []
        for at in audio_tags:
            if at and at.tag_id:
                tag = db.session.get(Tag, at.tag_id)
                if tag:
                    tags.append(tag.name)
        
        # 获取关联的标注
        annotations = []
        audio_annotations = AudioAnnotation.query.filter_by(audio_id=audio.id, deleted=False).all()
        for ann in audio_annotations:
            annotations.append({
                "format": ann.format,
                "code": ann.code,
                "data": ann.data,
                "source_language": ann.source_language,
                "target_language": ann.target_language
            })

        return success_response(
                AudioItem(
                    id=audio.id,
                    name=audio.name,
                    original_filename=audio.original_filename,
                    file_path=get_relative_path(audio.file_path),
                    duration=audio.duration,
                    size=audio.size,
                    sample_rate=audio.sample_rate,
                    channels=audio.channels,
                    bitrate=audio.bitrate,
                    format=audio.format,
                    audio_type=audio.audio_type,
                    asr_text=audio.asr_text,
                    description=audio.description,
                    tags=tags,
                    annotations=annotations,
                    created_at=audio.created_at.isoformat() if audio.created_at else None,
                    updated_at=audio.updated_at.isoformat() if audio.updated_at else None,
                )
            )

    @staticmethod
    def get_by_ids():
        if not request.is_json:
            return error_response("请求必须是 JSON 格式")
        
        data = request.get_json() or {}
        audio_ids = data.get('ids', [])
        
        if not audio_ids:
            return success_response([])
        
        if not isinstance(audio_ids, list):
            return error_response("ids 必须是数组")
        
        audio_ids = [int(aid) if str(aid).isdigit() else aid for aid in audio_ids]
        
        audios = Audio.query.filter(Audio.id.in_(audio_ids), Audio.deleted == False).all()
        
        results = []
        for audio in audios:
            audio_tags = AudioTag.query.filter_by(audio_id=audio.id).all()
            tags = []
            for at in audio_tags:
                if at and at.tag_id:
                    tag = db.session.get(Tag, at.tag_id)
                    if tag:
                        tags.append(tag.name)
            
            annotations = []
            audio_annotations = AudioAnnotation.query.filter_by(audio_id=audio.id, deleted=False).all()
            for ann in audio_annotations:
                annotations.append({
                    "format": ann.format,
                    "code": ann.code,
                    "data": ann.data,
                    "source_language": ann.source_language,
                    "target_language": ann.target_language
                })
            
            results.append(
                AudioItem(
                    id=audio.id,
                    name=audio.name,
                    original_filename=audio.original_filename,
                    file_path=get_relative_path(audio.file_path),
                    duration=audio.duration,
                    size=audio.size,
                    sample_rate=audio.sample_rate,
                    channels=audio.channels,
                    bitrate=audio.bitrate,
                    format=audio.format,
                    audio_type=audio.audio_type,
                    asr_text=audio.asr_text,
                    description=audio.description,
                    tags=tags,
                    annotations=annotations,
                    created_at=audio.created_at.isoformat() if audio.created_at else None,
                    updated_at=audio.updated_at.isoformat() if audio.updated_at else None,
                )
            )
        
        return success_response(results)

    # 按 MD5 批量查询音频（用于批量更新标注时匹配）
    @staticmethod
    def get_by_md5():
        if not request.is_json:
            return error_response("请求必须是 JSON 格式")

        data = request.get_json() or {}
        md5_list = data.get('md5_list', [])

        if not md5_list:
            return success_response({})

        if not isinstance(md5_list, list):
            return error_response("md5_list 必须是数组")

        audios = Audio.query.filter(
            Audio.md5.in_(md5_list),
            Audio.deleted == False
        ).all()

        result = {}
        for audio in audios:
            result[audio.md5] = {
                'id': audio.id,
                'name': audio.name,
            }

        return success_response(result)

    # 获取所有音频ID列表（用于全选功能）
    @staticmethod
    def get_all_ids():
        # 优先从 body 获取参数（POST），其次从 query 获取（GET）
        if request.method == 'POST' and request.is_json:
            data = request.get_json() or {}
            keyword = data.get('keyword')
            format_ = data.get('format')
            audio_type = data.get('audioType', data.get('audio_type'))
            sample_rate = data.get('sampleRate', data.get('sample_rate'))
            duration = data.get('duration')
            tags_data = data.get('tags', [])
            direction = data.get('direction')
        else:
            keyword = request.args.get('keyword')
            format_ = request.args.get('format')
            audio_type = request.args.get('audio_type')
            sample_rate = request.args.get('sample_rate')
            duration = request.args.get('duration')
            tags = request.args.getlist('tags')
            tags_data = [{'name': t, 'mode': 'and'} for t in tags] if tags else []
            direction = request.args.get('direction')

        query = Audio.query.filter_by(deleted=False)

        if keyword:
            query = query.filter(
                (Audio.name.like(f"%{keyword}%")) |
                (Audio.original_filename.like(f"%{keyword}%"))
            )
        if format_:
            query = query.filter_by(format=format_)
        if audio_type:
            query = query.filter_by(audio_type=audio_type)
        if sample_rate and sample_rate != '':
            try:
                rate_value = float(sample_rate.split()[0]) * 1000
                query = query.filter_by(sample_rate=rate_value)
            except (ValueError, IndexError):
                pass
        if duration:
            if duration == 'short':
                query = query.filter(Audio.duration <= 30)
            elif duration == 'medium':
                query = query.filter(Audio.duration.between(30, 300))
            elif duration == 'long':
                query = query.filter(Audio.duration > 300)

        if direction:
            query = query.join(AudioAnnotation).filter(
                (AudioAnnotation.source_language.like(f"%{direction.split('-')[0]}%")) |
                (AudioAnnotation.target_language.like(f"%{direction.split('-')[1]}%"))
            )

        if tags_data:
            # 处理标签：支持字符串数组和对象数组 [{name: 'xxx', mode: 'or'}, 'yyy']
            or_tags = []
            and_tags = []
            
            for t in tags_data:
                if isinstance(t, dict):
                    tag_name = t.get('name', '').strip()
                    tag_mode = t.get('mode', 'and')
                    if tag_name:
                        if tag_mode == 'or':
                            or_tags.append(tag_name)
                        else:
                            and_tags.append(tag_name)
                elif isinstance(t, str):
                    for part in t.split(','):
                        p = part.strip()
                        if p:
                            and_tags.append(p)
            
            # OR 模式：音频拥有任一 OR 标签即可
            if or_tags:
                or_audio_ids = (
                    db.session.query(AudioTag.audio_id)
                    .join(Tag, Tag.id == AudioTag.tag_id)
                    .filter(Tag.name.in_(or_tags))
                    .distinct()
                )
                query = query.filter(Audio.id.in_(or_audio_ids))
            
            # AND 模式：音频必须拥有所有 AND 标签
            if and_tags:
                and_tag_ids = (
                    db.session.query(Tag.id)
                    .filter(Tag.name.in_(and_tags))
                    .subquery()
                )
                audio_tag_counts = (
                    db.session.query(AudioTag.audio_id, db.func.count(AudioTag.tag_id).label('tag_count'))
                    .filter(AudioTag.tag_id.in_(db.session.query(and_tag_ids)))
                    .group_by(AudioTag.audio_id)
                    .subquery()
                )
                query = query.join(audio_tag_counts, audio_tag_counts.c.audio_id == Audio.id).filter(audio_tag_counts.c.tag_count == len(and_tags))

        audio_ids = query.with_entities(Audio.id).all()
        ids = [audio.id for audio in audio_ids]

        return success_response(AudioIdsData(ids=ids, total=len(ids)))

    # 内部辅助方法：处理文件名冲突
    @staticmethod
    def _get_unique_filename(directory, original_filename):
        # 清理文件名中的危险字符，保留中文等非ASCII字符
        safe_filename = _sanitize_filename(original_filename)
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
        base_upload_dir = current_app.config.get('AUDIO_STORAGE_PATH')
        
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
            safe_filename = AudioController._get_unique_filename(base_upload_dir, prefixed_filename)
            temp_file_path = os.path.join(base_upload_dir, safe_filename)
        
        # 先保存原始文件
        retry_file_operation(file.save, temp_file_path)
        
        try:
            # 转换为WAV格式
            wav_file_path, wav_filename, sample_rate, bits_per_sample = convert_to_wav(temp_file_path)
            
            # 删除原始临时文件
            if os.path.exists(temp_file_path) and temp_file_path != wav_file_path:
                retry_file_operation(os.remove, temp_file_path)
            
            # 更新文件路径为WAV文件（统一用正斜杠，避免 Windows 反斜杠导致后续查询/拼接问题）
            file_path = wav_file_path.replace('\\', '/')
            # 更新文件名为WAV文件名
            original_filename = wav_filename
            
        except Exception as e:
            # 如果转换失败，删除临时文件并抛出异常
            if os.path.exists(temp_file_path):
                retry_file_operation(os.remove, temp_file_path)
            raise ValueError(f"音频转换失败: {str(e)}")
        
        # 提取WAV文件元数据
        file_size = os.path.getsize(file_path)
        try:
            audio_seg = AudioSegment.from_file(file_path)
            duration = len(audio_seg) / 1000.0
            channels = audio_seg.channels
            # 使用实际的位深计算比特率
            bitrate = bits_per_sample * sample_rate * channels
            
            # 严格校验：如果时长为0，通常意味着不是有效的音频文件
            if duration <= 0:
                raise ValueError("音频时长为0，可能是无效的音频文件")
                
        except Exception as e:
            # 如果元数据提取失败，说明不是有效的音频文件
            if os.path.exists(file_path):
                retry_file_operation(os.remove, file_path)
            raise ValueError(f"无法识别的音频格式或文件已损坏: {str(e)}")
        
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
        base_upload_dir = current_app.config.get('AUDIO_STORAGE_PATH')
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
            AudioController._init_upload_dirs()
            
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
            from backend.utils.web.log_handler import log_and_emit
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
            dirs = AudioController._init_upload_dirs()
            
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
            from backend.utils.web.log_handler import log_and_emit
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
            dirs = AudioController._init_upload_dirs()
            
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
            from backend.utils.web.log_handler import log_and_emit
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
            dirs = AudioController._init_upload_dirs()
            
            # 检查是否是秒传文件（total_chunks = 0 且状态为 completed）
            is_instant_upload = upload_file.total_chunks == 0 and upload_file.status == 'completed'
            
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
                        # 秒传场景：已有音频的 name 可能改过名，前端传的 audio_name 匹配不上，
                        # 这里直接把 existing_audio.id 填进 rounds_config 里对应的项
                        if rounds_config:
                            # 先收集所有未匹配的音频项
                            unmatched_items = []
                            for r in rounds_config:
                                if not isinstance(r, dict):
                                    continue
                                for a in r.get('audios', []):
                                    if not isinstance(a, dict) or a.get('audio_id'):
                                        continue
                                    unmatched_items.append(a)
                            # 对未匹配项尝试按 name/original_filename/md5 匹配
                            matched_count = 0
                            for a in unmatched_items:
                                item_name = a.get('audio_name') or ''
                                if (item_name == existing_audio.name
                                        or item_name == (existing_audio.original_filename or '')
                                        or item_name == (existing_audio.md5 or '')
                                        or not item_name):
                                    a['audio_id'] = existing_audio.id
                                    matched_count += 1
                            # 如果按名称都匹配不上，且只有一个未匹配项，直接填（秒传的音频就是它）
                            if matched_count == 0 and len(unmatched_items) == 1:
                                unmatched_items[0]['audio_id'] = existing_audio.id
                        # 秒传场景也要持久化标注（同 code 覆盖旧记录），并构造 raw_annotations 供用例参数提取
                        raw_annotations_data = AudioController._persist_annotations_and_raw(
                            existing_audio.id,
                            validated.annotations,
                            algorithm_type,
                        )
                        tc_ids = AudioController._create_test_case_from_audio(
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
                        AudioController._persist_annotations_and_raw(
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
            chunk_dir = os.path.join(dirs['chunk'], file_id)
            
            # 生成最终文件路径
            if upload_file.relative_path:
                # 保持原目录结构
                final_path = os.path.join(dirs['base'], upload_file.relative_path)
                # 确保目录存在
                os.makedirs(os.path.dirname(final_path), exist_ok=True)
            else:
                # 直接保存到基础目录
                safe_filename = AudioController._get_unique_filename(dirs['base'], upload_file.filename)
                final_path = os.path.join(dirs['base'], safe_filename)
            
            # 合并所有分片
            def perform_merge():
                # 确保目标目录存在
                os.makedirs(os.path.dirname(final_path), exist_ok=True)
                
                # 如果文件已存在，先尝试删除（解决某些情况下的占用问题）
                if os.path.exists(final_path):
                    # 使用带重试机制的删除操作
                    retry_file_operation(os.remove, final_path)

                with open(final_path, 'wb') as final_file:
                    for i in range(upload_file.total_chunks):
                        chunk_path = os.path.join(chunk_dir, f"chunk_{i}")
                        if os.path.exists(chunk_path):
                            with open(chunk_path, 'rb') as chunk_file:
                                final_file.write(chunk_file.read())
            
            retry_file_operation(perform_merge)
            
            # 规范化路径（处理混合斜杠问题）
            final_path = os.path.normpath(final_path)
            
            # 转换为WAV格式
            try:
                wav_file_path, wav_filename, sample_rate, bits_per_sample = convert_to_wav(final_path)
                
                # 删除原始合并文件
                if os.path.exists(final_path) and final_path != wav_file_path:
                    retry_file_operation(os.remove, final_path)
                
                # 更新文件路径为WAV文件（统一用正斜杠）
                final_path = wav_file_path.replace('\\', '/')
                # 更新文件名为WAV文件名（转换后存储用的文件名）
                # original_filename 保留注册时记录的原始上传名，不覆盖
                upload_file.filename = wav_filename
                
            except Exception as e:
                # 如果转换失败，保留原始文件但标记格式
                logger.warning(f"音频转换失败，将保留原始格式: {str(e)}")
                sample_rate = 44100
                bits_per_sample = 16
            
            # 提取音频元数据
            file_size = os.path.getsize(final_path)
            
            # 初始化元数据默认值（不依赖ffmpeg）
            duration = 0.0
            sample_rate = 44100  # 默认采样率
            channels = 1  # 默认单声道
            bitrate = 128000  # 默认比特率
            
            # 尝试提取详细元数据，但不依赖ffmpeg可用性
            try:
                # 尝试提取详细元数据
                audio_seg = AudioSegment.from_file(final_path)
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
                # 保留合并后的文件，不删除，继续使用默认元数据
            
            # 获取源语言（从算法参数中提取）
            source_language = AudioController._get_source_language_from_algorithm_params(algorithm_params)

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
                raw_annotations_data = AudioController._persist_annotations_and_raw(
                    new_audio.id,
                    validated.annotations,
                    algorithm_type,
                )
                
                # 处理音频算法关联
                algorithm_relations = validated.algorithm_relations
                if algorithm_relations:
                    from backend.models.models import AudioAlgorithmRelation
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
                    from backend.models.models import AudioAlgorithmRelation
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
                tc_ids = AudioController._create_test_case_from_audio(
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

            # 清理临时分片文件
            safe_rmtree(chunk_dir)

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
            from backend.utils.web.log_handler import log_and_emit
            log_and_emit(
                level='error',
                module='audio_controller',
                content=f'分片合并失败: {str(e)}',
                category='audio',
                source='backend'
            )
            db.session.rollback()
            return error_response(str(e))
    
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
    

    # 内部辅助方法：从文件列表构建 rounds 配置
    @staticmethod
    def _build_rounds_from_files(files, mode="multi_round", spl=65.0, playback_device_id=None):
        """从文件列表构建 rounds 配置。

        :param files: 文件列表，每项含 file_id / audio_id / filename
        :param mode: "multi_round"（每音频一轮）或 "single_round_multi_audio"（多音频同轮）
        :param spl: 干声压级
        :param playback_device_id: 播放设备 ID（E2E）
        :return: rounds 列表
        """
        if not files:
            return []

        def _make_audio_config(item, play_order):
            cfg = {
                "audio_id": item["audio_id"],
                "spl": spl,
                "play_order": play_order,
            }
            if playback_device_id:
                cfg["playback_device_id"] = playback_device_id
            return cfg

        if mode == "single_round_multi_audio":
            # 所有音频合并为一轮
            audios = [_make_audio_config(item, idx) for idx, item in enumerate(files)]
            return [{"round_number": 1, "audios": audios}]
        else:
            # multi_round: 每音频一轮
            rounds = []
            for idx, item in enumerate(files):
                rounds.append({
                    "round_number": idx + 1,
                    "audios": [_make_audio_config(item, 0)],
                })
            return rounds

    # 内部辅助方法：持久化音频标注，返回 raw_annotations_data（未剔除用例参数）供用例参数提取使用
    @staticmethod
    def _persist_annotations_and_raw(audio_id, annotations_from_request, algorithm_type):
        """把请求里的 annotations 写入 audio_annotations 表（同 code 覆盖旧记录），返回 raw_annotations_data。

        - 入库的 data 已剔除用例参数字段（只保留参考参数 + 元数据）
        - raw_annotations_data 保留完整原始标注，供 _create_test_case_from_audio 提取用例参数
        """
        from backend.models.models import AudioAnnotation
        # 查用例参数字段列表，用于从标注数据中剔除（标注表只保留参考参数 + 元数据）
        case_param_fields = set()
        if algorithm_type:
            from backend.models.algorithm_models import CaseAlgorithmParam
            # 查参考参数的 field_path 集合，这些字段不能从标注数据中剔除
            from backend.models.algorithm_models import AlgorithmReferenceParam
            ref_field_paths = set()
            ref_params = AlgorithmReferenceParam.query.filter_by(
                algorithm_type=algorithm_type, deleted=False
            ).all()
            for rp in ref_params:
                fp = rp.field_path or rp.code
                if fp:
                    if '[]' in fp:
                        seg_key = fp.split('[].')[1] if '[].' in fp else fp
                        ref_field_paths.add(seg_key)
                    else:
                        ref_field_paths.add(fp)

            case_params = CaseAlgorithmParam.query.filter_by(
                algorithm_type=algorithm_type, deleted=False
            ).all()
            for p in case_params:
                fp = p.field_path or p.param_code
                if fp and '[]' in fp:
                    seg_key = fp.split('[].')[1] if '[].' in fp else fp
                    # 跳过同时作为参考参数的字段，避免把参考参数也从标注中删除
                    if seg_key not in ref_field_paths:
                        case_param_fields.add(seg_key)
                else:
                    if fp not in ref_field_paths:
                        case_param_fields.add(fp)

        raw_annotations_data = []
        for ann in annotations_from_request or []:
            ann_format = ann.get('format', 'json')
            ann_data = ann.get('data', {}) or {}
            ann_code = ann.get('code', '')
            ann_source_lang = ann.get('source_language', '')
            ann_target_lang = ann.get('target_language', '')

            # 保留原始标注数据（未剔除用例参数），用于创建用例时提取用例参数
            raw_annotations_data.append({
                'code': ann_code,
                'data': ann_data,
            })

            # 从标注数据中剔除用例参数字段（只保留参考参数 + 元数据）
            if case_param_fields and isinstance(ann_data, dict):
                import copy as _copy
                ann_data_clean = _copy.deepcopy(ann_data)
                segments = ann_data_clean.get('segments', [])
                if isinstance(segments, list):
                    for seg in segments:
                        if isinstance(seg, dict):
                            for field_key in list(seg.keys()):
                                if field_key in case_param_fields:
                                    del seg[field_key]
                ann_data = ann_data_clean

            # 秒传/重新上传时，同 audio_id + code 的旧标注先软删再写新记录
            existing = AudioAnnotation.query.filter_by(
                audio_id=audio_id, code=ann_code, deleted=False
            ).first()
            if existing:
                existing.deleted = True
                db.session.flush()

            audio_annotation = AudioAnnotation(
                audio_id=audio_id,
                format=ann_format,
                code=ann_code,
                data=ann_data,
                source_language=ann_source_lang,
                target_language=ann_target_lang
            )
            db.session.add(audio_annotation)

        # flush 确保 annotation 写入数据库，后续 _create_test_case_from_audio
        # 调 apply_to_config → _preload_audio_data 时能查到这些 annotation
        if annotations_from_request:
            db.session.flush()

        return raw_annotations_data or None

    # 内部辅助方法：从音频创建测试用例
    @staticmethod
    def _create_test_case_from_audio(audio_id, test_types, audio_tags, playback_device_id=None, spl=65.0, noise_spl=60.0, noise_audio_id=None, group_name=None, dimensions_data=None, algorithm_type=None, algorithm_params=None, rounds_config=None, inherit_tags=True, raw_annotations=None):
        """
        根据音频创建测试用例，支持多测试类型（API和E2E）。

        :param audio_id: 音频ID（主音频，用于命名和描述）
        :param test_types: 测试类型列表，如 ['api', 'e2e']
        :param audio_tags: 音频标签列表
        :param playback_device_id: 播放设备ID（用于E2E测试）
        :param spl: 干声压级
        :param noise_spl: 噪声声压级
        :param noise_audio_id: 噪声音频ID
        :param group_name: 分组名称
        :param dimensions_data: 评估维度配置
        :param algorithm_type: 算法类型
        :param algorithm_params: 算法参数
        :param rounds_config: 完整的 rounds 配置（多轮用例）。传入时优先使用，跳过平面 config 构建。
        :param inherit_tags: 是否继承音频标签到用例（默认 True）
        """
        # 确保 test_types 是列表，并清理可能的空白字符
        if isinstance(test_types, str):
            test_types = [test_types.strip()]
        else:
            test_types = [tt.strip() if isinstance(tt, str) else tt for tt in test_types]

        logger.debug(f'_create_test_case_from_audio called, audio_id={audio_id}, test_types={test_types}, rounds_config={rounds_config}')

        audio = db.session.get(Audio, audio_id)
        if not audio:
            return None

        # 使用提供的分组名称，如果没有则使用默认值
        effective_group_name = group_name if group_name else '音频上传生成'

        with db.session.no_autoflush:
            # 获取或创建分组
            group = TestCaseGroup.query.filter_by(name=effective_group_name).first()
            if not group:
                group = TestCaseGroup(
                    id=str(uuid.uuid4()),
                    name=effective_group_name,
                    description=f'通过音频上传自动创建的测试用例分组: {effective_group_name}'
                )
                db.session.add(group)
                db.session.flush()

            # 获取默认播放设备（如果需要E2E测试但没有指定设备）
            effective_playback_device_id = playback_device_id
            if 'e2e' in test_types and not effective_playback_device_id:
                default_device = PlaybackDevice.query.filter_by(device_type='dry', is_deleted=0).first()
                if default_device:
                    effective_playback_device_id = default_device.id

            # 创建测试用例名称（基础名）
            # 秒传场景下 audio.name 可能是旧的改名（如 "1.wav"），
            # 优先用 rounds_config 里前端传的 audio_name 作为用例名
            tc_audio_name = audio.name
            if rounds_config:
                for r in rounds_config:
                    if not isinstance(r, dict):
                        continue
                    for a in r.get('audios', []):
                        if isinstance(a, dict) and a.get('audio_name'):
                            tc_audio_name = a['audio_name']
                            break
                    if tc_audio_name != audio.name:
                        break
            base_name = f"测试用例_{tc_audio_name}"

            # 确保至少有一个 test_type
            if not test_types:
                test_types = ['api']

            created_tc_ids = []
            import copy

            for tt in test_types:
                # 每种 test_type 一个用例，名称加后缀区分
                if len(test_types) > 1:
                    test_case_name = f"{base_name}_{tt}"
                else:
                    test_case_name = base_name

                # 同名时加时间戳避免冲突
                existing = TestCase.query.filter_by(name=test_case_name, group_id=group.id, deleted=False).first()
                if existing:
                    test_case_name = f"{test_case_name}_{now_cst().strftime('%H%M%S')}"

                # ===== 构建 config =====
                # 统一走 rounds 架构，前端始终构建 rounds_config
                # 新设计：algorithm_params 和 reference_params 不在 config.rounds[] 中，存独立列
                if rounds_config:
                    rounds_resolved = copy.deepcopy(rounds_config)
                else:
                    # 兜底：前端未传 rounds_config 时构建最小 rounds
                    audio_config = {
                        "audio_id": audio_id,
                        "spl": spl if spl else 65.0,
                        "play_order": 0
                    }
                    if tt == 'e2e':
                        audio_config["playback_device_id"] = effective_playback_device_id
                    rounds_resolved = [{
                        "round_number": 1,
                        "audios": [audio_config],
                    }]

                # 从 rounds_resolved 中剥离 algorithm_params 到独立列
                algo_params_col = []
                import json as _json
                logger.debug(f'rounds_resolved before strip: {_json.dumps(rounds_resolved, ensure_ascii=False)[:500]}')
                log_not_emit('INFO', 'audio_controller', f'[DEBUG_STRIP] rounds_resolved before strip: {_json.dumps(rounds_resolved, ensure_ascii=False)[:500]}', category='audio')
                for round_item in rounds_resolved:
                    if not isinstance(round_item, dict):
                        continue
                    rn = round_item.get('round_number', 1)
                    # 剥离 algorithm_params / algorithmParams
                    round_ap = round_item.pop('algorithm_params', None) or round_item.pop('algorithmParams', None)
                    if round_ap:
                        params_list = []
                        if isinstance(round_ap, dict):
                            params_list = [{'field_code': k, 'field_value': v} for k, v in round_ap.items()]
                        elif isinstance(round_ap, list):
                            for p in round_ap:
                                if isinstance(p, dict):
                                    fc = p.get('field_code') or p.get('fieldCode')
                                    fv = p.get('field_value', p.get('fieldValue'))
                                    if fc:
                                        params_list.append({'field_code': fc, 'field_value': fv})
                        if params_list:
                            algo_params_col.append({'round_number': rn, 'params': params_list})
                    # 剥离 reference_params_path / referenceParamsPath（不应在 config 中）
                    round_item.pop('reference_params_path', None)
                    round_item.pop('referenceParamsPath', None)

                logger.debug(f'rounds_resolved after strip: {_json.dumps(rounds_resolved, ensure_ascii=False)[:500]}')
                logger.debug(f'algo_params_col: {_json.dumps(algo_params_col, ensure_ascii=False)[:500]}')
                log_not_emit('INFO', 'audio_controller', f'[DEBUG_STRIP] rounds_resolved after strip: {_json.dumps(rounds_resolved, ensure_ascii=False)[:500]}', category='audio')
                log_not_emit('INFO', 'audio_controller', f'[DEBUG_STRIP] algo_params_col: {_json.dumps(algo_params_col, ensure_ascii=False)[:500]}', category='audio')

                # 兜底：前端传了平面 algorithm_params 但没 rounds_config 时
                if not algo_params_col and algorithm_params:
                    round_algorithm_params = []
                    if isinstance(algorithm_params, dict):
                        round_algorithm_params = [
                            {'field_code': fc, 'field_value': fv} for fc, fv in algorithm_params.items()
                        ]
                    elif isinstance(algorithm_params, list):
                        for p in algorithm_params:
                            if isinstance(p, dict):
                                fc = p.get('field_code') or p.get('fieldCode')
                                fv = p.get('field_value', p.get('fieldValue'))
                                if fc:
                                    round_algorithm_params.append({'field_code': fc, 'field_value': fv})
                    if round_algorithm_params:
                        algo_params_col = [{'round_number': 1, 'params': round_algorithm_params}]

                # 把 audio_name 替换为真实的 audio_id
                # 前端构建 rounds 时音频还没上传完，只能用文件名占位；
                # 后端按 audio_name 匹配当前音频，同时查库补全其他已入库音频的 audio_id
                # （多轮上传最后一个音频 mergeChunks 时，其他音频已入库，可从数据库查到）
                # 秒传场景下已有音频的 name 可能与前端传的 audio_name 不一致（之前上传时可能改名），
                # 所以额外用 original_filename 和 md5 兜底匹配
                audio_name_for_match = audio.name
                audio_original_for_match = getattr(audio, 'original_filename', None) or audio.name
                audio_md5_for_match = getattr(audio, 'md5', None) or ''
                log_not_emit('INFO', 'audio_controller', f'[DEBUG_MATCH] audio_id={audio_id}, audio.name={audio.name}, original_filename={audio_original_for_match}, md5={audio_md5_for_match}', category='audio')
                # 预查所有 audio_name → audio_id 映射（避免循环里重复查库）
                # 按 name / original_filename / md5 三重匹配
                audio_name_to_id = {}
                for round_item in rounds_resolved:
                    if not isinstance(round_item, dict):
                        continue
                    for audio_item in round_item.get('audios', []):
                        if not isinstance(audio_item, dict):
                            continue
                        item_name = audio_item.get('audio_name') or ''
                        if item_name and not audio_item.get('audio_id') and item_name not in audio_name_to_id:
                            # 查库：按文件名找已入库的音频
                            found = Audio.query.filter_by(name=item_name, deleted=False).first()
                            if not found:
                                # 按 original_filename 兜底
                                found = Audio.query.filter_by(original_filename=item_name, deleted=False).first()
                            if found:
                                audio_name_to_id[item_name] = found.id
                # 第一轮：按 name / original_filename / md5 / 预查映射 匹配
                unmatched_items = []
                for round_item in rounds_resolved:
                    if not isinstance(round_item, dict):
                        continue
                    audios = round_item.get('audios', [])
                    if not isinstance(audios, list):
                        round_item['audios'] = []
                        audios = []
                    for audio_item in audios:
                        if not isinstance(audio_item, dict):
                            continue
                        if audio_item.get('audio_id'):
                            log_not_emit('INFO', 'audio_controller', f'[DEBUG_MATCH] skip (already has audio_id): item_name={audio_item.get("audio_name")}', category='audio')
                            continue
                        item_name = audio_item.get('audio_name') or ''
                        log_not_emit('INFO', 'audio_controller', f'[DEBUG_MATCH] comparing item_name="{item_name}" == name="{audio_name_for_match}" / original="{audio_original_for_match}" / md5="{audio_md5_for_match}"', category='audio')
                        if (item_name == audio_name_for_match
                                or item_name == audio_original_for_match
                                or (audio_md5_for_match and item_name == audio_md5_for_match)
                                or not item_name):
                            audio_item['audio_id'] = audio_id
                            log_not_emit('INFO', 'audio_controller', f'[DEBUG_MATCH] MATCHED current: set audio_id={audio_id}', category='audio')
                        elif item_name in audio_name_to_id:
                            audio_item['audio_id'] = audio_name_to_id[item_name]
                            log_not_emit('INFO', 'audio_controller', f'[DEBUG_MATCH] MATCHED preload: set audio_id={audio_name_to_id[item_name]}', category='audio')
                        else:
                            unmatched_items.append(audio_item)
                            log_not_emit('WARNING', 'audio_controller', f'[DEBUG_MATCH] NO MATCH for item_name="{item_name}"', category='audio')
                # 第二轮兜底：剩余唯一未匹配项直接用当前 audio_id
                # （秒传场景下当前 audio_id 就是已有音频 ID，无论单轮多轮都适用）
                if len(unmatched_items) == 1:
                    unmatched_items[0]['audio_id'] = audio_id
                    log_not_emit('WARNING', 'audio_controller', f'[DEBUG_MATCH] FALLBACK sole-unmatched: set audio_id={audio_id} (name mismatch, sole unmatched item)', category='audio')

                # 从标注 JSON 提取 spl 和 playback_device_name，注入到每个 audio_item
                # 标注 segment 里可写 spl / playback_device_name / playback_device_id
                # playback_device_name 通过查表换成 playback_device_id
                # 四种模式都适用：单轮单音频、单轮多音频、多轮每轮单音频、多轮每轮多音频
                logger.info(f'raw_annotations is {"truthy" if raw_annotations else "falsy"}, len={len(raw_annotations) if raw_annotations else 0}')
                if raw_annotations:
                    # 预查设备名→ID 映射（避免循环里重复查库）
                    from backend.models.models import PlaybackDevice as _PlaybackDevice
                    dev_name_to_id = {}
                    all_devs = _PlaybackDevice.query.filter_by(is_deleted=0).all()
                    for d in all_devs:
                        dev_name_to_id.setdefault(d.name, d.id)

                    # 先从 rounds_config 里前端已传的 playback_device_name 查表换 ID
                    # （多轮场景下，非最后一个文件的标注不在 raw_annotations 里）
                    for round_item in rounds_resolved:
                        if not isinstance(round_item, dict):
                            continue
                        for audio_item in round_item.get('audios', []):
                            if not isinstance(audio_item, dict):
                                continue
                            if not audio_item.get('playback_device_id'):
                                dev_name = audio_item.get('playback_device_name')
                                if dev_name and dev_name in dev_name_to_id:
                                    audio_item['playback_device_id'] = dev_name_to_id[dev_name]

                    for round_item in rounds_resolved:
                        if not isinstance(round_item, dict):
                            continue
                        for audio_item in round_item.get('audios', []):
                            if not isinstance(audio_item, dict):
                                continue
                            need_spl = audio_item.get('spl') is None
                            need_dev = not audio_item.get('playback_device_id')
                            if not need_spl and not need_dev:
                                continue
                            for ann in raw_annotations:
                                data = ann.get('data')
                                if not isinstance(data, dict):
                                    continue
                                segments = data.get('segments', [])
                                if not isinstance(segments, list):
                                    continue
                                for seg in segments:
                                    if not isinstance(seg, dict):
                                        continue
                                    if need_spl and audio_item.get('spl') is None:
                                        v = seg.get('spl')
                                        if v is not None:
                                            try:
                                                audio_item['spl'] = float(v)
                                            except (TypeError, ValueError):
                                                audio_item['spl'] = v
                                            need_spl = False
                                    if need_dev and not audio_item.get('playback_device_id'):
                                        # 优先用 playback_device_name 查表
                                        dev_name = (
                                            seg.get('playback_device_name')
                                            or seg.get('playbackDeviceName')
                                        )
                                        if dev_name and dev_name in dev_name_to_id:
                                            audio_item['playback_device_id'] = dev_name_to_id[dev_name]
                                            need_dev = False
                                        # 也支持直接写 playback_device_id
                                        elif not dev_name:
                                            v = seg.get('playback_device_id') or seg.get('playbackDeviceId')
                                            if v:
                                                audio_item['playback_device_id'] = v
                                                need_dev = False
                                    if not need_spl and not need_dev:
                                        break
                                if not need_spl and not need_dev:
                                    break
                        # 兜底：e2e 且仍缺 playback_device_id，用默认设备
                        if tt == 'e2e':
                            for audio_item in round_item.get('audios', []):
                                if isinstance(audio_item, dict) and not audio_item.get('playback_device_id'):
                                    audio_item['playback_device_id'] = effective_playback_device_id
                                if isinstance(audio_item, dict) and audio_item.get('spl') is None:
                                    audio_item['spl'] = spl if spl else 65.0

                # 后端按 test_type + scope 从原始标注提取用例参数（不依赖前端提取）
                if algorithm_type and raw_annotations:
                    from backend.models.algorithm_models import CaseAlgorithmParam
                    case_params_list = CaseAlgorithmParam.query.filter_by(
                        algorithm_type=algorithm_type, deleted=False
                    ).all()
                    # 按 scope 过滤：只取匹配当前 test_type 的参数
                    scoped_params = [
                        p for p in case_params_list
                        if p.scope == 'common' or p.scope == tt
                    ]
                    if scoped_params:
                        for round_item in rounds_resolved:
                            if not isinstance(round_item, dict):
                                continue
                            round_audios = round_item.get('audios', [])
                            if not isinstance(round_audios, list):
                                continue
                            # 收集该 round 涉及的 audio_id
                            round_audio_ids = [
                                a.get('audio_id') for a in round_audios
                                if isinstance(a, dict) and a.get('audio_id')
                            ]
                            if not round_audio_ids:
                                continue
                            # 从原始标注提取用例参数
                            extracted_params = []
                            for param in scoped_params:
                                param_code = param.param_code
                                field_path = param.field_path or param_code
                                ann_code = param.annotation_code or algorithm_type
                                # 找匹配的标注
                                matched_anns = [a for a in raw_annotations if a.get('code') == ann_code]
                                if not matched_anns:
                                    matched_anns = raw_annotations
                                value = None
                                for ann in matched_anns:
                                    data = ann.get('data')
                                    if data is None:
                                        continue
                                    if isinstance(data, str):
                                        value = data
                                        break
                                    if isinstance(data, dict):
                                        # field_path 不含 '[]' 时，自动补 'segments[].' 前缀
                                        effective_fp = field_path
                                        if 'segments[]' not in effective_fp:
                                            effective_fp = f'segments[].{effective_fp}'
                                        if 'segments[]' in effective_fp:
                                            parts = effective_fp.split('[].')
                                            arr_key = parts[0]
                                            field_key = parts[1] if len(parts) > 1 else None
                                            # NamingRequest 已把驼峰转成下划线，尝试两种 key
                                            def _get_seg_field(seg, key):
                                                if seg.get(key) is not None:
                                                    return seg.get(key)
                                                # 尝试驼峰转下划线
                                                import re
                                                snake = re.sub(r'([A-Z])', r'_\1', key).lower()
                                                return seg.get(snake)
                                            arr = data.get(arr_key, [])
                                            if isinstance(arr, list) and field_key:
                                                collected = [
                                                    _get_seg_field(seg, field_key) for seg in arr
                                                    if isinstance(seg, dict) and _get_seg_field(seg, field_key) is not None
                                                ]
                                                if collected:
                                                    value = collected[0] if len(collected) == 1 else collected
                                                    break
                                                if value is not None:
                                                    break
                                if value is not None:
                                    extracted_params.append({
                                        'field_code': param_code,
                                        'field_value': value
                                    })
                            # 合并到 algo_params_col 中对应轮（前端传来的优先，后端提取的补缺）
                            round_number = round_item.get('round_number', 1)
                            # 找到 algo_params_col 中对应轮的记录
                            round_ap_entry = None
                            for entry in algo_params_col:
                                if entry.get('round_number') == round_number:
                                    round_ap_entry = entry
                                    break
                            if not round_ap_entry:
                                round_ap_entry = {'round_number': round_number, 'params': []}
                                algo_params_col.append(round_ap_entry)
                            existing_codes = set(
                                p.get('field_code') for p in round_ap_entry.get('params', [])
                            )
                            for p in extracted_params:
                                if p['field_code'] not in existing_codes:
                                    round_ap_entry.setdefault('params', []).append(p)
                                    existing_codes.add(p['field_code'])

                config = {
                    "source_audio": audio.name,
                    "auto_generated": True,
                    "rounds": rounds_resolved,
                }
                logger.debug(f'config rounds: {_json.dumps(config["rounds"], ensure_ascii=False)[:500]}')
                log_not_emit('INFO', 'audio_controller', f'[DEBUG_CONFIG] config rounds: {_json.dumps(config["rounds"], ensure_ascii=False)[:500]}', category='audio')
                # 噪声配置
                if (noise_spl and noise_spl > 0) or noise_audio_id:
                    config["background_noise"] = {
                        "audio_id": noise_audio_id,
                        "spl": noise_spl if noise_spl else 60.0
                    }
                # 评估维度：按当前 test_type 过滤
                # 前端给每条 dimension 加了 test_type 标记（'api'/'e2e'），
                # 没有 test_type 的视为通用维度，所有 test_type 都收
                # round_scope='single' 的维度写入 rounds[].evaluation.dimensions（每轮独立评估）
                # round_scope='multi' 的维度写入 config.dimensions（多轮聚合评估）
                if dimensions_data:
                    raw_dims = []
                    if isinstance(dimensions_data, dict):
                        raw_dims = dimensions_data.get('dimensions', [])
                    elif isinstance(dimensions_data, list):
                        raw_dims = dimensions_data
                    # 统一转换为 dict，确保 pydantic model 也能正确取 test_type
                    norm_dims = []
                    for d in raw_dims:
                        if isinstance(d, dict):
                            norm_dims.append(d)
                        elif hasattr(d, 'model_dump'):
                            norm_dims.append(d.model_dump(by_alias=False, exclude_none=True))
                        else:
                            norm_dims.append({'id': d})
                    filtered_dims = [
                        d for d in norm_dims
                        if not d.get('test_type') or d.get('test_type') == tt
                    ]
                    # 按 (id, round_scope) 组合去重
                    # 同一维度可以同时有 single 和 multi 两个 scope，分别写入不同位置
                    seen_keys = set()
                    unique_dims = []
                    for d in filtered_dims:
                        dim_id = d.get('id')
                        scope = d.get('round_scope', 'single')
                        key = (dim_id, scope)
                        if dim_id and key not in seen_keys:
                            seen_keys.add(key)
                            unique_dims.append(d)
                    # 按 round_scope 分发维度
                    single_round_dims = [d for d in unique_dims if d.get('round_scope', 'single') == 'single']
                    multi_round_dims = [d for d in unique_dims if d.get('round_scope') == 'multi']
                    # 单轮维度写入 rounds[].evaluation.dimensions
                    for round_item in rounds_resolved:
                        if isinstance(round_item, dict):
                            if 'evaluation' not in round_item:
                                round_item['evaluation'] = {}
                            round_item['evaluation']['dimensions'] = single_round_dims
                    # 多轮维度写入 config.dimensions（顶层聚合维度）
                    if multi_round_dims:
                        config['dimensions'] = multi_round_dims
                else:
                    # 确保 rounds 有 evaluation 结构
                    for round_item in rounds_resolved:
                        if isinstance(round_item, dict):
                            if 'evaluation' not in round_item:
                                round_item['evaluation'] = {}
                            if 'dimensions' not in round_item['evaluation']:
                                round_item['evaluation']['dimensions'] = []

                # 创建测试用例
                tc_id = str(uuid.uuid4())

                new_tc = TestCase(
                    id=tc_id,
                    name=test_case_name,
                    description=f"自动从音频 '{audio.name}' 创建的测试用例",
                    group_id=group.id,
                    test_type=tt,
                    algorithm_type=algorithm_type,
                    config=config,
                    algorithm_params=algo_params_col if algo_params_col else None
                )
                db.session.add(new_tc)
                log_not_emit('DEBUG', 'audio_controller', f'tc.algorithm_params={_json.dumps(algo_params_col, ensure_ascii=False)[:300]}', category='audio')
                log_not_emit('DEBUG', 'audio_controller', f'config.rounds[0] keys={list(config["rounds"][0].keys()) if config.get("rounds") else "no rounds"}', category='audio')
                # 继承音频的标签（受 inherit_tags 开关控制）
                if inherit_tags:
                    for tag_name in audio_tags:
                        tag = Tag.query.filter_by(name=tag_name).first()
                        if tag:
                            new_tc.tags.append(tag)

                # 同步生成参考参数（rounds 模式和平面模式都会真正生成文件）
                from backend.utils.algorithm.reference_params_generator import ReferenceParamsGenerator
                ReferenceParamsGenerator.apply_to_config(new_tc)
                log_not_emit('DEBUG', 'audio_controller', f'new_tc.algorithm_params={_json.dumps(new_tc.algorithm_params, ensure_ascii=False)[:300] if new_tc.algorithm_params else "None"}', category='audio')
                log_not_emit('DEBUG', 'audio_controller', f'new_tc.reference_params={_json.dumps(new_tc.reference_params, ensure_ascii=False)[:300] if new_tc.reference_params else "None"}', category='audio')
                log_not_emit('DEBUG', 'audio_controller', f'config.rounds[0] keys={list(config["rounds"][0].keys()) if config.get("rounds") else "no rounds"}', category='audio')

                created_tc_ids.append(tc_id)

            # 不在这里 commit，交给调用者统一提交
            db.session.flush()
            # 返回完整列表，调用方可获取真实创建用例数
            return created_tc_ids

    # URL 远程导入
    @staticmethod
    def url_import():
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
            from io import BytesIO
            file_content = BytesIO(response.content)
            file_content.filename = original_filename
            
            meta = AudioController._save_audio(file_content, "url_", relative_path=relative_path)
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

                from backend.utils.report.stats_cache import refresh_stats_cache
                refresh_stats_cache()
            
            return success_response({"id": new_audio.id, "name": new_audio.name}, "URL 导入成功", http_code=201)
        except Exception as e:
            db.session.rollback()
            return error_response(str(e))

    # 音频格式转换
    @staticmethod
    def convert(audio_id):
        audio = db.session.get(Audio, audio_id)
        if not audio:
            return error_response("未找到音频文件", 404)
        
        data = request.get_json()
        if not data:
            return error_response("请求体不能为空")
        
        try:
            validated = ConvertFormatRequest.model_validate(data)
        except ValidationError as e:
            return error_response(f"参数验证失败: {e}")
        
        target_format = validated.format.lower()
        
        try:
            # 1. 准备路径
            old_path = audio.file_path
            upload_dir = os.path.dirname(old_path)
            new_filename = f"conv_{uuid.uuid4().hex}.{target_format}"
            new_path = os.path.join(upload_dir, new_filename)

            # 2. 执行转换 (使用 pydub)
            audio_seg = AudioSegment.from_file(old_path)
            audio_seg.export(new_path, format=target_format)

            # 3. 更新数据库记录 (统一用正斜杠存储 file_path)
            audio.file_path = new_path.replace('\\', '/')
            audio.format = target_format
            audio.size = os.path.getsize(new_path)
            audio.updated_at = now_cst()
            
            db.session.commit()
            return success_response({
                "id": audio.id,
                "format": target_format,
                "file_path": get_relative_path(new_path)
            }, f"音频已成功转换为 {target_format}")
            
        except Exception as e:
            return error_response(f"转换失败: {str(e)}")

    # 元数据管理
    @staticmethod
    def update_metadata(audio_id):
        audio = db.session.get(Audio, audio_id)
        if not audio:
            return error_response("未找到音频文件", 404)
        
        data = request.get_json() or {}
        try:
            validated = UpdateMetadataRequest.model_validate(data)
        except ValidationError as e:
            return error_response(f"参数验证失败: {e}")
        
        try:
            if validated.name is not None:
                audio.name = validated.name
            if validated.audio_type is not None:
                audio.audio_type = validated.audio_type
            if validated.asr_text is not None:
                audio.asr_text = validated.asr_text
            if validated.description is not None:
                audio.description = validated.description
            if validated.source_language is not None:
                audio.source_language = validated.source_language
            
            if validated.tags is not None:
                AudioTag.query.filter_by(audio_id=audio_id).delete()
                
                if validated.tags:
                    tags = validated.tags.split(',')
                    for tag_name in tags:
                        tag_name = tag_name.strip()
                        if tag_name:
                            tag = Tag.query.filter_by(name=tag_name).first()
                            if not tag:
                                tag = Tag(name=tag_name)
                                db.session.add(tag)
                                db.session.flush()
                            
                            audio_tag = AudioTag(audio_id=audio_id, tag_id=tag.id)
                            db.session.add(audio_tag)
            
            if validated.annotations is not None:
                AudioAnnotation.query.filter_by(audio_id=audio_id).delete()

                for ann in validated.annotations:
                    ann_format = ann.get('format', 'json')
                    ann_data = ann.get('data', {})
                    ann_code = ann.get('code', '')
                    ann_source_lang = ann.get('source_language', '')
                    ann_target_lang = ann.get('target_language', '')

                    new_annotation = AudioAnnotation(
                        audio_id=audio_id,
                        format=ann_format,
                        code=ann_code,
                        data=ann_data,
                        source_language=ann_source_lang,
                        target_language=ann_target_lang
                    )
                    db.session.add(new_annotation)

            audio.updated_at = now_cst()
            db.session.commit()
            return success_response(None, "元数据更新成功")
        except Exception as e:
            db.session.rollback()
            return error_response(str(e))

    # 批量更新标注
    @staticmethod
    def batch_update_annotations():
        """批量更新音频标注，可选刷新关联测试用例的参数和参考参数。

        前端按文件名匹配已入库音频，构建 [{audio_id, annotations}] 列表提交。
        后端逐个写标注（同 code 覆盖），然后按 audio_id 反查 TestCase 刷新。
        """
        data = request.get_json()
        if not data:
            return error_response("请求体不能为空")

        try:
            validated = BatchUpdateAnnotationsRequest.model_validate(data)
        except ValidationError as e:
            return error_response(f"参数验证失败: {e}")

        if not validated.items:
            return error_response("标注列表不能为空")

        algorithm_type = validated.algorithm_type
        refresh_test_cases = validated.refresh_test_cases

        updated_audio_ids = []
        updated_count = 0
        failed_count = 0
        refreshed_tc_ids = []

        try:
            for item in validated.items:
                audio_id = item.audio_id
                annotations = item.annotations
                if not annotations:
                    continue

                audio = db.session.get(Audio, audio_id)
                if not audio:
                    failed_count += 1
                    continue

                # 复用已有的持久化逻辑：写标注 + 返回 raw_annotations
                AudioController._persist_annotations_and_raw(
                    audio_id, annotations, algorithm_type
                )
                updated_audio_ids.append(audio_id)
                updated_count += 1

            db.session.flush()

            # 刷新关联测试用例
            if refresh_test_cases and updated_audio_ids:
                refreshed_tc_ids = AudioController._refresh_test_cases_for_audios(
                    updated_audio_ids, algorithm_type
                )

            db.session.commit()

            return success_response({
                "updated_count": updated_count,
                "failed_count": failed_count,
                "refreshed_test_case_ids": refreshed_tc_ids,
            }, f"批量更新标注成功，更新 {updated_count} 个音频，刷新 {len(refreshed_tc_ids)} 个用例")
        except Exception as e:
            db.session.rollback()
            import traceback
            from backend.utils.web.log_handler import log_and_emit
            log_and_emit(
                level='error',
                module='audio_controller',
                content=f'批量更新标注失败: {str(e)}\n{traceback.format_exc()}',
                category='audio',
            )
            return error_response(str(e))

    @staticmethod
    def _refresh_test_cases_for_audios(audio_ids, algorithm_type=None):
        """按 audio_id 反查 config.rounds[].audios[].audio_id 关联的 TestCase，
        重新提取用例参数并刷新参考参数。

        Returns: 刷新的 TestCase id 列表
        """
        import json as _json
        from backend.models.algorithm_models import CaseAlgorithmParam

        # 查所有未删除的 TestCase，过滤出 config.rounds 中包含目标 audio_id 的
        all_tcs = TestCase.query.filter_by(deleted=False).all()
        target_ids = set(audio_ids)
        affected_tcs = []

        for tc in all_tcs:
            config = tc.config or {}
            rounds = config.get('rounds', [])
            if not isinstance(rounds, list):
                continue
            found = False
            for round_item in rounds:
                if not isinstance(round_item, dict):
                    continue
                for audio_item in round_item.get('audios', []):
                    if isinstance(audio_item, dict) and audio_item.get('audio_id') in target_ids:
                        found = True
                        break
                if found:
                    break
            if found:
                affected_tcs.append(tc)

        if not affected_tcs:
            return []

        refreshed_ids = []
        for tc in affected_tcs:
            tc_algo_type = algorithm_type or tc.algorithm_type
            # 重新提取用例参数
            if tc_algo_type:
                case_params_list = CaseAlgorithmParam.query.filter_by(
                    algorithm_type=tc_algo_type, deleted=False
                ).all()
                tc_test_type = tc.test_type or 'api'
                scoped_params = [
                    p for p in case_params_list
                    if p.scope == 'common' or p.scope == tc_test_type
                ]

                if scoped_params:
                    # 收集该用例所有轮的 audio_id → annotation 映射
                    config = tc.config or {}
                    rounds = config.get('rounds', [])
                    algo_params_col = tc.algorithm_params or []

                    for round_item in rounds:
                        if not isinstance(round_item, dict):
                            continue
                        round_number = round_item.get('round_number', 1)
                        round_audios = round_item.get('audios', [])
                        if not isinstance(round_audios, list):
                            continue

                        round_audio_ids = [
                            a.get('audio_id') for a in round_audios
                            if isinstance(a, dict) and a.get('audio_id')
                        ]
                        if not round_audio_ids:
                            continue

                        # 从数据库查这些音频的最新标注
                        raw_anns = []
                        for aid in round_audio_ids:
                            anns = AudioAnnotation.query.filter_by(
                                audio_id=aid, deleted=False
                            ).all()
                            for ann in anns:
                                raw_anns.append({
                                    'code': ann.code,
                                    'data': ann.data,
                                })

                        if not raw_anns:
                            continue

                        # 提取参数（复用 _create_test_case_from_audio 中的逻辑）
                        extracted_params = []
                        for param in scoped_params:
                            param_code = param.param_code
                            field_path = param.field_path or param_code
                            ann_code = param.annotation_code or tc_algo_type
                            matched_anns = [a for a in raw_anns if a.get('code') == ann_code]
                            if not matched_anns:
                                matched_anns = raw_anns
                            value = None
                            for ann in matched_anns:
                                a_data = ann.get('data')
                                if a_data is None:
                                    continue
                                if isinstance(a_data, str):
                                    value = a_data
                                    break
                                if isinstance(a_data, dict):
                                    effective_fp = field_path
                                    if 'segments[]' not in effective_fp:
                                        effective_fp = f'segments[].{effective_fp}'
                                    if 'segments[]' in effective_fp:
                                        parts = effective_fp.split('[].')
                                        arr_key = parts[0]
                                        field_key = parts[1] if len(parts) > 1 else None
                                        def _get_seg_field(seg, key):
                                            if seg.get(key) is not None:
                                                return seg.get(key)
                                            import re
                                            snake = re.sub(r'([A-Z])', r'_\1', key).lower()
                                            return seg.get(snake)
                                        arr = a_data.get(arr_key, [])
                                        if isinstance(arr, list) and field_key:
                                            collected = [
                                                _get_seg_field(seg, field_key) for seg in arr
                                                if isinstance(seg, dict) and _get_seg_field(seg, field_key) is not None
                                            ]
                                            if collected:
                                                value = collected[0] if len(collected) == 1 else collected
                                                break
                            if value is not None:
                                extracted_params.append({
                                    'field_code': param_code,
                                    'field_value': value
                                })

                        # 合并到 algo_params_col 中对应轮（保留已有参数，补缺新提取的）
                        round_ap_entry = None
                        for entry in algo_params_col:
                            if entry.get('round_number') == round_number:
                                round_ap_entry = entry
                                break
                        if not round_ap_entry:
                            round_ap_entry = {'round_number': round_number, 'params': []}
                            algo_params_col.append(round_ap_entry)
                        existing_codes = set(
                            p.get('field_code') for p in round_ap_entry.get('params', [])
                        )
                        for p in extracted_params:
                            if p['field_code'] not in existing_codes:
                                round_ap_entry.setdefault('params', []).append(p)
                                existing_codes.add(p['field_code'])

                    tc.algorithm_params = algo_params_col

            # 刷新参考参数
            try:
                from backend.controllers.testcase_controller import TestCaseController
                TestCaseController.refresh_reference_texts(tc)
                refreshed_ids.append(tc.id)
            except Exception as e:
                logger.warning(f'刷新用例 {tc.id} 参考参数失败: {e}')

        return refreshed_ids

    # 批量操作
    @staticmethod
    def batch_action():
        data = request.get_json()
        if not data:
            return error_response("请求体不能为空")
        
        try:
            validated = BatchActionRequest.model_validate(data)
        except ValidationError as e:
            return error_response(f"参数验证失败: {e}")
        
        audio_ids = validated.audio_ids
        action = validated.action
        
        try:
            if action == 'delete':
                # 批量删除音频文件
                from backend.models.models import TestCase, Device, Task, AudioAnnotation, AudioTag
                import os
                
                # 收集可删除的音频ID和被引用的音频ID
                deletable_audio_ids = []
                skipped_audio_ids = []
                
                # 检查每个音频文件是否被引用
                for audio_id in audio_ids:
                    is_referenced = False
                    
                    # 1. 检查测试用例音频关联（在config.audios中）
                    test_case_count = TestCase.query.filter(
                        TestCase.deleted == False,
                        cast(TestCase.config, String).like(f'%"audio_id": {audio_id}%')
                    ).count()
                    if test_case_count > 0:
                        skipped_audio_ids.append(audio_id)
                        continue
                    
                    # 2. 检查测试用例背景噪音引用（在config.background_noise中）
                    test_case_noise_count = TestCase.query.filter(
                        TestCase.deleted == False,
                        cast(TestCase.config, String).like(f'%"background_noise": {{"audio_id": {audio_id}}}%')
                    ).count()
                    if test_case_noise_count > 0:
                        skipped_audio_ids.append(audio_id)
                        continue
                    
                    # 3. 检查设备提示词音频引用
                    device_count = Device.query.filter(
                        cast(Device.prompt_config, String).like(f'%{audio_id}%'),
                        Device.deleted == False
                    ).count()
                    if device_count > 0:
                        skipped_audio_ids.append(audio_id)
                        continue
                    
                    # 4. 检查任务配置中的音频引用
                    task_count = Task.query.filter(
                        cast(Task.config, String).like(f'%{audio_id}%'),
                        Task.deleted == False
                    ).count()
                    if task_count > 0:
                        skipped_audio_ids.append(audio_id)
                        continue
                    
                    # 如果没有被引用，添加到可删除列表
                    deletable_audio_ids.append(audio_id)
                
                # 如果没有可删除的音频，返回提示
                if not deletable_audio_ids:
                    return success_response(None, "没有可删除的音频文件，所有音频都被其他资源引用")
                
                # 获取所有要删除的音频文件
                audios = Audio.query.filter(Audio.id.in_(deletable_audio_ids)).all()
                
                for audio in audios:
                    # 物理删除音频文件
                    if os.path.exists(audio.file_path):
                        os.remove(audio.file_path)
                    
                    # 删除关联的标注
                    AudioAnnotation.query.filter_by(audio_id=audio.id).delete()
                    
                    # 删除关联的音频标签
                    AudioTag.query.filter_by(audio_id=audio.id).delete()
                
                # 删除音频文件记录
                Audio.query.filter(Audio.id.in_(deletable_audio_ids)).delete(synchronize_session=False)
                
                # 构建返回信息
                message = f"成功删除 {len(deletable_audio_ids)} 个音频文件"
                if skipped_audio_ids:
                    message += f"，跳过了 {len(skipped_audio_ids)} 个被引用的音频文件"
            elif action == 'export':
                # 批量导出为 ZIP
                import zipfile
                from io import BytesIO
                
                audios = Audio.query.filter(Audio.id.in_(audio_ids)).all()
                memory_file = BytesIO()
                with zipfile.ZipFile(memory_file, 'w') as zf:
                    for audio in audios:
                        if os.path.exists(audio.file_path):
                            zf.write(audio.file_path, audio.original_filename)
                
                memory_file.seek(0)
                return send_file(
                    memory_file,
                    mimetype='application/zip',
                    as_attachment=True,
                    download_name=f'audios_export_{now_cst().strftime("%Y%m%d%H%M%S")}.zip'
                )
            elif action == 'tags':
                tags = validated.tags
                for audio_id in audio_ids:
                    audio = db.session.get(Audio, audio_id)
                    if audio:
                        # 清空旧标签并添加新标签 (简化处理)
                        from backend.models.models import AudioTag, Tag
                        AudioTag.query.filter_by(audio_id=audio_id).delete()
                        for tag_name in tags:
                            tag = Tag.query.filter_by(name=tag_name).first()
                            if not tag:
                                tag = Tag(name=tag_name)
                                db.session.add(tag)
                                db.session.flush()
                            db.session.add(AudioTag(audio_id=audio_id, tag_id=tag.id))
            
            db.session.commit()
            if action == 'delete':
                return success_response(None, message)
            else:
                return success_response(None, f"批量操作 {action} 执行成功")
        except Exception as e:
            db.session.rollback()
            return error_response(str(e))

    # 音频流式播放 (支持 Range 请求)
    @staticmethod
    def stream(audio_id):
        # 尝试作为音频ID查询
        audio = db.session.get(Audio, audio_id)
        
        # 如果不是音频ID，尝试作为测试用例ID查询
        if not audio or audio.deleted:
            # 查询测试用例
            test_case = TestCase.query.filter_by(id=audio_id, deleted=False).first()
            if test_case:
                # 从测试用例配置中提取音频ID
                config = test_case.config or {}
                audios_config = config.get('audios', [])
                
                # 获取任务类型参数，默认为 'api'
                task_type = request.args.get('task_type', 'api')
                tc_test_type = test_case.test_type or 'api'
                
                # 记录的 test_type 匹配则取第一个有效音频
                if tc_test_type == task_type:
                    target_audio_config = next((c for c in audios_config if c.get('audio_id')), None)
                    if target_audio_config:
                        target_audio_id = target_audio_config.get('audio_id')
                        if target_audio_id:
                            # 使用目标音频ID重新查询音频
                            audio = db.session.get(Audio, target_audio_id)
        
        # 检查最终音频是否存在
        if not audio or audio.deleted:
            return error_response("音频不存在", 404)
        
        path = audio.file_path
        if not os.path.exists(path):
            return error_response("音频文件已从磁盘移除", 404)

        file_size = os.path.getsize(path)
        range_header = request.headers.get('Range', None)
        
        if not range_header:
            return send_file(path, mimetype=f"audio/{audio.format or 'wav'}", as_attachment=True, download_name=audio.name or f"audio_{audio_id}.{audio.format or 'wav'}")

        # 处理 Range 请求: bytes=start-end
        import re
        match = re.search(r'bytes=(\d+)-(\d*)', range_header)
        if not match:
            return send_file(path, mimetype=f"audio/{audio.format or 'wav'}", as_attachment=True, download_name=audio.name or f"audio_{audio_id}.{audio.format or 'wav'}")

        start = int(match.group(1))
        end = match.group(2)
        end = int(end) if end else file_size - 1

        if start >= file_size:
            return Response("Range Not Satisfiable", status=416)

        chunk_size = end - start + 1
        
        def generate():
            with open(path, 'rb') as f:
                f.seek(start)
                remaining = chunk_size
                while remaining > 0:
                    read_size = min(remaining, 1024 * 64)
                    data = f.read(read_size)
                    if not data:
                        break
                    yield data
                    remaining -= len(data)

        rv = Response(generate(), 206, mimetype=f"audio/{audio.format or 'wav'}", direct_passthrough=True)
        rv.headers.add('Content-Range', f'bytes {start}-{end}/{file_size}')
        rv.headers.add('Accept-Ranges', 'bytes')
        rv.headers.add('Content-Length', str(chunk_size))
        return rv

    @staticmethod
    def stream_by_path():
        path = request.args.get('path')
        if not path:
            return error_response("未提供路径", 400)
            
        if not os.path.exists(path):
            return error_response("文件不存在", 404)

        # 安全检查：确保路径在允许的目录下（例如音频存储目录或任务结果目录）
        # 这里为了简化，仅检查是否存在。在生产环境中应加强检查。
        
        file_size = os.path.getsize(path)
        ext = os.path.splitext(path)[1].lower().replace('.', '')
        if not ext:
            ext = 'wav'
        mimetype = f"audio/{ext}"
        
        range_header = request.headers.get('Range', None)
        if not range_header:
            return send_file(path, mimetype=mimetype)
            
        # 处理 Range 请求: bytes=start-end
        import re
        match = re.search(r'bytes=(\d+)-(\d*)', range_header)
        if not match:
            return send_file(path, mimetype=mimetype)

        start = int(match.group(1))
        end = match.group(2)
        end = int(end) if end else file_size - 1

        if start >= file_size:
            return Response("Range Not Satisfiable", status=416)

        chunk_size = end - start + 1
        
        def generate():
            with open(path, 'rb') as f:
                f.seek(start)
                remaining = chunk_size
                while remaining > 0:
                    read_size = min(remaining, 1024 * 64)
                    data = f.read(read_size)
                    if not data:
                        break
                    yield data
                    remaining -= len(data)

        rv = Response(generate(), 206, mimetype=mimetype, direct_passthrough=True)
        rv.headers.add('Content-Range', f'bytes {start}-{end}/{file_size}')
        rv.headers.add('Accept-Ranges', 'bytes')
        rv.headers.add('Content-Length', str(chunk_size))
        return rv

    # 试听音频 (前端或后端播放)
    @staticmethod
    def preview(audio_id):
        if has_running_e2e_tasks():
            return error_response("当前有待执行的E2E测试任务，不允许使用后端扬声器播放", code=403)
        
        # 尝试两种可能性：1. 直接作为音频ID查找 2. 作为测试用例ID查找
        try:
            # 1. 首先尝试作为音频ID查找
            audio = db.session.get(Audio, audio_id)
            
            if not audio or audio.deleted:
                # 2. 如果不是音频ID，尝试作为测试用例ID查找
                from backend.models.models import TestCase
                test_case = db.session.get(TestCase, audio_id)
                
                if test_case and not test_case.deleted:
                    # 从测试用例配置中提取音频ID
                    config = test_case.config or {}
                    audios = config.get('audios', [])
                    if audios:
                        # 取第一个音频作为预览音频
                        audio_item = audios[0]
                        actual_audio_id = audio_item.get('audio_id')
                        if actual_audio_id:
                            audio = db.session.get(Audio, actual_audio_id)
        except Exception as e:
            import logging
            logging.error(f"Error resolving audio for preview: {str(e)}", exc_info=True)
        
        if not audio or audio.deleted:
            return error_response("音频不存在", 404)
        
        try:
            validated = BatchPlaybackRequest.model_validate(request.get_json() or {})
        except ValidationError as e:
            return error_response(f"参数验证失败: {e}")
        
        playback_device_id = validated.playback_device_id
        playback_device_ids = validated.playback_device_ids or []
        device_unique_ids = validated.device_unique_ids or []
        
        spl = validated.spl
        offset = validated.offset
        
        # 统一处理设备ID，确保playback_device_ids是数组
        if playback_device_id:
            playback_device_ids = [playback_device_id] + playback_device_ids
        
        # 去重
        playback_device_ids = list(set(playback_device_ids))
        device_unique_ids = list(set(device_unique_ids))
        
        # 无论是否提供设备ID，都使用后端硬件播放
        try:
            from backend.services.audio.audio_engine import audio_service
            from backend.models.models import PlaybackDevice, SPLMapping
            
            # 设备信息
            device_names = []
            gains = []
            
            # 确定要使用的设备列表，统一处理所有音频类型
            devices_to_use = []
            
            if device_unique_ids:
                # 如果前端指定了deviceUniqueIds，使用指定的设备
                for device_uid in device_unique_ids:
                    device = PlaybackDevice.query.filter_by(device_unique_id=device_uid, is_deleted=0).first()
                    if device:
                        devices_to_use.append(device)
            elif playback_device_ids:
                # 兼容旧版，使用playback_device_ids，同时支持扫描设备格式
                for device_id in playback_device_ids:
                    device = None
                    # 扫描设备使用 device_name（字符串），数据库设备使用数字ID
                    if isinstance(device_id, str):
                        # 扫描设备格式：使用 device_unique_id 查询
                        device = PlaybackDevice.query.filter_by(device_unique_id=device_id, is_deleted=0).first()
                    else:
                        # 数据库ID格式：通过主键查询
                        device = db.session.get(PlaybackDevice, device_id)
                    
                    if device and not device.is_deleted:
                        devices_to_use.append(device)
            else:
                # 如果前端没有指定设备，使用默认设备
                default_device = type('obj', (object,), {
                    'name': '默认设备',
                    'device_unique_id': '',
                    'channel_index': 0,
                    'current_spl_mapping_id': None
                })
                devices_to_use.append(default_device)
            
            # 循环处理所有设备
            for device in devices_to_use:
                device_name = device.name
                device_unique_id = getattr(device, 'device_unique_id', '')
                channel_index = getattr(device, 'channel_index', 0)
                gain = 1.0
                
                # 计算音量/增益
                if spl and getattr(device, 'current_spl_mapping_id', None):
                    from backend.services.audio.spl_service import spl_service
                    gain = spl_service.spl_to_gain(device.current_spl_mapping_id, spl)
                
                # 获取物理设备索引
                device_index = 0
                if device_unique_id:
                    device_index = audio_service.get_device_index(device_unique_id)
                    if device_index is None:
                        continue  # 跳过无法定位的设备，继续处理其他设备
                
                # 触发播放指令，统一播放器类型命名
                player_type = f'ch_{getattr(device, "id", "default")}'
                audio_service.play_audio(
                    task_id=f"preview_{audio.id}_{getattr(device, 'id', 'default')}",
                    file_path=audio.file_path,
                    device_index=device_index,
                    channel_index=channel_index,
                    gain=gain,
                    player_type=player_type,
                    offset=offset
                )
                
                device_names.append(device_name)
                gains.append(round(gain, 4))
            
            if not device_names:
                return error_response("没有找到可用的播放设备", 404)
            
            # 构建响应，兼容旧版和新版前端
            response_data = {
                "audio": audio.name,
                "duration": audio.duration
            }
            
            # 兼容旧版前端，保留device和gain字段
            if device_names:
                response_data["device"] = device_names[0]
                response_data["gain"] = gains[0]
            
            # 新版前端使用devices和gains数组
            response_data["devices"] = device_names
            response_data["gains"] = gains
            
            return success_response(
                response_data,
                f"已在 {len(device_names)} 个设备上开始试听"
            )
        except Exception as e:
            import logging
            logging.error(f"Audio preview error: {str(e)}", exc_info=True)
            return error_response(f"硬件播放失败: {str(e)}")
    
    # 停止音频试听
    @staticmethod
    def stop_preview(audio_id):
        try:
            from backend.services.audio.audio_engine import audio_service
            
            # 解析实际的音频ID（与preview方法相同的逻辑）
            actual_audio_id = audio_id
            
            try:
                # 1. 首先尝试作为音频ID查找
                audio = db.session.get(Audio, audio_id)
                
                if not audio or audio.deleted:
                    # 2. 如果不是音频ID，尝试作为测试用例ID查找
                    from backend.models.models import TestCase
                    test_case = db.session.get(TestCase, audio_id)
                    
                    if test_case and not test_case.deleted:
                        # 从测试用例配置中提取音频ID
                        config = test_case.config or {}
                        audios = config.get('audios', [])
                        if audios:
                            # 取第一个音频作为预览音频
                            audio_item = audios[0]
                            resolved_audio_id = audio_item.get('audio_id')
                            if resolved_audio_id:
                                actual_audio_id = resolved_audio_id
            except Exception as e:
                import logging
                logging.error(f"Error resolving audio for stop_preview: {str(e)}", exc_info=True)
            
            # 构建task_id前缀
            task_id_prefix = f"preview_{actual_audio_id}"
            
            # 使用前缀匹配所有相关的task_id，而不是精确匹配
            import logging
            logging.debug(f"Stopping preview for audio_id: {audio_id}, actual_audio_id: {actual_audio_id}, task_id_prefix: {task_id_prefix}")
            logging.debug(f"Active players before: {list(audio_service.active_players.keys())}")
            
            # 遍历所有活跃的播放器，停止所有匹配前缀的任务
            stopped_tasks = []
            for task_id in list(audio_service.active_players.keys()):
                if task_id.startswith(task_id_prefix):
                    audio_service.stop_task_audio(task_id)
                    stopped_tasks.append(task_id)
            
            logging.debug(f"Active players after: {list(audio_service.active_players.keys())}")
            logging.debug(f"Stopped tasks: {stopped_tasks}")
            
            if stopped_tasks:
                return success_response(None, f"音频试听已停止，共停止了 {len(stopped_tasks)} 个任务")
            else:
                return success_response(None, f"没有找到正在播放的任务")
        except Exception as e:
            import logging
            logging.error(f"Stop audio preview error: {str(e)}", exc_info=True)
            return error_response(f"停止试听失败: {str(e)}")


    # 删除音频文件（逻辑删除）
    @staticmethod
    def delete(audio_id):
        audio = db.session.get(Audio, audio_id)
        if not audio:
            return error_response("未找到音频文件", 404)
        
        try:
            # 检查是否有其他实体引用该音频文件
            # 1. 检查测试用例音频关联（在config.audios中）
            test_case_count = TestCase.query.filter(
                TestCase.deleted == False,
                cast(TestCase.config, String).like(f'%"audio_id": {audio_id}%')
            ).count()
            if test_case_count > 0:
                return error_response("该音频文件已被测试用例使用，禁止删除", 400)
            
            # 2. 检查测试用例背景噪音引用
            test_case_noise_count = TestCase.query.filter(
                TestCase.deleted == False,
                cast(TestCase.config, String).like(f'%"background_noise": {{"audio_id": {audio_id}}}%')
            ).count()
            if test_case_noise_count > 0:
                return error_response("该音频文件已被测试用例作为背景噪音使用，禁止删除", 400)
            
            # 3. 检查设备提示词音频引用
            from backend.models.models import Device
            device_count = Device.query.filter(
                cast(Device.prompt_config, String).like(f'%{audio_id}%'),
                Device.deleted == False
            ).count()
            if device_count > 0:
                return error_response("该音频文件已被设备作为提示词使用，禁止删除", 400)
            
            # 4. 检查任务配置中的音频引用
            from backend.models.models import Task
            task_count = Task.query.filter(
                cast(Task.config, String).like(f'%{audio_id}%'),
                Task.deleted == False
            ).count()
            if task_count > 0:
                return error_response("该音频文件已被任务使用，禁止删除", 400)
            
            # 物理删除音频文件
            import os
            if os.path.exists(audio.file_path):
                os.remove(audio.file_path)
            
            # 删除关联的标注
            from backend.models.models import AudioAnnotation
            AudioAnnotation.query.filter_by(audio_id=audio_id).delete()
            
            # 删除关联的音频标签
            from backend.models.models import AudioTag
            AudioTag.query.filter_by(audio_id=audio_id).delete()
            
            # 删除音频文件记录
            db.session.delete(audio)
            db.session.commit()

            from backend.utils.report.stats_cache import refresh_stats_cache
            refresh_stats_cache()

            return success_response(None, "音频文件已删除")
        except Exception as e:
            db.session.rollback()
            return error_response(str(e))

    # 获取音频关联的算法
    @staticmethod
    def get_audio_algorithms(audio_id):
        try:
            from backend.models.models import AudioAlgorithmRelation
            audio = db.session.get(Audio, audio_id)
            if not audio or audio.deleted:
                return error_response("音频不存在", 404)
            
            relations = AudioAlgorithmRelation.query.filter_by(
                audio_id=audio_id, deleted=False
            ).all()
            
            return success_response([r.to_dict() for r in relations])
        except Exception as e:
            return error_response(str(e))

    # 更新音频关联的算法
    @staticmethod
    def update_audio_algorithms(audio_id):
        try:
            from backend.models.models import AudioAlgorithmRelation
            from backend.schemas.audio import UpdateAudioAlgorithmsRequest
            
            audio = db.session.get(Audio, audio_id)
            if not audio or audio.deleted:
                return error_response("音频不存在", 404)
            
            data = request.get_json() or {}
            try:
                validated = UpdateAudioAlgorithmsRequest.model_validate(data)
            except Exception as e:
                return error_response(f"参数验证失败: {e}")
            
            AudioAlgorithmRelation.query.filter_by(audio_id=audio_id).update({'deleted': True})
            
            for item in validated.algorithms:
                relation = AudioAlgorithmRelation(
                    audio_id=audio_id,
                    algorithm_type=item.algorithm_type,
                    is_primary=item.is_primary,
                    weight=item.weight,
                    params=item.params
                )
                db.session.add(relation)
            
            db.session.commit()
            return success_response(None, "算法关联更新成功")
        except Exception as e:
            db.session.rollback()
            return error_response(str(e))

    # 批量更新音频算法关联
    @staticmethod
    def batch_update_audio_algorithms():
        try:
            from backend.models.models import AudioAlgorithmRelation
            from backend.schemas.audio import BatchUpdateAudioAlgorithmsRequest
            
            data = request.get_json() or {}
            try:
                validated = BatchUpdateAudioAlgorithmsRequest.model_validate(data)
            except Exception as e:
                return error_response(f"参数验证失败: {e}")
            
            audio_ids = validated.audio_ids
            algorithms = validated.algorithms
            
            updated_count = 0
            for audio_id in audio_ids:
                audio = db.session.get(Audio, audio_id)
                if not audio or audio.deleted:
                    continue
                
                AudioAlgorithmRelation.query.filter_by(audio_id=audio_id).update({'deleted': True})
                
                for item in algorithms:
                    relation = AudioAlgorithmRelation(
                        audio_id=audio_id,
                        algorithm_type=item.algorithm_type,
                        is_primary=item.is_primary,
                        weight=item.weight,
                        params=item.params
                    )
                    db.session.add(relation)
                updated_count += 1
            
            db.session.commit()
            return success_response({"updated_count": updated_count}, f"成功更新 {updated_count} 个音频的算法关联")
        except Exception as e:
            db.session.rollback()
            return error_response(str(e))

    @staticmethod
    def folder_import():
        """
        文件夹批量导入（服务端扫描指定目录）
        请求体: { path: str, recursive: bool, createTestCase: bool, ... }
        当前为占位实现，前端暂未调用。
        """
        return error_response('文件夹批量导入接口尚未实现，请使用逐文件上传接口', 501)

    @staticmethod
    def get_folder_tree():
        """
        获取音频文件夹树结构（支持筛选、懒加载）
        服务端计算文件夹树，支持大数据量
        """
        data = request.get_json() or {}

        # NamingRequest already normalizes camelCase → snake_case,
        # so data.get('audio_type') works; keep fallback for safety.
        keyword = data.get('keyword')
        audio_type = data.get('audio_type')
        format_ = data.get('format')
        sample_rate = data.get('sample_rate')
        duration = data.get('duration')
        tags_data = data.get('tags', [])
        direction = data.get('direction')
        algorithm_type = data.get('algorithm_type')
        parent_path = data.get('parent_path', '')
        depth = data.get('depth', 1)

        query = Audio.query.filter_by(deleted=False)

        if keyword:
            query = query.filter(
                (Audio.name.like(f'%{keyword}%')) |
                (Audio.original_filename.like(f'%{keyword}%')) |
                (Audio.asr_text.like(f'%{keyword}%'))
            )

        if audio_type:
            query = query.filter_by(audio_type=audio_type)
        if format_:
            query = query.filter_by(format=format_)
        if sample_rate:
            query = query.filter(Audio.sample_rate.between(sample_rate - 100, sample_rate + 100))
        if direction:
            query = query.filter(Audio.source_language == direction)

        if duration:
            if duration == 'short':
                query = query.filter(Audio.duration <= 30)
            elif duration == 'medium':
                query = query.filter(Audio.duration > 30, Audio.duration <= 300)
            elif duration == 'long':
                query = query.filter(Audio.duration > 300)

        if tags_data:
            or_tags = []
            and_tags = []

            for t in tags_data:
                if isinstance(t, dict):
                    tag_name = t.get('name', '')
                    mode = t.get('mode', 'and')
                    if tag_name:
                        if mode == 'or':
                            or_tags.append(tag_name)
                        else:
                            and_tags.append(tag_name)
                elif isinstance(t, str):
                    and_tags.append(t)

            if or_tags:
                or_audio_ids = (
                    db.session.query(AudioTag.audio_id)
                    .join(Tag, Tag.id == AudioTag.tag_id)
                    .filter(Tag.name.in_(or_tags))
                    .distinct()
                )
                query = query.filter(Audio.id.in_(or_audio_ids))

            if and_tags:
                and_tag_ids = (
                    db.session.query(Tag.id)
                    .filter(Tag.name.in_(and_tags))
                    .subquery()
                )
                audio_tag_counts = (
                    db.session.query(AudioTag.audio_id, db.func.count(AudioTag.tag_id).label('tag_count'))
                    .filter(AudioTag.tag_id.in_(db.session.query(and_tag_ids)))
                    .group_by(AudioTag.audio_id)
                    .subquery()
                )
                query = query.join(audio_tag_counts, audio_tag_counts.c.audio_id == Audio.id).filter(audio_tag_counts.c.tag_count == len(and_tags))

        if algorithm_type:
            from backend.models.models import AudioAlgorithmRelation
            audio_ids_with_algo = (
                db.session.query(AudioAlgorithmRelation.audio_id)
                .filter(AudioAlgorithmRelation.algorithm_type == algorithm_type, AudioAlgorithmRelation.deleted == False)
                .distinct()
            )
            query = query.filter(Audio.id.in_(audio_ids_with_algo))

        # Lazy loading: when parent_path is provided, only query files under that path.
        # 数据库中 file_path 可能用 Windows 反斜杠 (\) 或正斜杠 (/) 存储，
        # 用 func.replace 统一转成正斜杠再匹配，避免 escape 字符导致的语义问题。
        if parent_path:
            normalized_parent = parent_path.replace(chr(92), '/')
            escaped = normalized_parent.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
            normalized_path_expr = func.replace(Audio.file_path, chr(92), '/')
            query = query.filter(
                normalized_path_expr.like(f'%{escaped}/%', escape='\\')
            )

        # Only load the columns needed for tree building (performance)
        audios = query.with_entities(
            Audio.id, Audio.name, Audio.original_filename, Audio.file_path,
            Audio.format, Audio.duration, Audio.size, Audio.audio_type, Audio.created_at
        ).order_by(Audio.file_path).all()

        # Compute the base storage path prefix for reliable folder key extraction
        audio_storage_path = current_app.config.get('AUDIO_STORAGE_PATH', '')
        base_normalized = audio_storage_path.replace(chr(92), '/').rstrip('/')

        def get_folder_key(file_path):
            """Extract folder hierarchy relative to the audio storage root."""
            normalized = file_path.replace(chr(92), '/') if file_path else ''
            parts = [p for p in normalized.split('/') if p]

            # Strategy 1: strip configured AUDIO_STORAGE_PATH prefix (most reliable)
            if base_normalized and normalized.startswith(base_normalized + '/'):
                relative = normalized[len(base_normalized) + 1:]
                rel_parts = [p for p in relative.split('/') if p]
                return rel_parts[:-1] if len(rel_parts) > 1 else []

            # Strategy 2: strip everything up to and including the last 'audios'/'audio' segment
            last_audio_idx = -1
            for idx, p in enumerate(parts):
                if p in ('audios', 'audio'):
                    last_audio_idx = idx
            if last_audio_idx >= 0:
                parts = parts[last_audio_idx + 1:]
                return parts[:-1] if len(parts) > 1 else []

            # Strategy 3: strip drive letter and common project directory prefixes
            if parts and len(parts[0]) == 2 and parts[0][1] == ':':
                parts = parts[1:]
            skip_segments = {'static', 'S2TT', 'auto_test', 'ver8', '202604231600', 'Intelligent-Audio-TEST'}
            while parts and parts[0] in skip_segments:
                parts = parts[1:]
            return parts[:-1] if len(parts) > 1 else []

        def make_file_item(audio):
            return {
                'id': audio.id,
                'name': audio.name,
                'filename': audio.original_filename or audio.name,
                'format': audio.format,
                'duration': audio.duration,
                'size': audio.size,
                'audio_type': audio.audio_type,
                'created_at': audio.created_at.isoformat() if audio.created_at else None
            }

        folder_map = {}
        root_files = []
        subfolder_parents = set()  # pre-compute which folders have sub-folders

        for audio in audios:
            folder_parts = get_folder_key(audio.file_path)

            if not folder_parts:
                root_files.append(make_file_item(audio))
                continue

            current_path = ''
            for i, part in enumerate(folder_parts):
                parent = current_path
                current_path = f'{current_path}/{part}' if current_path else part

                if current_path not in folder_map:
                    folder_map[current_path] = {
                        'name': part,
                        'path': current_path,
                        'parent': parent,
                        'depth': i + 1,
                        'count': 0,
                        'file_count': 0,
                        'files': []
                    }
                folder_map[current_path]['count'] += 1

                if parent:
                    subfolder_parents.add(parent)

                if i == len(folder_parts) - 1:
                    folder_map[current_path]['file_count'] += 1
                    # 仅当显式指定 parent_path（懒加载子树）或 depth 严格大于文件夹深度时才返回文件
                    # 这样 depth=1 时只返回根目录文件，子文件夹仅返回元数据
                    if parent_path or depth > i + 1:
                        folder_map[current_path]['files'].append(make_file_item(audio))

        # O(n) tree building: group folder paths by their parent key
        from collections import defaultdict
        children_map = defaultdict(list)
        for path_key, folder in folder_map.items():
            children_map[folder['parent']].append(path_key)

        def build_tree(parent_key=''):
            result = []
            for path_key in children_map.get(parent_key, []):
                folder = folder_map[path_key]
                children = build_tree(path_key)
                result.append({
                    'name': folder['name'],
                    'path': folder['path'],
                    'count': folder['count'],
                    'file_count': folder['file_count'],
                    'has_children': len(children) > 0 or folder['file_count'] > 0,
                    'files': folder['files'] if parent_path or depth > folder['depth'] else [],
                    'folders': children
                })
            return sorted(result, key=lambda x: x['name'])

        tree = {
            'name': '音频文件',
            'path': '',
            'count': len(audios),
            'file_count': len(root_files),
            'has_children': len(folder_map) > 0 or len(root_files) > 0,
            'files': root_files if depth >= 1 else [],
            'folders': build_tree()
        }

        folder_list = []
        for path_key in children_map.get('', []):
            folder = folder_map[path_key]
            folder_list.append({
                'name': folder['name'],
                'path': folder['path'],
                'count': folder['count'],
                'file_count': folder['file_count'],
                'has_children': path_key in subfolder_parents
            })

        return success_response({
            'tree': tree,
            'folders': sorted(folder_list, key=lambda x: x['name']),
            'total': len(audios),
            'folder_count': len(folder_map)
        })
