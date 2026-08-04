# -*- coding: utf-8 -*-
"""
数据提取函数
"""

import json
from typing import Dict, List, Any
from shared.models.database import db
from shared.models.models import Audio, AudioAnnotation
from shared.utils.log_handler import log_not_emit

from .helpers import (
    _KNOWN_DATA_KEYS,
    _get_overlap_rate,
    _get_overlap_time,
)
from .audio_utils import (
    _calculate_speaker_aware_offsets,
    _adjust_segment_timestamps,
    _merge_annotation_segments,
    _segments_to_rttm,
    _segments_to_stm,
)


def _extract_field_from_audios(config: Dict, field_path: str, merge_mode: str = 'join',
                                annotation_code: str = None, annotation_format: str = None) -> Dict[str, Any]:
    """
    从音频标注的 data 中按字段路径提取值
    
    field_path 格式:
    - 'model'          → 取 data['model']（顶层标量）
    - 'segments[].emotion' → 遍历 data['segments']，每项取 ['emotion']（数组字段）
    
    merge_mode:
    - 'join'    → 空格拼接成字符串（适用于 text 类型）
    - 'collect' → 收集成数组
    - 'first'   → 只取第一个音频的值
    """
    record_test_type = config.get('_record_test_type', 'api')
    result = {'api': None, 'e2e': None}
    
    audios_config = config.get('audios', [])
    if not audios_config:
        return result
    
    sorted_audios = sorted(audios_config, key=lambda x: x.get('play_order', 0))
    
    preload_context = config.get('_preload_context', {})
    annotation_map = preload_context.get('annotation_map', {})
    
    # field_path 不含 '[]' 时，自动补 'segments[].' 前缀（标注统一存为 segments 结构）
    if '[]' not in field_path:
        field_path = f'segments[].{field_path}'
    is_segment_field = True
    seg_key = field_path.split('[].')[1] if '[].' in field_path else None
    
    def _get_annotations_for_audio(audio_id: int, code: str = None, fmt: str = None) -> List:
        if annotation_map and audio_id in annotation_map:
            all_anns = annotation_map[audio_id]
            if code and fmt:
                filtered = [a for a in all_anns if a.code == code and a.format == fmt]
                if filtered:
                    return filtered
            if code:
                filtered = [a for a in all_anns if a.code == code]
                if filtered:
                    return filtered
            if fmt:
                filtered = [a for a in all_anns if a.format == fmt]
                if filtered:
                    return filtered
            return all_anns
        else:
            query = AudioAnnotation.query.filter_by(audio_id=audio_id, deleted=False)
            if code:
                query = query.filter_by(code=code)
            if fmt:
                query = query.filter_by(format=fmt)
            return query.all()
    
    collected_values = []
    
    for audio_item in sorted_audios:
        audio_id = audio_item.get('audio_id')
        if not audio_id:
            continue
        
        annotations = _get_annotations_for_audio(audio_id, annotation_code, annotation_format)
        if not annotations:
            annotations = _get_annotations_for_audio(audio_id)
        
        for ann in annotations:
            if not ann.data or not isinstance(ann.data, dict):
                continue
            
            if is_segment_field:
                segments = ann.data.get('segments', [])
                for seg in segments:
                    val = seg.get(seg_key) if seg_key else None
                    if val is not None:
                        collected_values.append(val)
            else:
                # 兜底：顶层取值（理论上不会走到，field_path 已自动补 segments[]. 前缀）
                val = ann.data.get(field_path)
                if val is not None:
                    collected_values.append(val)
                    break
        
        if merge_mode == 'first' and collected_values:
            break
    
    if not collected_values:
        return result
    
    if merge_mode == 'first':
        value = collected_values[0]
    elif merge_mode == 'collect':
        value = collected_values
    else:  # join
        value = ' '.join(str(v) for v in collected_values)
    
    result[record_test_type] = value
    return result


