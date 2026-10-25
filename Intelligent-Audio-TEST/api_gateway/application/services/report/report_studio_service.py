# -*- coding: utf-8 -*-
"""Report Studio BFF Service（api_gateway Application 层）

职责：参数校验 → gRPC 调用 report_service.ReportStudioService → 响应组装。
不含业务逻辑（乐观锁/权限/版本快照由 report_service 领域层强制）。
"""
import base64
import logging
import os
from urllib.parse import quote

from api_gateway.infrastructure.request_adapter import request
from api_gateway.infrastructure.oss.storage import ReportOSSStorage
from api_gateway.utils.response import success_response, error_response
from api_gateway.infrastructure.grpc_proxies.report_studio_proxies import (
    report_studio_service,
)
from shared.infrastructure.config import BaseConfig
from shared.models.common_enums import StudioUploadFormat
from shared.proto import report_service_pb2 as report_pb
from shared.utils.grpc_json import loads as _loads, dumps as _dumps

logger = logging.getLogger(__name__)

# 上传件格式 → (扩展名, 允许的 Content-Type)
# 浏览器 / curl / 脚本对同一扩展名的 Content-Type 上报不一致（md 常见 text/plain、
# pptx 常见 application/zip），因此按「格式允许集合 + 通用兜底」双校验，而不是
# 只认单一 MIME；扩展名与 format 入参必须一致（不匹配 415）。
_STUDIO_UPLOAD_TYPES = {
    'md': ('text/markdown', 'text/x-markdown', 'text/plain', 'application/octet-stream'),
    'html': ('text/html', 'application/xhtml+xml', 'application/octet-stream'),
    'pptx': ('application/vnd.openxmlformats-officedocument.presentationml.presentation',
             'application/zip', 'application/octet-stream'),
}
_STUDIO_DOWNLOAD_MIME = {
    'md': 'text/markdown',
    'html': 'text/html',
    'pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
}
# 上传件永不作为同源文档直接返回（D0 A11-3）：附件下载 + nosniff + 沙箱 CSP
_STUDIO_DOWNLOAD_HEADERS = {
    'X-Content-Type-Options': 'nosniff',
    'Content-Security-Policy': "sandbox; default-src 'none'; img-src data:; "
                               "style-src 'unsafe-inline'",
}


def _parse_json_body(default=None):
    """读取请求体 JSON（FastAPI request_adapter 兼容）。"""
    try:
        body = request.get_json()
    except Exception:
        body = None
    return body if isinstance(body, dict) else (default or {})


def _grpc_max_message_bytes() -> int:
    """gRPC 单条消息上限（与共享客户端 channel / report_service 服务端同口径）。"""
    return max(int(BaseConfig.GRPC_MAX_MESSAGE_MB), 1) * 1024 * 1024


def _call(stub_method, payload: dict):
    """统一 gRPC 调用 + 响应映射。

    Report Studio 响应带 HTTP 语义业务码（StudioResponse.code：
    404/403/409/400/500，0 = 200），网关据此还原 HTTP 状态。

    序列化后超过 gRPC 单条消息上限先回 413：上传上限按文件字节数把关，契约里
    还有 OSS 引用只记元数据的小体积路径，但 markdown 正文是整段进的，JSON 转义
    后可能再膨胀；不预判的话超限请求在传输层被 RESOURCE_EXHAUSTED 拒收，网关
    无从映射 → HTTP 500（INT-1763 §6.2）。
    """
    serialized = _dumps(payload)
    if len(serialized.encode('utf-8')) > _grpc_max_message_bytes():
        return error_response(
            f'请求体超过网关处理上限 {BaseConfig.GRPC_MAX_MESSAGE_MB}MB', http_code=413)
    resp = stub_method(report_pb.StudioDocumentRequest(data=serialized))
    data = _loads(resp.data, {}) or {}
    if resp.success:
        return success_response(data)
    return error_response(resp.message or '操作失败', http_code=resp.code or 400, detail=data)


class _UploadEmpty(ValueError):
    """上传文件为空。"""


class _UploadTooLarge(ValueError):
    """上传文件超过 REPORT_STUDIO_UPLOAD_MAX_MB。"""


def _read_upload(file, max_bytes: int) -> bytes:
    """流式读取上传件并强制大小上限（边读边计数，不整体驻留超限文件）。"""
    chunks = []
    total = 0
    while True:
        chunk = file.file.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise _UploadTooLarge(
                f'文件超过上传上限 {BaseConfig.REPORT_STUDIO_UPLOAD_MAX_MB}MB')
        chunks.append(chunk)
    if total == 0:
        raise _UploadEmpty('上传文件为空')
    return b''.join(chunks)


def _decode_markdown(content: bytes) -> str:
    """Markdown 正文解码：UTF-8（含 BOM）优先，退化 GB18030 兼容历史文件。"""
    for encoding in ('utf-8-sig', 'gb18030'):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError('Markdown 文件编码无法识别，请使用 UTF-8')


