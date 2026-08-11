# -*- coding: utf-8 -*-
"""algorithm_service 跨域 ACL 仓储接口。"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

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
    def get_field_mappings(self, algorithm_type) -> AlgoFieldMappingsDTO:
        """查询算法字段映射。"""
        ...

    @abstractmethod
    def get_device_params(self, algorithm_type) -> List[AlgoParamDTO]:
        """查询算法设备参数列表。"""
        ...

    @abstractmethod
    def get_api_params(self, algorithm_type) -> List[AlgoParamDTO]:
        """查询算法 API 参数列表。"""
        ...

    @abstractmethod
    def get_param_mapping(self, algorithm_type, comp_type) -> List[AlgoParamMappingDTO]:
        """查询参数映射。"""
        ...
