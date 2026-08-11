# -*- coding: utf-8 -*-
"""参考参数生成查询处理器

CQRS 读侧 - 迁移自 shared/algorithm/reference_params/generator.py
注意：生成逻辑在 algorithm_service 内，存储逻辑（写回 test_case.reference_params）由调用方处理。
"""

import json
from typing import Dict, List, Any, Optional

from algorithm_service.domain.services.reference_helpers import (
    ReferenceHelpersService,
    _REF_PARAMS_BUCKET,
)
from algorithm_service.domain.services.audio_analysis import AudioAnalysisService
from algorithm_service.infrastructure.acl.audio_acl_repository import audio_acl_repository
from algorithm_service.infrastructure.storage.ref_params_storage import ref_params_storage
from algorithm_service.infrastructure.persistence.param_repository import reference_param_repository
from shared.utils.log_handler import log_not_emit


class ReferenceParamsQueryHandler:
    """参考参数生成查询处理器"""

    @classmethod
    def generate_for_round(cls, test_case_config: Dict, round_data: dict) -> list:
        """为单个 round 生成参考参数列表

        Args:
            test_case_config: 测试用例配置 dict（需含 algorithm_type, config 等字段）
            round_data: 单个 round 的配置字典

        Returns:
            参考参数列表
        """
        if not test_case_config or not round_data:
            return []

        algorithm_type = test_case_config.get('algorithm_type')

        config = (test_case_config.get('config') or {}).copy()

        ap = round_data.get('algorithm_params')
        if ap:
            config['algorithm_params'] = ap

        config['audios'] = round_data.get('audios', [])
        config['_record_test_type'] = test_case_config.get('test_type', 'api') or 'api'

        round_audios = config['audios']
        audio_ids = [item.get('audio_id') for item in round_audios if item.get('audio_id')]

        round_number = round_data.get('round_number', '?')
        log_not_emit('DEBUG', 'reference_params_queries',
                     f'Generating reference params for round {round_number}, algorithm_type: {algorithm_type}, audio_ids: {audio_ids}',
                     category='algorithm')

        preload_context = audio_acl_repository.preload_audio_data(audio_ids)
        config['_preload_context'] = preload_context

        ref_params = reference_param_repository.list_by_algorithm(algorithm_type)

        if not ref_params:
            log_not_emit('WARNING', 'reference_params_queries',
                         f'No reference params found for algorithm: {algorithm_type}',
                         category='algorithm')
            return []

        result = []
        for ref_param in ref_params:
            try:
                param = cls._generate_single_param(config, ref_param)
                if param:
                    result.append(param)
            except Exception as e:
                log_not_emit('ERROR', 'reference_params_queries',
                             f'Error generating param {ref_param.get("code")} for round {round_number}: {e}',
                             category='algorithm')
                continue

        log_not_emit('DEBUG', 'reference_params_queries',
                     f'Generated {len(result)} reference params for round {round_number}',
                     category='algorithm')
        return result

    @classmethod
    def generate(cls, test_case_config: Dict) -> list:
        """为所有 round 生成参考参数列表"""
        if not test_case_config:
            return []

        config = test_case_config.get('config') or {}
        rounds = config.get('rounds', [])

        if not rounds:
            return []

        all_params = []
        for round_item in rounds:
            if isinstance(round_item, dict):
                round_params = cls.generate_for_round(test_case_config, round_item)
                all_params.extend(round_params)
        return all_params

    @classmethod
    def _generate_single_param(cls, config: Dict, ref_param) -> Dict:
        """根据参考参数配置生成单个参数"""
        code = ref_param.get('code')
        param_type = ref_param.get('param_type') or ref_param.get('type')
        annotation_code = ref_param.get('annotation_code')
        annotation_format = ref_param.get('annotation_format')
        field_path = ref_param.get('field_path')
        merge_mode = ref_param.get('merge_mode') or 'join'
        record_test_type = config.get('_record_test_type', 'api')

        if not field_path and code and param_type == 'text':
            field_path = f'segments[].{code}'

        values = {}

        if field_path:
            values = cls._extract_field_from_audios(
                config, field_path, merge_mode,
                annotation_code=annotation_code,
                annotation_format=annotation_format,
            )
        elif annotation_code == 'translation' or (code and 'translation' in code.lower()):
            values = cls._extract_translation_from_audios(config)
        elif param_type in ['json', 'rttm', 'stm']:
            values = cls._extract_annotation_with_overlap(
                config, param_type,
                annotation_code=annotation_code,
                annotation_format=annotation_format,
            )
        else:
            values = cls._extract_text_from_audios(
                config,
                annotation_code=annotation_code,
                annotation_format=annotation_format,
            )

        value = values.get(record_test_type)

        if not value:
            return None

        param = {
            'code': code,
            'type': param_type,
            'value': value,
        }

        if annotation_code:
            param['annotation_code'] = annotation_code
        if annotation_format:
            param['annotation_format'] = annotation_format

        return param

    @classmethod
    def _extract_field_from_audios(
        cls, config: Dict, field_path: str, merge_mode: str = 'join',
        annotation_code: str = None, annotation_format: str = None,
    ) -> Dict[str, Any]:
        """按字段路径从音频标注 segments 提取值"""
        if not field_path.startswith('segments[].'):
            field_path = f'segments[].{field_path}'

        field_name = field_path.replace('segments[].', '')

        preload = config.get('_preload_context', {})
        annotation_map = preload.get('annotation_map', {})
        audios = config.get('audios', [])

        api_values = []
        e2e_values = []

        for audio_item in audios:
            audio_id = audio_item.get('audio_id')
            anns = annotation_map.get(audio_id, [])
            for ann in anns:
                if annotation_code and AudioAnalysisService.ann_field(ann, 'annotation_code') != annotation_code:
                    continue
                if annotation_format and AudioAnalysisService.ann_field(ann, 'annotation_format') != annotation_format:
                    continue
                data = AudioAnalysisService.ann_field(ann, 'data', {})
                segments = data.get('segments', []) if isinstance(data, dict) else []
                for seg in segments:
                    if isinstance(seg, dict) and field_name in seg:
                        api_values.append(seg[field_name])
                        e2e_values.append(seg[field_name])

        def _merge(vals, mode):
            if not vals:
                return ''
            if mode == 'first':
                return vals[0]
            if mode == 'collect':
                return vals
            return '\n'.join(str(v) for v in vals)

        return {
            'api': _merge(api_values, merge_mode),
            'e2e': _merge(e2e_values, merge_mode),
        }

    @classmethod
    def _extract_text_from_audios(
        cls, config: Dict, text_field: str = None,
        annotation_code: str = None, annotation_format: str = None,
    ) -> Dict[str, str]:
        """从标注提取文本"""
        preload = config.get('_preload_context', {})
        annotation_map = preload.get('annotation_map', {})
        audios = config.get('audios', [])

        api_values = []
        e2e_values = []

        for audio_item in audios:
            audio_id = audio_item.get('audio_id')
            anns = annotation_map.get(audio_id, [])
            for ann in anns:
                if annotation_code and AudioAnalysisService.ann_field(ann, 'annotation_code') != annotation_code:
                    continue
                if annotation_format and AudioAnalysisService.ann_field(ann, 'annotation_format') != annotation_format:
                    continue
                data = AudioAnalysisService.ann_field(ann, 'data', {})
                if isinstance(data, dict):
                    text = data.get('text', '')
                    if text:
                        api_values.append(text)
                        e2e_values.append(text)
                    segments = data.get('segments', [])
                    for seg in segments:
                        if isinstance(seg, dict) and seg.get('text'):
                            api_values.append(seg['text'])
                            e2e_values.append(seg['text'])

        return {
            'api': '\n'.join(api_values),
            'e2e': '\n'.join(e2e_values),
        }

    @classmethod
    def _extract_annotation_with_overlap(
        cls, config: Dict, format_type: str = 'rttm',
        annotation_code: str = None, annotation_format: str = None,
    ) -> Dict[str, Any]:
        """提取标注数据支持重叠播放时间戳调整"""
        preload = config.get('_preload_context', {})
        audio_map = preload.get('audio_map', {})
        annotation_map = preload.get('annotation_map', {})
        duration_map = preload.get('duration_map', {})
        audios = config.get('audios', [])

        overlap_rate = ReferenceHelpersService.get_overlap_rate(config)
        overlap_time = ReferenceHelpersService.get_overlap_time(config)

        audio_speakers = {}
        for audio_item in audios:
            audio_id = audio_item.get('audio_id')
            speakers = AudioAnalysisService.extract_speakers_from_annotations(audio_id, annotation_map)
            audio_speakers[audio_id] = speakers

        offsets = AudioAnalysisService.calculate_speaker_aware_offsets(
            audios, overlap_rate, overlap_time,
            audio_durations=duration_map,
            audio_speakers=audio_speakers,
        )

        all_segments = []
        for idx, audio_item in enumerate(audios):
            audio_id = audio_item.get('audio_id')
            anns = annotation_map.get(audio_id, [])
            offset = offsets.get(audio_id, 0)

            for ann in anns:
                if annotation_code and AudioAnalysisService.ann_field(ann, 'annotation_code') != annotation_code:
                    continue
                if annotation_format and AudioAnalysisService.ann_field(ann, 'annotation_format') != annotation_format:
                    continue
                data = AudioAnalysisService.ann_field(ann, 'data', {})
                segments = data.get('segments', []) if isinstance(data, dict) else []
                adjusted = AudioAnalysisService.adjust_segment_timestamps(segments, offset, idx)
                all_segments.extend(adjusted)

        merged = AudioAnalysisService.merge_annotation_segments([all_segments])

        if format_type == 'rttm':
            text = AudioAnalysisService.segments_to_rttm(merged)
        elif format_type == 'stm':
            text = AudioAnalysisService.segments_to_stm(merged)
        else:
            text = json.dumps(merged, ensure_ascii=False)

        result = {'text': text, 'json': merged, 'segments': merged}
        return {'api': result, 'e2e': result}

    @classmethod
    def _extract_translation_from_audios(cls, config: Dict) -> Dict[str, Any]:
        """提取翻译参考文本"""
        preload = config.get('_preload_context', {})
        annotation_map = preload.get('annotation_map', {})
        audios = config.get('audios', [])

        translations = []
        for audio_item in audios:
            audio_id = audio_item.get('audio_id')
            anns = annotation_map.get(audio_id, [])
            for ann in anns:
                ann_code = AudioAnalysisService.ann_field(ann, 'annotation_code', '')
                if ann_code == 'translation':
                    data = AudioAnalysisService.ann_field(ann, 'data', {})
                    if isinstance(data, dict):
                        segments = data.get('segments', [])
                        text_parts = [seg.get('text', '') for seg in segments if isinstance(seg, dict) and seg.get('text')]
                        if text_parts:
                            translations.append('\n'.join(text_parts))

        result = '\n'.join(translations)
        return {'api': result, 'e2e': result}

    @classmethod
    def load_from_file(cls, filepath: str) -> list:
        """从 OSS 加载参考参数"""
        return ref_params_storage.load_reference_params(filepath)

    @classmethod
    def get_reference_text(cls, reference_params_col, code: str) -> str:
        """从参考参数获取参考文本"""
        all_params = cls.get_all_reference_params(reference_params_col)
        if not all_params:
            return ''
        if code:
            for param in all_params:
                if param.get('code') == code:
                    return param.get('value', '') or ''
        return ''

    @classmethod
    def get_all_reference_params(cls, reference_params_col) -> list:
        """获取所有参考参数（从 reference_params_col 加载）"""
        if not reference_params_col:
            return []

        if isinstance(reference_params_col, dict):
            direct_ref = reference_params_col.get('reference_params')
            if direct_ref:
                return ReferenceHelpersService.normalize_reference_params(direct_ref)

            rounds = reference_params_col.get('rounds', [])
            if not rounds:
                return []

            all_refs = []
            for round_item in rounds:
                if not isinstance(round_item, dict):
                    continue
                ref_path = round_item.get('reference_params_path') or round_item.get('referenceParamsPath')
                if ref_path:
                    round_refs = cls.load_from_file(ref_path)
                    if round_refs:
                        rn = round_item.get('round_number') or round_item.get('roundNumber')
                        for p in round_refs:
                            if isinstance(p, dict) and 'round_number' not in p:
                                p['round_number'] = rn
                        all_refs.extend(round_refs)
            return all_refs

        if isinstance(reference_params_col, list):
            if reference_params_col and isinstance(reference_params_col[0], dict) and 'code' in reference_params_col[0]:
                return ReferenceHelpersService.normalize_reference_params(reference_params_col)

            all_refs = []
            for item in reference_params_col:
                if not isinstance(item, dict):
                    continue
                ref_path = item.get('reference_params_path') or item.get('referenceParamsPath')
                if ref_path:
                    round_refs = cls.load_from_file(ref_path)
                    if round_refs:
                        rn = item.get('round_number') or item.get('roundNumber')
                        for p in round_refs:
                            if isinstance(p, dict) and 'round_number' not in p:
                                p['round_number'] = rn
                        all_refs.extend(round_refs)
            return all_refs

        return []

    @classmethod
    def get_reference_params_for_report(cls, reference_params_col) -> Dict[str, Any]:
        """获取用于报告展示的参考参数字典"""
        result = {}
        reference_params = cls.get_all_reference_params(reference_params_col)

        if not reference_params:
            return result

        by_code = {}
        for param in reference_params:
            if not isinstance(param, dict):
                continue
            code = param.get('code')
            if not code:
                continue
            by_code.setdefault(code, []).append(param)

        for code, params in by_code.items():
            has_multi_round = any(p.get('round_number') is not None for p in params) and len(params) > 1
            for param in params:
                rn = param.get('round_number')
                if has_multi_round and rn is not None:
                    key = f'{code}@round:{rn}'
                else:
                    key = code

                param_type = param.get('type', 'text')
                value = param.get('value')

                param_info = {
                    'code': code,
                    'type': param_type,
                    'value': value,
                }
                if rn is not None:
                    param_info['round_number'] = rn
                    param_info['label'] = f'{code} (第{rn}轮)'

                if param_type in ['rttm', 'stm'] and isinstance(value, dict):
                    param_info['segments'] = value.get('segments', [])
                    param_info['text'] = value.get('text', '')
                    param_info['json'] = value.get('json', '')

                if param.get('annotation_code'):
                    param_info['annotation_code'] = param.get('annotation_code')
                if param.get('annotation_format'):
                    param_info['annotation_format'] = param.get('annotation_format')

                result[key] = param_info

        return result
