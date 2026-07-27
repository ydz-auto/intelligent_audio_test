# -*- coding: utf-8 -*-
"""
算法配置模块（兼容性入口）

注意：以下模块已迁移到 shared.utils 共享层，供 task_service、e2e_test_service、
api_gateway 等多服务共用。本包保留作为兼容性 re-export 入口，建议新代码直接
从 shared.utils 引用。

- AlgorithmConfigLoader: 从数据库加载算法配置 -> shared.utils.algorithm_config_loader
- CaseParameterExtractor: 从用例配置提取参数 -> shared.utils.case_parameter_extractor
- FieldMapper: 字段映射和数据转换 -> shared.utils.field_mapper
- ReferenceParamsGenerator: 从标注生成参考参数 -> shared.utils.reference_params_generator
- AlgorithmResultFieldMapper: 算法结果字段映射 -> shared.utils.algorithm_result_field_mapper
"""

from shared.utils.algorithm_config_loader import get_config_loader, AlgorithmConfigLoader
from shared.utils.case_parameter_extractor import get_parameter_extractor, CaseParameterExtractor
from shared.utils.reference_params_generator import (
    get_reference_params_generator,
    ReferenceParamsGenerator,
    get_reference_value,
)
from shared.utils.field_mapper import get_field_mapper, FieldMapper
from shared.utils.algorithm_result_field_mapper import (
    AlgorithmResultFieldMapper,
    get_result_field_mapper,
)

__all__ = [
    'get_config_loader',
    'AlgorithmConfigLoader',
    'get_parameter_extractor',
    'CaseParameterExtractor',
    'get_reference_params_generator',
    'ReferenceParamsGenerator',
    'get_reference_value',
    'get_field_mapper',
    'FieldMapper',
    'AlgorithmResultFieldMapper',
    'get_result_field_mapper',
]
