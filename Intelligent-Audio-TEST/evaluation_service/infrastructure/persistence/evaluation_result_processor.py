# -*- coding: utf-8 -*-
"""评估结果处理器（组合入口）

原 738 行大文件按职责拆分为 4 个混入，本文件通过多继承组合，
对外保持 `EvaluationResultProcessor` 类名与导入路径不变：
- _result_parse_mixin.ParseDimensionMixin: 维度结果解析与完成检查
- _result_dimension_mixin.DimensionResultMixin: 维度结果 DB 持久化
- _result_status_mixin.ResultStatusMixin: TaskCase/Task 状态推进
- _result_group_mixin.GroupResultMixin: 组处理与 algorithm_results 快照
"""
from evaluation_service.infrastructure.persistence.round_aggregator import RoundAggregator
from evaluation_service.infrastructure.persistence._result_parse_mixin import ParseDimensionMixin
from evaluation_service.infrastructure.persistence._result_dimension_mixin import DimensionResultMixin
from evaluation_service.infrastructure.persistence._result_status_mixin import ResultStatusMixin
from evaluation_service.infrastructure.persistence._result_group_mixin import GroupResultMixin


class EvaluationResultProcessor(
    ParseDimensionMixin,
    DimensionResultMixin,
    ResultStatusMixin,
    GroupResultMixin,
    RoundAggregator,
):
    """
    评估结果处理器，负责解析API响应、计算分数并更新数据库

    继承 RoundAggregator 获取多轮聚合能力，对外保持原有接口不变。

    P1.4 改造：所有 Task/TaskCase/TaskDevice/TaskAPI/TestCase/TestResult 的访问
    改为通过 task_acl_repository (gRPC) 调 task_service。
    仅保留 Dimension / TestResultDimension 的本地 DB 访问（本服务自有 PO）。
    """
