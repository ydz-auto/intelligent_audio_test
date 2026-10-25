# -*- coding: utf-8 -*-
"""评估维度导入导出 gRPC ACL（task_service → evaluation_service）

导出/导入/回滚维度评分段的防腐层：JSON 信封编解码 + 超时 + 失败降级约定
（导出失败抛出由编排层决定；导入/回滚失败抛出触发补偿）。
"""
import json
import logging
from typing import Dict, List, Optional

from shared.clients.grpc_clients import get_evaluation_data_service_stub
from shared.proto import evaluation_service_pb2 as eval_pb
from shared.utils.grpc_json import loads as _loads

logger = logging.getLogger(__name__)

# ExecuteImport 为长耗时调用：导入/回滚段 RPC 超时放宽到 10 分钟
_GRPC_TIMEOUT_SECONDS = 600

# 维度定义全量分页拉取上限（防御性上限，正常维度数远小于此）
_DIMENSION_PAGE_SIZE = 200
_DIMENSION_MAX_PAGES = 50


class TransferMergeError(RuntimeError):
    """跨服务合并 RPC 失败（携带 HTTP 语义业务码与远端明细）

    远端失败时业务码折在 `data.code`（INT-566 口径），编排层据此回 HTTP 状态；
    `code=0` 表示远端未给码（按 500 处理）。
    """

    def __init__(self, message: str, code: int = 500, data: Optional[dict] = None):
        super().__init__(message)
        self.code = int(code or 500)
        self.data = data or {}


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

    # ---------- 增量回导：维度覆盖集合并（INT-1761 → D4 MergeDimensions）----------

    def merge_dimensions(self, rows: List[dict],
                         dimension_id_mapping: Dict[int, int],
                         batch_id: str) -> dict:
        """增量回导维度合并（覆盖集 + 旧值快照，远端单事务）。

        Args:
            rows: 包内维度评分行（test_result_id 已是 A 原始 id；dimension_id
                仍是 B 侧 id，由 `dimension_id_mapping` 翻译）
            dimension_id_mapping: {B 维度 id: A 维度 id}，未命中的行远端跳过
            batch_id: 编排方批次 ID（D4 快照按它回滚）

        Returns: 远端 data {imported, deleted, id_mapping, skipped_dimensions,
            batch_id, rollback_available}
        Raises: TransferMergeError（携带业务码与 data 明细，如 409 missing_result_ids）
        """
        stub = get_evaluation_data_service_stub()
        resp = stub.MergeDimensions(
            eval_pb.MergeDimensionsRequest(data=json.dumps({
                'rows': rows,
                'dimension_id_mapping': {str(k): int(v) for k, v in
                                         (dimension_id_mapping or {}).items()},
                'batch_id': batch_id,
            }, ensure_ascii=False, default=str)),
            timeout=_GRPC_TIMEOUT_SECONDS)
        data = _loads(resp.data, {}) if resp.data else {}
        if not resp.success:
            code = int((data or {}).get('code') or 500) if isinstance(data, dict) else 500
            raise TransferMergeError(f'维度合并失败: {resp.message}',
                                     code=code, data=data if isinstance(data, dict) else {})
        return data if isinstance(data, dict) else {}

    def rollback_dimension_merge(self, batch_id: str) -> dict:
        """回滚维度合并批次（补偿失败必须显式暴露）。

        无快照（已回滚 / 超 7 天 TTL）远端按 no-op 返回 success——编排层可无条件
        调用，不依赖「该段是否已提交」的本地判断。
        """
        stub = get_evaluation_data_service_stub()
        resp = stub.RollbackDimensionMerge(
            eval_pb.RollbackDimensionMergeRequest(batch_id=batch_id),
            timeout=_GRPC_TIMEOUT_SECONDS)
        if not resp.success:
            raise RuntimeError(f'维度合并回滚失败: {resp.message}')
        return _loads(resp.data, {})

    def list_dimension_defs(self) -> List[dict]:
        """拉取目标库（A）全部未删除维度定义（增量导入按名称链翻译维度 id 用）。

        走 EvaluationConfigService.ListDimensions 分页拉取；返回字段含
        id / name / parent_dimension_id / task_type_code / dimension_type。
        失败抛出 RuntimeError——维度翻译的依据缺失时不得静默按「无映射」处理
        （否则会把整批维度行当未匹配跳过）。
        """
        from shared.clients.grpc_clients import get_evaluation_config_service_stub
        stub = get_evaluation_config_service_stub()
        defs: List[dict] = []
        seen_ids = set()
        for page in range(1, _DIMENSION_MAX_PAGES + 1):
            resp = stub.ListDimensions(eval_pb.ListDimensionsRequest(
                page=page, per_page=_DIMENSION_PAGE_SIZE), timeout=_GRPC_TIMEOUT_SECONDS)
            if not resp.success:
                raise RuntimeError(f'拉取目标库维度定义失败: {resp.message}')
            payload = _loads(resp.data, {}) if resp.data else {}
            items = (payload or {}).get('items') or []
            for item in items:
                dim_id = item.get('id')
                if dim_id is None or dim_id in seen_ids:
                    continue
                seen_ids.add(dim_id)
                defs.append({
                    'id': dim_id,
                    'name': item.get('name'),
                    'parent_dimension_id': item.get('parent_dimension_id'),
                    'task_type_code': item.get('task_type_code'),
                    'dimension_type': item.get('dimension_type'),
                })
            if len(items) < _DIMENSION_PAGE_SIZE:
                break
        return defs


evaluation_transfer_acl_repository = EvaluationTransferAclRepository()
