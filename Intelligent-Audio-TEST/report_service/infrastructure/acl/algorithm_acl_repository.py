# -*- coding: utf-8 -*-
"""algorithm_service.AlgorithmQueryService ACL 仓储 — gRPC 实现。"""
from __future__ import annotations

import logging
from typing import List, Optional

from report_service.domain.dto import (
    AlgoNormalizedParamsDTO,
    AlgoReferenceParamsDTO,
    DimensionParamDTO,
)
from report_service.domain.repositories.acl.algorithm_acl_repository import (
    AlgorithmConfigAclRepository,
)
from shared.utils.dto_utils import dict_to_dto

logger = logging.getLogger(__name__)


def _attach(dto, payload):
    if dto is not None and payload is not None:
        try:
            dto.result_data = payload
        except Exception:
            pass
    return dto


class AlgorithmConfigAclRepositoryImpl(AlgorithmConfigAclRepository):
    """algorithm_service.AlgorithmQueryService 跨域只读查询 gRPC 实现。"""

    def get_dimension_params(self, dimension_id) -> List[DimensionParamDTO]:
        from shared.clients.grpc_clients import get_algorithm_config_service_stub
        from shared.proto import task_service_pb2 as task_pb
        from shared.utils.grpc_json import loads as _loads
        try:
            stub = get_algorithm_config_service_stub()
            resp = stub.GetDimensionParams(task_pb.GetDimensionParamsRequest(dimension_id=dimension_id))
            if not resp.success:
                return []
            data = _loads(resp.data, None)
            if isinstance(data, dict):
                items = data.get('params', []) or []
            else:
                items = data if isinstance(data, list) else []
            return [_attach(dict_to_dto(d, DimensionParamDTO), d)
                    for d in items if isinstance(d, dict)]
        except Exception as e:
            logger.warning("get_dimension_params gRPC failed: %s", e)
            return []

    def normalize_algorithm_params(self, algorithm_params) -> AlgoNormalizedParamsDTO:
        from shared.clients.grpc_clients import algo_normalize_algorithm_params
        try:
            data = algo_normalize_algorithm_params(algorithm_params)
            if not isinstance(data, dict):
                return None
            return _attach(dict_to_dto(data, AlgoNormalizedParamsDTO), data)
        except Exception as e:
            logger.warning("normalize_algorithm_params gRPC failed: %s", e)
            return None

    def get_reference_params_for_report(self, reference_params_col) -> AlgoReferenceParamsDTO:
        from shared.clients.grpc_clients import algo_get_reference_params_for_report
        try:
            data = algo_get_reference_params_for_report(reference_params_col)
            if not isinstance(data, dict):
                return None
            return _attach(dict_to_dto(data, AlgoReferenceParamsDTO), data)
        except Exception as e:
            logger.warning("get_reference_params_for_report gRPC failed: %s", e)
            return None
