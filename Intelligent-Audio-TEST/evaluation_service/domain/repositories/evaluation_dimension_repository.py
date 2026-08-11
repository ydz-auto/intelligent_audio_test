# -*- coding: utf-8 -*-
"""评估维度领域仓储接口（ABC）

Domain 层通过此接口访问自有数据（Dimension / TestResultDimension），
不直接依赖 infrastructure/persistence。
"""
from abc import ABC, abstractmethod
from typing import List, Optional

from evaluation_service.domain.entities import (
    EvaluationDimension,
    DimensionScore,
)


class EvaluationDimensionRepository(ABC):
    """评估维度领域仓储抽象接口"""

    # ========== Dimension 读 ==========

    @abstractmethod
    def get_dimension_by_id(self, dim_id: int) -> Optional[EvaluationDimension]:
        """按 ID 加载维度聚合根"""
        ...

    @abstractmethod
    def list_dimensions_by_ids(self, dim_ids: List[int]) -> List[EvaluationDimension]:
        """批量加载维度聚合根（仅未删除）"""
        ...

    @abstractmethod
    def list_active_dimensions_by_algorithm(
        self, algorithm_type: str
    ) -> List[EvaluationDimension]:
        """按算法类型列出可用维度（未删除 + 已启用 + API 在线）"""
        ...

    @abstractmethod
    def list_active_dimensions_by_ids(
        self, dim_ids: List[int]
    ) -> List[EvaluationDimension]:
        """按 ID 列表批量加载可用维度（未删除 + 已启用）。"""
        ...

    @abstractmethod
    def list_all_endpoint_dimensions(self) -> List[EvaluationDimension]:
        """加载全部维度（含已禁用，不含已删除），用于端点 Worker 初始化预加载。"""
        ...

    @abstractmethod
    def get_dimension_basics_by_ids(
        self, dim_ids: List[int]
    ) -> List[dict]:
        """按 dim_id 列表批量查询维度基础信息（id/name/type/description）。
        返回 dict 列表，供 gRPC servicer 直接序列化。"""
        ...

    # ========== DimensionScore 读 ==========

    @abstractmethod
    def list_scores_by_result_id(
        self, result_id: int
    ) -> List[DimensionScore]:
        """读取某 TestResult 的所有维度评分"""
        ...

    @abstractmethod
    def list_pending_scores(self, result_id: int) -> List[DimensionScore]:
        """读取待评估的维度评分"""
        ...

    # ========== DimensionScore 写 ==========

    @abstractmethod
    def create_score(self, score: DimensionScore) -> int:
        """创建维度评分记录（含 flush，未 commit）。返回新 ID。"""
        ...

    @abstractmethod
    def create_score_with_commit(self, score: DimensionScore) -> Optional[int]:
        """创建维度评分记录并提交事务。失败时返回 None。"""
        ...

    @abstractmethod
    def update_score(self, score_id: int, score: DimensionScore) -> None:
        """更新维度评分（含 flush，未 commit）。"""
        ...

    @abstractmethod
    def mark_score_status(
        self, score_id: int, evaluation_status: str, error_message: Optional[str] = None
    ) -> None:
        """快速更新评估状态（含 flush，未 commit）。"""
        ...

    @abstractmethod
    def mark_result_dimensions_completed(self, result_id: int) -> int:
        """将某 TestResult 的所有维度评分标记为 completed。返回受影响行数。"""
        ...

    @abstractmethod
    def delete_scores_by_result_id(self, result_id: int) -> int:
        """删除某 TestResult 的所有维度评分记录（重新评估前清理）。返回删除行数。"""
        ...

    @abstractmethod
    def get_dimension_results_with_names_by_result_ids(
        self, result_ids: List[int]
    ) -> List[dict]:
        """按 result_id 列表批量查询维度评估结果（含 dimension_name）。
        返回 dict 列表，供 gRPC servicer 直接序列化。"""
        ...

    @abstractmethod
    def delete_scores_by_result_ids(self, result_ids: List[int]) -> int:
        """按 result_id 列表批量删除维度评估记录。返回删除行数。"""
        ...
