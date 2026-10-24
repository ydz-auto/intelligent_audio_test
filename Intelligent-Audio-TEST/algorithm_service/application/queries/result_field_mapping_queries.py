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
        """读取算法输出字段声明（配置驱动，C0 裁定 3）。

        来源：
        - 字段清单与类型：`algorithm_api_params(direction=output)`（API 输出声明，
          优先且唯一）+ `algorithm_device_params(direction=output)`（设备输出声明，
          供同一算法类型的设备/E2E 结果展示，API 侧已声明的键不重复）；
          顺序均按 ui_order / id；
        - API 字段的映射目标键：`param_mappings(source='api', source_direction='output')`，
          无映射时按恒等（target_param = param_code）。

        配置缺失时明确降级并写 WARNING，不再回落到任何硬编码字段表，避免静默错值。

        Args:
            algorithm_type: 算法类型
            test_type: 仅为 RPC 契约保留，输出字段不再按 test_type 分支
        """
        if not algorithm_type:
            return []
        if algorithm_type in cls._output_field_cache:
            return cls._output_field_cache[algorithm_type]

        try:
            api_declared = cls._output_declarations(algorithm_type, 'api')
            device_declared = cls._output_declarations(algorithm_type, 'device')
            if not api_declared and not device_declared:
                log_not_emit(
                    'WARNING', 'result_field_mapping_queries',
                    f'algorithm_type={algorithm_type} 无 direction=output 的输出字段声明，'
                    f'输出字段按空清单降级（请在算法配置中补输出字段声明）',
                    category='algorithm', algorithm_type=algorithm_type,
                )
                return []
            if not api_declared:
                log_not_emit(
                    'WARNING', 'result_field_mapping_queries',
                    f'algorithm_type={algorithm_type} 无 algorithm_api_params(direction=output) '
                    f'声明，API 结果将无输出字段（仅设备声明可用）',
                    category='algorithm', algorithm_type=algorithm_type,
                )

            mappings = mapping_repository.list_by_algorithm(algorithm_type, source_type='api')
            mapping_by_source: Dict[str, Dict[str, Any]] = {}
            for m in mappings:
                if not isinstance(m, dict) or m.get('source') != 'api':
                    continue
                if m.get('source_direction') != 'output':
                    continue
                source_param = m.get('source_param')
                if source_param and source_param not in mapping_by_source:
                    mapping_by_source[source_param] = m

            fields: List[Dict[str, Any]] = []
            seen = set()

            for p in api_declared:
                param_code = p.get('param_code')
                if not param_code or param_code in seen:
                    continue
                seen.add(param_code)
                mapping = mapping_by_source.get(param_code) or {}
                fields.append({
                    'source': 'api',
                    'source_param': param_code,
                    'target_param': mapping.get('target_param') or param_code,
                    'param_type': p.get('param_type') or 'text',
                    'label': p.get('label') or p.get('param_name') or param_code,
                    'dimension_id': mapping.get('dimension_id'),
                    'dimension_name': None,
                    'transform_type': mapping.get('transform_type') or 'none',
                    'field_path': p.get('field_path'),
                    'ui_order': p.get('ui_order') or 0,
                })

            for p in device_declared:
                param_code = p.get('param_code')
                if not param_code or param_code in seen:
                    continue
                seen.add(param_code)
                fields.append({
                    'source': 'device',
                    'source_param': param_code,
                    'target_param': param_code,
                    'param_type': p.get('param_type') or 'text',
                    'label': p.get('label') or p.get('param_name') or param_code,
                    'dimension_id': None,
                    'dimension_name': None,
                    'transform_type': 'none',
                    'field_path': None,
                    'ui_order': p.get('ui_order') or 0,
                })

            cls._output_field_cache[algorithm_type] = fields
            return fields

        except Exception as e:
            log_not_emit('ERROR', 'result_field_mapping_queries',
                         f'Error loading output fields for {algorithm_type}: {e}', category='algorithm')
            return []

    @staticmethod
    def _output_declarations(algorithm_type: str, param_type: str) -> List[Dict[str, Any]]:
        """按来源（api / device）读取 direction=output 的声明，按 ui_order / id 排序。"""
        params = algorithm_param_repository.list_by_algorithm(algorithm_type, param_type)
        declared = [
            p for p in params
            if isinstance(p, dict) and (p.get('direction') or '') == 'output'
        ]
        return sorted(declared, key=lambda item: (item.get('ui_order') or 0, item.get('id') or 0))

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
                'label': f.get('label') or f.get('dimension_name') or param_code,
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
