# -*- coding: utf-8 -*-
"""algorithm_service.AlgorithmQueryService ACL 仓储 — gRPC 实现。

封装 shared.clients.grpc_clients 中的 algo_* 便利函数，对返回 raw dict 的
查询应用 dict_to_dto / dict_list_to_dto 转换为 dataclass DTO。
"""
from __future__ import annotations

import logging
from typing import List

from api_test_service.domain.dto import (
    AlgoFieldMappingsDTO, AlgoParamDTO, AlgoParamMappingDTO, ExtractedCaseParamsDTO,
)
from api_test_service.domain.repositories.acl.algorithm_acl_repository import (
    AlgorithmQueryAclRepository,
)
from shared.utils.dto_utils import dict_to_dto, dict_list_to_dto

logger = logging.getLogger(__name__)


def _attach(dto, payload):
    if dto is not None and payload is not None:
        try:
            dto.result_data = payload
        except Exception:
            pass
    return dto


class AlgorithmQueryAclRepositoryImpl(AlgorithmQueryAclRepository):
    """algorithm_service.AlgorithmQueryService 跨域只读查询 gRPC 实现。"""

    def extract_case_all_params(self, case_config) -> ExtractedCaseParamsDTO:
        from shared.clients.grpc_clients import algo_extract_case_all_params
        try:
            data = algo_extract_case_all_params(case_config)
            return _attach(dict_to_dto(data, ExtractedCaseParamsDTO), data)
        except Exception as e:
            logger.warning("extract_case_all_params failed: %s", e)
            return ExtractedCaseParamsDTO()

    def load_reference_params_file(self, filepath) -> List:
        from shared.clients.grpc_clients import algo_load_reference_params_file
        try:
            data = algo_load_reference_params_file(filepath)
            return data if isinstance(data, list) else []
        except Exception as e:
            logger.warning("load_reference_params_file failed: %s", e)
            return []

    def get_field_mappings(self, algorithm_type) -> AlgoFieldMappingsDTO:
        from shared.clients.grpc_clients import algo_get_field_mappings
        try:
            data = algo_get_field_mappings(algorithm_type)
            return _attach(dict_to_dto(data, AlgoFieldMappingsDTO), data)
        except Exception as e:
            logger.warning("get_field_mappings failed: %s", e)
            return AlgoFieldMappingsDTO()

    def get_device_params(self, algorithm_type) -> List[AlgoParamDTO]:
        from shared.clients.grpc_clients import algo_get_device_params
        try:
            data = algo_get_device_params(algorithm_type)
            return [_attach(dict_to_dto(d, AlgoParamDTO), d)
                    for d in data if isinstance(d, dict)]
        except Exception as e:
            logger.warning("get_device_params failed: %s", e)
            return []

    def get_api_params(self, algorithm_type) -> List[AlgoParamDTO]:
        from shared.clients.grpc_clients import algo_get_api_params
        try:
            data = algo_get_api_params(algorithm_type)
            return [_attach(dict_to_dto(d, AlgoParamDTO), d)
                    for d in data if isinstance(d, dict)]
        except Exception as e:
            logger.warning("get_api_params failed: %s", e)
            return []

    def get_param_mapping(self, algorithm_type, comp_type) -> List[AlgoParamMappingDTO]:
        from shared.clients.grpc_clients import algo_get_param_mapping
        try:
            data = algo_get_param_mapping(algorithm_type, comp_type)
            return [_attach(dict_to_dto(d, AlgoParamMappingDTO), d)
                    for d in data if isinstance(d, dict)]
        except Exception as e:
            logger.warning("get_param_mapping failed: %s", e)
            return []
