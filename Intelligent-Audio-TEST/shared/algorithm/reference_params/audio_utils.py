# -*- coding: utf-8 -*-
"""
音频相关辅助函数
"""

from typing import Dict, List
from shared.models.database import db
from shared.models.models import Audio, AudioAnnotation
from shared.utils.log_handler import log_not_emit


def _extract_speakers_from_audio(audio_id: int, annotation_map: Dict = None) -> set:
    """
    从音频的diarization标注中提取所有speaker集合
    
    Args:
        audio_id: 音频ID
        annotation_map: 预加载的标注映射 {audio_id: [annotations]}，用于性能优化
        
    Returns:
        set: speaker标签集合，如 {'spk9', 'spk8'}
    """
    if not audio_id:
        return set()
    
    speakers = set()
    
    if annotation_map and audio_id in annotation_map:
        annotations = annotation_map[audio_id]
    else:
        annotations = AudioAnnotation.query.filter_by(
            audio_id=audio_id,
            deleted=False
        ).all()
    
    for ann in annotations:
        if not ann.data:
            continue
        
        if isinstance(ann.data, dict):
            segments = ann.data.get('segments', [])
            for seg in segments:
                if 'speaker' in seg and seg['speaker']:
                    speakers.add(seg['speaker'])
        elif isinstance(ann.data, list):
            for seg in ann.data:
                if isinstance(seg, dict) and 'speaker' in seg and seg['speaker']:
                    speakers.add(seg['speaker'])
    
    log_not_emit('DEBUG', 'reference_params_generator', 
        f'[_extract_speakers_from_audio] audio_id={audio_id}, speakers={speakers}', 
        category='algorithm')
    
    return speakers


