# -*- coding: utf-8 -*-
"""evaluation_service 持久化对象（PO）— re-export 入口

PO 定义真正位于 evaluation_service/infrastructure/persistence/models/ 下。
本文件保留作为向后兼容的导入路径，从 models/ re-export。

按 DDD 单库逻辑隔离原则，本服务只定义自己拥有的表的 PO：
- Category                       评估分类（表：categories）
- Dimension                      评估维度（表：dimensions）
- TestResultDimension            测试结果维度得分（表：test_result_dimensions）

不归属本服务的表（如 test_results / tasks / task_cases）的 PO 不在此定义，
跨服务访问应通过 gRPC 调用对应服务，而非直接建模对方的 ORM。
"""
from evaluation_service.infrastructure.persistence.models import (
    Category,
    Dimension,
    TestResultDimension,
)

__all__ = [
    'Category',
    'Dimension',
    'TestResultDimension',
]
