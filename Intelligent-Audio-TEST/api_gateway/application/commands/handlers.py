"""api_gateway 应用层 —— 命令处理器

CQRS Command Handler：执行写操作。

策略：
1. TestCase CRUD → 直接操作本地 DB（网关是 CRUD 代理）
2. Task 执行/停止 → gRPC 转发到 task_service
3. 报告生成 → gRPC 转发到 task_service，通过 SSE 推送进度
4. Audio 上传 → OSS 存储
"""
import json
import traceback
from typing import Optional, Dict, Any, List

from shared.models.database import db
from shared.models.models import TestCase, TestCaseGroup, Tag, Task, Report, ReportStatus, Audio
from shared.utils.response import success_response, error_response
from shared.utils.log_handler import log_and_emit

from api_gateway.application.commands.case_commands import (
    CreateTestCaseCommand,
    UpdateTestCaseCommand,
    DeleteTestCaseCommand,
    StartTaskCommand,
    StopTaskCommand,
    GenerateReportCommand,
    UploadAudioCommand,
    BatchImportCasesCommand,
)


class CreateTestCaseHandler:
    """创建测试用例 —— 直接操作本地 DB"""

    def handle(self, cmd: CreateTestCaseCommand) -> tuple:
        try:
            case = TestCase(
                name=cmd.name,
                description=cmd.description or '',
                group_id=cmd.group_id,
                algorithm_type=cmd.algorithm_type,
                config=cmd.config or {},
            )
            db.session.add(case)
            db.session.commit()

            if cmd.tags:
                for tag_name in cmd.tags:
                    tag = Tag.query.filter_by(name=tag_name).first()
                    if not tag:
                        tag = Tag(name=tag_name)
                        db.session.add(tag)
                        db.session.flush()
                    case.tags.append(tag)
                db.session.commit()

            log_and_emit('INFO', 'testcase', f'创建测试用例: {case.id} - {case.name}')
            return success_response({'id': case.id, 'name': case.name}, '创建成功')
        except Exception as e:
            db.session.rollback()
            log_and_emit('ERROR', 'testcase', f'创建测试用例失败: {str(e)}\n{traceback.format_exc()}')
            return error_response(f'创建失败: {str(e)}')


class UpdateTestCaseHandler:
    """更新测试用例 —— 直接操作本地 DB"""

    def handle(self, cmd: UpdateTestCaseCommand) -> tuple:
        try:
            case = db.session.get(TestCase, cmd.tc_id)
            if not case:
                return error_response('未找到指定测试用例')

            if cmd.name is not None:
                case.name = cmd.name
            if cmd.description is not None:
                case.description = cmd.description
            if cmd.group_id is not None:
                case.group_id = cmd.group_id
            if cmd.config is not None:
                case.config = cmd.config

            db.session.commit()
            log_and_emit('INFO', 'testcase', f'更新测试用例: {case.id}')
            return success_response({'id': case.id}, '更新成功')
        except Exception as e:
            db.session.rollback()
            return error_response(f'更新失败: {str(e)}')


class DeleteTestCaseHandler:
    """删除测试用例 —— 软删除"""

    def handle(self, cmd: DeleteTestCaseCommand) -> tuple:
        try:
            case = db.session.get(TestCase, cmd.tc_id)
            if not case:
                return error_response('未找到指定测试用例')

            case.deleted = True
            db.session.commit()
            log_and_emit('INFO', 'testcase', f'删除测试用例: {cmd.tc_id}')
            return success_response({'id': cmd.tc_id}, '删除成功')
        except Exception as e:
            db.session.rollback()
            return error_response(f'删除失败: {str(e)}')