class ReportStudioQueryService:
    """Report Studio 读侧 BFF Service。"""

    # ------------------------------------------------------------------
    # 文档
    # ------------------------------------------------------------------

    @staticmethod
    def get_document(doc_id):
        if not doc_id:
            return error_response('缺少 doc_id', http_code=400)
        return _call(report_studio_service.stub.GetStudioDocument, {'doc_id': doc_id})

    @staticmethod
    def list_documents(params=None):
        """文档列表（INT-1763 §6.4）：report_id / source_type / parent_doc_id 过滤。

        过滤条件由调用方显式给出：平台报告详情页文档列表必须带
        ``source_type=platform_report``；独立文档库带 ``source_type=uploaded_file``。
        """
        params = params or {}
        payload = {}
        for key in ('report_id', 'source_type', 'parent_doc_id', 'limit', 'offset'):
            value = params.get(key)
            if value not in (None, ''):
                payload[key] = value
        return _call(report_studio_service.stub.ListStudioDocuments, payload)

    @staticmethod
    def download_source(doc_id):
        """上传件（html/pptx）鉴权下载：附件语义 + nosniff + 沙箱 CSP。"""
        if not doc_id:
            return error_response('缺少 doc_id', http_code=400)
        resp = report_studio_service.stub.GetStudioDocument(
            report_pb.StudioDocumentRequest(data=_dumps({'doc_id': doc_id})))
        data = _loads(resp.data, {}) or {}
        if not resp.success:
            return error_response(resp.message or '文档不存在',
                                  http_code=resp.code or 400, detail=data)
        path = data.get('source_file_path')
        if not path:
            return error_response('该文档没有源文件（Markdown 文档正文直接读取 markdown_content）',
                                  http_code=400)
        try:
            content = ReportOSSStorage.download_bytes(path)
        except FileNotFoundError:
            return error_response('源文件已丢失', http_code=404)
        except Exception as e:
            logger.exception('读取 Report Studio 源文件失败')
            return error_response(f'读取源文件失败: {e}', http_code=500)

        fmt = str(data.get('source_format') or '').lower()
        ext = f'.{fmt}' if fmt else os.path.splitext(str(path))[1]
        filename = f"{data.get('title') or doc_id}{ext}"
        headers = dict(_STUDIO_DOWNLOAD_HEADERS)
        # 标题可含中文：Content-Disposition 头只能用 ASCII，文件名走 RFC 5987
        headers['Content-Disposition'] = (
            f"attachment; filename=\"doc{ext}\"; filename*=UTF-8''{quote(filename)}")
        return {
            'binary': True,
            'content': content,
            'mime_type': _STUDIO_DOWNLOAD_MIME.get(fmt, 'application/octet-stream'),
            'filename': filename,
            'headers': headers,
        }

    @staticmethod
    def list_versions(doc_id):
        if not doc_id:
            return error_response('缺少 doc_id', http_code=400)
        return _call(report_studio_service.stub.ListStudioDocumentVersions,
                     {'doc_id': doc_id})

    # ------------------------------------------------------------------
    # 图表
    # ------------------------------------------------------------------

    @staticmethod
    def get_chart_data(doc_id, chart_id):
        if not doc_id or not chart_id:
            return error_response('缺少 doc_id 或 chart_id', http_code=400)
        return _call(report_studio_service.stub.GetStudioChartData,
                     {'doc_id': doc_id, 'chart_id': chart_id})

    # ------------------------------------------------------------------
    # 导出作业
    # ------------------------------------------------------------------

    @staticmethod
    def get_export_job(export_id):
        if not export_id:
            return error_response('缺少 export_id', http_code=400)
        return _call(report_studio_service.stub.GetStudioExportJob,
                     {'export_id': export_id})

    @staticmethod
    def download_export(export_id):
        if not export_id:
            return error_response('缺少 export_id', http_code=400)
        resp = report_studio_service.stub.DownloadStudioExport(
            report_pb.StudioExportJobRequest(data=_dumps({'export_id': export_id})))
        data = _loads(resp.data, {}) or {}
        if not resp.success:
            return error_response(resp.message or '下载失败', http_code=resp.code or 400, detail=data)
        if data.get('content_base64'):
            return {
                'binary': True,
                'content': base64.b64decode(data['content_base64']),
                'mime_type': data.get('mime_type', 'application/octet-stream'),
                'filename': data.get('filename', 'export'),
            }
        return success_response(data)


