# -*- coding: utf-8 -*-
"""algorithm_service 跨域 ACL 仓储接口。"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from api_test_service.domain.dto import (
    AlgoFieldMappingsDTO, AlgoParamDTO, AlgoParamMappingDTO, ExtractedCaseParamsDTO,
)


class AlgorithmQueryAclRepository(ABC):
    """algorithm_service.AlgorithmQueryService 跨域只读查询接口。"""

    @abstractmethod
    def extract_case_all_params(self, case_config) -> ExtractedCaseParamsDTO:
        """提取用例全量参数。"""
        ...

    @abstractmethod
    def load_reference_params_file(self, filepath) -> List:
        """加载参考参数文件，返回原始列表。"""
        ...

    @abstractmethod
    def get_field_mappings(self, algorithm_type, api_id: Optional[int] = None) -> AlgoFieldMappingsDTO:
        """查询算法字段映射（api_id 传入时按 API 实例级合并，INT-1757）。"""
        ...

    @abstractmethod
    def get_device_params(self, algorithm_type) -> List[AlgoParamDTO]:
        """查询算法设备参数列表。"""
        ...

    @abstractmethod
    def get_api_params(self, algorithm_type, api_id: Optional[int] = None) -> List[AlgoParamDTO]:
        """查询算法 API 参数列表（api_id 传入时按 API 实例级合并，INT-1757）。"""
        ...

    @abstractmethod
    def get_param_mapping(self, algorithm_type, comp_type,
                          api_id: Optional[int] = None) -> List[AlgoParamMappingDTO]:
        """查询参数映射（api_id 传入时按 API 实例级合并，INT-1757）。"""
        ...

    @abstractmethod
    def convert_field_values(self, items) -> List:
        """批量字段值转换（一次 gRPC 处理 N 个值）。

        Args:
            items: ``[{'transform_type': str, 'value': Any}, ...]``

        Returns:
            与 items 同序的转换结果列表；服务端不可达时返回 None，
            调用方按原值落库（INT-1749）。
        """
        ...
