# -*- coding: utf-8 -*-
"""evaluation_service 领域仓储接口（ABC）

Domain 层只依赖此处的抽象接口，不直接 import infrastructure 层。
Infrastructure 层的 acl/ 和 persistence/ 实现这些接口，通过依赖注入传入 Domain。
"""
from evaluation_service.domain.repositories.task_acl_repository import TaskAclRepository
from evaluation_service.domain.repositories.algorithm_acl_repository import AlgorithmAclRepository
from evaluation_service.domain.repositories.evaluation_dimension_repository import EvaluationDimensionRepository
from evaluation_service.domain.repositories.evaluation_repository_abc import EvaluationRepositoryABC

__all__ = [
    'TaskAclRepository',
    'AlgorithmAclRepository',
    'EvaluationDimensionRepository',
    'EvaluationRepositoryABC',
]
