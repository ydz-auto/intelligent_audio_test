# -*- coding: utf-8 -*-
"""AlgorithmService ACL 仓储 — gRPC 实现

封装 algorithm_service gRPC 调用，供 e2e_test_service application 层使用。
替代直接 import shared.clients.grpc_clients 的 algo_* 函数。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class AlgorithmAclRepositoryImpl:
    """AlgorithmService ACL 仓储实现

    封装 algorithm_service 的 gRPC 调用，application 层通过此仓储访问算法配置，
    不直接 import shared.clients.grpc_clients。
    """

    @staticmethod
    def normalize_algorithm_params(algorithm_params=None) -> Dict[str, Any]:
        """将按轮分组的 algorithm_params 扁平化为 {field_code: field_value} dict"""
        from shared.clients.grpc_clients import algo_normalize_algorithm_params
        return algo_normalize_algorithm_params(algorithm_params)

    @staticmethod
    def get_round_algo_params(algorithm_params_col=None, round_number: int = 0) -> List[Dict]:
        """从 algorithm_params 列中取指定轮的 params"""
        from shared.clients.grpc_clients import algo_get_round_algo_params
        return algo_get_round_algo_params(algorithm_params_col, round_number)

    @staticmethod
    def load_reference_params_file(filepath: str = '') -> List[Dict]:
        """加载参考参数文件"""
        from shared.clients.grpc_clients import algo_load_reference_params_file
        return algo_load_reference_params_file(filepath)

    @staticmethod
    def get_device_params(algorithm_type: str) -> List[Dict]:
        """获取设备参数列表"""
        from shared.clients.grpc_clients import algo_get_device_params
        return algo_get_device_params(algorithm_type)

    @staticmethod
    def get_api_params(algorithm_type: str) -> List[Dict]:
        """获取 API 参数列表"""
        from shared.clients.grpc_clients import algo_get_api_params
        return algo_get_api_params(algorithm_type)

    @staticmethod
    def get_param_mapping(algorithm_type: str, component_type: str) -> List[Dict]:
        """获取参数映射"""
        from shared.clients.grpc_clients import algo_get_param_mapping
        return algo_get_param_mapping(algorithm_type, component_type)

    @staticmethod
    def get_field_mappings(algorithm_type: str):
        """获取字段定义（original + mapped），返回 FieldMapperWrapper"""
        from shared.clients.grpc_clients import algo_get_field_mappings
        return algo_get_field_mappings(algorithm_type)

    @staticmethod
    def extract_case_all_params(case_config=None) -> Dict[str, Any]:
        """提取用例所有参数"""
        from shared.clients.grpc_clients import algo_extract_case_all_params
        return algo_extract_case_all_params(case_config)
