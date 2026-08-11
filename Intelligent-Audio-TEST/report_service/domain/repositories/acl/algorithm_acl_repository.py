# -*- coding: utf-8 -*-
"""algorithm_service.AlgorithmQueryService 跨域 ACL 仓储接口。"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from report_service.domain.dto import (
    AlgoNormalizedParamsDTO,
    AlgoReferenceParamsDTO,
    DimensionParamDTO,
)


class AlgorithmConfigAclRepository(ABC):
    """algorithm_service.AlgorithmQueryService 跨域只读查询接口。"""

    @abstractmethod
    def get_dimension_params(self, dimension_id) -> List[DimensionParamDTO]:
        """查询维度参数列表。"""
        ...

    @abstractmethod
    def normalize_algorithm_params(self, algorithm_params) -> AlgoNormalizedParamsDTO:
        """规范化算法参数为 dict。"""
        ...

    @abstractmethod
    def get_reference_params_for_report(self, reference_params_col) -> AlgoReferenceParamsDTO:
        """获取报告用参考参数。"""
        ...
