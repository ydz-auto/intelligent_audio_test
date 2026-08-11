# -*- coding: utf-8 -*-
"""algorithm_service.domain — DDD 领域层 re-export 入口。

聚合根 / 实体 / 值对象 / 领域事件 / 领域服务统一从此处导出。
"""
from .entities import (
    AlgorithmDefinitionAggregate,
    AlgorithmDimensionRelationEntity,
    AlgorithmGroupAggregate,
    AlgorithmGroupSnapshot,
    AlgorithmParamEntity,
    AlgorithmStatus,
    CaseAlgorithmParamEntity,
    ParamMappingEntity,
)
from .events import (
    AlgorithmCreated,
    AlgorithmDeprecated,
    AlgorithmEvent,
    AlgorithmUpdated,
)
from .services import AlgorithmValidator
from .value_objects import AlgorithmConfig

__all__ = [
    # 实体
    "AlgorithmGroupAggregate",
    "AlgorithmGroupSnapshot",
    "AlgorithmDefinitionAggregate",
    "AlgorithmStatus",
    "AlgorithmParamEntity",
    "AlgorithmDimensionRelationEntity",
    "CaseAlgorithmParamEntity",
    "ParamMappingEntity",
    # 值对象
    "AlgorithmConfig",
    # 领域事件
    "AlgorithmEvent",
    "AlgorithmCreated",
    "AlgorithmUpdated",
    "AlgorithmDeprecated",
    # 领域服务
    "AlgorithmValidator",
]
