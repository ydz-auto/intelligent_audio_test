import json
import logging
from datetime import datetime, timezone, timedelta

from api_gateway.infrastructure.request_adapter import request
from shared.models.models import (
    Task, Tag, TaskCase, TaskDevice, TaskAPI, TestCase, TestResult,
    TestResultDimension, Log, Dimension,
)
from shared.models.database import db
from shared.utils.response import success_response, error_response, convert_keys_to_camel
from shared.utils.error_codes import ErrorCode
from shared.utils.log_handler import log_not_emit
# 跨服务调用：通过 gRPC ExecutionService 调用任务执行引擎
from api_gateway.infrastructure.grpc_proxies import (
    execution_engine, _ReevaluationExecutorProxy,
)
from shared.utils.result_data_store import load_full_result_data
from shared.infrastructure.storage import storage
from api_gateway.schemas.common import IdData, TaskStatusData
from api_gateway.schemas.task import (
    TaskApiBrief,
    TaskCaseBrief,
    TaskDetailData,
    TaskDeviceBrief,
    TaskListData,
    TaskListItem,
    TaskProgressCurrentCase,
    TaskProgressData,
    TaskReportItem,
    TaskReportsData,
    TaskStartData,
    TaskStatsData,
    TaskUpdateCasesData,
    TaskCreateRequest,
    TaskControlRequest,
    TaskUpdateCasesRequest,
    TaskBatchActionRequest,
    TaskMergeRequest,
)
from shared.utils.query_utils import now_cst
from sqlalchemy import and_, or_

logger = logging.getLogger(__name__)


