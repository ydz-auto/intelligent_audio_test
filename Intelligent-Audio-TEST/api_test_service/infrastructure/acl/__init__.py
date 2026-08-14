# -*- coding: utf-8 -*-
"""api_test_service 基础设施层 — ACL 仓储实现包。

跨服务 gRPC 调用的具体实现，对应 domain/repositories/acl/ 下的 ABC 接口。
所有只读查询方法经 shared.utils.dto_utils.dict_to_dto /
dict_list_to_dto 转换为 dataclass DTO 返回。
"""
from api_test_service.infrastructure.acl.adapter_acl_repository import (
    AdapterAclRepositoryImpl,
)
from api_test_service.infrastructure.acl.algorithm_acl_repository import (
    AlgorithmQueryAclRepositoryImpl,
)
from api_test_service.infrastructure.acl.audio_acl_repository import (
    AudioConfigAclRepositoryImpl,
)
from api_test_service.infrastructure.acl.device_result_acl_repository_impl import (
    DeviceResultAclRepositoryImpl,
)
from api_test_service.infrastructure.acl.evaluation_acl_repository import (
    EvaluationAclRepositoryImpl,
)
from api_test_service.infrastructure.acl.task_data_acl_repository import (
    TaskDataAclRepositoryImpl,
)
from api_test_service.infrastructure.acl.testcase_acl_repository import (
    TestCaseConfigAclRepositoryImpl,
)

__all__ = [
    'AdapterAclRepositoryImpl',
    'AlgorithmQueryAclRepositoryImpl',
    'AudioConfigAclRepositoryImpl',
    'DeviceResultAclRepositoryImpl',
    'EvaluationAclRepositoryImpl',
    'TaskDataAclRepositoryImpl',
    'TestCaseConfigAclRepositoryImpl',
]
