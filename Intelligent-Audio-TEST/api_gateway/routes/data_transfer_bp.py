# -*- coding: utf-8 -*-
"""任务数据导入导出路由（INT-25，前缀 /api/v1/data-transfer，app.py 注册）

- POST /export            导出任务数据 ZIP（权限 task:export）
- POST /import/preview    导入预检（权限 task:import，multipart）
- POST /import            执行导入（权限 task:import，multipart，长耗时）
- GET  /import/progress   导入进度快照（权限 task:import）
"""
from typing import Optional

from fastapi import APIRouter, Form, UploadFile

from api_gateway.application.services.auth.dependencies import require_permission
from api_gateway.application.services.transfer.data_transfer_service import (
    DataTransferGatewayService,
)
from api_gateway.routes._response import to_response
from api_gateway.schemas.data_transfer import TaskDataExportRequest
from shared.constants.data_transfer import DEFAULT_TRANSFER_INTENT

router = APIRouter()


def _import_options(require_case_consistency: Optional[bool], intent: str) -> dict:
    """导入请求级选项（INT-1759）：表单缺省 = 全局策略（migrate + 全局开关）"""
    return {
        'require_case_consistency': require_case_consistency,
        'intent': (intent or DEFAULT_TRANSFER_INTENT).strip().lower(),
    }


@router.post('/export')
def export_tasks(request: TaskDataExportRequest,
                 _: None = require_permission('task:export')):
    """导出任务数据为 ZIP 文件流（task_export_<timestamp>.zip）"""
    result = DataTransferGatewayService.export(request)
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result  # FileResponse 直接透出


@router.post('/import/preview')
def import_preview(file: UploadFile,
                   require_case_consistency: Optional[bool] = Form(None),
                   intent: str = Form(DEFAULT_TRANSFER_INTENT),
                   _: None = require_permission('task:import')):
    """导入预检：manifest 摘要 + 统计 + ID 冲突 + 缺失引用 warning + 用例一致性回执

    `require_case_consistency` 只能放宽到 false；`intent=restore` 默认不做用例硬校验。
    """
    result = DataTransferGatewayService.preview_import(
        file, _import_options(require_case_consistency, intent))
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result


@router.post('/import')
def execute_import(file: UploadFile,
                   require_case_consistency: Optional[bool] = Form(None),
                   intent: str = Form(DEFAULT_TRANSFER_INTENT),
                   _: None = require_permission('task:import')):
    """执行导入（分段提交 + 补偿回滚；长耗时，实时进度走 SocketIO import_progress）

    用例一致性不满足时返回 HTTP 422 + `data.missingCaseIds/missingCount`，不写任何数据。
    """
    result = DataTransferGatewayService.execute_import(
        file, _import_options(require_case_consistency, intent))
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result


@router.get('/import/progress')
def import_progress(_: None = require_permission('task:import')):
    """最近一次导入进度快照（实时进度走 SocketIO，本接口兜底）"""
    result = DataTransferGatewayService.import_progress()
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result