def _calculate_speaker_aware_offsets(audios_config: List[Dict], overlap_rate: float, overlap_time: float = 0, preload_context: Dict = None) -> Dict[int, float]:
    """
    计算每个音频播放项的开始时间偏移（speaker感知版本）

    规则：
    - 相邻音频有共同speaker → 顺序播放（offset = prev_end_time）
    - 相邻音频无共同speaker → 按overlap_time或overlap_rate交叠

    Args:
        audios_config: 音频配置列表
        overlap_rate: 重叠率 (0.0-1.0)
        overlap_time: 重叠时间（秒），优先级高于 overlap_rate
        preload_context: 预加载数据上下文，用于性能优化

    Returns:
        {play_order: offset_seconds}
    """
    offsets = {}
    sorted_audios = sorted(audios_config, key=lambda x: x.get('play_order', 0))
    
    log_not_emit('DEBUG', 'reference_params_generator', 
        f'[_calculate_speaker_aware_offsets] START: overlap_rate={overlap_rate}, overlap_time={overlap_time}, audio_count={len(sorted_audios)}', 
        category='algorithm')
    
    annotation_map = preload_context.get('annotation_map', {}) if preload_context else {}
    duration_map = preload_context.get('duration_map', {}) if preload_context else {}
    
    audio_speakers = {}
    for audio_item in sorted_audios:
        audio_id = audio_item.get('audio_id')
        if audio_id:
            audio_speakers[audio_id] = _extract_speakers_from_audio(audio_id, annotation_map)
    
    log_not_emit('DEBUG', 'reference_params_generator', 
        f'[_calculate_speaker_aware_offsets] audio_speakers={audio_speakers}', 
        category='algorithm')
    
    cumulative_duration = 0.0
    prev_end_time = 0.0
    
    for i, audio_item in enumerate(sorted_audios):
        play_order = audio_item.get('play_order', 0)
        audio_id = audio_item.get('audio_id')
        
        audio_duration = 1.0
        if audio_id:
            if duration_map and audio_id in duration_map:
                audio_duration = duration_map[audio_id] or 1.0
            else:
                audio = db.session.get(Audio, audio_id)
                if audio and audio.duration:
                    audio_duration = audio.duration
        
        log_not_emit('DEBUG', 'reference_params_generator', 
            f'[_calculate_speaker_aware_offsets] i={i}, play_order={play_order}, audio_id={audio_id}, audio_duration={audio_duration}, cumulative_duration={cumulative_duration}, prev_end_time={prev_end_time}', 
            category='algorithm')
        
        if i == 0:
            offsets[play_order] = 0
            log_not_emit('DEBUG', 'reference_params_generator', 
                f'[_calculate_speaker_aware_offsets] i=0, first audio, offset=0', 
                category='algorithm')
        else:
            prev_audio_id = sorted_audios[i-1].get('audio_id')
            curr_speakers = audio_speakers.get(audio_id, set())
            prev_speakers = audio_speakers.get(prev_audio_id, set())
            
            has_common_speaker = len(curr_speakers & prev_speakers) > 0
            
            log_not_emit('DEBUG', 'reference_params_generator', 
                f'[_calculate_speaker_aware_offsets] i={i}, prev_audio_id={prev_audio_id}, prev_speakers={prev_speakers}, curr_speakers={curr_speakers}, has_common_speaker={has_common_speaker}', 
                category='algorithm')
            
            if has_common_speaker:
                offsets[play_order] = prev_end_time
                log_not_emit('DEBUG', 'reference_params_generator', 
                    f'[_calculate_speaker_aware_offsets] Has common speaker, sequential playback: offset=prev_end_time={prev_end_time}', 
                    category='algorithm')
            else:
                if overlap_time and overlap_time > 0:
                    offset_val = prev_end_time - overlap_time
                    if offset_val < 0:
                        log_not_emit('WARNING', 'reference_params_generator', 
                            f'[_calculate_speaker_aware_offsets] overlap_time={overlap_time} > prev_end_time={prev_end_time}, clamping offset to 0', 
                            category='algorithm')
                        offset_val = 0
                    offsets[play_order] = offset_val
                    log_not_emit('DEBUG', 'reference_params_generator', 
                        f'[_calculate_speaker_aware_offsets] Using overlap_time: offset=prev_end_time({prev_end_time}) - {overlap_time} = {offset_val}', 
                        category='algorithm')
                elif overlap_rate is not None and overlap_rate > 0:
                    offsets[play_order] = prev_end_time * (1 - overlap_rate)
                    log_not_emit('DEBUG', 'reference_params_generator', 
                        f'[_calculate_speaker_aware_offsets] Using overlap_rate: offset=prev_end_time({prev_end_time}) * {1 - overlap_rate} = {prev_end_time * (1 - overlap_rate)}', 
                        category='algorithm')
                else:
                    offsets[play_order] = prev_end_time
                    log_not_emit('DEBUG', 'reference_params_generator', 
                        f'[_calculate_speaker_aware_offsets] No overlap, offset=prev_end_time={prev_end_time}', 
                        category='algorithm')
        
        prev_end_time = offsets[play_order] + audio_duration
        cumulative_duration += audio_duration
        
        log_not_emit('DEBUG', 'reference_params_generator', 
            f'[_calculate_speaker_aware_offsets] After i={i}: prev_end_time={prev_end_time}, cumulative_duration={cumulative_duration}, offsets={offsets}', 
            category='algorithm')
    
    log_not_emit('DEBUG', 'reference_params_generator', 
        f'[_calculate_speaker_aware_offsets] FINAL: offsets={offsets}', 
        category='algorithm')
    
    return offsets


