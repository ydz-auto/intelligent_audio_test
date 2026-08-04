# -*- coding: utf-8 -*-
"""DefaultOverlapMixin - 提供默认参数与重叠播放场景参数读取

拆分自原 case_parameter_extractor.py 的 CaseParameterExtractor：
- get_default_params
- get_overlap_rate
- get_overlap_time
"""

from typing import Dict, Any

from ._helpers import _get_algo_param


class DefaultOverlapMixin:
    """默认参数与重叠播放场景 mixin"""

    @classmethod
    def get_default_params(cls, algorithm_type: str) -> Dict[str, Any]:
        """获取算法默认参数"""
        loader = cls._get_loader()
        params = loader.get_algorithm_params(algorithm_type)

        defaults = {}
        for param in params:
            code = param.get('code')
            default_value = param.get('default_value')
            if default_value is not None:
                defaults[code] = default_value

        return defaults

    @classmethod
    def get_overlap_rate(cls, case_config: Dict) -> float:
        """获取重叠率 — 支持 algorithm_params 为 list [{field_code, field_value}] 或 dict"""
        if not case_config:
            return 0
        algorithm_params = case_config.get('algorithm_params', {})
        if isinstance(algorithm_params, list):
            value = _get_algo_param(algorithm_params, 'overlap_rate', 0)
        else:
            value = algorithm_params.get('overlap_rate', 0)
        try:
            return max(0.0, min(1.0, float(value)))
        except (ValueError, TypeError):
            return 0

    @classmethod
    def get_overlap_time(cls, case_config: Dict) -> float:
        """获取重叠时间（秒） — 支持 algorithm_params 为 list [{field_code, field_value}] 或 dict"""
        if not case_config:
            return 0
        algorithm_params = case_config.get('algorithm_params', {})
        if isinstance(algorithm_params, list):
            value = _get_algo_param(algorithm_params, 'overlap_time', 0)
        else:
            value = algorithm_params.get('overlap_time', 0)
        try:
            return max(0.0, float(value))
        except (ValueError, TypeError):
            return 0
