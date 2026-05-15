import os
import uuid
import requests
import time
import shutil
from flask import request, send_file, Response, current_app
from werkzeug.utils import secure_filename
from sqlalchemy.orm import joinedload
from backend.models.models import Audio, Tag, AudioAnnotation, TranslationDirection, AudioTag, TestCase, TestCaseGroup, PlaybackDevice, UploadTask, UploadFile, UploadChunk, PromptAudioRelation
from backend.models.database import db
from backend.utils.response import success_response, error_response
from backend.utils.task_utils import has_running_e2e_tasks
from backend.schemas.audio import (
    AudioIdsData,
    AudioItem,
    AudioListData,
    AudioListStats,
    BatchActionRequest,
    BatchPlaybackRequest,
    ConvertFormatRequest,
    DirectionItem,
    DirectionListData,
    InitUploadTaskRequest,
    MergeChunksRequest,
    RegisterUploadFileRequest,
    TagListData as AudioTagListData,
    URLImportRequest,
    UpdateMetadataRequest,
)
from pydantic import ValidationError
from datetime import datetime, timedelta, timezone
from pydub import AudioSegment

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
    
    # 获取原始音频的采样率和位深信息
    original_sample_rate = audio_seg.frame_rate
    original_channels = audio_seg.channels
    # 位深信息通过frame_width获取（bytes per sample）
    original_bits_per_sample = audio_seg.frame_width * 8
    
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

    # 获取所有翻译语向列表
    @staticmethod
    def get_directions():
        directions = TranslationDirection.query.all()
        data = []
        for d in directions:
            data.append(
                DirectionItem(
                    id=d.id,
                    source_language=d.source_language,
                    target_language=d.target_language,
                    description=d.description,
                )
            )
        return success_response(DirectionListData(items=data, total=len(data)))

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
        
        today_start = datetime.now(timezone(timedelta(hours=8))).replace(hour=0, minute=0, second=0, microsecond=0)

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
            
            # 更新文件路径为WAV文件
            file_path = wav_file_path
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
                expired_at=datetime.now(timezone(timedelta(hours=8))) + timedelta(days=7)
            )
            db.session.add(task)
            db.session.commit()
            
            return success_response({
                "task_id": task_id,
                "message": "任务初始化成功"
            })
        except Exception as e:
            import traceback
            from backend.utils.log_handler import log_and_emit
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
                            print(f"MD5查询失败: {str(e)}")
                    
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
            from backend.utils.log_handler import log_and_emit
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
                    existing_chunk.updated_at = datetime.now(timezone(timedelta(hours=8)))
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
            from backend.utils.log_handler import log_and_emit
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
                        test_case_id = AudioController._create_test_case_from_audio(
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
                            algorithm_params_dict
                        )
                        
                        # 提交测试用例创建
                        db.session.commit()
                        
                        return success_response({
                            "file_id": file_id,
                            "audio_id": existing_audio.id,
                            "name": existing_audio.name,
                            "status": "completed",
                            "test_case_id": test_case_id,
                            "instant_upload": True
                        }, "秒传成功，测试用例已创建")
                    else:
                        # 秒传但不需要创建测试用例
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
                
                # 更新文件路径为WAV文件
                final_path = wav_file_path
                # 更新文件名为WAV文件名
                upload_file.filename = wav_filename
                upload_file.original_filename = wav_filename
                
            except Exception as e:
                # 如果转换失败，保留原始文件但标记格式
                print(f"[WARN] 音频转换失败，将保留原始格式: {str(e)}")
                sample_rate = 44100
                bits_per_sample = 16
            
            # 提取音频元数据
            file_size = os.path.getsize(final_path)
            
            # 初始化元数据默认值（不依赖ffmpeg）
            duration = 0.0
            sample_rate = 44100  # 默认采样率
            channels = 2  # 默认双声道
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
                print(f"[INFO] 音频元数据提取失败，使用默认值: {str(e)}")
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
                
                # 处理提示词音频关联（仅当 audio_type 为 prompt 且有配置时）
                if validated.audio_type == 'prompt' and prompt_device_id:
                    prompt_translation_direction = validated.prompt_translation_direction
                    prompt_relation = PromptAudioRelation(
                        audio_id=new_audio.id,
                        device_id=prompt_device_id,
                        algorithm_type=prompt_algorithm_type,
                        source_language=prompt_source_language,
                        target_language=prompt_target_language,
                        translation_direction=prompt_translation_direction,
                        priority=0
                    )
                    db.session.add(prompt_relation)
                
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
                
                # 处理标注信息（支持 JSON/RTTM/STM 格式）
                annotations_from_request = validated.annotations

                if annotations_from_request:
                    for ann in annotations_from_request:
                        ann_format = ann.get('format', 'json')
                        ann_data = ann.get('data', {})
                        ann_code = ann.get('code', '')
                        ann_source_lang = ann.get('source_language', '')
                        ann_target_lang = ann.get('target_language', '')

                        audio_annotation = AudioAnnotation(
                            audio_id=new_audio.id,
                            format=ann_format,
                            code=ann_code,
                            data=ann_data,
                            source_language=ann_source_lang,
                            target_language=ann_target_lang
                        )
                        db.session.add(audio_annotation)
                
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
            if create_test_case:
                created_test_case_id = AudioController._create_test_case_from_audio(
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
                    algorithm_params_dict
                )
            
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
            
            return success_response(response_data, "文件合并成功")
        except Exception as e:
            db.session.rollback()
            import traceback
            from backend.utils.log_handler import log_and_emit
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
    

    # 内部辅助方法：从音频创建测试用例
    @staticmethod
    def _create_test_case_from_audio(audio_id, test_types, audio_tags, playback_device_id=None, spl=65.0, noise_spl=60.0, noise_audio_id=None, group_name=None, dimensions_data=None, algorithm_type=None, algorithm_params=None):
        """
        根据音频创建测试用例，支持多测试类型（API和E2E）
        :param audio_id: 音频ID
        :param test_types: 测试类型列表，如 ['api', 'e2e']
        :param audio_tags: 音频标签列表
        :param playback_device_id: 播放设备ID（用于E2E测试）
        :param spl: 干声压级（用于E2E测试）
        :param noise_spl: 噪声声压级（用于E2E测试）
        :param noise_audio_id: 噪声音频ID（用于E2E测试）
        :param group_name: 分组名称
        :param dimensions_data: 评估维度配置
        :param algorithm_type: 算法类型
        :param algorithm_params: 算法参数
        """
        # 确保 test_types 是列表，并清理可能的空白字符
        if isinstance(test_types, str):
            test_types = [test_types.strip()]
        else:
            test_types = [tt.strip() if isinstance(tt, str) else tt for tt in test_types]
        
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
            
            # 创建测试用例名称
            test_case_name = f"测试用例_{audio.name}"
            
            # 检查是否已存在同名用例
            existing = TestCase.query.filter_by(name=test_case_name, group_id=group.id, deleted=False).first()
            if existing:
                test_case_name = f"测试用例_{audio.name}_{datetime.now(timezone(timedelta(hours=8))).strftime('%H%M%S')}"
            
            # 构建多类型的音频配置 - 新结构：每个音频都需要 spl 字段
            audios = []
            for i, test_type in enumerate(test_types):
                audio_config = {
                    "audio_id": audio_id,
                    "test_type": test_type,
                    "spl": spl if spl else 65.0,  # 新结构：每个音频都需要 spl
                    "play_order": i
                }
                
                # E2E测试需要额外的播放设备配置
                if test_type == 'e2e':
                    audio_config["playback_device_id"] = effective_playback_device_id
                
                audios.append(audio_config)
            
            # 构建噪声配置 - 新结构
            background_noise = None
            if (noise_spl and noise_spl > 0) or noise_audio_id:
                background_noise = {
                    "audio_id": noise_audio_id,
                    "spl": noise_spl if noise_spl else 60.0
                }
            
            # 创建测试用例配置 - 新结构
            config = {
                "source_audio": audio.name,
                "auto_generated": True,
                "audios": audios
            }
            
            # 添加噪声配置
            if background_noise:
                config["background_noise"] = background_noise
            
            # 添加评估维度配置（按类型分开）
            if dimensions_data:
                # 统一处理：将可能的嵌套结构展平
                if isinstance(dimensions_data, dict):
                    if 'dimensions' in dimensions_data:
                        dimensions_data = dimensions_data.get('dimensions')
                    
                    # 最终验证：确保包含 api 或 e2e 键
                    if 'api' in dimensions_data or 'e2e' in dimensions_data:
                        config["dimensions"] = dimensions_data
                    else:
                        # 兜底：检查是否有其他格式
                        all_keys = list(dimensions_data.keys())
                        
                        # 如果维度数据是嵌套的，尝试提取
                        if 'dimensions' in all_keys:
                            inner = dimensions_data.get('dimensions')
                            if isinstance(inner, dict) and ('api' in inner or 'e2e' in inner):
                                config["dimensions"] = inner
                            else:
                                config["dimensions"] = inner
                        else:
                            config["dimensions"] = dimensions_data
                elif isinstance(dimensions_data, list):
                    config["dimensions"] = {tt: dimensions_data.copy() for tt in test_types}
                else:
                    config["dimensions"] = dimensions_data
            
            # 创建测试用例
            tc_id = str(uuid.uuid4())
            
            new_tc = TestCase(
                id=tc_id,
                name=test_case_name,
                description=f"自动从音频 '{audio.name}' 创建的测试用例",
                group_id=group.id,
                algorithm_type=algorithm_type,
                algorithm_params=algorithm_params if algorithm_params else [],
                config=config
            )
            db.session.add(new_tc)
            
            # 继承音频的标签
            for tag_name in audio_tags:
                tag = Tag.query.filter_by(name=tag_name).first()
                if tag:
                    new_tc.tags.append(tag)
            
            # 刷新用例参考文本/音频/... - 新结构：自动生成参考参数
            from backend.algorithm.reference_params_generator import ReferenceParamsGenerator
            ReferenceParamsGenerator.apply_to_config(new_tc)
            
            # 不在这里 commit，交给调用者统一提交
            db.session.flush()
            return tc_id

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

                from backend.utils.stats_cache import refresh_stats_cache
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

            # 3. 更新数据库记录 (或创建新记录，此处选择更新当前记录并保留旧文件元数据参考)
            audio.file_path = new_path
            audio.format = target_format
            audio.size = os.path.getsize(new_path)
            audio.updated_at = datetime.now(timezone(timedelta(hours=8)))
            
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

            audio.updated_at = datetime.now(timezone(timedelta(hours=8)))
            db.session.commit()
            return success_response(None, "元数据更新成功")
        except Exception as e:
            db.session.rollback()
            return error_response(str(e))

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
                        TestCase.config.contains(f'"audio_id": {audio_id}')
                    ).count()
                    if test_case_count > 0:
                        skipped_audio_ids.append(audio_id)
                        continue
                    
                    # 2. 检查测试用例背景噪音引用（在config.background_noise中）
                    test_case_noise_count = TestCase.query.filter(
                        TestCase.deleted == False,
                        TestCase.config.contains(f'"background_noise": {{"audio_id": {audio_id}}}')
                    ).count()
                    if test_case_noise_count > 0:
                        skipped_audio_ids.append(audio_id)
                        continue
                    
                    # 3. 检查设备提示词音频引用
                    device_count = Device.query.filter(
                        Device.prompt_config.contains(str(audio_id)),
                        Device.deleted == False
                    ).count()
                    if device_count > 0:
                        skipped_audio_ids.append(audio_id)
                        continue
                    
                    # 4. 检查任务配置中的音频引用
                    task_count = Task.query.filter(
                        Task.config.contains(str(audio_id)),
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
                    download_name=f'audios_export_{datetime.now(timezone(timedelta(hours=8))).strftime("%Y%m%d%H%M%S")}.zip'
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
                
                # 查找指定测试类型的音频
                target_audio_config = next((config for config in audios_config if config.get('test_type') == task_type), None)
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
            from backend.utils.audio_engine import audio_service
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
                    from backend.utils.spl_service import spl_service
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
            from backend.utils.audio_engine import audio_service
            
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
                TestCase.config.contains(f'"audio_id": {audio_id}')
            ).count()
            if test_case_count > 0:
                return error_response("该音频文件已被测试用例使用，禁止删除", 400)
            
            # 2. 检查测试用例背景噪音引用
            test_case_noise_count = TestCase.query.filter(
                TestCase.deleted == False,
                TestCase.config.contains(f'"background_noise": {{"audio_id": {audio_id}}}')
            ).count()
            if test_case_noise_count > 0:
                return error_response("该音频文件已被测试用例作为背景噪音使用，禁止删除", 400)
            
            # 3. 检查设备提示词音频引用
            from backend.models.models import Device
            device_count = Device.query.filter(
                Device.prompt_config.contains(str(audio_id)),
                Device.deleted == False
            ).count()
            if device_count > 0:
                return error_response("该音频文件已被设备作为提示词使用，禁止删除", 400)
            
            # 4. 检查任务配置中的音频引用
            from backend.models.models import Task
            task_count = Task.query.filter(
                Task.config.contains(str(audio_id)),
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

            from backend.utils.stats_cache import refresh_stats_cache
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
    def get_folder_tree():
        """
        获取音频文件夹树结构（支持筛选、懒加载）
        服务端计算文件夹树，支持大数据量
        """
        data = request.get_json() or {}
        
        keyword = data.get('keyword')
        audio_type = data.get('audioType', data.get('audio_type'))
        format_ = data.get('format')
        sample_rate = data.get('sampleRate', data.get('sample_rate'))
        duration = data.get('duration')
        tags_data = data.get('tags', [])
        direction = data.get('direction')
        algorithm_type = data.get('algorithmType')
        parent_path = data.get('parentPath', '')
        depth = data.get('depth', 1)
        
        query = Audio.query.filter_by(deleted=False)
        
        if keyword:
            query = query.filter(
                (Audio.name.like(f"%{keyword}%")) |
                (Audio.original_filename.like(f"%{keyword}%")) |
                (Audio.asr_text.like(f"%{keyword}%"))
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
        
        audios = query.order_by(Audio.file_path).all()
        
        def get_folder_key(file_path):
            normalized = file_path.replace('\\', '/') if file_path else ''
            parts = [p for p in normalized.split('/') if p and p not in ['audios', 'audio']]
            return parts[:-1] if parts else []
        
        folder_map = {}
        root_files = []
        
        for audio in audios:
            folder_parts = get_folder_key(audio.file_path)
            
            if not folder_parts:
                root_files.append({
                    'id': audio.id,
                    'name': audio.name,
                    'filename': audio.original_filename or audio.name,
                    'format': audio.format,
                    'duration': audio.duration,
                    'size': audio.size,
                    'audio_type': audio.audio_type,
                    'created_at': audio.created_at.isoformat() if audio.created_at else None
                })
                continue
            
            current_path = ''
            for i, part in enumerate(folder_parts):
                parent = current_path
                current_path = f"{current_path}/{part}" if current_path else part
                
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
                
                if i == len(folder_parts) - 1:
                    folder_map[current_path]['file_count'] += 1
                    if depth >= i + 1:
                        folder_map[current_path]['files'].append({
                            'id': audio.id,
                            'name': audio.name,
                            'filename': audio.original_filename or audio.name,
                            'format': audio.format,
                            'duration': audio.duration,
                            'size': audio.size,
                            'audio_type': audio.audio_type,
                            'created_at': audio.created_at.isoformat() if audio.created_at else None
                        })
        
        def build_tree(folders, parent=''):
            result = []
            for path, folder in folders.items():
                if folder['parent'] == parent:
                    children = build_tree(folders, path)
                    result.append({
                        'name': folder['name'],
                        'path': folder['path'],
                        'count': folder['count'],
                        'file_count': folder['file_count'],
                        'has_children': len(children) > 0 or folder['file_count'] > 0,
                        'files': folder['files'] if depth >= folder['depth'] else [],
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
            'folders': build_tree(folder_map)
        }
        
        folder_list = []
        for path, folder in folder_map.items():
            if folder['parent'] == '':
                folder_list.append({
                    'name': folder['name'],
                    'path': folder['path'],
                    'count': folder['count'],
                    'file_count': folder['file_count'],
                    'has_children': any(f['parent'] == folder['path'] for f in folder_map.values())
                })
        
        return success_response({
            'tree': tree,
            'folders': sorted(folder_list, key=lambda x: x['name']),
            'total': len(audios),
            'folder_count': len(folder_map)
        })
