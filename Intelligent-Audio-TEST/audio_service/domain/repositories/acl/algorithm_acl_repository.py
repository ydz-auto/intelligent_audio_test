# -*- coding: utf-8 -*-
"""Algorithm 跨域 ACL 仓储接口。

algorithm_service 域的算法定义/参数/参考参数等数据通过 gRPC 只读访问，
接口定义在此 ABC，实现在 infrastructure/acl/algorithm_acl_repository.py。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List


class AlgorithmACLRepository(ABC):
    """algorithm_service 跨域查询接口。"""

    @abstractmethod
    def list_case_params(self, algorithm_type: str) -> List[dict]:
        """查询用例参数列表（ListCaseParams）"""
        ...

    @abstractmethod
    def list_reference_params(self, algorithm_type: str) -> List[dict]:
        """查询参考参数列表（ListReferenceParams）"""
        ...

    @abstractmethod
    def generate_reference_params(self, test_case_config=None, round_data=None) -> list:
        """生成参考参数（GenerateReferenceParams）"""
        ...

    @abstractmethod
    def get_all_reference_params(self, reference_params_col=None) -> list:
        """获取所有参考参数（GetAllReferenceParams）"""
        ...

    @abstractmethod
    def get_reference_params_for_report(self, reference_params_col=None) -> dict:
        """获取报告用参考参数（GetReferenceParamsForReport）"""
        ...

    @abstractmethod
    def normalize_algorithm_params_to_list(self, algorithm_params=None) -> list:
        """规范化算法参数为 list（NormalizeAlgorithmParamsToList）"""
        ...

    @abstractmethod
    def normalize_algorithm_params(self, algorithm_params=None) -> dict:
        """规范化算法参数为 dict（NormalizeAlgorithmParams）"""
        ...
