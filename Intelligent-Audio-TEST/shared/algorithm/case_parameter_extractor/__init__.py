# -*- coding: utf-8 -*-
"""用例参数提取器

职责：
- 从用例配置字典中提取算法类型、算法参数、参考参数等
- 支持 rounds-as-top-level 架构：从 round.algorithmParams [{field_code, field_value}] 读取参数
- 构建设备参数、API参数、评估参数
- 提供表单schema生成
- 判断重叠播放场景

本包由原 case_parameter_extractor.py 拆分而来，保持对外导出名称完全向后兼容：
    from shared.algorithm.case_parameter_extractor import CaseParameterExtractor
    from shared.algorithm.case_parameter_extractor import get_parameter_extractor
    from shared.algorithm.case_parameter_extractor import _normalize_algorithm_params
    from shared.algorithm.case_parameter_extractor import _normalize_algorithm_params_to_list
    from shared.algorithm.case_parameter_extractor import _get_round_algo_params
    from shared.algorithm.case_parameter_extractor import _get_algo_param
"""

from ._helpers import (
    _REF_PARAMS_BUCKET,
    _get_algo_param,
    _get_round_algo_params,
    _normalize_algorithm_params,
    _normalize_algorithm_params_to_list,
)
from .extractor import CaseParameterExtractor, get_parameter_extractor

__all__ = [
    'CaseParameterExtractor',
    'get_parameter_extractor',
    '_REF_PARAMS_BUCKET',
    '_get_algo_param',
    '_get_round_algo_params',
    '_normalize_algorithm_params',
    '_normalize_algorithm_params_to_list',
]
