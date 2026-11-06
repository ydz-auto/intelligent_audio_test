# -*- coding: utf-8 -*-
"""algorithm_service.AlgorithmQueryService ACL 仓储 — gRPC 实现。

封装 shared.clients.grpc_clients 中的 algo_* 便利函数，对返回 raw dict 的
查询应用 dict_to_dto / dict_list_to_dto 转换为 dataclass DTO。
"""
from __future__ import annotations

import logging
from typing import List, Optional

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
            logger.debug("附加 result_data 到 DTO 失败", exc_info=True)
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

    def normalize_algorithm_params(self, algorithm_params=None):
        """将按轮分组的 algorithm_params 扁平化为 {field_code: field_value} dict"""
        from shared.clients.grpc_clients import algo_normalize_algorithm_params
        return algo_normalize_algorithm_params(algorithm_params)

    def get_round_algo_params(self, algorithm_params_col=None, round_number: int = 0):
        """从 algorithm_params 列中取指定轮的 params"""
        from shared.clients.grpc_clients import algo_get_round_algo_params
        return algo_get_round_algo_params(algorithm_params_col, round_number)

    def load_reference_params_file(self, filepath) -> List:
        from shared.clients.grpc_clients import algo_load_reference_params_file
        try:
            data = algo_load_reference_params_file(filepath)
            return data if isinstance(data, list) else []
        except Exception as e:
            logger.warning("load_reference_params_file failed: %s", e)
            return []

    def get_field_mappings(self, algorithm_type,
                           api_id: Optional[int] = None,
                           device_id: Optional[int] = None) -> AlgoFieldMappingsDTO:
        from shared.clients.grpc_clients import algo_get_field_mappings
        try:
            data = algo_get_field_mappings(
                algorithm_type, api_id=api_id, device_id=device_id)
            raw = data._data if hasattr(data, '_data') else data
            return _attach(dict_to_dto(raw, AlgoFieldMappingsDTO), raw)
        except Exception as e:
            logger.warning("get_field_mappings failed: %s", e)
            return AlgoFieldMappingsDTO()

    def get_device_params(self, algorithm_type,
                          device_id: Optional[int] = None) -> List[AlgoParamDTO]:
        from shared.clients.grpc_clients import algo_get_device_params
        try:
            data = algo_get_device_params(algorithm_type, device_id=device_id)
            return [_attach(dict_to_dto(d, AlgoParamDTO), d)
                    for d in data if isinstance(d, dict)]
        except Exception as e:
            logger.warning("get_device_params failed: %s", e)
            return []

    def get_api_params(self, algorithm_type,
                       api_id: Optional[int] = None) -> List[AlgoParamDTO]:
        from shared.clients.grpc_clients import algo_get_api_params
        try:
            data = algo_get_api_params(algorithm_type, api_id=api_id)
            return [_attach(dict_to_dto(d, AlgoParamDTO), d)
                    for d in data if isinstance(d, dict)]
        except Exception as e:
            logger.warning("get_api_params failed: %s", e)
            return []

    def get_param_mapping(self, algorithm_type, comp_type,
                          api_id: Optional[int] = None,
                          device_id: Optional[int] = None) -> List[AlgoParamMappingDTO]:
        from shared.clients.grpc_clients import algo_get_param_mapping
        try:
            data = algo_get_param_mapping(
                algorithm_type, comp_type, api_id=api_id, device_id=device_id)
            return [_attach(dict_to_dto(d, AlgoParamMappingDTO), d)
                    for d in data if isinstance(d, dict)]
        except Exception as e:
            logger.warning("get_param_mapping failed: %s", e)
            return []

    def convert_field_values(self, items):
        """批量字段值转换（INT-1749）：一次 RPC 处理 N 个值。"""
        from shared.clients.grpc_clients import algo_convert_field_values
        try:
            values = algo_convert_field_values(items or [])
        except Exception as e:
            logger.warning("convert_field_values failed: %s", e)
            return None
        if not isinstance(values, list) or len(values) != len(items or []):
            logger.warning("convert_field_values 返回长度不匹配（请求 %s / 返回 %s），按原值保留",
                           len(items or []),
                           len(values) if isinstance(values, list) else None)
            return None
        return values
