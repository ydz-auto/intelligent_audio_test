# -*- coding: utf-8 -*-
"""报告 7 表导入导出应用服务（report_service 段，INT-25）

供 ReportConfigService gRPC servicer 调用；导入/回滚经 Redis 批次登记
配合 task_service 编排层的分段补偿（batch_id 由编排方生成传入）。
"""
import logging
from typing import Dict, List

from shared.utils.data_transfer_batch import transfer_batch_registry
from shared.utils.log_handler import log_not_emit
from report_service.infrastructure.persistence.report_transfer_repository import (
    report_transfer_repository,
)

logger = logging.getLogger(__name__)

_MODULE_NAME = 'report_transfer_service'

_OWNER = 'report_service'


class ReportTransferService:
    """报告 7 表导出/导入/回滚"""

    def export_reports_for_tasks(self, task_ids: List[int]) -> dict:
        """按 task_id 列表导出报告 7 表只读行"""
        clean_ids = [int(tid) for tid in (task_ids or [])]
        tables_rows = report_transfer_repository.export_by_task_ids(clean_ids)
        return {'success': True, 'message': '', 'data': tables_rows}

    def import_reports(self, tables_rows: Dict[str, List[dict]],
                       task_id_mapping: Dict[str, int],
                       batch_id: str) -> dict:
        """导入报告 7 表（单事务）并登记批次主键。

        Args:
            tables_rows: 表名 → 行列表（ZIP 内 JSON）
            task_id_mapping: test_tasks old→new 映射（键为 str——JSON 信封）
            batch_id: 编排方批次 ID
        """
        clean_mapping = {int(k): int(v) for k, v in (task_id_mapping or {}).items()}
        clean_tables = {table: [r for r in (rows or []) if isinstance(r, dict)]
                        for table, rows in (tables_rows or {}).items()}
        id_mapping, inserted_pks = report_transfer_repository.import_reports(
            clean_tables, clean_mapping)
        try:
            transfer_batch_registry.record(batch_id, _OWNER, inserted_pks)
        except Exception as e:
            # DB 已提交但登记失败：返回专用前缀错误（编排层并入人工介入清单，
            # 防止孤儿行静默残留——审计问题 1③）
            log_not_emit('ERROR', _MODULE_NAME,
                         f'报告已提交但批次登记失败 batch={batch_id}: {e}',
                         category='system', exc_info=True)
            return {'success': False,
                    'message': f'已提交但批次登记失败: {e}',
                    'data': {'batch_id': batch_id,
                             'imported': sum(len(v) for v in inserted_pks.values())}}
        log_not_emit('INFO', _MODULE_NAME,
                     f'报告导入完成 batch={batch_id} rows={sum(len(v) for v in inserted_pks.values())}',
                     category='system')
        return {'success': True, 'message': '', 'data': {
            'imported': sum(len(v) for v in inserted_pks.values()),
            'id_mapping': {str(k): v for k, v in id_mapping.items()},
            'batch_id': batch_id,
        }}

    def rollback_report_import(self, batch_id: str) -> dict:
        """回滚报告导入批次（按登记主键逆依赖删除；无登记视为无可回滚内容）"""
        tables_pks = transfer_batch_registry.load_service(batch_id, _OWNER)
        deleted = report_transfer_repository.rollback_by_pks(tables_pks)
        transfer_batch_registry.remove_service(batch_id, _OWNER)
        log_not_emit('INFO', _MODULE_NAME,
                     f'报告导入回滚完成 batch={batch_id} deleted={deleted}',
                     category='system')
        return {'success': True, 'message': '', 'data': {'deleted': deleted}}


report_transfer_service = ReportTransferService()
