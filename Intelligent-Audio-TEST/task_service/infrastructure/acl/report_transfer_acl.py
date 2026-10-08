# -*- coding: utf-8 -*-
"""报告 7 表导入导出 gRPC ACL（task_service → report_service）

导出/导入/回滚报告段的防腐层，约定同 evaluation_transfer_acl。
"""
import json
import logging
from typing import Dict, List

from shared.clients.grpc_clients import get_report_config_service_stub
from shared.proto import report_service_pb2 as report_pb
from shared.utils.grpc_json import loads as _loads

logger = logging.getLogger(__name__)

# 长耗时调用：导入/回滚段 RPC 超时放宽到 10 分钟
_GRPC_TIMEOUT_SECONDS = 600


class ReportTransferAclRepository:
    """report_service 报告 7 表导出/导入/回滚客户端"""

    def export_reports_for_tasks(self, task_ids: List[int]) -> dict:
        """按任务 ID 列表拉取报告 7 表只读行。返回 {表名: 行列表}。

        Raises: 失败抛出 RuntimeError。
        """
        stub = get_report_config_service_stub()
        resp = stub.ExportReportsForTasks(report_pb.ExportReportsForTasksRequest(
            task_ids=json.dumps(task_ids, ensure_ascii=False)))
        if not resp.success:
            raise RuntimeError(f'拉取报告数据失败: {resp.message}')
        return _loads(resp.data, {})

    def import_reports(self, tables_rows: Dict[str, List[dict]],
                       task_id_mapping: Dict[int, int],
                       batch_id: str) -> dict:
        """导入报告 7 表（远端单事务 + 主键冲突剥离 + 外键重映射）。

        Returns: {'imported': int, 'id_mapping': {old: new}, 'batch_id': str}
        Raises: 失败抛出 RuntimeError。
        """
        stub = get_report_config_service_stub()
        resp = stub.ImportReports(report_pb.ImportReportsRequest(
            data=json.dumps({
                'tables': tables_rows,
                'task_id_mapping': {str(k): v for k, v in task_id_mapping.items()},
                'batch_id': batch_id,
            }, ensure_ascii=False, default=str), timeout=_GRPC_TIMEOUT_SECONDS))
        if not resp.success:
            raise RuntimeError(f'报告导入失败: {resp.message}')
        return _loads(resp.data, {})

    def rollback_report_import(self, batch_id: str) -> dict:
        """回滚报告导入批次。失败抛出 RuntimeError。"""
        stub = get_report_config_service_stub()
        resp = stub.RollbackReportImport(
            report_pb.RollbackReportImportRequest(batch_id=batch_id),
            timeout=_GRPC_TIMEOUT_SECONDS)
        if not resp.success:
            raise RuntimeError(f'报告导入回滚失败: {resp.message}')
        return _loads(resp.data, {})


report_transfer_acl_repository = ReportTransferAclRepository()
