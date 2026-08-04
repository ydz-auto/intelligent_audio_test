# -*- coding: utf-8 -*-
"""
参考参数生成器包

职责：
- 根据算法类型和用例配置，从数据库读取参考参数配置
- 自动生成对应测试用例的参考参数（ASR文本、翻译文本、RTTM/STM标注等）
- 支持重叠播放场景的时间戳调整
- 提供参考参数值的获取接口
"""

from .helpers import (
    _REF_PARAMS_BUCKET,
    _KNOWN_DATA_KEYS,
    _build_ref_params_key,
    normalize_reference_params,
    _normalize_single_ref_param,
    _get_overlap_rate,
    _get_overlap_time,
)
from .audio_utils import (
    _extract_speakers_from_audio,
    _calculate_speaker_aware_offsets,
    _calculate_audio_offsets,
    _adjust_segment_timestamps,
    _merge_annotation_segments,
    _segments_to_rttm,
    _segments_to_stm,
)
from .extractors import (
    _extract_field_from_audios,
    _extract_text_from_audios,
    _extract_annotation_with_overlap,
    _extract_translation_from_audios,
    _extract_annotation_from_audios,
)
from .generator import ReferenceParamsGenerator
from .factory import get_reference_params_generator, get_reference_value

__all__ = [
    # helpers
    '_REF_PARAMS_BUCKET',
    '_KNOWN_DATA_KEYS',
    '_build_ref_params_key',
    'normalize_reference_params',
    '_normalize_single_ref_param',
    '_get_overlap_rate',
    '_get_overlap_time',
    # audio_utils
    '_extract_speakers_from_audio',
    '_calculate_speaker_aware_offsets',
    '_calculate_audio_offsets',
    '_adjust_segment_timestamps',
    '_merge_annotation_segments',
    '_segments_to_rttm',
    '_segments_to_stm',
    # extractors
    '_extract_field_from_audios',
    '_extract_text_from_audios',
    '_extract_annotation_with_overlap',
    '_extract_translation_from_audios',
    '_extract_annotation_from_audios',
    # generator
    'ReferenceParamsGenerator',
    # factory
    'get_reference_params_generator',
    'get_reference_value',
]
