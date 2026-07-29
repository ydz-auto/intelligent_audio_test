# -*- coding: utf-8 -*-
"""算法领域共享模块

包含算法配置加载、字段映射、用例参数提取、参考参数生成、结果字段映射等领域逻辑。
供 api_gateway、task_service、e2e_test_service 等多服务直接 import 共享使用。

模块清单:
- AlgorithmConfigLoader: 从数据库加载算法配置 -> algorithm_config_loader
- FieldMapper: 字段映射和数据转换 -> field_mapper
- CaseParameterExtractor: 从用例配置提取参数 -> case_parameter_extractor
- ReferenceParamsGenerator: 从标注生成参考参数 -> reference_params_generator
- AlgorithmResultFieldMapper: 算法结果字段映射 -> algorithm_result_field_mapper
"""

from shared.algorithm.algorithm_config_loader import get_config_loader, AlgorithmConfigLoader
from shared.algorithm.case_parameter_extractor import get_parameter_extractor, CaseParameterExtractor
from shared.algorithm.reference_params_generator import (
    get_reference_params_generator,
    ReferenceParamsGenerator,
    get_reference_value,
)
from shared.algorithm.field_mapper import get_field_mapper, FieldMapper
from shared.algorithm.algorithm_result_field_mapper import (
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
