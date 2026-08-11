# -*- coding: utf-8 -*-
"""task_service domain 仓储接口（ABC）。

infrastructure/persistence 和 infrastructure/acl 下的实现继承此处的 ABC，
实现依赖倒置。
"""
from task_service.domain.repositories.task_repository import TaskRepositoryABC
from task_service.domain.repositories.task_case_repository import TaskCaseRepositoryABC
from task_service.domain.repositories.testcase_group_repository import TestCaseGroupRepositoryABC
from task_service.domain.repositories.log_repository import LogRepositoryABC
from task_service.domain.repositories.test_result_repository import TestResultRepositoryABC
from task_service.domain.repositories.task_merge_repository import TaskMergeRelationRepositoryABC
from task_service.domain.repositories.algorithm_acl_repository import AlgorithmAclRepository

__all__ = [
    'TaskRepositoryABC',
    'TaskCaseRepositoryABC',
    'TestCaseGroupRepositoryABC',
    'LogRepositoryABC',
    'TestResultRepositoryABC',
    'TaskMergeRelationRepositoryABC',
    'AlgorithmAclRepository',
]
