# -*- coding: utf-8 -*-
"""api_test_service 领域层 — 仓储接口（ABC）

DDD 规则3：Repository 必须继承 ABC，在 domain 层定义抽象接口，
infrastructure/persistence 层提供具体实现。
"""
from api_test_service.domain.repositories.api_test_repository_abc import (
    APITestRepositoryABC,
)
from api_test_service.domain.repositories.acl import (
    AdapterAclRepository,
    AlgorithmQueryAclRepository,
    AudioConfigAclRepository,
    TaskDataAclRepository,
    TestCaseConfigAclRepository,
)

__all__ = [
    'APITestRepositoryABC',
    'AdapterAclRepository',
    'AlgorithmQueryAclRepository',
    'AudioConfigAclRepository',
    'TaskDataAclRepository',
    'TestCaseConfigAclRepository',
]
