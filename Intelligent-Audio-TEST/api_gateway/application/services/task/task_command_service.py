import logging

from api_gateway.infrastructure.request_adapter import request
from api_gateway.utils.response import success_response, error_response
from api_gateway.utils.error_codes import ErrorCode
from api_gateway.infrastructure.grpc_proxies import task_config_service
from api_gateway.schemas.common import IdData
from api_gateway.schemas.task import (
    TaskCreateRequest,
    TaskUpdateCasesRequest,
    TaskBatchActionRequest,
    TaskUpdateCasesData,
)

logger = logging.getLogger(__name__)


class TaskCommandService:
    """任务写操作 Service（CQRS Command Side）。

    按 DDD 原则，网关不再直接操作 DB，而是通过 gRPC 调用 task_service。
    保留对路由层的签名不变（静态方法 + success_response/error_response 包装）。
    保留 Pydantic schema 校验。
    """

    # 创建新任务
    @staticmethod
    def create():
        try:
            req = TaskCreateRequest.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"请求数据验证失败: {str(e)}", 400)

        data_dict = req.model_dump(by_alias=False, exclude_none=True)

        result = task_config_service.create(data_dict)

        if not result.get('success'):
            code = result.get('code', 500)
            return error_response(result.get('message', '创建任务失败'), code=code)

        new_id = (result.get('data') or {}).get('id')
        return success_response(IdData(id=new_id), result.get('message', '任务创建成功'), http_code=201)

    # 动态调整用例
    @staticmethod
    def update_cases(task_id):
        try:
            req = TaskUpdateCasesRequest.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"请求数据验证失败: {str(e)}", 400)

        data_dict = req.model_dump(by_alias=False, exclude_none=True)

        result = task_config_service.update_cases(task_id, data_dict)

        if not result.get('success'):
            code = result.get('code', 400)
            if code == 404:
                return error_response(result.get('message', '任务 ID 不存在'), code=ErrorCode.NOT_FOUND, http_code=404)
            return error_response(result.get('message', '操作失败'), code=code)

        data = result.get('data') or {}
        return success_response(
            TaskUpdateCasesData(task_id=str(data.get('task_id', '')), total_count=data.get('total_count', 0)),
            result.get('message', 'Cases updated successfully'),
        )

    # 批量操作
    @staticmethod
    def batch_action():
        try:
            req = TaskBatchActionRequest.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"请求数据验证失败: {str(e)}", 400)

        data_dict = req.model_dump(by_alias=False, exclude_none=True)
        # 导出时需要 format 参数
        if req.action == 'export':
            data_dict['format'] = request.args.get('format', 'json')

        result = task_config_service.batch_action(data_dict)

        if not result.get('success'):
            code = result.get('code', 400)
            if code == 404:
                return error_response(result.get('message', '没有可导出的数据'), code=ErrorCode.NOT_FOUND, http_code=404)
            return error_response(result.get('message', '操作失败'), code=code)

        data = result.get('data')
        # 导出文件处理
        if isinstance(data, dict) and data.get('format') in ['excel', 'pdf']:
            format_ = data['format']
            tasks_data = data.get('tasks', [])

            if format_ == 'excel':
                import pandas as pd
                import io
                from fastapi.responses import FileResponse

                df = pd.DataFrame(tasks_data)
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    df.to_excel(writer, index=False, sheet_name='Tasks')
                output.seek(0)

                from shared.utils.query_utils import now_cst
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
                from reportlab.platypus import SimpleDocTemplate, Table, TableStyle
                from reportlab.pdfbase import pdfmetrics
                from reportlab.pdfbase.ttfonts import TTFont
                import os
                import platform

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
                    font_name = "Helvetica"

                output = io.BytesIO()
                doc = SimpleDocTemplate(output, pagesize=landscape(A4))
                elements = []

                table_data = [list(tasks_data[0].keys())] if tasks_data else []
                for item in tasks_data:
                    table_data.append(list(item.values()))

                table = Table(table_data)
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

                from shared.utils.query_utils import now_cst
                return FileResponse(
                    output,
                    media_type='application/pdf',
                    headers={"Content-Disposition": f"attachment; filename=tasks_export_{now_cst().strftime('%Y%m%d%H%M%S')}.pdf"}
                )

        return success_response(data, result.get('message', '批量操作执行成功'))

    # 删除任务
    @staticmethod
    def delete(task_id):
        result = task_config_service.delete(task_id)

        if not result.get('success'):
            code = result.get('code', 400)
            if code == 404:
                return error_response("未找到任务", 404)
            return error_response(result.get('message', '删除失败'), code=code)

        return success_response(None, result.get('message', '任务已删除'))

    # 更新任务
    @staticmethod
    def update(task_id):
        json_data = request.get_json()
        if not json_data:
            return error_response("请求数据不能为空", 400)

        result = task_config_service.update(task_id, json_data)

        if not result.get('success'):
            code = result.get('code', 400)
            if code == 404:
                return error_response("未找到任务", 404)
            return error_response(result.get('message', '更新失败'), code=code)

        return success_response(result.get('data'), result.get('message', '任务已更新'))
