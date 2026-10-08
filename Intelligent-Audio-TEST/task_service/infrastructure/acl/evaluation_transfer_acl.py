# -*- coding: utf-8 -*-
"""评估维度导入导出 gRPC ACL（task_service → evaluation_service）

导出/导入/回滚维度评分段的防腐层：JSON 信封编解码 + 超时 + 失败降级约定
（导出失败抛出由编排层决定；导入/回滚失败抛出触发补偿）。
"""
import json
import logging
from typing import Dict, List

from shared.clients.grpc_clients import get_evaluation_data_service_stub
from shared.proto import evaluation_service_pb2 as eval_pb
from shared.utils.grpc_json import loads as _loads

logger = logging.getLogger(__name__)

# ExecuteImport 为长耗时调用：导入/回滚段 RPC 超时放宽到 10 分钟
_GRPC_TIMEOUT_SECONDS = 600


class EvaluationTransferAclRepository:
    """evaluation_service 维度导出/导入/回滚客户端"""

    def export_dimensions_for_tasks(self, result_ids: List[int]) -> dict:
        """按结果 ID 列表拉取维度评分行 + 维度定义快照。

        Returns: {'dimensions': [...], 'dimension_defs': [...]}
        Raises: gRPC 失败或远端返回 success=False 时抛出 RuntimeError。
        """
        stub = get_evaluation_data_service_stub()
        resp = stub.ExportDimensionsForTasks(eval_pb.ExportDimensionsForTasksRequest(
            result_ids=json.dumps(result_ids, ensure_ascii=False)))
        if not resp.success:
            raise RuntimeError(f'拉取维度评分失败: {resp.message}')
        return _loads(resp.data, {})

    def import_dimensions(self, rows: List[dict],
                          result_id_mapping: Dict[int, int],
                          batch_id: str) -> dict:
        """导入维度评分（远端单事务 + 主键冲突剥离 + test_result_id 重映射）。

        Returns: {'imported': int, 'id_mapping': {old: new}, 'batch_id': str}
        Raises: 失败抛出 RuntimeError（编排层据此回滚已提交前序段）。
        """
        stub = get_evaluation_data_service_stub()
        # timeout 是 gRPC 调用的关键字参数，不是 Request 消息字段（缺陷 4 修复）
        resp = stub.ImportDimensions(
            eval_pb.ImportDimensionsRequest(data=json.dumps({
                'rows': rows,
                'result_id_mapping': {str(k): v for k, v in result_id_mapping.items()},
                'batch_id': batch_id,
            }, ensure_ascii=False, default=str)),
            timeout=_GRPC_TIMEOUT_SECONDS)
        if not resp.success:
            raise RuntimeError(f'维度评分导入失败: {resp.message}')
        return _loads(resp.data, {})

    def rollback_dimension_import(self, batch_id: str) -> dict:
        """回滚维度导入批次。失败抛出 RuntimeError（补偿失败必须显式暴露）。"""
        stub = get_evaluation_data_service_stub()
        resp = stub.RollbackDimensionImport(
            eval_pb.RollbackDimensionImportRequest(batch_id=batch_id),
            timeout=_GRPC_TIMEOUT_SECONDS)
        if not resp.success:
            raise RuntimeError(f'维度评分导入回滚失败: {resp.message}')
        return _loads(resp.data, {})


evaluation_transfer_acl_repository = EvaluationTransferAclRepository()
