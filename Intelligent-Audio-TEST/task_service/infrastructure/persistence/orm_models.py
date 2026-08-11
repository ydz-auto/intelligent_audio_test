# -*- coding: utf-8 -*-
"""task_service 持久化对象（PO）— re-export 入口

PO 定义真正位于 task_service/infrastructure/persistence/models/ 下。
本文件保留作为向后兼容的导入路径，从 models/ re-export。

按 DDD 单库逻辑隔离原则，本服务只定义自己拥有的表的 PO：
- Task / TaskTag / TaskCase / TaskDevice / TaskAPI / TaskMergeRelation / TestResult
- TagCategory / Tag / TestCaseGroup / TestCase / TestCaseTag
- Log

不归属本服务的表（如 Dimension / TestResultDimension / Device / Audio / API /
Algorithm* / Report* / User* / StatsCache）不在本服务定义，
跨服务访问应通过 gRPC 调用对应服务。
"""
from task_service.infrastructure.persistence.models import (
    Task, TaskTag, TaskCase, TaskDevice, TaskAPI, TaskMergeRelation,
    TestResult,
    TagCategory, Tag, TestCaseGroup, TestCase, TestCaseTag,
    Log,
)

__all__ = [
    'Task', 'TaskTag', 'TaskCase', 'TaskDevice', 'TaskAPI', 'TaskMergeRelation',
    'TestResult',
    'TagCategory', 'Tag', 'TestCaseGroup', 'TestCase', 'TestCaseTag',
    'Log',
]
