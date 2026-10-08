# -*- coding: utf-8 -*-
"""任务数据导入导出网关应用服务（INT-25）

- 导出：调 task_service RPC 生成 ZIP（共享盘 DATA_TRANSFER_TMP_DIR/export/），
  网关 FileResponse 下发下载——大 ZIP 不过 gRPC（参照 excel/pdf 导出先例）
- 导入：接收 multipart 上传，ZIP 落盘 DATA_TRANSFER_TMP_DIR/import/，
  以文件路径调 task_service 预检/执行；调用结束即删临时文件
- 进度：直读 Redis 快照兜底（实时推送走 Redis → SocketIO）
"""
import os
import time
import uuid
import zipfile

from fastapi.responses import FileResponse

from api_gateway.infrastructure.acl import DataTransferAclRepositoryImpl
from api_gateway.schemas.data_transfer import TaskDataExportRequest
from api_gateway.utils.response import error_response, success_response
from shared.infrastructure.config import BaseConfig
from shared.utils.log_handler import log_not_emit

_module = 'gateway.data_transfer'

_data_acl = DataTransferAclRepositoryImpl()

_ZIP_SUFFIX = '.zip'


def _import_tmp_dir() -> str:
    return os.path.join(BaseConfig.DATA_TRANSFER_TMP_DIR, 'import')


def _save_upload_to_tmp(upload_file) -> str:
    """把上传 ZIP 流式落盘（带大小上限），返回临时文件路径。

    Raises: ValueError 超限 / 非法 ZIP。
    """
    os.makedirs(_import_tmp_dir(), exist_ok=True)
    max_bytes = max(int(BaseConfig.DATA_TRANSFER_MAX_UPLOAD_MB), 1) * 1024 * 1024
    target = os.path.join(_import_tmp_dir(), f'upload_{uuid.uuid4().hex}{_ZIP_SUFFIX}')
    written = 0
    try:
        with open(target, 'wb') as out:
            while True:
                chunk = upload_file.file.read(1024 * 1024)
                if not chunk:
                    break
                written += len(chunk)
                if written > max_bytes:
                    raise ValueError(
                        f'ZIP 文件超过上传上限 {BaseConfig.DATA_TRANSFER_MAX_UPLOAD_MB}MB')
                out.write(chunk)
    except Exception:
        try:
            os.remove(target)
        except OSError:
            pass
        raise
    if written == 0:
        os.remove(target)
        raise ValueError('上传文件为空')
    # 内容必须是合法 ZIP（防误传其他格式进入解析层）
    if not zipfile.is_zipfile(target):
        os.remove(target)
        raise ValueError('上传文件不是合法的 ZIP 包')
    return target


def _shared_filename() -> str:
    return f"task_export_{time.strftime('%Y%m%d%H%M%S')}.zip"


class DataTransferGatewayService:
    """网关侧导出/导入编排"""

    @staticmethod
    def export(request: TaskDataExportRequest):
        """导出任务数据：返回 FileResponse（ZIP 下载）"""
        if not request.task_ids:
            return error_response('task_ids 不能为空', code=400)
        result = _data_acl.export_tasks(
            request.task_ids,
            {'include_ref_params': request.include_ref_params,
             'include_audios': request.include_audios})
        if not result.success:
            return error_response(result.message or '导出失败', code=result.code or 500)
        zip_path = (result.data or {}).get('zip_path') or ''
        if not zip_path or not os.path.isfile(zip_path):
            # 网关与 task_service 必须共享 DATA_TRANSFER_TMP_DIR（docker 需挂同一卷）
            log_not_emit('ERROR', _module,
                         f'导出 ZIP 不可见: {zip_path}（检查 DATA_TRANSFER_TMP_DIR 共享挂载）',
                         category='system')
            return error_response('导出文件不可访问（网关与任务服务未共享临时目录）', code=500)
        return FileResponse(
            zip_path,
            media_type='application/zip',
            filename=_shared_filename(),
        )

    @staticmethod
    def preview_import(upload_file):
        """导入预检：保存上传 ZIP → 调 task_service → 删临时文件"""
        tmp_path = None
        try:
            try:
                tmp_path = _save_upload_to_tmp(upload_file)
            except ValueError as e:
                return error_response(str(e), code=400)
            result = _data_acl.preview_import(tmp_path)
            if not result.success:
                return error_response(result.message or '预检失败', code=result.code or 500)
            return success_response(result.data, message='预检完成')
        except Exception as e:
            log_not_emit('ERROR', _module, f'导入预检异常: {e}', category='system', exc_info=True)
            return error_response(f'导入预检异常: {e}', code=500)
        finally:
            if tmp_path:
                _remove_tmp(tmp_path)

    @staticmethod
    def execute_import(upload_file):
        """执行导入：保存上传 ZIP → 调 task_service（长耗时）→ 删临时文件

        实时进度走 SocketIO import_progress 事件；本接口回包携带最终统计。
        """
        tmp_path = None
        try:
            try:
                tmp_path = _save_upload_to_tmp(upload_file)
            except ValueError as e:
                return error_response(str(e), code=400)
            result = _data_acl.execute_import(tmp_path)
            if not result.success:
                data = result.data if isinstance(result.data, dict) else None
                return error_response(result.message or '导入失败',
                                      code=result.code or 500,
                                      http_code=500, detail=data)
            return success_response(result.data, message=result.message or '导入成功')
        except Exception as e:
            log_not_emit('ERROR', _module, f'执行导入异常: {e}', category='system', exc_info=True)
            return error_response(f'执行导入异常: {e}', code=500)
        finally:
            if tmp_path:
                _remove_tmp(tmp_path)

    @staticmethod
    def import_progress():
        """最近一次导入进度快照（GET /import/progress 兜底）"""
        result = _data_acl.get_progress_snapshot()
        if not result.success:
            return error_response(result.message or '读取进度失败', code=result.code or 500)
        return success_response(result.data)


def _remove_tmp(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        log_not_emit('WARNING', _module, f'删除导入临时文件失败: {path}', category='system')
