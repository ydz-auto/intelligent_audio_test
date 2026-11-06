# -*- coding: utf-8 -*-
"""evaluation_service 领域值对象

值对象定义在 entities/evaluation_dimension.py 中，这里做 re-export 统一导出。
（值对象与实体在同一文件定义是因为它们紧密相关，避免文件碎片化。）
"""
from evaluation_service.domain.entities.evaluation_dimension import (
    ScoringRule,
    DimensionSnapshot,
    RoundResult,
)
from evaluation_service.domain.value_objects.evaluation_config import (
    ScoringRule as ConfigScoringRule,
    DimensionSnapshot as ConfigDimensionSnapshot,
    RoundResult as ConfigRoundResult,
    ScoreRange,
    ApiSettings,
)

__all__ = [
    'ScoringRule',
    'DimensionSnapshot',
    'RoundResult',
    'ConfigScoringRule',
    'ConfigDimensionSnapshot',
    'ConfigRoundResult',
    'ScoreRange',
    'ApiSettings',
]
