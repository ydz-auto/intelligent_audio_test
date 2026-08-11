# -*- coding: utf-8 -*-
"""api_test_service 跨域 ACL 仓储接口包。

按 DDD 约定：跨域只读/调用查询的 ABC 定义在 domain/repositories/acl/，
实现放在 infrastructure/acl/。
"""
from api_test_service.domain.repositories.acl.adapter_acl_repository import (
    AdapterAclRepository,
)
from api_test_service.domain.repositories.acl.algorithm_acl_repository import (
    AlgorithmQueryAclRepository,
)
from api_test_service.domain.repositories.acl.audio_acl_repository import (
    AudioConfigAclRepository,
)
from api_test_service.domain.repositories.acl.evaluation_acl_repository import (
    EvaluationAclRepository,
)
from api_test_service.domain.repositories.acl.task_data_acl_repository import (
    TaskDataAclRepository,
)
from api_test_service.domain.repositories.acl.testcase_acl_repository import (
    TestCaseConfigAclRepository,
)

__all__ = [
    'AdapterAclRepository',
    'AlgorithmQueryAclRepository',
    'AudioConfigAclRepository',
    'EvaluationAclRepository',
    'TaskDataAclRepository',
    'TestCaseConfigAclRepository',
]
