# -*- coding: utf-8 -*-
"""维度评分导入导出应用服务（evaluation_service 段，INT-25）

供 DataTransfer gRPC servicer 调用；导入/回滚经 Redis 批次登记配合
task_service 编排层的分段补偿（batch_id 由编排方生成传入）。
"""
import logging
from typing import Dict, List, Tuple

from shared.utils.data_transfer_batch import transfer_batch_registry
from shared.utils.log_handler import log_not_emit
from evaluation_service.infrastructure.persistence.dimension_transfer_repository import (
    dimension_transfer_repository,
)

logger = logging.getLogger(__name__)

_MODULE_NAME = 'dimension_transfer_service'

_OWNER = 'evaluation_service'


class DimensionTransferService:
    """维度评分导出/导入/回滚"""

    def export_dimensions_for_tasks(self, result_ids: List[int]) -> dict:
        """按 result_id 列表导出维度评分行 + 维度定义快照（只读）"""
        clean_ids = [int(rid) for rid in (result_ids or [])]
        rows, dim_defs = dimension_transfer_repository.export_by_result_ids(clean_ids)
        return {'success': True, 'message': '', 'data': {
            'dimensions': rows,
            'dimension_defs': dim_defs,
        }}

    def import_dimensions(self, rows: List[dict],
                          result_id_mapping: Dict[str, int],
                          batch_id: str) -> dict:
        """导入维度评分（单事务）并登记批次主键。

        Args:
            rows: ZIP 内 test_result_dimensions.json 行
            result_id_mapping: task_service 段 flush 出的 test_results old→new 映射
                （键为 str——JSON 信封；内部转 int）
            batch_id: 编排方批次 ID
        """
        clean_mapping = {int(k): int(v) for k, v in (result_id_mapping or {}).items()}
        clean_rows = [r for r in (rows or []) if isinstance(r, dict)]
        id_mapping, inserted_pks = dimension_transfer_repository.import_rows(
            clean_rows, clean_mapping)
        transfer_batch_registry.record(batch_id, _OWNER, {
            'test_result_dimensions': inserted_pks,
        })
        log_not_emit('INFO', _MODULE_NAME,
                     f'维度评分导入完成 batch={batch_id} rows={len(inserted_pks)}',
                     category='system')
        return {'success': True, 'message': '', 'data': {
            'imported': len(inserted_pks),
            'id_mapping': {str(k): v for k, v in id_mapping.items()},
            'batch_id': batch_id,
        }}

    def rollback_dimension_import(self, batch_id: str) -> dict:
        """回滚维度导入批次（按登记主键删除；无登记视为无可回滚内容）"""
        pks = transfer_batch_registry.load_service(batch_id, _OWNER).get(
            'test_result_dimensions') or []
        deleted = dimension_transfer_repository.rollback_by_pks(pks)
        transfer_batch_registry.remove_service(batch_id, _OWNER)
        log_not_emit('INFO', _MODULE_NAME,
                     f'维度评分导入回滚完成 batch={batch_id} deleted={deleted}',
                     category='system')
        return {'success': True, 'message': '', 'data': {'deleted': deleted}}


dimension_transfer_service = DimensionTransferService()
