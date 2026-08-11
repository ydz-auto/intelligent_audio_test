# -*- coding: utf-8 -*-
"""evaluation_service 防腐层（ACL）— 跨服务数据访问的出站适配器

- task_acl_repository.py: 调 task_service 的 TaskDataService（跨服务数据访问）
- algorithm_acl_repository.py: 调 algorithm_service 的 AlgorithmDefinitionService（跨服务数据访问）
"""
from evaluation_service.infrastructure.acl.task_acl_repository import (
    TaskAclRepository,
    task_acl_repository,
)
from evaluation_service.infrastructure.acl.algorithm_acl_repository import (
    AlgorithmAclRepository,
    algorithm_acl_repository,
)

__all__ = [
    'TaskAclRepository',
    'task_acl_repository',
    'AlgorithmAclRepository',
    'algorithm_acl_repository',
]
