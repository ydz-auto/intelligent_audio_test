import logging

from api_gateway.infrastructure.request_adapter import request
from api_gateway.utils.response import success_response, error_response
from api_gateway.utils.error_codes import ErrorCode
from api_gateway.infrastructure.acl import TaskConfigAclRepositoryImpl
from api_gateway.schemas.task import (
    TaskCreateRequest,
    TaskCreateData,
    TaskUpdateCasesRequest,
    TaskBatchActionRequest,
    TaskUpdateCasesData,
    TaskBatchExportQuery,
    TaskValidateRequest,
    TaskValidateData,
    TaskValidateError,
)

logger = logging.getLogger(__name__)

_task_acl = TaskConfigAclRepositoryImpl()


def _parse_query_params(model_cls):
    params = {k: v[0] if isinstance(v, list) else v for k, v in request.args.to_dict().items()}
    return model_cls.model_validate(params)


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

        # INT-540：lab_ids 存在性校验（软删过滤）——不存在 → 400 校验错误
        if req.lab_ids:
            missing = TaskCommandService._validate_lab_ids_exist(req.lab_ids)
            if missing:
                return error_response(
                    f"实验室不存在或已删除: {', '.join(str(x) for x in missing)}", 400)

        data_dict = req.model_dump(by_alias=False, exclude_none=True)

        result = _task_acl.create(data_dict)

        if not result.get('success'):
            code = result.get('code', 500)
            return error_response(result.get('message', '创建任务失败'), code=code)

        new_id = (result.get('data') or {}).get('id')
        # INT-540：任务响应内联 labs（多实验室 N:M，取自 task_laboratory_relations）
        labs = TaskCommandService._fetch_task_labs(new_id)
        return success_response(
            TaskCreateData(id=new_id, labs=labs),
            result.get('message', '任务创建成功'), http_code=201)

    # INT-540：任务资源归属校验（POST /api/tasks/validate，设计文档 §5.4.4）
    @staticmethod
    def validate():
        try:
            req = TaskValidateRequest.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"请求数据验证失败: {str(e)}", 400)

        lab_ids = [int(x) for x in (req.lab_ids or [])]
        lab_set = set(lab_ids)
        errors: list = []

        # 1. lab_ids 存在性（软删过滤）
        missing = TaskCommandService._validate_lab_ids_exist(lab_ids)
        for lab_id in missing:
            errors.append(TaskValidateError(
                resource_type='laboratory', resource_id=lab_id,
                reason='实验室不存在或已删除'))

        # 2. 用例归属校验（口径③）：case 合法 ⇔ config lab_id IS NULL（通用用例）
        #    OR config lab_id IN lab_ids；不存在用例视为非法
        if req.case_ids:
            from api_gateway.infrastructure.grpc_proxies.task_data_proxies import task_data_service
            try:
                case_lab_map = task_data_service.get_testcase_lab_ids(req.case_ids)
            except Exception as e:
                logger.error(f"用例 lab_id 查询失败: {e}", exc_info=True)
                return error_response(f"用例 lab_id 查询失败: {e}", 500)
            for case_id in req.case_ids:
                cid = str(case_id)
                if cid not in case_lab_map:
                    errors.append(TaskValidateError(
                        resource_type='test_case', resource_id=cid,
                        reason='用例不存在'))
                elif case_lab_map[cid] is not None and case_lab_map[cid] not in lab_set:
                    errors.append(TaskValidateError(
                        resource_type='test_case', resource_id=cid,
                        reason='用例不属于已选实验室'))

        # 3. 设备归属校验：device 合法 ⇔ lab_id IN lab_ids（未绑定=非法）
        if req.device_ids:
            from api_gateway.infrastructure.acl import DeviceAclRepositoryImpl
            _device_acl = DeviceAclRepositoryImpl()
            for device_id in req.device_ids:
                res = _device_acl.get_one(device_id)
                if not res.get('success'):
                    errors.append(TaskValidateError(
                        resource_type='device', resource_id=device_id,
                        reason='设备不存在'))
                    continue
                dev_lab = (res.get('data') or {}).get('lab_id')
                if dev_lab not in lab_set:
                    errors.append(TaskValidateError(
                        resource_type='device', resource_id=device_id,
                        reason='设备不属于已选实验室'))

        # 4. 播放设备归属校验（可选）：有值时校验，无值跳过
        if req.playback_device_ids:
            from api_gateway.infrastructure.acl import PlaybackConfigAclRepositoryImpl
            _playback_acl = PlaybackConfigAclRepositoryImpl()
            for pdev_id in req.playback_device_ids:
                res = _playback_acl.get_one(pdev_id)
                if not res.get('success'):
                    errors.append(TaskValidateError(
                        resource_type='playback_device', resource_id=pdev_id,
                        reason='播放设备不存在'))
                    continue
                dev_lab = (res.get('data') or {}).get('lab_id')
                if dev_lab not in lab_set:
                    errors.append(TaskValidateError(
                        resource_type='playback_device', resource_id=pdev_id,
                        reason='播放设备不属于已选实验室'))

        return success_response(
            TaskValidateData(valid=not errors, errors=errors),
            '校验通过' if not errors else '资源归属校验未通过')

    @staticmethod
    def _validate_lab_ids_exist(lab_ids):
        """返回不存在的实验室 ID 列表（软删过滤，INT-540）。

        实验室为网关自有域（设计文档 §7.2），经实验室仓储直读共享库
        laboratories 表，同 INT-537 拆分① 先例。
        """
        from api_gateway.infrastructure.repositories.laboratory_repository import (
            LaboratoryRepositoryImpl,
        )
        repo = LaboratoryRepositoryImpl()
        return [
            int(lab_id) for lab_id in lab_ids
            if repo.get(int(lab_id)) is None
        ]

    @staticmethod
    def _fetch_task_labs(task_id):
        """获取任务关联实验室简报（INT-540，经 task_service GetTaskLabs RPC）。

        创建后立即查询，失败降级为空列表（不阻塞创建响应）。
        """
        if task_id is None:
            return []
        try:
            from api_gateway.infrastructure.grpc_proxies.task_data_proxies import task_data_service
            data = task_data_service.get_task_labs(task_id)
            return (data or {}).get('labs', []) or []
        except Exception:
            logger.warning("创建任务后获取 labs 失败 task_id=%s", task_id, exc_info=True)
            return []

    # 动态调整用例
    @staticmethod
    def update_cases(task_id):
        try:
            req = TaskUpdateCasesRequest.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"请求数据验证失败: {str(e)}", 400)

        data_dict = req.model_dump(by_alias=False, exclude_none=True)

        result = _task_acl.update_cases(task_id, data_dict)

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
            query = _parse_query_params(TaskBatchExportQuery)
            data_dict['format'] = query.format

        result = _task_acl.batch_action(data_dict)

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
        # INT-466：admin 删除私有任务落 PRIVATE_RESOURCE_ACCESS 审计（旁路预取，仅 admin 取数）
        from api_gateway.application.services.visibility.visibility_audit import (
            maybe_audit_private_write,
            preload_private_state,
        )
        pre_data = preload_private_state(
            lambda: _task_acl.get_task_detail(task_id).get('data') or {})

        result = _task_acl.delete(task_id)

        if not result.get('success'):
            code = result.get('code', 400)
            if code == 404:
                return error_response("未找到任务", 404)
            return error_response(result.get('message', '删除失败'), code=code)

        maybe_audit_private_write('task', task_id, 'delete', pre_data)
        return success_response(None, result.get('message', '任务已删除'))

    # 更新任务
    @staticmethod
    def update(task_id):
        json_data = request.get_json()
        if not json_data:
            return error_response("请求数据不能为空", 400)

        # INT-466：admin 修改私有任务落 PRIVATE_RESOURCE_ACCESS 审计（旁路预取，仅 admin 取数）
        from api_gateway.application.services.visibility.visibility_audit import (
            maybe_audit_private_write,
            preload_private_state,
        )
        pre_data = preload_private_state(
            lambda: _task_acl.get_task_detail(task_id).get('data') or {})

        result = _task_acl.update(task_id, json_data)

        if not result.get('success'):
            code = result.get('code', 400)
            if code == 404:
                return error_response("未找到任务", 404)
            return error_response(result.get('message', '更新失败'), code=code)

        maybe_audit_private_write('task', task_id, 'update', pre_data)
        return success_response(result.get('data'), result.get('message', '任务已更新'))
