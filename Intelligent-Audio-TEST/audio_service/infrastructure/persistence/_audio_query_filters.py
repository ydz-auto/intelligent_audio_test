# -*- coding: utf-8 -*-
"""音频仓储公共查询过滤器（从 audio_repository.py 拆分，P4-4）。
list_audios / get_all_audio_ids / collect_folder_files 三处存在大段重复的
过滤逻辑（关键词/格式/类型/采样率/时长/语向/标签/算法关联），本模块按
"组合优于重复"抽取为可复用的过滤器函数，消除重复代码。

设计：
- 每个过滤器函数接收 (query, params) 并返回过滤后的 query，可自由组合
- 标签过滤依赖 AudioRepository._get_tag_name_to_id_map（通过 gRPC 跨域查询 Tag），
  因此以回调形式注入，保持本模块无跨域依赖
- 时长档位阈值（30/300 秒）集中在 _DURATION_BUCKETS 配置，避免魔法数字
"""
from typing import Callable, List, Tuple
import logging

from sqlalchemy import func

from audio_service.infrastructure.persistence.models import (
    Audio,
    AudioAnnotation,
    AudioTag,
    AudioAlgorithmRelation,
)

logger = logging.getLogger(__name__)

# 时长档位阈值（秒）：short ≤ 短音频上限 < medium ≤ 中音频上限 < long
_DURATION_SHORT_MAX = 30
_DURATION_MEDIUM_MAX = 300

# 时长档位 → SQLAlchemy 过滤条件工厂
_DURATION_BUCKETS = {
    'short': lambda q: q.filter(Audio.duration <= _DURATION_SHORT_MAX),
    'medium': lambda q: q.filter(Audio.duration > _DURATION_SHORT_MAX,
                                 Audio.duration <= _DURATION_MEDIUM_MAX),
    'long': lambda q: q.filter(Audio.duration > _DURATION_MEDIUM_MAX),
}


def _parse_tag_filters(tags_data: list) -> Tuple[List[str], List[str]]:
    """解析标签过滤参数为 (or_tags, and_tags)。

    支持 dict 形式 {'name': xx, 'mode': 'or'/'and'} 与逗号分隔的字符串形式。
    """
    or_tags: List[str] = []
    and_tags: List[str] = []
    for t in tags_data or []:
        if isinstance(t, dict):
            tag_name = (t.get('name') or '').strip()
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
    return or_tags, and_tags


def _apply_tag_filter(query, session, or_tags, and_tags, get_tag_name_to_id_map: Callable):
    """应用标签过滤（需先通过 gRPC 将标签名解析为 task_service 域的 Tag ID）。

    - or_tags：任一命中即通过（IN 子查询）
    - and_tags：全部命中才通过（按 audio_id 分组计数子查询）
    """
    if not or_tags and not and_tags:
        return query

    tag_name_to_id = get_tag_name_to_id_map(or_tags + and_tags)

    if or_tags:
        or_tag_ids = [tag_name_to_id[n] for n in or_tags if n in tag_name_to_id]
        if or_tag_ids:
            or_audio_ids = (
                session.query(AudioTag.audio_id)
                .filter(AudioTag.tag_id.in_(or_tag_ids))
                .distinct()
            )
            query = query.filter(Audio.id.in_(or_audio_ids))

    if and_tags:
        and_tag_ids = [tag_name_to_id[n] for n in and_tags if n in tag_name_to_id]
        if and_tag_ids:
            audio_tag_counts = (
                session.query(AudioTag.audio_id, func.count(AudioTag.tag_id).label('tag_count'))
                .filter(AudioTag.tag_id.in_(and_tag_ids))
                .group_by(AudioTag.audio_id)
                .subquery()
            )
            query = query.join(audio_tag_counts, audio_tag_counts.c.audio_id == Audio.id).filter(
                audio_tag_counts.c.tag_count == len(and_tag_ids)
            )
    return query


def apply_audio_list_filters(query, session, params: dict,
                             get_tag_name_to_id_map: Callable):
    """list_audios / get_all_audio_ids 的通用过滤逻辑。

    支持：keyword / format_ / audio_type / sample_rate / duration /
    direction（语向）/ tags_data（标签 or/and 组合）。
    """
    keyword = params.get('keyword')
    format_ = params.get('format_')
    audio_type = params.get('audio_type')
    sample_rate = params.get('sample_rate')
    duration = params.get('duration')
    direction = params.get('direction')

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
            # 采样率参数以 kHz 为单位（如 "48 kHz"），转换为 Hz
            rate_value = float(str(sample_rate).split()[0]) * 1000
            query = query.filter_by(sample_rate=rate_value)
        except (ValueError, IndexError):
            logger.debug("解析采样率参数失败，跳过采样率过滤: sample_rate=%s", sample_rate, exc_info=True)
    if duration:
        bucket = _DURATION_BUCKETS.get(duration)
        if bucket:
            query = bucket(query)

    if direction:
        query = query.join(AudioAnnotation).filter(
            (AudioAnnotation.source_language.like(f"%{direction.split('-')[0]}%")) |
            (AudioAnnotation.target_language.like(f"%{direction.split('-')[1]}%"))
        )

    if params.get('tags_data'):
        or_tags, and_tags = _parse_tag_filters(params.get('tags_data'))
        query = _apply_tag_filter(query, session, or_tags, and_tags, get_tag_name_to_id_map)

    return query


def apply_folder_tree_filters(query, session, params: dict,
                              get_tag_name_to_id_map: Callable):
    """collect_folder_files 的过滤逻辑（文件夹树构建场景）。

    与 apply_audio_list_filters 的差异：
    - keyword 额外匹配 asr_text
    - direction 按 source_language 精确匹配（而非语向 like）
    - sample_rate 允许 ±100 Hz 容差
    - 额外支持 algorithm_type / parent_path 过滤
    """
    keyword = params.get('keyword')
    audio_type = params.get('audio_type')
    format_ = params.get('format_')
    sample_rate = params.get('sample_rate')
    duration = params.get('duration')
    direction = params.get('direction')
    algorithm_type = params.get('algorithm_type')
    parent_path = params.get('parent_path')

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
        bucket = _DURATION_BUCKETS.get(duration)
        if bucket:
            query = bucket(query)

    if params.get('tags_data'):
        or_tags, and_tags = _parse_tag_filters(params.get('tags_data'))
        query = _apply_tag_filter(query, session, or_tags, and_tags, get_tag_name_to_id_map)

    if algorithm_type:
        audio_ids_with_algo = (
            session.query(AudioAlgorithmRelation.audio_id)
            .filter(AudioAlgorithmRelation.algorithm_type == algorithm_type,
                    AudioAlgorithmRelation.deleted == False)
            .distinct()
        )
        query = query.filter(Audio.id.in_(audio_ids_with_algo))

    if parent_path:
        query = _apply_parent_path_filter(query, parent_path)

    return query


def _apply_parent_path_filter(query, parent_path: str):
    """按父路径过滤（Windows/POSIX 路径分隔符归一化为 '/' 后做前缀匹配）"""
    normalized_parent = parent_path.replace(chr(92), '/')
    escaped = normalized_parent.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
    normalized_path_expr = func.replace(Audio.file_path, chr(92), '/')
    return query.filter(
        normalized_path_expr.like(f'%{escaped}/%', escape='\\')
    )
