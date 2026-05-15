# -*- coding: utf-8 -*-
"""
算法结果字段映射器

职责：
- 从数据库 param_mappings 表动态获取算法结果字段
- 支持从 algorithm_result 和 result_data 中提取字段值
- 替代硬编码的字段名 (rttm_res, stm_res, asr_result 等)
"""

from typing import Dict, List, Any, Optional
from backend.models.algorithm_models import ParamMapping
from backend.utils.log_handler import log_not_emit


class AlgorithmResultFieldMapper:
    """
    算法结果字段映射器 - 从数据库动态获取算法输出字段

    使用方式:
    1. 获取算法的所有输出字段: get_output_fields(algorithm_type)
    2. 从结果中提取字段值: extract_fields_from_result(result_data, fields, source='result_data')
    """

    _output_field_cache: Dict[str, List[Dict[str, Any]]] = {}

    @classmethod
    def get_output_fields(cls, algorithm_type: str) -> List[Dict[str, Any]]:
        """
        获取算法的所有输出字段（从 param_mappings 表）

        返回格式:
        [
            {"source_param": "rttm_res", "field_type": "json", "label": "RTTM结果"},
            {"source_param": "stm_res", "field_type": "json", "label": "STM结果"},
            {"source_param": "asr_result", "field_type": "text", "label": "ASR结果"},
            ...
        ]

        Args:
            algorithm_type: 算法类型 (asr, translation, speaker_recognition 等)

        Returns:
            输出字段列表
        """
        if algorithm_type in cls._output_field_cache:
            return cls._output_field_cache[algorithm_type]

        try:
            mappings = ParamMapping.query.filter(
                ParamMapping.algorithm_type == algorithm_type,
                ParamMapping.source.in_(['api', 'device']),
                ParamMapping.source_direction == 'output',
                ParamMapping.deleted == False
            ).all()

            fields = []
            for m in mappings:
                field_info = {
                    'source_param': m.source_param,
                    'target_param': m.target_param,
                    'transform_type': m.transform_type,
                    'dimension_id': m.dimension_id,
                    'dimension_name': m.dimension.name if m.dimension else None
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
            {"source_param": "asr_reference_text", "field_type": "text", "label": "ASR参考文本"},
            {"source_param": "rttm_ref", "field_type": "json", "label": "RTTM参考"},
            ...
        ]

        Args:
            algorithm_type: 算法类型

        Returns:
            参考参数字段列表
        """
        try:
            mappings = ParamMapping.query.filter_by(
                algorithm_type=algorithm_type,
                source='reference',
                deleted=False
            ).all()

            fields = []
            for m in mappings:
                field_info = {
                    'source_param': m.source_param,
                    'target_param': m.target_param,
                    'transform_type': m.transform_type
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
    def clear_cache(cls) -> None:
        """清除字段缓存"""
        cls._output_field_cache.clear()
        log_not_emit('DEBUG', 'algorithm_result_field_mapper', 'Cache cleared', category='algorithm')


def get_result_field_mapper() -> AlgorithmResultFieldMapper:
    """获取算法结果字段映射器实例"""
    return AlgorithmResultFieldMapper
