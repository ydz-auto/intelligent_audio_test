import logging
from sqlalchemy import cast, String, func
from api_gateway.infrastructure.request_adapter import request
from shared.models.models import Audio, Tag, AudioAnnotation, AudioTag, TestCase
from shared.models.database import db
from shared.utils.response import success_response, error_response
from shared.utils.query_utils import now_cst
from api_gateway.schemas.audio import (
    AudioIdsData,
    AudioItem,
    AudioListData,
    AudioListStats,
    TagListData as AudioTagListData,
)
from api_gateway.application.services.audio_common import get_relative_path

logger = logging.getLogger(__name__)


class AudioQueryService:
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

        # file_path 存的是带 scheme 前缀的存储路径（如 oss://audios/xxx）
        file_path = audio.file_path
        if not file_path:
            return error_response("音频文件路径缺失", 404)

        # 生成预签名 URL（OSS 可用时），让前端直接从 OSS 拉取（支持 Range 请求）
        # 兼容旧数据：file_path 可能是裸 OSS key（无 scheme 前缀）
        from shared.infrastructure.storage import storage
        presigned_url = storage.get_url(file_path if file_path.startswith(('oss://', 'local://')) else storage.build_path('audios', file_path), expires=3600)
        if presigned_url:
            return {"url": presigned_url}
        # OSS 不可用或本地降级模式：返回本地文件路径供前端下载
        return {"url": f"/api/audio/download?path={file_path}"}

    @staticmethod
    def stream_by_path():
        """通过 OSS key 获取预签名 URL 播放音频"""
        from shared.infrastructure.storage import storage
        oss_key = request.args.get('path')
        if not oss_key:
            return error_response("未提供路径", 400)

        # 根据 OSS key 前缀确定 bucket
        if oss_key.startswith('case_result/'):
            bucket = 'case_result'
        else:
            bucket = 'audios'

        try:
            presigned_url = storage.get_url(oss_key, expires=3600)
            return {"url": presigned_url}
        except Exception as e:
            logging.getLogger(__name__).error(f"stream_by_path 获取存储 URL 失败: {e}, key={oss_key}")
            return error_response(f"获取音频失败: {e}", 404)

    # 获取音频关联的算法
    @staticmethod
    def get_audio_algorithms(audio_id):
        try:
            from shared.models.models import AudioAlgorithmRelation
            audio = db.session.get(Audio, audio_id)
            if not audio or audio.deleted:
                return error_response("音频不存在", 404)

            relations = AudioAlgorithmRelation.query.filter_by(
                audio_id=audio_id, deleted=False
            ).all()

            return success_response([r.to_dict() for r in relations])
        except Exception as e:
            return error_response(str(e))

    @staticmethod
    def get_folder_tree():
        """
        获取音频文件夹树结构（支持筛选、懒加载）
        服务端计算文件夹树，支持大数据量
        """
        from api_gateway.config.config import Config
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
            from shared.models.models import AudioAlgorithmRelation
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
        audio_storage_path = Config.AUDIO_STORAGE_PATH
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
