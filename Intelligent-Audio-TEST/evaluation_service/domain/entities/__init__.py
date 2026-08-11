# -*- coding: utf-8 -*-
"""evaluation_service 领域实体

纯领域对象，不依赖 SQLAlchemy / db.Model。
Repository 负责 PO ↔ Entity 转换。
"""
from evaluation_service.domain.entities.evaluation_dimension import (
    EvaluationDimension,
    DimensionScore,
    DimensionSnapshot,
    RoundResult,
    ScoringRule,
)

__all__ = [
    'EvaluationDimension',
    'DimensionScore',
    'DimensionSnapshot',
    'RoundResult',
    'ScoringRule',
]