class ReportStudioCommandService:
    """Report Studio 写侧 BFF Service。"""

    # ------------------------------------------------------------------
    # 文档
    # ------------------------------------------------------------------

    @staticmethod
    def create_document():
        body = _parse_json_body()
        report_id = body.get('report_id')
        if not report_id:
            return error_response('缺少 report_id', http_code=400)
        payload = {
            'report_id': report_id,
            'agent_session_id': body.get('agent_session_id'),
            'title': body.get('title'),
            'markdown_content': body.get('markdown_content'),
            'chart_refs': body.get('chart_refs'),
            'style_prefs': body.get('style_prefs'),
        }
        return _call(report_studio_service.stub.CreateStudioDocument, payload)

    @staticmethod
    def import_document(file, title=None, task_id=None, fmt=None):
        """文件型独立报告导入（3b，设计文档 §6.2）。

        校验顺序：扩展名 + format + Content-Type 白名单（415）→ 大小上限（413）
        → md 解码进正文 / html+pptx 落 OSS（category=reports，
        key=studio_uploads/{uuid}.{ext}）→ gRPC 建文档。建档失败时删除已上传
        对象（D0 A11-4 补偿），不留下孤立文件。
        """
        file_name = getattr(file, 'filename', '') or ''
        ext = os.path.splitext(file_name)[1].lower().lstrip('.')
        declared = str(fmt or '').strip().lower() or ext
        if ext not in _STUDIO_UPLOAD_TYPES or declared != ext:
            return error_response(
                '仅支持 md / html / pptx 文件，且扩展名与 format 需一致', http_code=415)
        content_type = (getattr(file, 'content_type', '') or '').split(';')[0].strip().lower()
        if content_type and content_type not in _STUDIO_UPLOAD_TYPES[ext]:
            return error_response(
                f'Content-Type {content_type} 与扩展名 .{ext} 不匹配', http_code=415)

        max_bytes = max(int(BaseConfig.REPORT_STUDIO_UPLOAD_MAX_MB), 1) * 1024 * 1024
        try:
            content = _read_upload(file, max_bytes)
        except _UploadTooLarge as e:
            return error_response(str(e), http_code=413)
        except _UploadEmpty as e:
            return error_response(str(e), http_code=400)

        payload = {'title': title, 'source_format': ext, 'file_name': file_name}
        if task_id not in (None, ''):
            try:
                payload['task_id'] = int(task_id)
            except (TypeError, ValueError):
                return error_response('task_id 非法', http_code=400)

        stored_path = None
        if ext == StudioUploadFormat.MD.value:
            try:
                payload['markdown_content'] = _decode_markdown(content)
            except ValueError as e:
                return error_response(str(e), http_code=400)
        else:
            try:
                stored_path = ReportOSSStorage.upload_studio_upload(
                    content, file_name, content_type or 'application/octet-stream')
            except Exception as e:
                logger.exception('上传 Report Studio 源文件失败')
                return error_response(f'文件保存失败: {e}', http_code=500)
            payload['source_file_path'] = stored_path
            payload['source_file_size'] = len(content)

        result = _call(report_studio_service.stub.CreateStudioUploadDocument, payload)
        # 建档失败 → 删除已写对象，避免孤立文件（补偿失败只记日志，不掩盖主错误）
        if stored_path and isinstance(result, tuple) and result[1] >= 400:
            try:
                ReportOSSStorage.delete(stored_path)
            except Exception:
                logger.warning('补偿删除上传对象失败: %s', stored_path, exc_info=True)
        return result

    @staticmethod
    def update_document(doc_id):
        body = _parse_json_body()
        if not doc_id:
            return error_response('缺少 doc_id', http_code=400)
        expected_version = body.get('expected_version')
        if expected_version is None:
            return error_response('缺少 expected_version', http_code=400)
        payload = {
            'doc_id': doc_id,
            'expected_version': expected_version,
            'idempotency_key': body.get('idempotency_key'),
            'markdown_content': body.get('markdown_content'),
            'chart_refs': body.get('chart_refs'),
            'style_prefs': body.get('style_prefs'),
        }
        return _call(report_studio_service.stub.UpdateStudioDocument, payload)

    @staticmethod
    def restore_version(doc_id):
        body = _parse_json_body()
        if not doc_id:
            return error_response('缺少 doc_id', http_code=400)
        version = body.get('version')
        expected_version = body.get('expected_version')
        if version is None or expected_version is None:
            return error_response('缺少 version 或 expected_version', http_code=400)
        return _call(report_studio_service.stub.RestoreStudioDocumentVersion,
                     {'doc_id': doc_id, 'version': version, 'expected_version': expected_version})

    # ------------------------------------------------------------------
    # 导出
    # ------------------------------------------------------------------

    @staticmethod
    def create_export_job(doc_id):
        body = _parse_json_body()
        if not doc_id:
            return error_response('缺少 doc_id', http_code=400)
        version = body.get('version')
        fmt = body.get('format')
        if version is None or not fmt:
            return error_response('缺少 version 或 format', http_code=400)
        return _call(report_studio_service.stub.CreateStudioExportJob,
                     {'doc_id': doc_id, 'version': version, 'format': fmt,
                      'theme': body.get('theme')})
