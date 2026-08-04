# -*- coding: utf-8 -*-
"""CoreParamsMixin - 提供 loader 获取、算法类型/参数读取与统一接口方法

拆分自原 case_parameter_extractor.py 的 CaseParameterExtractor：
- _get_loader
- get_algorithm_type
- get_algorithm_params
- get_round_algorithm_params
- get_all_params
"""

from typing import Dict, Any

from ..algorithm_config_loader import get_config_loader
from shared.utils.log_handler import log_not_emit
from ._helpers import (
    _normalize_algorithm_params,
    _get_round_algo_params,
)


class CoreParamsMixin:
    """核心参数读取 mixin，提供 loader 缓存与算法类型/参数基础读取方法"""

    _loader = None

    @classmethod
    def _get_loader(cls):
        if cls._loader is None:
            cls._loader = get_config_loader()
        return cls._loader

    @classmethod
    def get_algorithm_type(cls, case_config: Dict) -> str:
        """获取算法类型"""
        algorithm_type = case_config.get('algorithm_type', 'unknown')
        log_not_emit('DEBUG', 'case_parameter_extractor', f'Getting algorithm_type: {algorithm_type}', category='algorithm')
        return algorithm_type

    @classmethod
    def get_algorithm_params(cls, case_config: Dict) -> Dict[str, Any]:
        """获取算法参数 — 统一返回 dict 格式

        支持 case_config.algorithm_params 为:
        - dict: 直接返回
        - list [{field_code, field_value}]: 转为 dict
        """
        raw = case_config.get('algorithm_params', {})
        return _normalize_algorithm_params(raw)

    @classmethod
    def get_round_algorithm_params(cls, algorithm_params_col, round_number) -> Dict[str, Any]:
        """从独立列按轮获取算法参数 dict

        Args:
            algorithm_params_col: test_cases.algorithm_params 列，按轮分组
                [{round_number, params:[{field_code, field_value}]}]
            round_number: 轮次序号
        Returns:
            {field_code: field_value}，找不到返回 {}
        """
        params_list = _get_round_algo_params(algorithm_params_col, round_number)
        if not params_list:
            return {}
        result = {}
        for item in params_list:
            field_code = item.get('field_code')
            if field_code:
                result[field_code] = item.get('field_value')
        return result

    @classmethod
    def get_all_params(cls, case_config: Dict) -> Dict[str, Any]:
        """获取所有参数（统一接口）"""
        log_not_emit('DEBUG', 'case_parameter_extractor', 'Getting all params for case', category='algorithm')
        result = {
            'algorithm_type': cls.get_algorithm_type(case_config),
            'device': cls.get_device_params(case_config),
            'api': cls.get_api_params(case_config),
            'evaluation': cls.get_evaluation_params(case_config)
        }
        log_not_emit('DEBUG', 'case_parameter_extractor', f'All params retrieved: {list(result.keys())}', category='algorithm')
        return result
