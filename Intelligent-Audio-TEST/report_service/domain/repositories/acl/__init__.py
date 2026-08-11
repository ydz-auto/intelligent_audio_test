# -*- coding: utf-8 -*-
"""report_service 跨域 ACL 仓储接口包。

按 DDD 约定：跨域只读查询的 ABC 定义在 domain/repositories/acl/，
实现放在 infrastructure/acl/。
"""
from report_service.domain.repositories.acl.algorithm_acl_repository import (
    AlgorithmConfigAclRepository,
)
from report_service.domain.repositories.acl.apitest_acl_repository import (
    ApiTestAclRepository,
)
from report_service.domain.repositories.acl.audio_acl_repository import (
    AudioConfigAclRepository,
)
from report_service.domain.repositories.acl.device_acl_repository import (
    DeviceConfigAclRepository,
    PlaybackConfigAclRepository,
)
from report_service.domain.repositories.acl.evaluation_acl_repository import (
    EvaluationConfigAclRepository,
    EvaluationDataAclRepository,
)
from report_service.domain.repositories.acl.tag_acl_repository import (
    TagConfigAclRepository,
)
from report_service.domain.repositories.acl.task_data_acl_repository import (
    TaskDataAclRepository,
)
from report_service.domain.repositories.acl.task_merge_relation_acl_repository import (
    TaskMergeRelationAclRepository,
)
from report_service.domain.repositories.acl.testcase_acl_repository import (
    TestCaseConfigAclRepository,
)

__all__ = [
    'AlgorithmConfigAclRepository',
    'ApiTestAclRepository',
    'AudioConfigAclRepository',
    'DeviceConfigAclRepository',
    'EvaluationConfigAclRepository',
    'EvaluationDataAclRepository',
    'PlaybackConfigAclRepository',
    'TagConfigAclRepository',
    'TaskDataAclRepository',
    'TaskMergeRelationAclRepository',
    'TestCaseConfigAclRepository',
]