def _extract_text_from_audios(config: Dict, text_field: str = None, annotation_code: str = None, annotation_format: str = None) -> Dict[str, str]:
    """从音频配置中提取文本"""
    reference_texts = {'api': '', 'e2e': ''}
    
    audios_config = config.get('audios', [])
    if not audios_config:
        return reference_texts
    
    sorted_audios = sorted(audios_config, key=lambda x: x.get('play_order', 0))
    
    preload_context = config.get('_preload_context', {})
    annotation_map = preload_context.get('annotation_map', {})
    audio_map = preload_context.get('audio_map', {})
    
    # 新双记录架构：使用记录的 test_type
    record_test_type = config.get('_record_test_type', 'api')
    
    def _extract_text_from_annotation(ann: AudioAnnotation, target_test_type: str) -> str:
        """从单个标注中提取文本，支持多种格式"""
        if not ann.data:
            return ''
        
        if isinstance(ann.data, str):
            return ann.data
        
        actual_format = ann.format
        
        if actual_format == 'text':
            return ann.data.get('text', '')
        
        segments = ann.data.get('segments', [])
        text_parts = []
        for seg in segments:
            text = seg.get('text', '')
            if text:
                text_parts.append(text)
        return ' '.join(text_parts)
    
    def _get_annotations_for_audio_text(audio_id: int, code: str = None, fmt: str = None) -> List:
        if annotation_map and audio_id in annotation_map:
            all_anns = annotation_map[audio_id]
            if code and fmt:
                filtered = [a for a in all_anns if a.code == code and a.format == fmt]
                if filtered:
                    return filtered
            return all_anns
        else:
            query = AudioAnnotation.query.filter_by(audio_id=audio_id, deleted=False)
            if code:
                query = query.filter_by(code=code)
            if fmt:
                query = query.filter_by(format=fmt)
            return query.all()
    
    for audio_item in sorted_audios:
        audio_id = audio_item.get('audio_id')
        # 新双记录架构：使用记录的 test_type，而非音频的 test_type
        if not audio_id:
            continue
        
        extracted_text = ''
        
        if annotation_code and annotation_format:
            log_not_emit('DEBUG', 'reference_params_generator', 
                f'_extract_text_from_audios: trying exact match code={annotation_code}, format={annotation_format}', 
                category='algorithm')
            
            annotations = _get_annotations_for_audio_text(audio_id, annotation_code, annotation_format)
            
            log_not_emit('DEBUG', 'reference_params_generator', 
                f'_extract_text_from_audios: exact match found {len(annotations)} annotations', 
                category='algorithm')
            
            for ann in annotations:
                extracted_text = _extract_text_from_annotation(ann, record_test_type)
                if extracted_text:
                    break
            
            if not extracted_text:
                log_not_emit('DEBUG', 'reference_params_generator', 
                    f'_extract_text_from_audios: fallback - querying all annotations for audio_id={audio_id}', 
                    category='algorithm')
                
                annotations = _get_annotations_for_audio_text(audio_id)
                
                log_not_emit('DEBUG', 'reference_params_generator', 
                    f'_extract_text_from_audios: fallback found {len(annotations)} annotations', 
                    category='algorithm')
                
                for ann in annotations:
                    extracted_text = _extract_text_from_annotation(ann, record_test_type)
                    if extracted_text:
                        log_not_emit('DEBUG', 'reference_params_generator', 
                            f'_extract_text_from_audios: extracted from code={ann.code}, format={ann.format}', 
                            category='algorithm')
                        break
        elif text_field:
            if audio_map and audio_id in audio_map:
                audio = audio_map[audio_id]
            else:
                audio = db.session.get(Audio, audio_id)
            if audio:
                extracted_text = getattr(audio, text_field, None) or ""
        
        if extracted_text:
            reference_texts[record_test_type] += extracted_text + " "
    
    for t in ['api', 'e2e']:
        reference_texts[t] = reference_texts[t].strip()
    
    return reference_texts


