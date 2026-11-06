# -*- coding: utf-8 -*-
"""report_service 基础设施层 — ACL 仓储实现包。

跨服务 gRPC 调用的具体实现，对应 domain/repositories/acl/ 下的 ABC 接口。
所有只读查询方法经 shared.utils.dto_utils.dict_to_dto /
dict_list_to_dto 转换为 dataclass DTO 返回。
"""
from report_service.infrastructure.acl.algorithm_acl_repository import (
    AlgorithmConfigAclRepositoryImpl,
)
from report_service.infrastructure.acl.apitest_acl_repository import (
    ApiTestAclRepositoryImpl,
)
from report_service.infrastructure.acl.audio_acl_repository import (
    AudioConfigAclRepositoryImpl,
)
from report_service.infrastructure.acl.device_acl_repository import (
    DeviceConfigAclRepositoryImpl,
    PlaybackConfigAclRepositoryImpl,
)
from report_service.infrastructure.acl.evaluation_acl_repository import (
    EvaluationConfigAclRepositoryImpl,
    EvaluationDataAclRepositoryImpl,
)
from report_service.infrastructure.acl.tag_acl_repository import (
    TagConfigAclRepositoryImpl,
)
from report_service.infrastructure.acl.task_data_acl_repository import (
    TaskDataAclRepositoryImpl,
)
from report_service.infrastructure.acl.task_merge_relation_acl_repository import (
    TaskMergeRelationAclRepositoryImpl,
)
from report_service.infrastructure.acl.testcase_acl_repository import (
    TestCaseConfigAclRepositoryImpl,
)

__all__ = [
    'AlgorithmConfigAclRepositoryImpl',
    'ApiTestAclRepositoryImpl',
    'AudioConfigAclRepositoryImpl',
    'DeviceConfigAclRepositoryImpl',
    'EvaluationConfigAclRepositoryImpl',
    'EvaluationDataAclRepositoryImpl',
    'PlaybackConfigAclRepositoryImpl',
    'TagConfigAclRepositoryImpl',
    'TaskDataAclRepositoryImpl',
    'TaskMergeRelationAclRepositoryImpl',
    'TestCaseConfigAclRepositoryImpl',
]