class TaskCommandService:
    """任务写操作 Service（CQRS Command Side）。

    承载 TaskController 中 CRUD 与批量操作方法，保持原有逻辑不变。
    """

    # 创建新任务
    @staticmethod
    def create():
        req = TaskCreateRequest.model_validate(request.get_json())

        try:
            case_ids = req.case_ids or []
            device_ids = req.device_ids or []
            api_ids = req.api_ids or []
            tags = req.tags or []

            new_task = Task(
                name=req.name,
                description=req.description,
                type=req.type,
                status='pending',
                config=req.config or {},
                total_cases=len(case_ids),
                created_by=req.created_by
            )
            db.session.add(new_task)
            db.session.flush() # 获取 ID

            # 建立用例关联
            for case_id in case_ids:
                task_case = TaskCase(
                    task_id=new_task.id,
                    test_case_id=case_id,
                    status='pending',
                    execution_status='pending',
                    evaluation_status='pending'
                )
                db.session.add(task_case)

            # 建立设备关联
            for device_id in device_ids:
                task_device = TaskDevice(task_id=new_task.id, device_id=device_id)
                db.session.add(task_device)

            # 建立 API 关联
            for api_id in api_ids:
                task_api = TaskAPI(task_id=new_task.id, api_id=api_id)
                db.session.add(task_api)

            # 处理标签
            for tag_name in tags:
                tag = Tag.query.filter_by(name=tag_name).first()
                if not tag:
                    tag = Tag(name=tag_name)
                    db.session.add(tag)
                new_task.tags.append(tag)

            db.session.commit()

            from shared.utils.report.stats_cache import refresh_stats_cache
            refresh_stats_cache()

            return success_response(IdData(id=new_task.id), "任务创建成功", http_code=201)
        except Exception as e:
            db.session.rollback()
            return error_response(str(e), code=ErrorCode.DATABASE_ERROR)

    # 动态调整用例
    @staticmethod
    def update_cases(task_id):
        task = db.session.get(Task, task_id)
        if not task:
            return error_response("任务 ID 不存在", code=ErrorCode.NOT_FOUND, http_code=404)

        req = TaskUpdateCasesRequest.model_validate(request.get_json())

        action = req.action
        case_ids = req.case_ids

        try:
            if action == 'add':
                has_running_case = TaskCase.query.filter_by(task_id=task_id, execution_status='running').first() is not None
                if task.status in ['queued', 'running', 'paused'] or has_running_case:
                    return error_response("任务执行中不允许新增用例", code=ErrorCode.OPERATION_FAILED, http_code=400)

            if action == 'add':
                for cid in case_ids:
                    if not TaskCase.query.filter_by(task_id=task_id, test_case_id=cid).first():
                        db.session.add(TaskCase(
                            task_id=task_id,
                            test_case_id=cid,
                            status='pending',
                            execution_status='pending',
                            evaluation_status='pending'
                        ))
            elif action == 'remove':
                TaskCase.query.filter(
                    TaskCase.task_id == task_id,
                    TaskCase.test_case_id.in_(case_ids),
                    TaskCase.execution_status == 'pending'
                ).delete(synchronize_session=False)

            # 重新计算总数
            task.total_cases = TaskCase.query.filter_by(task_id=task_id).count()
            task.updated_at = now_cst()
            db.session.commit()
            return success_response(
                TaskUpdateCasesData(task_id=str(task.id), total_count=task.total_cases),
                "Cases updated successfully",
            )
        except Exception as e:
            db.session.rollback()
            return error_response(str(e), code=ErrorCode.DATABASE_ERROR)

    # 批量操作
    @staticmethod
    def batch_action():
        req = TaskBatchActionRequest.model_validate(request.get_json())

        action = req.action
        task_ids = req.task_ids

        try:
            if action == 'delete':
                app = None

                # 获取所有待删除任务，包括运行中的
                tasks = Task.query.filter(Task.id.in_(task_ids)).all()
                deleted_count = 0

                for t in tasks:
                    # 1. 如果任务正在运行，先停止任务
                    if t.status in ['running', 'paused']:
                        execution_engine.control_task(app, t.id, 'stop')

                    # 2. 从任务队列中移除任务
                    execution_engine.remove_from_queue(t.id)

                    # 3. 标记任务为已删除
                    t.deleted = True
                    deleted_count += 1

                db.session.commit()
                return success_response(None, f"成功删除 {deleted_count} 个任务")
            elif action == 'export':
                # 导出逻辑：支持 Excel 和 JSON
                format_ = request.args.get('format', 'json')
                tasks = Task.query.filter(Task.id.in_(task_ids)).all()

                export_data = []
                for t in tasks:
                    if format_ in ['excel', 'pdf']:
                        export_data.append({
                            "ID": t.id,
                            "任务名称": t.name,
                            "类型": t.type,
                            "状态": t.status,
                            "总用例数": t.total_cases,
                            "完成数": t.completed_cases,
                            "失败数": t.failed_cases,
                            "开始时间": t.started_at.isoformat() if t.started_at else "",
                            "完成时间": t.completed_at.isoformat() if t.completed_at else "",
                            "创建时间": t.created_at.isoformat()
                        })
                    else:
                        export_data.append({
                            "id": t.id,
                            "name": t.name,
                            "type": t.type,
                            "status": t.status,
                            "total_cases": t.total_cases,
                            "completed_cases": t.completed_cases,
                            "failed_cases": t.failed_cases,
                            "started_at": t.started_at.isoformat() if t.started_at else "",
                            "completed_at": t.completed_at.isoformat() if t.completed_at else "",
                            "created_at": t.created_at.isoformat()
                        })

                if not export_data:
                    return error_response("没有可导出的数据", code=ErrorCode.NOT_FOUND, http_code=404)

                if format_ == 'excel':
                    import pandas as pd
                    import io
                    from fastapi.responses import FileResponse

                    df = pd.DataFrame(export_data)
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine='openpyxl') as writer:
                        df.to_excel(writer, index=False, sheet_name='Tasks')
                    output.seek(0)

                    return FileResponse(
                        output,
                        media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                        headers={"Content-Disposition": f"attachment; filename=tasks_export_{now_cst().strftime('%Y%m%d%H%M%S')}.xlsx"}
                    )

                if format_ == 'pdf':
                    import io
                    from fastapi.responses import FileResponse
                    from reportlab.lib import colors
                    from reportlab.lib.pagesizes import A4, landscape
                    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
                    from reportlab.lib.styles import getSampleStyleSheet
                    from reportlab.pdfbase import pdfmetrics
                    from reportlab.pdfbase.ttfonts import TTFont
                    import os
                    import platform

                    # 注册中文字体 (跨平台候选路径)
                    font_candidates = (
                        ['C:\\Windows\\Fonts\\msyh.ttc', 'C:\\Windows\\Fonts\\simsun.ttc']
                        if platform.system() == 'Windows'
                        else ['/usr/share/fonts/truetype/wqy/wqy-microhei.ttc',
                              '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc']
                    )
                    font_path = next((p for p in font_candidates if os.path.exists(p)), None)

                    font_name = "CustomFont"
                    if font_path and os.path.exists(font_path):
                        pdfmetrics.registerFont(TTFont(font_name, font_path))
                    else:
                        font_name = "Helvetica" # 回退

                    output = io.BytesIO()
                    doc = SimpleDocTemplate(output, pagesize=landscape(A4))
                    elements = []

                    # 表格数据
                    data = [list(export_data[0].keys())] # 表头
                    for item in export_data:
                        data.append(list(item.values()))

                    # 创建表格
                    table = Table(data)
                    style = TableStyle([
                        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                        ('FONTNAME', (0, 0), (-1, -1), font_name),
                        ('FONTSIZE', (0, 0), (-1, 0), 12),
                        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                        ('GRID', (0, 0), (-1, -1), 1, colors.black)
                    ])
                    table.setStyle(style)
                    elements.append(table)

                    doc.build(elements)
                    output.seek(0)

                    return FileResponse(
                        output,
                        media_type='application/pdf',
                        headers={"Content-Disposition": f"attachment; filename=tasks_export_{now_cst().strftime('%Y%m%d%H%M%S')}.pdf"}
                    )

                return success_response(export_data, "数据准备就绪")

            db.session.commit()
            return success_response(None, f"批量操作 {action} 执行成功")
        except Exception as e:
            db.session.rollback()
            return error_response(str(e))

    # 删除任务
    @staticmethod
    def delete(task_id):
        task = Task.query.filter_by(id=task_id, deleted=False).first()
        if not task:
            return error_response("未找到任务", 404)

        try:
            app = None

            if task.status in ['running', 'paused']:
                # 跨服务调用：通过 gRPC ExecutionService 停止任务
                execution_engine.control_task(app, task_id, 'stop')

            # 2. 从任务队列中移除任务
            execution_engine.remove_from_queue(task_id)

            # 3. 标记任务为已删除
            task.deleted = True
            db.session.commit()

            from shared.utils.report.stats_cache import refresh_stats_cache
            refresh_stats_cache()

            return success_response(None, "任务已删除")
        except Exception as e:
            db.session.rollback()
            return error_response(str(e))

    @staticmethod
    def update(task_id):
        task = Task.query.filter_by(id=task_id, deleted=False).first()
        if not task:
            return error_response("未找到任务", 404)

        try:
            data = request.get_json()
            if not data:
                return error_response("请求数据不能为空", 400)

            if 'name' in data and data['name']:
                task.name = data['name']
            if 'description' in data:
                task.description = data['description']

            db.session.commit()
            return success_response({"id": task.id, "name": task.name}, "任务已更新")
        except Exception as e:
            db.session.rollback()
            return error_response(str(e))
