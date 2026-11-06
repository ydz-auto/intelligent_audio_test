# -*- coding: utf-8 -*-
"""algorithm_service.AlgorithmDefinitionService 防腐层仓储

封装 device_service 对 algorithm_service.AlgorithmDefinitionService 的跨域 gRPC 调用，
替代 device_service/infrastructure/persistence/device_repository.py 中
直接 import shared.clients.grpc_clients。

- 读操作通过 gRPC 完成，返回 dict / list，不返回 ORM 对象。
- 采用具体类 + 模块级单例（device_service ACL 层无统一 ABC）。
"""
import logging
from typing import List

logger = logging.getLogger(__name__)


class AlgorithmDefinitionAclRepository:
    """algorithm_service.AlgorithmDefinitionService 防腐层仓储

    封装 gRPC 调用，提供 device_service persistence 层可用的返回值。
    所有方法返回纯 dict / list，不返回 ORM 对象。
    """

    def list_case_params(self, algorithm_type: str) -> List[dict]:
        """查询指定算法类型的用例参数列表（返回 dict 列表）。

        通过 gRPC 调用 algorithm_service.AlgorithmDefinitionService.ListCaseParams，
        替代直连 CaseAlgorithmParam PO；gRPC 不可用时返回空列表。
        """
        try:
            from shared.clients.grpc_clients import (
                get_algorithm_definition_service_stub,
            )
            from shared.proto import algorithm_service_pb2 as _algo_pb
            from shared.utils.grpc_json import loads as _grpc_loads
            stub = get_algorithm_definition_service_stub()
            req = _algo_pb.ListCaseParamsRequest(algorithm_type=algorithm_type or '')
            resp = stub.ListCaseParams(req)
            if resp.success:
                data = _grpc_loads(resp.data, {}) or {}
                return data.get('parameters', []) or []
        except Exception:
            logger.debug("gRPC 查询用例参数列表失败 algorithm_type=%s", algorithm_type, exc_info=True)
        # gRPC 不可用时返回空列表
        return []

    def list_reference_params(self, algorithm_type: str) -> List[dict]:
        """查询指定算法类型的引用参数列表（返回 dict 列表）。

        通过 gRPC 调用 algorithm_service.AlgorithmDefinitionService.ListReferenceParams，
        替代直连 AlgorithmReferenceParam PO；gRPC 不可用时返回空列表。
        """
        try:
            from shared.clients.grpc_clients import (
                get_algorithm_definition_service_stub,
            )
            from shared.proto import algorithm_service_pb2 as _algo_pb
            from shared.utils.grpc_json import loads as _grpc_loads
            stub = get_algorithm_definition_service_stub()
            req = _algo_pb.ListReferenceParamsRequest(algorithm_type=algorithm_type or '')
            resp = stub.ListReferenceParams(req)
            if resp.success:
                data = _grpc_loads(resp.data, {}) or {}
                return data.get('parameters', []) or []
        except Exception:
            logger.debug("gRPC 查询引用参数列表失败 algorithm_type=%s", algorithm_type, exc_info=True)
        # gRPC 不可用时返回空列表
        return []

    def get_algorithm_definition_stub(self):
        """获取 AlgorithmDefinitionService gRPC stub。

        封装 shared.clients.grpc_clients.get_algorithm_definition_service_stub，
        供需要直接调用 stub 的场景使用。
        """
        from shared.clients.grpc_clients import (
            get_algorithm_definition_service_stub,
        )
        return get_algorithm_definition_service_stub()


# 模块级单例
algorithm_definition_acl_repository = AlgorithmDefinitionAclRepository()
