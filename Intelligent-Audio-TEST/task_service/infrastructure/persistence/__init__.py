# -*- coding: utf-8 -*-
"""task_service 持久化层

- orm_models.py: 本服务自有的 PO（Task / TaskTag / TaskCase / TaskDevice / TaskAPI / TaskMergeRelation / TestResult）
- task_repository.py: 任务仓储
- testcase_repository.py: 测试用例仓储（跨域，P3 阶段改 gRPC）
- read_models/: 读模型（CQRS 查询）

注：algorithm_repository.py 已移至 infrastructure/acl/algorithm_acl_repository.py（ACL 跨域 gRPC 适配）
"""
from task_service.infrastructure.persistence.orm_models import (
    Task,
    TaskTag,
    TaskCase,
    TaskDevice,
    TaskAPI,
    TaskMergeRelation,
    TestResult,
)

__all__ = [
    'Task',
    'TaskTag',
    'TaskCase',
    'TaskDevice',
    'TaskAPI',
    'TaskMergeRelation',
    'TestResult',
]