def _extract_annotation_with_overlap(config: Dict, format: str = 'rttm', annotation_code: str = None, annotation_format: str = None) -> Dict[str, Any]:
    """
    从音频提取标注数据，支持重叠播放时间戳调整
    
    核心功能:
    - 根据 format 参数提取 RTTM/STM 格式的标注数据
    - 支持重叠播放场景，自动调整每个音频的时间戳偏移
    - 分别返回 api 和 e2e 两类测试的参考数据
    
    处理流程:
    1. 从 config.audios 获取音频配置列表
    2. 根据重叠率 (overlap_rate) 计算每个音频的开始时间偏移
    3. 按 test_type (api/e2e) 分组处理
    4. 对每个音频查询对应标注，调整时间戳后合并
    5. 将 segments 转换为标准 RTTM/STM 文本格式
    
    Args:
        config: 用例配置，包含 audios, algorithm_params, case_id 等
        format: 标注格式 ('rttm' 或 'stm')
        annotation_code: 标注代码（可选，用于精确匹配，如 'asr', 'translation'）
        annotation_format: 标注格式（可选，用于精确匹配，如 'json', 'rttm'）
    
    Returns:
        {
            'api': {'segments': [...], 'format': 'rttm', 'text': '...', 'json': '...'},
            'e2e': {'segments': [...], 'format': 'rttm', 'text': '...', 'json': '...'}
        }
        - segments: 时间戳调整后的 JSON 结构化数据列表
        - text: 标准 RTTM/STM 文本格式字符串
        - json: segments 的 JSON 字符串形式
    """
    result = {
        'api': {'segments': [], 'format': format, 'text': '', 'json': ''},
        'e2e': {'segments': [], 'format': format, 'text': '', 'json': ''}
    }
    
    audios_config = config.get('audios', [])
    if not audios_config:
        log_not_emit('DEBUG', 'reference_params_generator', 'No audios config found, returning empty result', category='algorithm')
        return result
    
    case_id = config.get('case_id', 'test_case')
    
    preload_context = config.get('_preload_context', {})
    annotation_map = preload_context.get('annotation_map', {})
    
    overlap_rate = _get_overlap_rate(config)
    overlap_time = _get_overlap_time(config)
    log_not_emit('DEBUG', 'reference_params_generator', f'Extracting annotation with overlap_rate={overlap_rate}, overlap_time={overlap_time}, format={format}', category='algorithm')
    
    audio_offsets = _calculate_speaker_aware_offsets(audios_config, overlap_rate, overlap_time, preload_context)
    log_not_emit('DEBUG', 'reference_params_generator', f'audio_offsets={audio_offsets}, audios_config={audios_config}', category='algorithm')
    
    # 双记录架构：所有音频属于 record_test_type
    record_test_type = config.get('_record_test_type', 'api')
    sorted_audios = sorted(audios_config, key=lambda x: x.get('play_order', 0))
    
    def _get_annotations_for_audio(audio_id: int, code: str = None, fmt: str = None) -> List:
        if annotation_map and audio_id in annotation_map:
            all_anns = annotation_map[audio_id]
            if code and fmt:
                filtered = [a for a in all_anns if a.code == code and a.format == fmt]
                if filtered:
                    return filtered
            if fmt:
                filtered = [a for a in all_anns if a.format == fmt]
                if filtered:
                    return filtered
            if code:
                filtered = [a for a in all_anns if a.code == code]
                if filtered:
                    return filtered
            return all_anns
        else:
            query = AudioAnnotation.query.filter_by(audio_id=audio_id, deleted=False)
            if code:
                query = query.filter_by(code=code)
            if fmt:
                query = query.filter_by(format=fmt)
            return query.all()
    
    segments_list = []
    top_level_extra = {}
    
    for audio_item in sorted_audios:
        audio_id = audio_item.get('audio_id')
        play_order = audio_item.get('play_order', 0)
        if not audio_id:
            continue
        
        offset = audio_offsets.get(play_order, 0)

        # 收集 data 顶层的额外字段（非已知字段），平铺到参考参数
        for ann in _get_annotations_for_audio(audio_id):
            if ann.data and isinstance(ann.data, dict):
                for k, v in ann.data.items():
                    if k not in _KNOWN_DATA_KEYS:
                        top_level_extra[k] = v
        
        if annotation_code and annotation_format:
            annotations = _get_annotations_for_audio(audio_id, annotation_code, annotation_format)
            
            if not annotations:
                annotations = _get_annotations_for_audio(audio_id, fmt='json')
            
            if not annotations and annotation_format != 'rttm':
                annotations = _get_annotations_for_audio(audio_id, fmt='rttm')
            
            if not annotations and annotation_format != 'stm':
                annotations = _get_annotations_for_audio(audio_id, fmt='stm')
            
            for ann in annotations:
                if ann.data:
                    segments = ann.data.get('segments', [])
                    adjusted_segments = _adjust_segment_timestamps(segments, offset, play_order)
                    segments_list.append(adjusted_segments)
        else:
            annotations = _get_annotations_for_audio(audio_id, fmt=format)
            
            if not annotations:
                json_annotations = _get_annotations_for_audio(audio_id, fmt='json')
                for ann in json_annotations:
                    if ann.data:
                        segments = ann.data.get('segments', [])
                        adjusted_segments = _adjust_segment_timestamps(segments, offset, play_order)
                        segments_list.append(adjusted_segments)
            else:
                for ann in annotations:
                    if ann.data:
                        segments = ann.data.get('segments', [])
                        adjusted_segments = _adjust_segment_timestamps(segments, offset, play_order)
                        segments_list.append(adjusted_segments)
            
            if not segments_list and format != 'rttm':
                rttm_annotations = _get_annotations_for_audio(audio_id, fmt='rttm')
                for ann in rttm_annotations:
                    if ann.data:
                        segments = ann.data.get('segments', [])
                        adjusted_segments = _adjust_segment_timestamps(segments, offset, play_order)
                        segments_list.append(adjusted_segments)
            
            if not segments_list and format != 'stm':
                stm_annotations = _get_annotations_for_audio(audio_id, fmt='stm')
                for ann in stm_annotations:
                    if ann.data:
                        segments = ann.data.get('segments', [])
                        adjusted_segments = _adjust_segment_timestamps(segments, offset, play_order)
                        segments_list.append(adjusted_segments)
    
    merged_segments = _merge_annotation_segments(segments_list)
    
    if format == 'rttm':
        text_content = _segments_to_rttm(merged_segments, case_id)
    else:
        text_content = _segments_to_stm(merged_segments, case_id)
    
    value_data = {
        'segments': merged_segments,
        'text': text_content,
        'json': json.dumps(merged_segments, ensure_ascii=False),
        **top_level_extra
    }
    
    # 返回兼容结构，但仅 record_test_type 有值
    result = {'api': {'segments': [], 'text': '', 'json': '[]'}, 'e2e': {'segments': [], 'text': '', 'json': '[]'}}
    result[record_test_type] = value_data
    
    return result