def _calculate_audio_offsets(audios_config: List[Dict], overlap_rate: float, overlap_time: float = 0) -> Dict[int, float]:
    """
    计算每个音频播放项的开始时间偏移

    链式交叠公式：
    - overlap_time > 0: offset = cumulative_offset - overlap_time
    - overlap_rate > 0: offset = cumulative_offset * (1 - overlap_rate)
    - 否则: offset = cumulative_offset（顺序播放）

    Args:
        audios_config: 音频配置列表
        overlap_rate: 重叠率 (0.0-1.0)
        overlap_time: 重叠时间（秒），优先级高于 overlap_rate

    Returns:
        {play_order: offset_seconds}
    """
    offsets = {}
    sorted_audios = sorted(audios_config, key=lambda x: x.get('play_order', 0))

    log_not_emit('DEBUG', 'reference_params_generator', f'[_calculate_audio_offsets] START: overlap_rate={overlap_rate}, overlap_time={overlap_time}, audio_count={len(sorted_audios)}', category='algorithm')

    cumulative_offset = 0.0

    for i, audio_item in enumerate(sorted_audios):
        play_order = audio_item.get('play_order', 0)
        audio_id = audio_item.get('audio_id')

        audio_duration = 1.0
        if audio_id:
            audio = db.session.get(Audio, audio_id)
            if audio and audio.duration:
                audio_duration = audio.duration

        log_not_emit('DEBUG', 'reference_params_generator', f'[_calculate_audio_offsets] i={i}, play_order={play_order}, audio_id={audio_id}, audio_duration={audio_duration}, cumulative_offset={cumulative_offset}', category='algorithm')

        if i == 0:
            offsets[play_order] = 0
            log_not_emit('DEBUG', 'reference_params_generator', f'[_calculate_audio_offsets] i=0, set offset=0', category='algorithm')
        else:
            if overlap_time and overlap_time > 0:
                offset_val = cumulative_offset - overlap_time
                if offset_val < 0:
                    log_not_emit('WARNING', 'reference_params_generator', f'[_calculate_audio_offsets] overlap_time={overlap_time} > cumulative_offset={cumulative_offset}, clamping offset to 0', category='algorithm')
                    offset_val = 0
                offsets[play_order] = offset_val
                log_not_emit('DEBUG', 'reference_params_generator', f'[_calculate_audio_offsets] Using overlap_time: offset={cumulative_offset} - {overlap_time} = {offset_val}', category='algorithm')
            elif overlap_rate is not None and overlap_rate > 0:
                offsets[play_order] = cumulative_offset * (1 - overlap_rate)
                log_not_emit('DEBUG', 'reference_params_generator', f'[_calculate_audio_offsets] Using overlap_rate: offset={cumulative_offset} * {1 - overlap_rate} = {cumulative_offset * (1 - overlap_rate)}', category='algorithm')
            else:
                offsets[play_order] = cumulative_offset
                log_not_emit('DEBUG', 'reference_params_generator', f'[_calculate_audio_offsets] No overlap, offset=cumulative_offset={cumulative_offset}', category='algorithm')
        
        if overlap_time and overlap_time > 0:
            cumulative_offset = cumulative_offset - overlap_time + audio_duration
        elif overlap_rate is not None and overlap_rate > 0:
            cumulative_offset += audio_duration * (1 - overlap_rate)
        else:
            cumulative_offset += audio_duration
        
        log_not_emit('DEBUG', 'reference_params_generator', f'[_calculate_audio_offsets] After i={i}: cumulative_offset={cumulative_offset}, offsets={offsets}', category='algorithm')
    
    log_not_emit('DEBUG', 'reference_params_generator', f'[_calculate_audio_offsets] FINAL: offsets={offsets}', category='algorithm')
    return offsets


def _adjust_segment_timestamps(segments: List[Dict], offset: float, play_order: int = None) -> List[Dict]:
    """调整片段的时间戳"""
    adjusted = []
    for seg in segments:
        new_seg = seg.copy()
        if 'start' in new_seg:
            new_seg['start'] = new_seg['start'] + offset
        if 'end' in new_seg:
            new_seg['end'] = new_seg['end'] + offset
        if play_order is not None:
            new_seg['play_order'] = play_order
        adjusted.append(new_seg)
    return adjusted


def _merge_annotation_segments(segments_list: List[List[Dict]]) -> List[Dict]:
    """合并多个标注片段列表，并按时间排序"""
    all_segments = []
    for segments in segments_list:
        all_segments.extend(segments)
    
    all_segments.sort(key=lambda x: (x.get('start', 0), x.get('play_order', 0)))
    return all_segments


def _segments_to_rttm(segments: List[Dict], file_id: str = "test") -> str:
    """将 segments 转换为标准 RTTM 文本格式"""
    lines = []
    for seg in segments:
        speaker = seg.get('speaker', 'spk0')
        start = seg.get('start', 0)
        end = seg.get('end', 0)
        duration = end - start
        lines.append(f"SPEAKER {file_id} 1 {start:.3f} {duration:.3f} <NA> <NA> {speaker} <NA> <NA>")
    return '\n'.join(lines)


def _segments_to_stm(segments: List[Dict], file_id: str = "test", channel: int = 1) -> str:
    """将 segments 转换为标准 STM 文本格式"""
    lines = []
    for seg in segments:
        speaker = seg.get('speaker', 'spk0')
        start = seg.get('start', 0)
        end = seg.get('end', 0)
        text = seg.get('text', '')
        lines.append(f"{file_id} {channel} {speaker} {start:.3f} {end:.3f} {text}")
    return '\n'.join(lines)
