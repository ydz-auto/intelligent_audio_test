# -*- coding: utf-8 -*-
"""结果字段映射查询处理器

CQRS 读侧 - 迁移自 shared/algorithm/algorithm_result_field_mapper.py
"""

from typing import Dict, List, Any, Optional

from algorithm_service.infrastructure.persistence.config_cache import get_config_cache
from algorithm_service.infrastructure.persistence.param_repository import (
    algorithm_param_repository,
    reference_param_repository,
    mapping_repository,
)
from shared.utils.log_handler import log_not_emit
from shared.domain.algorithm_result_strategy import AlgorithmStrategyFactory


class ResultFieldMappingQueryHandler:
    """结果字段映射查询处理器"""

    _output_field_cache: Dict[str, List[Dict[str, Any]]] = {}
    _TRANSFORM_TO_PARAM_TYPE = {
        'rttm_to_obj': 'rttm',
        'stm_to_obj': 'stm',
    }

    @classmethod
    def _resolve_param_type(cls, param_type_map: Dict[str, str], source_param: str, transform_type: str) -> str:
        if source_param in param_type_map:
            return param_type_map[source_param]
        if transform_type in cls._TRANSFORM_TO_PARAM_TYPE:
            return cls._TRANSFORM_TO_PARAM_TYPE[transform_type]
        return 'text'

    @classmethod
    def get_output_fields(cls, algorithm_type: str, test_type: Optional[str] = None) -> List[Dict[str, Any]]:
        # 通过策略模式消除 voice_llm 硬编码分支
        strategy = AlgorithmStrategyFactory.get_strategy(algorithm_type)
        strategy_fields = strategy.get_output_fields(test_type)
        if strategy_fields is not None:
            return strategy_fields

        if algorithm_type in cls._output_field_cache:
            return cls._output_field_cache[algorithm_type]

        try:
            mappings = mapping_repository.list_by_algorithm(algorithm_type)
            output_mappings = [
                m for m in mappings
                if isinstance(m, dict)
                and m.get('source') in ('api', 'device')
                and m.get('source_direction') == 'output'
            ]

            param_type_map = {}
            device_params = algorithm_param_repository.list_by_algorithm(algorithm_type, 'device')
            api_params = algorithm_param_repository.list_by_algorithm(algorithm_type, 'api')
            for p in device_params + api_params:
                if isinstance(p, dict):
                    p_code = p.get('param_code') or p.get('code')
                    if p_code:
                        param_type_map[p_code] = p.get('param_type') or p.get('type')

            fields = []
            for m in output_mappings:
                field_info = {
                    'source_param': m.get('source_param'),
                    'target_param': m.get('target_param'),
                    'transform_type': m.get('transform_type'),
                    'dimension_id': m.get('dimension_id'),
                    'dimension_name': m.get('dimension_name'),
                    'param_type': cls._resolve_param_type(
                        param_type_map,
                        m.get('source_param') or '',
                        m.get('transform_type') or 'none',
                    ),
                }
                fields.append(field_info)

            cls._output_field_cache[algorithm_type] = fields
            return fields

        except Exception as e:
            log_not_emit('ERROR', 'result_field_mapping_queries',
                         f'Error loading output fields for {algorithm_type}: {e}', category='algorithm')
            return []

    @classmethod
    def get_reference_output_fields(cls, algorithm_type: str) -> List[Dict[str, Any]]:
        try:
            mappings = mapping_repository.list_by_algorithm(algorithm_type)
            ref_mappings = [m for m in mappings if isinstance(m, dict) and m.get('source') == 'reference']

            param_type_map = {}
            ref_params = reference_param_repository.list_by_algorithm(algorithm_type)
            for p in ref_params:
                if isinstance(p, dict):
                    code = p.get('code')
                    if code:
                        param_type_map[code] = p.get('param_type') or p.get('type')

            fields = []
            for m in ref_mappings:
                field_info = {
                    'source_param': m.get('source_param'),
                    'target_param': m.get('target_param'),
                    'transform_type': m.get('transform_type'),
                    'param_type': cls._resolve_param_type(
                        param_type_map,
                        m.get('source_param') or '',
                        m.get('transform_type') or 'none',
                    ),
                }
                fields.append(field_info)
            return fields

        except Exception as e:
            log_not_emit('ERROR', 'result_field_mapping_queries',
                         f'Error loading reference fields for {algorithm_type}: {e}', category='algorithm')
            return []

    @staticmethod
    def extract_fields_from_result(
        result_data: Dict[str, Any],
        fields: List[Dict[str, Any]],
        source: str = 'result_data',
    ) -> Dict[str, Any]:
        extracted = {}
        if not result_data:
            return extracted
        for field in fields:
            source_param = field.get('source_param')
            if not source_param:
                continue
            value = result_data.get(source_param)
            if value is not None:
                extracted[source_param] = {
                    'value': value,
                    'target_param': field.get('target_param'),
                    'source': source,
                }
        return extracted

    @classmethod
    def extract_all_result_fields(
        cls,
        algorithm_type: str,
        algorithm_result: Optional[Dict[str, Any]],
        result_data: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        output_fields = cls.get_output_fields(algorithm_type)
        result = {}

        if algorithm_result:
            from_algo_result = cls.extract_fields_from_result(algorithm_result, output_fields, 'algorithm_result')
            result.update(from_algo_result)

        if result_data:
            from_result_data = cls.extract_fields_from_result(result_data, output_fields, 'result_data')
            for key, value in from_result_data.items():
                if key not in result:
                    result[key] = value

        return result

    @classmethod
    def get_timeline_fields(cls, algorithm_type: str) -> List[Dict[str, Any]]:
        output_fields = cls.get_output_fields(algorithm_type)
        timeline_fields = []
        for field in output_fields:
            source_param = field.get('source_param', '').lower()
            if any(kw in source_param for kw in ['rttm', 'stm', 'segment', 'timeline']):
                timeline_fields.append(field)
        return timeline_fields

    @classmethod
    def get_field_mapping(cls, algorithm_type: str) -> Dict[str, List[Dict[str, Any]]]:
        if not algorithm_type:
            return {'result': [], 'reference': []}

        output_fields = cls.get_output_fields(algorithm_type)
        result_fields = []
        for f in output_fields:
            param_code = f.get('target_param') or f.get('source_param')
            result_fields.append({
                'param_code': param_code,
                'source_param': f.get('source_param'),
                'param_type': f.get('param_type', 'text'),
                'label': f.get('dimension_name') or param_code,
            })

        ref_output_fields = cls.get_reference_output_fields(algorithm_type)
        reference_fields = []
        for f in ref_output_fields:
            param_code = f.get('target_param') or f.get('source_param')
            reference_fields.append({
                'param_code': param_code,
                'source_param': f.get('source_param'),
                'param_type': f.get('param_type', 'text'),
                'label': param_code,
            })

        return {'result': result_fields, 'reference': reference_fields}

    @classmethod
    def map_api_results(cls, algorithm_type, raw_results, test_type=None):
        # 通过策略模式消除 voice_llm 硬编码分支
        strategy = AlgorithmStrategyFactory.get_strategy(algorithm_type)
        mapped = strategy.map_api_results(raw_results, test_type)
        if mapped is not None:
            return mapped

        output_fields = cls.get_output_fields(algorithm_type)
        mapped = {}
        for field in output_fields:
            source_param = field.get('source_param', '')
            target_param = field.get('target_param', source_param)
            if source_param and source_param in raw_results:
                mapped[target_param] = raw_results[source_param]
        return mapped

    @classmethod
    def extract_round_results(cls, algorithm_result, test_type=None):
        if not algorithm_result:
            return []

        rounds = algorithm_result.get('rounds', [])
        is_e2e = test_type == 'e2e' or algorithm_result.get('test_type') == 'e2e'

        if is_e2e:
            return [
                {
                    'round_number': r.get('round', idx),
                    'input_audio_name': r.get('input', {}).get('audio_name', ''),
                    'input_audio_path': r.get('input', {}).get('audio_path', ''),
                    'input_type': r.get('input', {}).get('type', ''),
                    'asr_text': r.get('output', {}).get('asr_text', ''),
                    'device_raw': r.get('output', {}).get('device_raw'),
                    'latency': r.get('latency', 0),
                    'wait_time': r.get('wait_time'),
                    'interruption': r.get('interruption'),
                    'evaluation': r.get('evaluation', {}),
                }
                for idx, r in enumerate(rounds)
            ]
        else:
            return [
                {
                    'round_number': r.get('roundNumber', idx + 1) - 1,
                    'input_text': r.get('input', {}).get('text', ''),
                    'llm_response': r.get('output', ''),
                    'latency': r.get('latency', 0),
                    'response_metrics': r.get('response_metrics', {}),
                    'round_evaluation': r.get('round_evaluation', {}),
                }
                for idx, r in enumerate(rounds)
            ]

    @classmethod
    def clear_cache(cls) -> None:
        cls._output_field_cache.clear()
