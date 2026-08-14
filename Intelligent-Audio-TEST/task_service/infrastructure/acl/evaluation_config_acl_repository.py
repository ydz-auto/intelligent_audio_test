# -*- coding: utf-8 -*-
"""evaluation_service 防腐层仓储 — gRPC ACL 适配层。

封装 task_service 对 evaluation_service 的跨域 gRPC 调用，
消除 infrastructure/persistence / read_models 层对
shared.clients.grpc_clients 的直接依赖。

相关 stub：
- shared.clients.grpc_clients.get_evaluation_config_service_stub
- shared.clients.grpc_clients.get_evaluation_data_service_stub

proto：shared/proto/evaluation_service_pb2
"""
import json
import logging
from typing import List

from shared.utils.grpc_json import loads as _loads

_logger = logging.getLogger(__name__)


class EvaluationConfigAclRepository:
    """evaluation_service 防腐层仓储（gRPC ACL 适配层）。"""

    def list_dimensions_by_ids(self, dim_ids) -> list:
        """按 ID 列表批量查询评价维度基础信息。

        封装 evaluation_service.EvaluationConfigService.GetDimensionByIds RPC。
        返回 [{'id', 'name', 'type', 'description'}, ...]；失败返回空列表。
        """
        if not dim_ids:
            return []
        from shared.clients.grpc_clients import get_evaluation_config_service_stub
        from shared.proto import evaluation_service_pb2 as eval_pb
        try:
            stub = get_evaluation_config_service_stub()
            resp = stub.GetDimensionByIds(eval_pb.GetDimensionByIdsRequest(
                dim_ids=json.dumps(list(dim_ids)),
            ))
            if not resp.success:
                _logger.warning("GetDimensionByIds gRPC 失败: %s", resp.message)
                return []
            payload = json.loads(resp.data) if resp.data else {}
        except Exception as e:
            _logger.warning("GetDimensionByIds gRPC 异常: %s", e)
            return []

        if not isinstance(payload, dict):
            return []
        return payload.get('items', [])

    def list_dimensions(self, page: int = 1, per_page: int = 1) -> dict:
        """查询维度列表（分页）。

        封装 evaluation_service.EvaluationConfigService.ListDimensions RPC，
        返回 {'total': N, 'items': [...]}；失败返回空 dict。
        """
        from shared.clients.grpc_clients import get_evaluation_config_service_stub
        from shared.proto import evaluation_service_pb2 as eval_pb
        try:
            stub = get_evaluation_config_service_stub()
            resp = stub.ListDimensions(eval_pb.ListDimensionsRequest(
                page=page, per_page=per_page,
            ))
            if not resp.success:
                return {}
            return _loads(resp.data, {}) or {}
        except Exception as e:
            _logger.warning("ListDimensions gRPC 异常: %s", e)
            return {}

    def get_evaluation_config_stub(self):
        """获取 EvaluationConfigService gRPC stub。

        封装 shared.clients.grpc_clients.get_evaluation_config_service_stub，
        供需要直接调用 stub 的场景使用。
        """
        from shared.clients.grpc_clients import get_evaluation_config_service_stub
        return get_evaluation_config_service_stub()

    def get_dimension_results_by_result_ids(self, result_ids) -> dict:
        """批量获取维度评估结果，按 test_result_id 分组返回。

        封装 evaluation_service.EvaluationDataService.GetDimensionResultsByResultIds RPC。
        失败时返回空 dict。
        """
        if not result_ids:
            return {}
        from shared.clients.grpc_clients import get_evaluation_data_service_stub
        from shared.proto import evaluation_service_pb2 as eval_pb
        try:
            stub = get_evaluation_data_service_stub()
            resp = stub.GetDimensionResultsByResultIds(
                eval_pb.GetDimensionResultsByResultIdsRequest(
                    result_ids=json.dumps(list(result_ids)),
                ))
            if not resp.success:
                _logger.warning(
                    "GetDimensionResultsByResultIds gRPC 失败: %s", resp.message)
                return {}
            payload = json.loads(resp.data) if resp.data else {}
        except Exception as e:
            _logger.warning(
                "GetDimensionResultsByResultIds gRPC 异常: %s", e)
            return {}

        items = payload.get('items', []) if isinstance(payload, dict) else []
        grouped = {}
        for item in items:
            rid = item.get('test_result_id')
            if rid is None:
                continue
            grouped.setdefault(rid, []).append({
                "id": item.get('id'),
                "name": item.get('dimension_name'),
                "value": item.get('dimension_value'),
                "score": item.get('score'),
                "status": item.get('status'),
                "evaluation_status": item.get('evaluation_status'),
                "error_message": item.get('error_message'),
                "round_number": item.get('round_number'),
            })
        return grouped

    def get_evaluation_data_stub(self):
        """获取 EvaluationDataService gRPC stub。

        封装 shared.clients.grpc_clients.get_evaluation_data_service_stub，
        供需要直接调用 stub 的场景使用。
        """
        from shared.clients.grpc_clients import get_evaluation_data_service_stub
        return get_evaluation_data_service_stub()


# 模块级单例
evaluation_config_acl_repository = EvaluationConfigAclRepository()
