# -*- coding: utf-8 -*-
"""增量回导维度合并应用服务（evaluation_service，INT-1762 D4）

供 EvaluationDataService gRPC servicer 调用（编排方 D3 增量导入编排）。
与 `DimensionTransferService.import_dimensions`（整包导入、ID 冲突重映射）不同，
本服务是**覆盖集合并**：包内 id 已是 A 原始 id，不做重映射，只按
`(test_result_id, dimension_id)` 覆盖，并把旧值落批次快照以支持回滚。
"""
import logging
from typing import Dict, List, Optional

from shared.utils.grpc_json import fold_business_code
from shared.utils.log_handler import log_not_emit
from evaluation_service.infrastructure.persistence.dimension_merge_repository import (
    MergeValidationError,
    dimension_merge_repository,
)

logger = logging.getLogger(__name__)

_MODULE_NAME = 'dimension_merge_service'


class DimensionMergeService:
    """维度评分覆盖集合并 / 批次快照回滚"""

    def merge_dimensions(self, rows: List[dict],
                         result_id_mapping: Optional[Dict[str, int]] = None,
                         dimension_id_mapping: Optional[Dict[str, int]] = None,
                         batch_id: str = '') -> dict:
        """合并包内维度评分（单事务 + 旧值快照）。

        Returns:
            {'success': bool, 'message': str, 'data': {...}}
            校验失败时 data 里带 `code`（HTTP 语义业务码）与明细（INT-566 口径，
            gRPC 响应无顶层 code 字段）。
        """
        try:
            data = dimension_merge_repository.merge_rows(
                rows, result_id_mapping, dimension_id_mapping, batch_id)
            return {'success': True, 'message': '', 'data': data}
        except MergeValidationError as e:
            detail = dict(e.detail or {})
            detail['batch_id'] = batch_id
            log_not_emit('WARNING', _MODULE_NAME,
                         f'维度合并校验失败 batch={batch_id} code={e.code}: {e}',
                         category='system')
            return {'success': False, 'message': str(e),
                    'data': fold_business_code(detail, e.code)}
        except Exception as e:
            log_not_emit('ERROR', _MODULE_NAME,
                         f'维度合并失败 batch={batch_id}: {e}',
                         category='system', exc_info=True)
            return {'success': False, 'message': str(e),
                    'data': fold_business_code({'batch_id': batch_id}, 500)}

    def rollback_merge(self, batch_id: str) -> dict:
        """按批次快照回滚维度合并。补偿失败必须显式报错（A8-4）。"""
        try:
            return {'success': True, 'message': '',
                    'data': dimension_merge_repository.rollback_by_batch(batch_id)}
        except Exception as e:
            log_not_emit('ERROR', _MODULE_NAME,
                         f'维度合并回滚失败 batch={batch_id}: {e}',
                         category='system', exc_info=True)
            return {'success': False,
                    'message': f'维度合并回滚失败（需人工介入）: {e}',
                    'data': fold_business_code({'batch_id': batch_id}, 500)}


dimension_merge_service = DimensionMergeService()
