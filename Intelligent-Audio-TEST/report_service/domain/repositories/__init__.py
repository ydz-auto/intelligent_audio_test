# -*- coding: utf-8 -*-
"""report_service 领域层 — 仓储接口（ABC）

DDD 规则3：Repository 必须继承 ABC，在 domain 层定义抽象接口，
infrastructure/persistence 层提供具体实现。
"""
from report_service.domain.repositories.report_repository_abc import (
    ReportRepositoryABC,
)
from report_service.domain.repositories.acl import (
    AlgorithmConfigAclRepository,
    ApiTestAclRepository,
    AudioConfigAclRepository,
    DeviceConfigAclRepository,
    EvaluationConfigAclRepository,
    EvaluationDataAclRepository,
    PlaybackConfigAclRepository,
    TagConfigAclRepository,
    TaskDataAclRepository,
    TaskMergeRelationAclRepository,
    TestCaseConfigAclRepository,
)

__all__ = [
    'ReportRepositoryABC',
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
