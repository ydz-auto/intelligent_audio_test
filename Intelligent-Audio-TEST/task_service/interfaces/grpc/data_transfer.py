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
            from task_service.application.commands.task_commands import PreviewImportCommand
            from task_service.application.handlers.command_handlers import task_command_handler
            return self._resp(task_command_handler.handle_preview_import(
                PreviewImportCommand(zip_path=request.zip_path)))
        except Exception as e:
            logger.exception('PreviewImport failed')
            return task_pb.TaskConfigResponse(success=False, message=str(e), data='')

    def ExecuteImport(self, request, context=None):
        # 长耗时 RPC：客户端超时需放宽（网关代理 timeout=3600s）；
        # 进度经 Redis 频道 import_progress 推送，不依赖本调用回包
        try:
            from task_service.application.commands.task_commands import ExecuteImportCommand
            from task_service.application.handlers.command_handlers import task_command_handler
            return self._resp(task_command_handler.handle_execute_import(
                ExecuteImportCommand(zip_path=request.zip_path)))
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
