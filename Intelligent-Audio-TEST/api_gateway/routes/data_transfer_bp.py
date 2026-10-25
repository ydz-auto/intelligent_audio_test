# -*- coding: utf-8 -*-
"""任务数据导入导出路由（INT-25，前缀 /api/v1/data-transfer，app.py 注册）

- POST /export            导出任务数据 ZIP（权限 task:export）
- POST /export-incremental 增量导出（链路 2，权限 task:export，INT-1761）
- POST /import/preview    导入预检（权限 task:import，multipart）
- POST /import            执行导入（权限 task:import，multipart，长耗时）
- POST /import-incremental 增量导入（链路 2，权限 task:import，multipart，INT-1761）
- GET  /import/progress   导入进度快照（权限 task:import）
"""
from typing import Optional

from fastapi import APIRouter, Form, UploadFile

from api_gateway.application.services.auth.dependencies import require_permission
from api_gateway.application.services.transfer.data_transfer_service import (
    DataTransferGatewayService,
)
from api_gateway.routes._response import to_response
from api_gateway.schemas.data_transfer import (
    ReportPackageExportRequest,
    TaskDataExportRequest,
    TaskDataIncrementalExportRequest,
)
from shared.constants.data_transfer import DEFAULT_TRANSFER_INTENT

router = APIRouter()


def _import_options(require_case_consistency: Optional[bool], intent: str) -> dict:
    """导入请求级选项（INT-1759）：表单缺省 = 全局策略（migrate + 全局开关）"""
    return {
        'require_case_consistency': require_case_consistency,
        'intent': (intent or DEFAULT_TRANSFER_INTENT).strip().lower(),
    }


def _resolve_require_case_consistency(snake_case: Optional[bool],
                                     camel_case: Optional[bool]) -> Optional[bool]:
    """请求级放宽开关的两种拼写归一（INT-1759 返工）

    契约字段名是 `requireCaseConsistency`（D0 §A10-1），既有表单口径是 snake_case；
    multipart 没有 JSON body 的 alias 合并机制，故双参数取非 None 者——契约拼写优先，
    避免前端按文档传 camelCase 时被静默丢弃。
    """
    return camel_case if camel_case is not None else snake_case


@router.post('/export')
def export_tasks(request: TaskDataExportRequest,
                 _: None = require_permission('task:export')):
    """导出任务数据为 ZIP 文件流（task_export_<timestamp>.zip）"""
    result = DataTransferGatewayService.export(request)
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result  # FileResponse 直接透出


@router.post('/export-incremental')
def export_incremental(request: TaskDataIncrementalExportRequest,
                       _: None = require_permission('task:export')):
    """增量导出（链路 2）：B 侧新评估 + 新报告子集，id 经 source_map 翻译回 A。

    请求：{taskIds: [int], include: ['dimensions','reports']}
    存在未映射结果行（B 侧重执行产生）→ HTTP 409 + `data.unmappedResultIds`。
    """
    result = DataTransferGatewayService.export_incremental(request)
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result  # FileResponse 直接透出


@router.post('/import/preview')
def import_preview(file: UploadFile,
                   require_case_consistency: Optional[bool] = Form(None),
                   require_case_consistency_camel: Optional[bool] = Form(
                       None, alias='requireCaseConsistency'),
                   intent: str = Form(DEFAULT_TRANSFER_INTENT),
                   _: None = require_permission('task:import')):
    """导入预检：manifest 摘要 + 统计 + ID 冲突 + 缺失引用 warning + 用例一致性回执

    `requireCaseConsistency` / `require_case_consistency`（同义）只能放宽到 false；
    `intent=restore` 默认不做用例硬校验。
    """
    result = DataTransferGatewayService.preview_import(
        file, _import_options(
            _resolve_require_case_consistency(require_case_consistency,
                                              require_case_consistency_camel), intent))
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result


@router.post('/import')
def execute_import(file: UploadFile,
                   require_case_consistency: Optional[bool] = Form(None),
                   require_case_consistency_camel: Optional[bool] = Form(
                       None, alias='requireCaseConsistency'),
                   intent: str = Form(DEFAULT_TRANSFER_INTENT),
                   _: None = require_permission('task:import')):
    """执行导入（分段提交 + 补偿回滚；长耗时，实时进度走 SocketIO import_progress）

    用例一致性不满足时返回 HTTP 422 + `data.missingCaseIds/missingCount`，不写任何数据。
    `requireCaseConsistency` / `require_case_consistency`（同义）只能放宽到 false。
    """
    result = DataTransferGatewayService.execute_import(
        file, _import_options(
            _resolve_require_case_consistency(require_case_consistency,
                                              require_case_consistency_camel), intent))
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result


@router.post('/import-incremental')
def import_incremental(file: UploadFile,
                       _: None = require_permission('task:import')):
    """增量导入（链路 2）：合并回 A 原任务（维度覆盖集 + 报告原地替换）

    multipart ZIP（manifest 1.1 + sourceTask）。失败码透传：
    400（包结构/多任务/id 不一致）、403（无权写任务）、404（源任务不存在）、
    409（指纹不符 / 包内 id 不存在）、500（补偿失败，data.compensationErrors）。
    """
    result = DataTransferGatewayService.import_incremental(file, {})
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


@router.post('/report/export')
def export_report_package(request: ReportPackageExportRequest,
                          _: None = require_permission('task:export')):
    """导出报告包（链路 3a 平台报告 + 3b/3c Studio 文档，INT-1764 D6）

    请求体：`{taskId?, reportIds?, docVersionScope?: 'full'|'latest'}`（camelCase，
    也接受 snake_case）；返回 ZIP 文件流。
    """
    result = DataTransferGatewayService.export_report_package(request)
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result  # FileResponse 直接透出


@router.post('/report/import')
def import_report_package(file: UploadFile,
                          target_report_id: Optional[int] = Form(None),
                          target_report_id_camel: Optional[int] = Form(
                              None, alias='targetReportId'),
                          batch_id: Optional[str] = Form(None),
                          _: None = require_permission('task:import')):
    """导入报告包（multipart ZIP，权限 task:import，INT-1764 D6）

    平台报告按 `manifest.sourceTask.id` 匹配 A 原任务原地替换，Studio 文档按
    拓扑序落库；源缺失 / 图表失联等降级全部写进回执 `warnings`。
    """
    options = {}
    resolved_target = (target_report_id_camel if target_report_id_camel is not None
                       else target_report_id)
    if resolved_target:
        options['target_report_id'] = resolved_target
    if batch_id:
        options['batch_id'] = batch_id
    result = DataTransferGatewayService.import_report_package(file, options)
    if isinstance(result, tuple) and len(result) == 2:
        return to_response(result)
    return result
