# -*- coding: utf-8 -*-
"""
算法结果字段映射器

职责：
- 从数据库 param_mappings 表动态获取算法结果字段
- 支持从 algorithm_result 和 result_data 中提取字段值
- 替代硬编码的字段名 (rttm_res, stm_res, asr_result 等)
"""

from typing import Dict, List, Any, Optional
from shared.models.algorithm_models import ParamMapping
from shared.utils.log_handler import log_not_emit


class AlgorithmResultFieldMapper:
    """
    算法结果字段映射器 - 从数据库动态获取算法输出字段

    使用方式:
    1. 获取算法的所有输出字段: get_output_fields(algorithm_type)
    2. 从结果中提取字段值: extract_fields_from_result(result_data, fields, source='result_data')
    """

    _output_field_cache: Dict[str, List[Dict[str, Any]]] = {}

    # transform_type → param_type 映射，用于 param_type_map 未命中时的 fallback
    _TRANSFORM_TO_PARAM_TYPE = {
        'rttm_to_obj': 'rttm',
        'stm_to_obj': 'stm',
    }

    @staticmethod
    def _resolve_param_type(param_type_map: Dict[str, str], source_param: str, transform_type: str) -> str:
        """
        解析 param_type：优先用 param_type_map，未命中时用 transform_type 推断
        """
        if source_param in param_type_map:
            return param_type_map[source_param]
        if transform_type in AlgorithmResultFieldMapper._TRANSFORM_TO_PARAM_TYPE:
            return AlgorithmResultFieldMapper._TRANSFORM_TO_PARAM_TYPE[transform_type]
        return 'text'

    @classmethod
    def get_output_fields(cls, algorithm_type: str, test_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        获取算法的所有输出字段（从 param_mappings 表）

        返回格式:
        [
            {"source_param": "rttm_res", "param_type": "rttm", "label": "RTTM结果"},
            {"source_param": "stm_res", "param_type": "stm", "label": "STM结果"},
            {"source_param": "asr_result", "param_type": "text", "label": "ASR结果"},
            ...
        ]

        Args:
            algorithm_type: 算法类型 (asr, translation, speaker_recognition 等)

        Returns:
            输出字段列表
        """
        if algorithm_type == 'voice_llm':
            return cls._get_voice_llm_output_fields(test_type)

        if algorithm_type in cls._output_field_cache:
            return cls._output_field_cache[algorithm_type]

        try:
            from shared.models.algorithm_models import AlgorithmDeviceParam, AlgorithmApiParam
            
            mappings = ParamMapping.query.filter(
                ParamMapping.algorithm_type == algorithm_type,
                ParamMapping.source.in_(['api', 'device']),
                ParamMapping.source_direction == 'output',
                ParamMapping.deleted == False
            ).all()

            # 构建 param_code → param_type 映射
            param_type_map = {}
            device_params = AlgorithmDeviceParam.query.filter_by(
                algorithm_type=algorithm_type, direction='output', deleted=False
            ).all()
            api_params = AlgorithmApiParam.query.filter_by(
                algorithm_type=algorithm_type, direction='output', deleted=False
            ).all()
            for p in device_params + api_params:
                param_type_map[p.param_code] = p.param_type

            fields = []
            for m in mappings:
                field_info = {
                    'source_param': m.source_param,
                    'target_param': m.target_param,
                    'transform_type': m.transform_type,
                    'dimension_id': m.dimension_id,
                    'dimension_name': m.dimension.name if m.dimension else None,
                    'param_type': cls._resolve_param_type(param_type_map, m.source_param, m.transform_type or 'none')
                }
                fields.append(field_info)

            cls._output_field_cache[algorithm_type] = fields
            log_not_emit('DEBUG', 'algorithm_result_field_mapper',
                        f'Loaded {len(fields)} output fields for {algorithm_type}',
                        category='algorithm')

            return fields

        except Exception as e:
            log_not_emit('ERROR', 'algorithm_result_field_mapper',
                        f'Error loading output fields for {algorithm_type}: {e}',
                        category='algorithm')
            return []

    @classmethod
    def get_reference_output_fields(cls, algorithm_type: str) -> List[Dict[str, Any]]:
        """
        获取算法的参考参数输出字段

        返回格式:
        [
            {"source_param": "asr_reference_text", "param_type": "text", "label": "ASR参考文本"},
            {"source_param": "rttm_ref", "param_type": "rttm", "label": "RTTM参考"},
            ...
        ]

        Args:
            algorithm_type: 算法类型

        Returns:
            参考参数字段列表
        """
        try:
            from shared.models.algorithm_models import AlgorithmReferenceParam
            
            mappings = ParamMapping.query.filter_by(
                algorithm_type=algorithm_type,
                source='reference',
                deleted=False
            ).all()

            # 构建 code → param_type 映射
            param_type_map = {}
            ref_params = AlgorithmReferenceParam.query.filter_by(
                algorithm_type=algorithm_type, deleted=False
            ).all()
            for p in ref_params:
                param_type_map[p.code] = p.param_type

            fields = []
            for m in mappings:
                field_info = {
                    'source_param': m.source_param,
                    'target_param': m.target_param,
                    'transform_type': m.transform_type,
                    'param_type': cls._resolve_param_type(param_type_map, m.source_param, m.transform_type or 'none')
                }
                fields.append(field_info)

            return fields

        except Exception as e:
            log_not_emit('ERROR', 'algorithm_result_field_mapper',
                        f'Error loading reference fields for {algorithm_type}: {e}',
                        category='algorithm')
            return []

    @classmethod
    def extract_fields_from_result(cls,
                                   result_data: Dict[str, Any],
                                   fields: List[Dict[str, Any]],
                                   source: str = 'result_data') -> Dict[str, Any]:
        """
        从结果数据中提取指定字段的值

        Args:
            result_data: 源数据 (algorithm_result 或 result_data)
            fields: 字段列表，由 get_output_fields 返回
            source: 数据来源标记 ('algorithm_result' 或 'result_data')

        Returns:
            按 source_param 分组的字段值字典
        """
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
                    'source': source
                }

        return extracted

    @classmethod
    def extract_all_result_fields(cls,
                                  algorithm_type: str,
                                  algorithm_result: Optional[Dict[str, Any]],
                                  result_data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """
        从 algorithm_result 和 result_data 中提取所有算法结果字段

        Args:
            algorithm_type: 算法类型
            algorithm_result: 算法执行结果（从 test_results.algorithm_result）
            result_data: 结果数据（从 test_results.result_data）

        Returns:
            按字段分组的完整结果:
            {
                "rttm_res": {"value": {...}, "source": "algorithm_result/result_data"},
                "stm_res": {"value": {...}, "source": "..."},
                ...
            }
        """
        output_fields = cls.get_output_fields(algorithm_type)

        result = {}

        if algorithm_result:
            from_algo_result = cls.extract_fields_from_result(
                algorithm_result, output_fields, 'algorithm_result'
            )
            result.update(from_algo_result)

        if result_data:
            from_result_data = cls.extract_fields_from_result(
                result_data, output_fields, 'result_data'
            )
            for key, value in from_result_data.items():
                if key not in result:
                    result[key] = value

        log_not_emit('DEBUG', 'algorithm_result_field_mapper',
                    f'Extracted {len(result)} result fields for {algorithm_type}',
                    category='algorithm')

        return result

    @classmethod
    def get_timeline_fields(cls, algorithm_type: str) -> List[Dict[str, Any]]:
        """
        获取用于时间轴展示的字段（RTTM/STM 等标注格式）

        Args:
            algorithm_type: 算法类型

        Returns:
            时间轴相关字段列表
        """
        output_fields = cls.get_output_fields(algorithm_type)

        timeline_fields = []
        for field in output_fields:
            source_param = field.get('source_param', '').lower()
            if any(keyword in source_param for keyword in ['rttm', 'stm', 'segment', 'timeline']):
                timeline_fields.append(field)

        return timeline_fields

    @classmethod
    def get_field_mapping(cls, algorithm_type: str) -> Dict[str, List[Dict[str, Any]]]:
        """
        获取完整的字段映射（包含结果和参考字段，含 param_type）

        返回格式:
        {
            "result": [
                {"param_code": "rttm_res", "param_type": "rttm", "label": "RTTM结果"},
                {"param_code": "asr_result", "param_type": "text", "label": "ASR结果"},
            ],
            "reference": [
                {"param_code": "rttm_ref", "param_type": "rttm", "label": "RTTM参考"},
                {"param_code": "asr_reference_text", "param_type": "text", "label": "ASR参考文本"},
            ]
        }

        Args:
            algorithm_type: 算法类型

        Returns:
            完整的字段映射
        """
        if not algorithm_type:
            return {'result': [], 'reference': []}

        # 结果字段
        output_fields = cls.get_output_fields(algorithm_type)
        result_fields = []
        for f in output_fields:
            param_code = f.get('target_param') or f.get('source_param')
            result_fields.append({
                'param_code': param_code,
                'source_param': f.get('source_param'),
                'param_type': f.get('param_type', 'text'),
                'label': f.get('dimension_name') or param_code
            })

        # 参考字段
        ref_output_fields = cls.get_reference_output_fields(algorithm_type)
        reference_fields = []
        for f in ref_output_fields:
            param_code = f.get('target_param') or f.get('source_param')
            reference_fields.append({
                'param_code': param_code,
                'source_param': f.get('source_param'),
                'param_type': f.get('param_type', 'text'),
                'label': param_code
            })

        return {
            'result': result_fields,
            'reference': reference_fields
        }

    @classmethod
    def _get_voice_llm_output_fields(cls, test_type=None):
        """voice_llm output fields (API vs E2E)"""
        if test_type == 'e2e':
            return [
                {'source_param': 'test_type', 'target_param': 'test_type', 'param_type': 'text', 'dimension_name': 'test type'},
                {'source_param': 'algorithm_type', 'target_param': 'algorithm_type', 'param_type': 'text', 'dimension_name': 'algorithm type'},
                {'source_param': 'session_id', 'target_param': 'session_id', 'param_type': 'text', 'dimension_name': 'session ID'},
                {'source_param': 'rail_distance', 'target_param': 'rail_distance', 'param_type': 'number', 'dimension_name': 'rail distance(cm)'},
                {'source_param': 'voiceprint_registered', 'target_param': 'voiceprint_registered', 'param_type': 'boolean', 'dimension_name': 'voiceprint registered'},
                {'source_param': 'total_rounds', 'target_param': 'total_rounds', 'param_type': 'number', 'dimension_name': 'total rounds'},
                {'source_param': 'rounds', 'target_param': 'rounds', 'param_type': 'json', 'dimension_name': 'round results'},
                {'source_param': 'aggregated', 'target_param': 'aggregated', 'param_type': 'json', 'dimension_name': 'aggregated metrics'},
            ]
        else:  # api
            return [
                {'source_param': 'session_id', 'target_param': 'session_id', 'param_type': 'text', 'dimension_name': 'session ID'},
                {'source_param': 'round_count', 'target_param': 'round_count', 'param_type': 'number', 'dimension_name': 'round count'},
                {'source_param': 'total_latency', 'target_param': 'total_latency', 'param_type': 'number', 'dimension_name': 'total latency(ms)'},
                {'source_param': 'context_mode', 'target_param': 'context_mode', 'param_type': 'text', 'dimension_name': 'context mode'},
                {'source_param': 'history_count', 'target_param': 'history_count', 'param_type': 'number', 'dimension_name': 'history count'},
                {'source_param': 'error', 'target_param': 'error', 'param_type': 'text', 'dimension_name': 'error'},
                {'source_param': 'rounds', 'target_param': 'rounds', 'param_type': 'json', 'dimension_name': 'round results'},
            ]

    @classmethod
    def map_api_results(cls, algorithm_type, raw_results, test_type=None):
        """Map raw API results to standard output fields.

        Args:
            algorithm_type: Algorithm type string
            raw_results: Raw result dict from API/executor
            test_type: 'api' or 'e2e', only used for voice_llm

        Returns:
            Mapped result dict
        """
        if algorithm_type == 'voice_llm':
            return cls._map_voice_llm_results(raw_results, test_type)

        output_fields = cls.get_output_fields(algorithm_type)
        mapped = {}
        for field in output_fields:
            source_param = field.get('source_param', '')
            target_param = field.get('target_param', source_param)
            if source_param and source_param in raw_results:
                mapped[target_param] = raw_results[source_param]
        return mapped

    @classmethod
    def _map_voice_llm_results(cls, raw_results, test_type=None):
        """voice_llm result mapping - API vs E2E"""
        if test_type == 'e2e':
            return {
                'test_type': raw_results.get('test_type', 'e2e'),
                'algorithm_type': raw_results.get('algorithm_type', 'voice_llm'),
                'session_id': raw_results.get('session_id'),
                'rail_distance': raw_results.get('rail_distance', 50),
                'voiceprint_registered': raw_results.get('voiceprint_registered', False),
                'total_rounds': raw_results.get('total_rounds', 0),
                'rounds': raw_results.get('rounds', []),
                'aggregated': raw_results.get('aggregated', {}),
            }
        else:  # api
            return {
                'session_id': raw_results.get('session_id', ''),
                'round_count': raw_results.get('round_count', 0),
                'total_latency': raw_results.get('total_latency', 0),
                'context_mode': raw_results.get('context_mode', ''),
                'history_count': raw_results.get('history_count', 0),
                'error': raw_results.get('error'),
                'rounds': raw_results.get('rounds', []),
            }

    @classmethod
    def extract_round_results(cls, algorithm_result, test_type=None):
        """Extract per-round results from stored algorithm_result JSON.

        Handles different indexing: API uses 1-indexed roundNumber,
        E2E uses 0-indexed round.

        Args:
            algorithm_result: Stored algorithm_result dict from DB
            test_type: 'api' or 'e2e'

        Returns:
            List of per-round result dicts, sorted by round_number
        """
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
        else:  # api
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
        """清除字段缓存"""
        cls._output_field_cache.clear()
        log_not_emit('DEBUG', 'algorithm_result_field_mapper', 'Cache cleared', category='algorithm')


def get_result_field_mapper() -> AlgorithmResultFieldMapper:
    """获取算法结果字段映射器实例"""
    return AlgorithmResultFieldMapper