class StartTaskHandler:
    """启动任务 —— gRPC 转发到 task_service"""

    def handle(self, cmd: StartTaskCommand) -> tuple:
        try:
            from shared.clients.grpc_clients import get_task_service_stub
            from shared.proto import task_service_pb2 as task_pb
            from shared.utils.grpc_json import dumps

            stub = get_task_service_stub()
            response = stub.StartTask(task_pb.StartTaskRequest(
                task_id=cmd.task_id,
            ))

            if response.success:
                return success_response(
                    json.loads(response.data) if response.data else {},
                    response.message or '任务已启动'
                )
            else:
                return error_response(response.message or '任务启动失败')
        except Exception as e:
            log_and_emit('ERROR', 'execution', f'启动任务失败 gRPC: {str(e)}\n{traceback.format_exc()}')
            return error_response(f'启动任务失败: {str(e)}')


class StopTaskHandler:
    """停止任务 —— gRPC 转发到 task_service"""

    def handle(self, cmd: StopTaskCommand) -> tuple:
        try:
            from shared.clients.grpc_clients import get_task_service_stub
            from shared.proto import task_service_pb2 as task_pb

            stub = get_task_service_stub()
            response = stub.StopTask(task_pb.StopTaskRequest(
                task_id=cmd.task_id,
            ))

            if response.success:
                return success_response({}, response.message or '任务已停止')
            else:
                return error_response(response.message or '任务停止失败')
        except Exception as e:
            return error_response(f'停止任务失败: {str(e)}')


class GenerateReportHandler:
    """生成报告 —— gRPC 转发到 task_service，SSE 推送进度"""

    def handle(self, cmd: GenerateReportCommand) -> tuple:
        try:
            from shared.clients.grpc_clients import get_task_service_stub
            from shared.proto import task_service_pb2 as task_pb
            from shared.utils.grpc_json import dumps

            stub = get_task_service_stub()
            response = stub.GenerateReport(task_pb.GenerateReportRequest(
                task_id=cmd.task_id,
                report_type=cmd.report_type,
            ))

            if response.success:
                result = json.loads(response.data) if response.data else {}
                return success_response(result, response.message or '报告生成中')
            else:
                return error_response(response.message or '报告生成失败')
        except Exception as e:
            log_and_emit('ERROR', 'report', f'生成报告失败 gRPC: {str(e)}\n{traceback.format_exc()}')
            return error_response(f'报告生成失败: {str(e)}')


class UploadAudioHandler:
    """上传音频 —— 存储到 OSS 或本地降级"""

    def handle(self, cmd: UploadAudioCommand) -> tuple:
        try:
            from shared.utils.storage import storage
            import os

            # 上传到存储（OSS 可用时走 OSS，不可用时降级到本地）
            key = cmd.file_name
            file_path = storage.save_file(cmd.file_path, 'audios', key)

            # 保存到 DB
            audio = Audio(
                file_name=cmd.file_name,
                file_path=file_path,
                md5=cmd.md5 or '',
                storage_type='storage',
            )
            db.session.add(audio)
            db.session.commit()

            log_and_emit('INFO', 'audio', f'上传音频: {audio.id} - {cmd.file_name}')
            return success_response({'id': audio.id, 'name': cmd.file_name}, '上传成功')
        except Exception as e:
            db.session.rollback()
            return error_response(f'上传失败: {str(e)}')


class BatchImportCasesHandler:
    """批量导入用例 —— 本地 DB 操作"""

    def handle(self, cmd: BatchImportCasesCommand) -> tuple:
        try:
            import pandas as pd

            df = pd.read_excel(cmd.file_path)
            imported = 0
            errors = []

            for _, row in df.iterrows():
                try:
                    case = TestCase(
                        name=str(row.get('name', '')),
                        description=str(row.get('description', '')),
                        group_id=cmd.group_id,
                        algorithm_type=str(row.get('algorithm_type', 'default')),
                    )
                    db.session.add(case)
                    imported += 1
                except Exception as row_err:
                    errors.append(f'行 {_ + 2}: {str(row_err)}')

            db.session.commit()
            log_and_emit('INFO', 'testcase', f'批量导入用例: {imported} 成功, {len(errors)} 失败')

            result = {'imported': imported, 'errors': errors}
            return success_response(result, f'导入 {imported} 条用例')
        except Exception as e:
            db.session.rollback()
            return error_response(f'导入失败: {str(e)}')
