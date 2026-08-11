# -*- coding: utf-8 -*-
"""参数规范化领域服务

纯逻辑，无 I/O 依赖。迁移自 shared/algorithm/case_parameter_extractor/_helpers.py
"""

from typing import Dict, List, Any, Optional


class ParamNormalizerService:
    """算法参数规范化服务 - 静态方法"""

    @staticmethod
    def get_algo_param(algorithm_params: Optional[List[Dict]], field_code: str, default=None):
        """从 [{field_code, field_value}] 数组中读取参数值"""
        if not algorithm_params:
            return default
        if isinstance(algorithm_params, list):
            for item in algorithm_params:
                if isinstance(item, dict) and item.get('field_code') == field_code:
                    return item.get('field_value', default)
        return default

    @staticmethod
    def get_round_algo_params(algorithm_params_col: list, round_number: int) -> list:
        """从按轮分组的 algorithm_params 列中读取指定轮的 params"""
        if not algorithm_params_col:
            return []
        for item in algorithm_params_col:
            if item.get('round_number') == round_number:
                return item.get('params', [])
        return []

    @staticmethod
    def normalize_algorithm_params(algorithm_params) -> Dict[str, Any]:
        """将 algorithm_params 统一转为 dict 格式 {field_code: field_value}"""
        if isinstance(algorithm_params, dict):
            return algorithm_params
        if isinstance(algorithm_params, list):
            result = {}
            for item in algorithm_params:
                if isinstance(item, dict) and 'field_code' in item:
                    result[item['field_code']] = item.get('field_value')
            return result
        return {}

    @staticmethod
    def normalize_algorithm_params_to_list(algorithm_params) -> List[Dict]:
        """将 algorithm_params 统一转为 list 格式 [{field_code, field_value}]"""
        if not algorithm_params:
            return []
        if isinstance(algorithm_params, dict):
            return [{'field_code': k, 'field_value': v} for k, v in algorithm_params.items()]
        if isinstance(algorithm_params, list):
            result = []
            for item in algorithm_params:
                if hasattr(item, 'model_dump'):
                    d = item.model_dump()
                    fc = d.get('field_code') or d.get('fieldCode')
                    fv = d.get('field_value', d.get('fieldValue'))
                    if fc is not None:
                        result.append({'field_code': fc, 'field_value': fv})
                    else:
                        result.append(d)
                elif isinstance(item, dict):
                    fc = item.get('field_code') or item.get('fieldCode')
                    fv = item.get('field_value', item.get('fieldValue'))
                    if fc is not None:
                        result.append({'field_code': fc, 'field_value': fv})
                    else:
                        result.append(item)
            return result
        return []

    @staticmethod
    def get_overlap_rate(case_config: Dict) -> float:
        """从 algorithm_params 取 overlap_rate，兼容 list/dict 格式"""
        from .param_normalizer import ParamNormalizerService
        ap = case_config.get('algorithm_params', {})
        normalized = ParamNormalizerService.normalize_algorithm_params(ap)
        rate = normalized.get('overlap_rate', 0.0)
        try:
            rate = float(rate)
        except (TypeError, ValueError):
            rate = 0.0
        return max(0.0, min(1.0, rate))

    @staticmethod
    def get_overlap_time(case_config: Dict) -> float:
        """从 algorithm_params 取 overlap_time，兼容 list/dict 格式"""
        from .param_normalizer import ParamNormalizerService
        ap = case_config.get('algorithm_params', {})
        normalized = ParamNormalizerService.normalize_algorithm_params(ap)
        time_val = normalized.get('overlap_time', 0.0)
        try:
            time_val = float(time_val)
        except (TypeError, ValueError):
            time_val = 0.0
        return max(0.0, time_val)
