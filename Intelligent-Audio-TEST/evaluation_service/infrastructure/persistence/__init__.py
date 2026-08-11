# -*- coding: utf-8 -*-
"""evaluation_service 持久化层

- orm_models.py: 本服务自有的 PO（Category / Dimension / TestResultDimension）
- evaluation_repository.py: 仓储实现
- evaluation_result_processor.py: 评估结果写入 DB
- round_aggregator.py: 多轮结果聚合
"""
from evaluation_service.infrastructure.persistence.orm_models import (
    Category,
    Dimension,
    TestResultDimension,
)

__all__ = [
    'Category',
    'Dimension',
    'TestResultDimension',
]