def _extract_translation_from_audios(config: Dict) -> Dict[str, Any]:
    """
    从音频的标注数据生成翻译参考文本
    
    用途:
    - 用于翻译算法，提取所有音频的标注文本作为参考翻译
    
    处理逻辑:
    1. 收集所有音频具备的翻译方向（source_language + target_language 组合）
    2. 找出所有音频**共同具备**的翻译方向（交集）
    3. 只为共同翻译方向生成标注
    
    返回格式:
    {
        'api': [
            {'translation_direction': 'zh2en', 'source_language': 'zh', 'target_language': 'en', 'text': '...'},
            {'translation_direction': 'en2zh', 'source_language': 'en', 'target_language': 'zh', 'text': '...'}
        ],
        'e2e': [...]
    }
    
    Args:
        config: 用例配置，包含 audios, translation_direction, source_language, target_language
        
    Returns:
        {'api': [...], 'e2e': [...]} 每个翻译方向一个对象
    """
    result = {'api': [], 'e2e': []}

    audios_config = config.get('audios', [])
    if not audios_config:
        return result

    sorted_audios = sorted(audios_config, key=lambda x: x.get('play_order', 0))

    preload_context = config.get('_preload_context', {})
    annotation_map = preload_context.get('annotation_map', {})
    
    # 新双记录架构：使用记录的 test_type
    record_test_type = config.get('_record_test_type', 'api')

    def _get_annotations_for_translation(audio_id: int, source_lang: str = None, target_lang: str = None) -> List:
        if annotation_map and audio_id in annotation_map:
            all_anns = annotation_map[audio_id]
            if source_lang and target_lang:
                filtered = [a for a in all_anns 
                           if a.source_language == source_lang and a.target_language == target_lang]
                if filtered:
                    return filtered
            return all_anns
        else:
            query = AudioAnnotation.query.filter_by(audio_id=audio_id, deleted=False)
            if source_lang:
                query = query.filter_by(source_language=source_lang)
            if target_lang:
                query = query.filter_by(target_language=target_lang)
            return query.all()

    audio_directions = {}
    audio_count = 0
    
    for audio_item in sorted_audios:
        audio_id = audio_item.get('audio_id')
        if not audio_id:
            continue
        
        audio_count += 1
        annotations = _get_annotations_for_translation(audio_id)
        
        directions = set()
        for ann in annotations:
            if ann.source_language and ann.target_language:
                direction = f"{ann.source_language}2{ann.target_language}"
                directions.add((ann.source_language, ann.target_language, direction))
        
        if record_test_type not in audio_directions:
            audio_directions[record_test_type] = directions
        else:
            if audio_count == 1:
                audio_directions[record_test_type] = directions
            else:
                audio_directions[record_test_type] = audio_directions[record_test_type] & directions

    for t_type in ['api', 'e2e']:
        if t_type not in audio_directions or not audio_directions[t_type]:
            continue
        
        for source_lang, target_lang, direction in audio_directions[t_type]:
            text_content = ''
            
            for audio_item in sorted_audios:
                audio_id = audio_item.get('audio_id')
                if not audio_id:
                    continue
                
                annotations = _get_annotations_for_translation(audio_id, source_lang, target_lang)
                
                for ann in annotations:
                    if ann.data:
                        segments = ann.data.get('segments', [])
                        for seg in segments:
                            text = seg.get('text', '')
                            if text:
                                text_content += text + " "
            
            text_content = text_content.strip()
            if text_content:
                result[t_type].append({
                    'translation_direction': direction,
                    'source_language': source_lang,
                    'target_language': target_lang,
                    'text': text_content
                })

    return result


def _extract_annotation_from_audios(config: Dict, format: str = None) -> Dict[str, str]:
    """从音频的标注数据提取文本（按格式过滤）"""
    record_test_type = config.get('_record_test_type', 'api')
    reference_texts = {'api': '', 'e2e': ''}

    audios_config = config.get('audios', [])
    if not audios_config:
        return reference_texts

    sorted_audios = sorted(audios_config, key=lambda x: x.get('play_order', 0))

    for audio_item in sorted_audios:
        audio_id = audio_item.get('audio_id')
        if not audio_id:
            continue

        query = AudioAnnotation.query.filter_by(audio_id=audio_id, deleted=False)
        if format:
            query = query.filter_by(format=format)

        annotations = query.all()

        for ann in annotations:
            if ann.data:
                segments = ann.data.get('segments', [])
                for seg in segments:
                    text = seg.get('text', '')
                    if text:
                        reference_texts[record_test_type] += text + " "

    for t_type in ['api', 'e2e']:
        reference_texts[t_type] = reference_texts[t_type].strip()

    return reference_texts
