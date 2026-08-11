# -*- coding: utf-8 -*-
"""algorithm_service 持久化对象（PO）包。

归属：algorithm_service（算法定义 + 参数映射上下文）
表：algorithm_groups / algorithm_definitions / algorithm_device_params
     / algorithm_api_params / algorithm_reference_params
     / evaluation_dimension_params / param_mappings
     / algorithm_dimension_relations / case_algorithm_params

P5 改造：PO 定义真正下沉到本包，shared/models/algorithm_models.py
改为从这里 re-export。
"""
from .algorithm_models import (
    AlgorithmGroup,
    AlgorithmDefinition,
    AlgorithmDeviceParam,
    AlgorithmApiParam,
    AlgorithmReferenceParam,
    EvaluationDimensionParam,
    ParamMapping,
    AlgorithmDimensionRelation,
    CaseAlgorithmParam,
)

__all__ = [
    'AlgorithmGroup', 'AlgorithmDefinition', 'AlgorithmDeviceParam',
    'AlgorithmApiParam', 'AlgorithmReferenceParam', 'EvaluationDimensionParam',
    'ParamMapping', 'AlgorithmDimensionRelation', 'CaseAlgorithmParam',
]
