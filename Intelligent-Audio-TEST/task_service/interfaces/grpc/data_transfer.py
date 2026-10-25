# -*- coding: utf-8 -*-
"""DataTransferServicer —— 任务数据导入导出 gRPC 服务（INT-25）

仅做 protocol 适配：JSON 信封 ↔ 应用服务 dict 返回值。
所有 DB / 文件 / 跨服务编排均在 application 层（data_transfer_*_service）。
"""
import logging

from shared.proto import task_service_pb2 as task_pb
from shared.proto import task_service_pb2_grpc as task_grpc
from shared.utils.grpc_json import loads as _loads, dumps as _dumps

logger = logging.getLogger(__name__)


class DataTransferServiceServicer(task_grpc.DataTransferServiceServicer):
    """任务数据导入导出 servicer"""

    @staticmethod
    def _resp(result):
        data = result.get('data')
        return task_pb.TaskConfigResponse(
            success=result.get('success', False),
            message=result.get('message', ''),
            data=_dumps(data) if data is not None else '',
            # INT-1759：业务码走 proto 字段（不再只靠 data JSON 折码），
            # 网关据此映射 HTTP 状态（422 用例一致性拒绝等）
            code=int(result.get('code') or 0),
        )

    def ExportTasks(self, request, context=None):
        try:
            data = _loads(request.data, {})
            from task_service.application.commands.task_commands import ExportTasksCommand
            from task_service.application.handlers.command_handlers import task_command_handler
            return self._resp(task_command_handler.handle_export_tasks(
                ExportTasksCommand(task_ids=data.get('task_ids') or [],
                                   options=data.get('options') or {})))
        except Exception as e:
            logger.exception('ExportTasks failed')
            return task_pb.TaskConfigResponse(success=False, message=str(e), data='')

    def PreviewImport(self, request, context=None):
        try:
            options = _loads(request.data, {}) or {}
            from task_service.application.commands.task_commands import PreviewImportCommand
            from task_service.application.handlers.command_handlers import task_command_handler
            return self._resp(task_command_handler.handle_preview_import(
                PreviewImportCommand(zip_path=request.zip_path, options=options)))
        except Exception as e:
            logger.exception('PreviewImport failed')
            return task_pb.TaskConfigResponse(success=False, message=str(e), data='')

    def ExecuteImport(self, request, context=None):
        # 长耗时 RPC：客户端超时需放宽（网关代理 timeout=3600s）；
        # 进度经 Redis 频道 import_progress 推送，不依赖本调用回包
        try:
            options = _loads(request.data, {}) or {}
            from task_service.application.commands.task_commands import ExecuteImportCommand
            from task_service.application.handlers.command_handlers import task_command_handler
            return self._resp(task_command_handler.handle_execute_import(
                ExecuteImportCommand(zip_path=request.zip_path, options=options)))
        except Exception as e:
            logger.exception('ExecuteImport failed')
            return task_pb.TaskConfigResponse(success=False, message=str(e), data='')

    def RollbackImport(self, request, context=None):
        try:
            from task_service.application.commands.task_commands import RollbackImportCommand
            from task_service.application.handlers.command_handlers import task_command_handler
            return self._resp(task_command_handler.handle_rollback_import(
                RollbackImportCommand(batch_id=request.batch_id)))
        except Exception as e:
            logger.exception('RollbackImport failed')
            return task_pb.TaskConfigResponse(success=False, message=str(e), data='')

    # ==================== 报告包（INT-1764 D6：链路 3a + 3b/3c） ====================

    def ExportReportPackage(self, request, context=None):
        """导出报告包（ZIP 落共享盘，网关 FileResponse 下发）。"""
        try:
            data = _loads(request.data, {}) or {}
            from task_service.application.commands.task_commands import (
                ExportReportPackageCommand,
            )
            from task_service.application.handlers.command_handlers import task_command_handler
            return self._resp(task_command_handler.handle_export_report_package(
                ExportReportPackageCommand(
                    task_ids=data.get('task_ids') or data.get('taskIds') or [],
                    report_ids=data.get('report_ids') or data.get('reportIds') or [],
                    doc_version_scope=(data.get('doc_version_scope')
                                       or data.get('docVersionScope') or ''))))
        except Exception as e:
            logger.exception('ExportReportPackage failed')
            return task_pb.TaskConfigResponse(success=False, message=str(e), data='')

    def ImportReportPackage(self, request, context=None):
        """导入报告包（3a 原地替换 + 3b/3c 拓扑序落库；长耗时调用需放宽超时）。"""
        try:
            options = _loads(request.data, {}) or {}
            from task_service.application.commands.task_commands import (
                ImportReportPackageCommand,
            )
            from task_service.application.handlers.command_handlers import task_command_handler
            return self._resp(task_command_handler.handle_import_report_package(
                ImportReportPackageCommand(zip_path=request.zip_path, options=options)))
        except Exception as e:
            logger.exception('ImportReportPackage failed')
            return task_pb.TaskConfigResponse(success=False, message=str(e), data='')
