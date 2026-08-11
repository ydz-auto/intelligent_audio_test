# -*- coding: utf-8 -*-
"""evaluation_service 持久化对象（PO）——PO 定义包

按 DDD 单库逻辑隔离原则，本包定义 evaluation_service 自有表的 PO：
- Category                       评估分类（表：categories）
- Dimension                      评估维度（表：dimensions）
- TestResultDimension            测试结果维度得分（表：test_result_dimensions）

不归属本服务的表（如 test_results / tasks / task_cases）的 PO 不在本包定义，
跨服务访问应通过 gRPC 调用对应服务，而非直接建模对方的 ORM。

P5 改造：PO 定义真正下沉到本包，shared/models/models/* 改为从这里 re-export。
"""
from .evaluation_models import Category, Dimension
from .result_models import TestResultDimension

__all__ = [
    'Category',
    'Dimension',
    'TestResultDimension',
]
