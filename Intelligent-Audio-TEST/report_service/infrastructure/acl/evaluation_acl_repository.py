# -*- coding: utf-8 -*-
"""evaluation_service ACL 仓储 — gRPC 实现。

从 report_service/infrastructure/clients/grpc_clients.py 迁出，
维度配置与维度评估结果查询返回 dataclass DTO。
"""
from __future__ import annotations

import json as _json
import logging
from typing import Dict, List

from report_service.domain.dto import DimensionDTO, DimensionResultDTO
from report_service.domain.repositories.acl.evaluation_acl_repository import (
    EvaluationConfigAclRepository,
    EvaluationDataAclRepository,
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


class EvaluationDataAclRepositoryImpl(EvaluationDataAclRepository):
    """evaluation_service.EvaluationDataService 跨域只读查询 gRPC 实现。"""

    def get_dimension_results_by_result_ids(
        self, result_ids,
    ) -> Dict[int, List[DimensionResultDTO]]:
        if not result_ids:
            return {}
        from shared.clients.grpc_clients import get_evaluation_data_service_stub
        from shared.proto import evaluation_service_pb2 as eval_pb
        from shared.utils.grpc_json import loads as _loads
        try:
            stub = get_evaluation_data_service_stub()
            resp = stub.GetDimensionResultsByResultIds(
                eval_pb.GetDimensionResultsByResultIdsRequest(
                    result_ids=_json.dumps(list(result_ids), ensure_ascii=False, default=str),
                ))
            if not resp.success:
                return {}
            data = _loads(resp.data, {})
            items = data.get('items', []) if isinstance(data, dict) else []
            result_map: Dict[int, List[DimensionResultDTO]] = {}
            for it in items:
                if not isinstance(it, dict):
                    continue
                rid = it.get('test_result_id') or it.get('result_id')
                if rid is None:
                    continue
                result_map.setdefault(rid, []).append(_attach(dict_to_dto(it, DimensionResultDTO), it))
            return result_map
        except Exception as e:
            logger.warning("get_dimension_results_by_result_ids gRPC failed: %s", e)
            return {}


class EvaluationConfigAclRepositoryImpl(EvaluationConfigAclRepository):
    """evaluation_service.EvaluationConfigService 跨域只读查询 gRPC 实现。"""

    def list_dimensions_all(self) -> List[DimensionDTO]:
        from shared.clients.grpc_clients import get_evaluation_config_service_stub
        from shared.proto import evaluation_service_pb2 as eval_pb
        from shared.utils.grpc_json import loads as _loads
        try:
            stub = get_evaluation_config_service_stub()
            resp = stub.ListDimensions(eval_pb.ListDimensionsRequest(
                category_id=0, page=1, per_page=10000, search='',
            ))
            if not resp.success:
                return []
            data = _loads(resp.data, {})
            if isinstance(data, dict):
                items = data.get('items', []) or data.get('list', [])
            else:
                items = data if isinstance(data, list) else []
            return [
                _attach(dict_to_dto(d, DimensionDTO), d)
                for d in items
                if isinstance(d, dict) and d.get('status', True) and not d.get('deleted', False)
            ]
        except Exception as e:
            logger.warning("list_dimensions_all gRPC failed: %s", e)
            return []

    def get_dimension_by_ids(self, dim_ids) -> Dict[str, DimensionDTO]:
        if not dim_ids:
            return {}
        from shared.clients.grpc_clients import get_evaluation_config_service_stub
        from shared.proto import evaluation_service_pb2 as eval_pb
        from shared.utils.grpc_json import loads as _loads
        try:
            stub = get_evaluation_config_service_stub()
            ids_list = [int(d) for d in dim_ids if d is not None]
            resp = stub.GetDimensionByIds(eval_pb.GetDimensionByIdsRequest(
                dim_ids=_json.dumps(ids_list, ensure_ascii=False, default=str),
            ))
            if not resp.success:
                return {}
            data = _loads(resp.data, {})
            items = data.get('items', []) if isinstance(data, dict) else data
            result_map: Dict[str, DimensionDTO] = {}
            if isinstance(items, list):
                for d in items:
                    if isinstance(d, dict) and d.get('id') is not None:
                        result_map[str(d.get('id'))] = _attach(dict_to_dto(d, DimensionDTO), d)
            elif isinstance(items, dict):
                for k, d in items.items():
                    if isinstance(d, dict):
                        result_map[str(k)] = _attach(dict_to_dto(d, DimensionDTO), d)
            return result_map
        except Exception as e:
            logger.warning("get_dimension_by_ids gRPC failed: %s", e)
            return {}
