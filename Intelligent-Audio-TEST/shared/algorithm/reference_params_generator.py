# -*- coding: utf-8 -*-
"""
参考参数生成器（兼容 shim）

此模块已重构为 reference_params 包，为保持向后兼容，
所有公共 API 从新包重新导出。

原始实现位于 shared.algorithm.reference_params 包中：
- helpers.py: 辅助函数和常量
- audio_utils.py: 音频相关辅助函数
- extractors.py: 数据提取函数
- generator.py: ReferenceParamsGenerator 类
- factory.py: 工厂函数
"""

from shared.algorithm.reference_params import (
    # helpers
    _REF_PARAMS_BUCKET,
    _KNOWN_DATA_KEYS,
    _build_ref_params_key,
    normalize_reference_params,
    _normalize_single_ref_param,
    _get_overlap_rate,
    _get_overlap_time,
    # audio_utils
    _extract_speakers_from_audio,
    _calculate_speaker_aware_offsets,
    _calculate_audio_offsets,
    _adjust_segment_timestamps,
    _merge_annotation_segments,
    _segments_to_rttm,
    _segments_to_stm,
    # extractors
    _extract_field_from_audios,
    _extract_text_from_audios,
    _extract_annotation_with_overlap,
    _extract_translation_from_audios,
    _extract_annotation_from_audios,
    # generator
    ReferenceParamsGenerator,
    # factory
    get_reference_params_generator,
    get_reference_value,
)

__all__ = [
    '_REF_PARAMS_BUCKET',
    '_KNOWN_DATA_KEYS',
    '_build_ref_params_key',
    'normalize_reference_params',
    '_normalize_single_ref_param',
    '_get_overlap_rate',
    '_get_overlap_time',
    '_extract_speakers_from_audio',
    '_calculate_speaker_aware_offsets',
    '_calculate_audio_offsets',
    '_adjust_segment_timestamps',
    '_merge_annotation_segments',
    '_segments_to_rttm',
    '_segments_to_stm',
    '_extract_field_from_audios',
    '_extract_text_from_audios',
    '_extract_annotation_with_overlap',
    '_extract_translation_from_audios',
    '_extract_annotation_from_audios',
    'ReferenceParamsGenerator',
    'get_reference_params_generator',
    'get_reference_value',
]
