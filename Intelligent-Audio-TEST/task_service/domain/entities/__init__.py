# -*- coding: utf-8 -*-
"""task_service 领域实体（re-export 入口）

纯领域对象，不依赖 SQLAlchemy / db.Model。
Repository 负责 PO ↔ Entity 转换。
"""
from task_service.domain.entities.task import (
    TaskAggregate,
    TaskSnapshot,
    TaskStatus,
)
from task_service.domain.entities.task_case import (
    TaskCaseEntity,
    TaskCaseSnapshot,
    TaskCaseStatus,
)
from task_service.domain.entities.task_merge_relation import (
    TaskMergeRelationEntity,
)
from task_service.domain.entities.testcase import (
    AlgorithmParam,
    CaseConfig,
    ReferenceParam,
    TagCategoryEntity,
    TagEntity,
    TestCaseAggregate,
    TestCaseEntity,
    TestCaseGroupEntity,
    TestCaseSnapshot,
    TestCaseTagEntity,
    TestCaseType,
)

__all__ = [
    'TaskAggregate',
    'TaskSnapshot',
    'TaskStatus',
    'TaskCaseEntity',
    'TaskCaseSnapshot',
    'TaskCaseStatus',
    'TaskMergeRelationEntity',
    'TestCaseAggregate',
    'TestCaseEntity',
    'TestCaseSnapshot',
    'TestCaseType',
    'TestCaseTagEntity',
    'TestCaseGroupEntity',
    'TagEntity',
    'TagCategoryEntity',
    'CaseConfig',
    'AlgorithmParam',
    'ReferenceParam',
]
