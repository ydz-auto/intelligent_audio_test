# -*- coding: utf-8 -*-
from .execution import ExecutionServiceServicer
from .task_config import TaskConfigServiceServicer
from .testcase_config import TestCaseConfigServiceServicer
from .tag_config import TagConfigServiceServicer
from .algorithm_config import AlgorithmConfigServiceServicer
from .task_data_service import TaskDataServiceServicer
# 注：EvaluationConfigServiceServicer 已迁移至 evaluation_service

__all__ = [
    'ExecutionServiceServicer',
    'TaskConfigServiceServicer',
    'TestCaseConfigServiceServicer',
    'TagConfigServiceServicer',
    'AlgorithmConfigServiceServicer',
    'TaskDataServiceServicer',
]
