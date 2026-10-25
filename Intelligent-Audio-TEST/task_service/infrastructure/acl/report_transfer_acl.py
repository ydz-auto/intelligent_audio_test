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
        # timeout 是 gRPC 调用的关键字参数，不是 Request 消息字段（缺陷 4 修复）
        resp = stub.ImportReports(
            report_pb.ImportReportsRequest(data=json.dumps({
                'tables': tables_rows,
                'task_id_mapping': {str(k): v for k, v in task_id_mapping.items()},
                'batch_id': batch_id,
            }, ensure_ascii=False, default=str)),
            timeout=_GRPC_TIMEOUT_SECONDS)
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


    def export_report_package(self, task_ids: List[int], report_ids: List[int],
                              doc_version_scope: str) -> dict:
        """导出报告包数据段（报告 7 表 + Studio 三表，INT-1764 D6）。

        Returns: {'tables', 'studio', 'reportIds', 'taskIds', 'entities', 'counts'}
        Raises: 失败抛出 RuntimeError。
        """
        stub = get_report_config_service_stub()
        resp = stub.ExportReportPackage(report_pb.ExportReportPackageRequest(
            data=json.dumps({'task_ids': task_ids, 'report_ids': report_ids,
                             'doc_version_scope': doc_version_scope},
                            ensure_ascii=False, default=str)),
            timeout=_GRPC_TIMEOUT_SECONDS)
        if not resp.success:
            raise RuntimeError(f'导出报告包失败: {resp.message}')
        return _loads(resp.data, {})

    def import_report_package(self, task_id: int, tables: Dict[str, list],
                              studio: Dict[str, list], batch_id: str,
                              doc_version_scope: str,
                              target_report_id=None) -> dict:
        """导入报告包（3a 原地替换 + 3b/3c 拓扑序落库）。失败抛 RuntimeError。

        Returns: 回执 {reportId, documentIdMapping, imported, warnings, ...}
        """
        stub = get_report_config_service_stub()
        payload = {
            'task_id': task_id,
            'tables': tables or {},
            'studio': studio or {},
            'batch_id': batch_id,
            'doc_version_scope': doc_version_scope,
        }
        if target_report_id is not None:
            payload['target_report_id'] = target_report_id
        resp = stub.ImportReportPackage(report_pb.ImportReportPackageRequest(
            data=json.dumps(payload, ensure_ascii=False, default=str)),
            timeout=_GRPC_TIMEOUT_SECONDS)
        if not resp.success:
            data = _loads(resp.data, {}) or {}
            raise ReportPackageImportError(
                resp.message or '导入报告包失败',
                code=int(getattr(resp, 'code', 0) or data.get('code') or 500),
                data=data)
        return _loads(resp.data, {}) or {}


class ReportPackageImportError(RuntimeError):
    """报告包导入失败（带业务码与 data 明细，供编排层映射 HTTP 状态）"""

    def __init__(self, message: str, code: int = 500, data: Dict = None):
        super().__init__(message)
        self.code = code
        self.data = data or {}


report_transfer_acl_repository = ReportTransferAclRepository()
