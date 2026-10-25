# -*- coding: utf-8 -*-
"""报告 7 表导入导出 gRPC ACL（task_service → report_service）

导出/导入/回滚报告段的防腐层，约定同 evaluation_transfer_acl。
"""
import json
import logging
from typing import Dict, List, Optional

from shared.clients.grpc_clients import get_report_config_service_stub
from shared.proto import report_service_pb2 as report_pb
from shared.utils.grpc_json import loads as _loads

logger = logging.getLogger(__name__)

# 长耗时调用：导入/回滚段 RPC 超时放宽到 10 分钟
_GRPC_TIMEOUT_SECONDS = 600


class TransferReplaceError(RuntimeError):
    """跨服务报告替换 RPC 失败（携带 HTTP 语义业务码与远端明细）"""

    def __init__(self, message: str, code: int = 500, data: Optional[dict] = None):
        super().__init__(message)
        self.code = int(code or 500)
        self.data = data or {}


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

    # ---------- 增量回导：报告原地替换（INT-1761 → D4 ReplaceReports）----------

    def replace_reports(self, tables_rows: Dict[str, List[dict]],
                        task_id: int,
                        target_report_id: Optional[int],
                        batch_id: str) -> dict:
        """把包内报告 7 表原地替换到 A 原任务的目标报告（保留 A 报告 id，D0 A5）。

        Args:
            tables_rows: 表名 → 包内行（已翻译为 A 原始 id；B 新建报告可能无 id）
            task_id: A 原始 task_id（目标报告必须属于它）
            target_report_id: 导出侧经 source_map 翻译得到的 A 报告 id；
                为空时远端按「任务下最新 task 型报告」或新建定位（A5-2）
            batch_id: 编排方批次 ID（旧值快照按它回滚）

        Returns: 远端 data {replaced_tasks, report_id, deleted_counts,
            inserted_report_ids, warnings, batch_id, rollback_available}
        Raises: TransferReplaceError（携带业务码与 data 明细）
        """
        stub = get_report_config_service_stub()
        payload = {
            'rows_by_table': tables_rows,
            'task_id': int(task_id),
            'batch_id': batch_id,
        }
        if target_report_id is not None:
            payload['target_report_id'] = int(target_report_id)
        resp = stub.ReplaceReports(
            report_pb.ReplaceReportsRequest(
                data=json.dumps(payload, ensure_ascii=False, default=str)),
            timeout=_GRPC_TIMEOUT_SECONDS)
        data = _loads(resp.data, {}) if resp.data else {}
        if not resp.success:
            code = int((data or {}).get('code') or 500) if isinstance(data, dict) else 500
            raise TransferReplaceError(f'报告替换失败: {resp.message}',
                                       code=code, data=data if isinstance(data, dict) else {})
        return data if isinstance(data, dict) else {}

    def rollback_report_replacement(self, batch_id: str) -> dict:
        """回滚报告替换批次（无快照时远端 no-op 返回 success，可无条件调用）。"""
        stub = get_report_config_service_stub()
        resp = stub.RollbackReportReplacement(
            report_pb.RollbackReportReplacementRequest(batch_id=batch_id),
            timeout=_GRPC_TIMEOUT_SECONDS)
        if not resp.success:
            raise RuntimeError(f'报告替换回滚失败: {resp.message}')
        return _loads(resp.data, {})


report_transfer_acl_repository = ReportTransferAclRepository()
