# -*- coding: utf-8 -*-
"""Algorithm 跨域 ACL 仓储实现 — 通过 gRPC 调用 algorithm_service。

封装 algorithm_service 的算法定义/参数/参考参数等查询，
使 application 层不再直接 import shared.clients.grpc_clients。
"""
from __future__ import annotations

import logging
from typing import List

from audio_service.domain.repositories.acl.algorithm_acl_repository import (
    AlgorithmACLRepository,
)

logger = logging.getLogger(__name__)


class AlgorithmACLRepositoryImpl(AlgorithmACLRepository):
    """algorithm_service 跨域查询 gRPC 实现。"""

    def list_case_params(self, algorithm_type: str) -> List[dict]:
        """查询用例参数列表（ListCaseParams）

        通过 gRPC 调用 algorithm_service.AlgorithmDefinitionService.ListCaseParams。
        """
        try:
            from shared.clients.grpc_clients import get_algorithm_definition_service_stub
            from shared.proto import algorithm_service_pb2 as _algo_pb
            from shared.utils.grpc_json import loads as _grpc_loads

            stub = get_algorithm_definition_service_stub()
            resp = stub.ListCaseParams(
                _algo_pb.ListCaseParamsRequest(algorithm_type=algorithm_type)
            )
            if resp.success:
                data = _grpc_loads(resp.data, {}) or {}
                return data.get('parameters', []) or []
        except Exception:
            logger.debug("通过 gRPC 查询用例参数列表失败: algorithm_type=%s", algorithm_type, exc_info=True)
        return []

    def list_reference_params(self, algorithm_type: str) -> List[dict]:
        """查询参考参数列表（ListReferenceParams）

        通过 gRPC 调用 algorithm_service.AlgorithmDefinitionService.ListReferenceParams。
        """
        try:
            from shared.clients.grpc_clients import get_algorithm_definition_service_stub
            from shared.proto import algorithm_service_pb2 as _algo_pb
            from shared.utils.grpc_json import loads as _grpc_loads

            stub = get_algorithm_definition_service_stub()
            resp = stub.ListReferenceParams(
                _algo_pb.ListReferenceParamsRequest(algorithm_type=algorithm_type)
            )
            if resp.success:
                data = _grpc_loads(resp.data, {}) or {}
                return data.get('parameters', []) or []
        except Exception:
            logger.debug("通过 gRPC 查询参考参数列表失败: algorithm_type=%s", algorithm_type, exc_info=True)
        return []

    def generate_reference_params(self, test_case_config=None, round_data=None) -> list:
        """生成参考参数（GenerateReferenceParams）

        通过 gRPC 调用 algorithm_service.AlgorithmQueryService.GenerateReferenceParams。
        """
        from shared.clients.grpc_clients import algo_generate_reference_params
        return algo_generate_reference_params(
            test_case_config=test_case_config, round_data=round_data
        ) or []

    def get_all_reference_params(self, reference_params_col=None) -> list:
        """获取所有参考参数（GetAllReferenceParams）

        通过 gRPC 调用 algorithm_service.AlgorithmQueryService.GetAllReferenceParams。
        """
        from shared.clients.grpc_clients import algo_get_all_reference_params
        return algo_get_all_reference_params(reference_params_col=reference_params_col) or []

    def get_reference_params_for_report(self, reference_params_col=None) -> dict:
        """获取报告用参考参数（GetReferenceParamsForReport）

        通过 gRPC 调用 algorithm_service.AlgorithmQueryService.GetReferenceParamsForReport。
        """
        from shared.clients.grpc_clients import algo_get_reference_params_for_report
        return algo_get_reference_params_for_report(
            reference_params_col=reference_params_col
        ) or {}

    def normalize_algorithm_params_to_list(self, algorithm_params=None) -> list:
        """规范化算法参数为 list（NormalizeAlgorithmParamsToList）

        通过 gRPC 调用 algorithm_service.AlgorithmQueryService.NormalizeAlgorithmParamsToList。
        """
        from shared.clients.grpc_clients import algo_normalize_algorithm_params_to_list
        return algo_normalize_algorithm_params_to_list(algorithm_params=algorithm_params) or []

    def normalize_algorithm_params(self, algorithm_params=None) -> dict:
        """规范化算法参数为 dict（NormalizeAlgorithmParams）

        通过 gRPC 调用 algorithm_service.AlgorithmQueryService.NormalizeAlgorithmParams。
        """
        from shared.clients.grpc_clients import algo_normalize_algorithm_params
        return algo_normalize_algorithm_params(algorithm_params=algorithm_params) or {}
