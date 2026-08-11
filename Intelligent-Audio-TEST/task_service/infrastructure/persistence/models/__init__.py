# -*- coding: utf-8 -*-
"""task_service 持久化对象（PO）——PO 定义包

按 DDD 单库逻辑隔离原则，本包定义 task_service 自有表的 PO：
- Task / TaskTag / TaskCase / TaskDevice / TaskAPI / TaskMergeRelation / TestResult
- TagCategory / Tag / TestCaseGroup / TestCase / TestCaseTag
- Log

不归属本服务的表（如 Dimension / TestResultDimension / Device / Audio / API /
Algorithm* / Report* / User* / StatsCache）不在本包定义，
跨服务访问应通过 gRPC 调用对应服务。

P5 改造：PO 定义真正下沉到本包，shared/models/models/* 改为从这里 re-export。
Algorithm* 已下沉到新建的 algorithm_service；Report* 下沉到 report_service；
User/OAuth 下沉到 auth_service；StatsCache 保留 api_gateway。
"""
from .task_models import (
    Task, TaskTag, TaskCase, TaskDevice, TaskAPI, TaskMergeRelation,
)
from .result_models import TestResult
from .testcase_models import (
    TagCategory, Tag, TestCaseGroup, TestCase, TestCaseTag,
)
from .system_models import Log

__all__ = [
    # 任务
    'Task', 'TaskTag', 'TaskCase', 'TaskDevice', 'TaskAPI', 'TaskMergeRelation',
    # 测试结果（不含 TestResultDimension，归属 evaluation_service）
    'TestResult',
    # 标签与用例
    'TagCategory', 'Tag', 'TestCaseGroup', 'TestCase', 'TestCaseTag',
    # 系统日志
    'Log',
]
