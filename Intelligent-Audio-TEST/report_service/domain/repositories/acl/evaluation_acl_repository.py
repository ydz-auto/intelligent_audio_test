# -*- coding: utf-8 -*-
"""evaluation_service 跨域 ACL 仓储接口。

report_service 通过 gRPC 只读访问 evaluation_service 的维度配置与维度评估结果，
接口定义在此 ABC，实现在 infrastructure/acl/evaluation_acl_repository.py。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, List

from report_service.domain.dto import DimensionDTO, DimensionResultDTO


class EvaluationDataAclRepository(ABC):
    """evaluation_service.EvaluationDataService 跨域只读查询接口。"""

    @abstractmethod
    def get_dimension_results_by_result_ids(
        self, result_ids,
    ) -> Dict[int, List[DimensionResultDTO]]:
        """按 result_ids 查询维度评估结果，返回 {result_id: [DTO, ...]}。"""
        ...


class EvaluationConfigAclRepository(ABC):
    """evaluation_service.EvaluationConfigService 跨域只读查询接口。"""

    @abstractmethod
    def list_dimensions_all(self) -> List[DimensionDTO]:
        """查询所有启用的维度列表。"""
        ...

    @abstractmethod
    def get_dimension_by_ids(self, dim_ids) -> Dict[str, DimensionDTO]:
        """按 ID 批量查询维度，返回 {dim_id_str: DimensionDTO}。"""
        ...
