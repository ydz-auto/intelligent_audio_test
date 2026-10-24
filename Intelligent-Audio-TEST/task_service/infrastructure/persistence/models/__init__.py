# -*- coding: utf-8 -*-
"""task_service 持久化对象（PO）——PO 定义包

按 DDD 单库逻辑隔离原则，本包定义 task_service 自有表的 PO：
- Task / TaskTag / TaskCase / TaskDevice / TaskAPI / TaskMergeRelation / TestResult
- TagCategory / Tag / TestCaseGroup / TestCase / TestCaseTag
- Log
- DataTransferSourceMap（离线搬运 source_map，INT-1760）

不归属本服务的表（如 Dimension / TestResultDimension / Device / Audio / API /
Algorithm* / Report* / User* / StatsCache）不在本包定义，
跨服务访问应通过 gRPC 调用对应服务。

P5 改造：PO 定义真正下沉到本包，shared/models/models/* 改为从这里 re-export。
Algorithm* 已下沉到新建的 algorithm_service；Report* 下沉到 report_service；
User/OAuth 下沉到 auth_service；StatsCache 保留 api_gateway。
"""
from .task_models import (
    Task, TaskTag, TaskCase, TaskDevice, TaskAPI, TaskLaboratoryRelation, TaskMergeRelation,
)
from .published_task_models import PublishedTask
from .result_models import TestResult
from .testcase_models import (
    TagCategory, Tag, TestCaseGroup, TestCase, TestCaseTag,
)
from .evaluation_strategy_models import EvaluationStrategy
from .favorite_models import Favorite
from .cherry_pick_models import (
    CherryPickCartItem, TaskCherryPickRelation, CherryPickSet, CherryPickSetItem,
)
from .review_models import TestResultReview
from .ai_review_models import AiReview
from .system_models import Log
from .transfer_source_map_models import DataTransferSourceMap

__all__ = [
    # 任务
    'Task', 'TaskTag', 'TaskCase', 'TaskDevice', 'TaskAPI',
    'TaskLaboratoryRelation', 'TaskMergeRelation',
    # 已发布任务（任务发布功能）
    'PublishedTask',
    # 测试结果（不含 TestResultDimension，归属 evaluation_service）
    'TestResult',
    # 标签与用例
    'TagCategory', 'Tag', 'TestCaseGroup', 'TestCase', 'TestCaseTag',
    # 评估策略（INT-590：整体评估维度+全局背景噪声 可复用包）
    'EvaluationStrategy',
    # 收藏（task|testcase，INT-141）
    'Favorite',
    # 挑选合并（INT-339：购物车 / 容器关系 / 挑选集）
    'CherryPickCartItem', 'TaskCherryPickRelation', 'CherryPickSet', 'CherryPickSetItem',
    # 人工复核留痕（INT-340）
    'TestResultReview',
    # AI 复核记录（INT-821/INT-800：机器判定，独立表）
    'AiReview',
    # 离线搬运 source_map（INT-1760：A 原始 id → 本地 id，增量回导翻译用）
    'DataTransferSourceMap',
    # 系统日志
    'Log',
]
