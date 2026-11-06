# -*- coding: utf-8 -*-
"""evaluation_service gRPC servicers（聚合导出模块）

P4-4 大文件拆分：三个 servicer 类已按职责拆分到独立模块，本文件保持
`from evaluation_service.interfaces.grpc.servicers import ...` 的导入路径不变：

- EvaluationServiceServicer        → evaluation_servicer.py（评估执行）
- EvaluationConfigServiceServicer  → evaluation_config_servicer.py（维度 CRUD）
- EvaluationDataServiceServicer    → evaluation_data_servicer.py（评估数据查询）
"""
from evaluation_service.interfaces.grpc.evaluation_servicer import EvaluationServiceServicer
from evaluation_service.interfaces.grpc.evaluation_config_servicer import EvaluationConfigServiceServicer
from evaluation_service.interfaces.grpc.evaluation_data_servicer import EvaluationDataServiceServicer

__all__ = [
    "EvaluationServiceServicer",
    "EvaluationConfigServiceServicer",
    "EvaluationDataServiceServicer",
]
