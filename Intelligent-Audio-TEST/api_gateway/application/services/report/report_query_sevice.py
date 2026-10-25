# -*- coding: utf-8 -*-
"""报告查询 Service（BFF Application 层 - CQRS Query Side）

职责：参数校验 + gRPC 调用 report_service，不含业务逻辑。
"""
import base64
import json
import logging
from urllib.parse import quote

from api_gateway.infrastructure.request_adapter import request
from api_gateway.utils.response import success_response, error_response
from api_gateway.schemas.report import (
    ReportListQuery,
    ReportCaseListQuery,
    ReportSearchCasesRequest,
    ReportRawResponseQuery,
    ReportExportRequest,
    GetCaseAveragesRequest,
    ReportExportQuery,
    ReportExportHistoryQuery,
    ReportStatisticsQuery,
    ReportStatisticsTrendQuery,
    GenerateStatisticsReportRequest,
)
from api_gateway.infrastructure.grpc_proxies import report_config_service
from shared.proto import report_service_pb2 as report_pb
from shared.utils.grpc_json import loads as _loads, dumps as _dumps

logger = logging.getLogger(__name__)


def _parse_query_params(model_cls):
    params = {k: v[0] if isinstance(v, list) else v for k, v in request.args.to_dict().items()}
    return model_cls.model_validate(params)


class ReportQueryService:
    """报告查询 BFF Service：参数校验 → gRPC 调用 → 响应组装"""

    # ------------------------------------------------------------------
    # 报告列表
    # ------------------------------------------------------------------

    @staticmethod
    def get_all():
        try:
            params = {k: v[0] if isinstance(v, list) else v
                      for k, v in request.args.to_dict().items()}
            query = ReportListQuery.model_validate(params)
        except Exception as e:
            return error_response(f'参数错误: {str(e)}', 400)

        try:
            stub = report_config_service.stub
            resp = stub.ListReports(report_pb.ListReportsRequest(
                report_type=query.report_type or '',
                status=query.status or '',
                task_id=query.task_id or 0,
                algorithm_type=query.algorithm_type or '',
                page=query.page,
                per_page=query.per_page or 20,
                search=query.keyword or '',
                start_date=query.start_time or '',
                end_date=query.end_time or '',
                # INT-141：收藏 / 回收站过滤
                favorite=getattr(query, 'favorite', False),
                deleted=getattr(query, 'deleted', False),
            ))
            if not resp.success:
                return error_response(resp.message or '查询失败')
            data = _loads(resp.data, {}) or {}
            return success_response(data)
        except Exception as e:
            return error_response(f'查询报告列表失败: {str(e)}')

    # ------------------------------------------------------------------
    # Tab 计数聚合（INT-280：HistoryReports Tab 计数服务端化）
    # ------------------------------------------------------------------

    @staticmethod
    def get_tab_counts():
        """四个视图 Tab 的全量计数（单次 RPC：report_service 一条条件聚合 SQL）。

        Tab → 过滤映射由 report_service 持有（all/draft/published/comparison，
        与 ReportStatus/ReportType 枚举一致）；本层只做透传，不再逐 Tab 串行
        CountReports（INT-1463：4 次 RPC 合并为 1 次）。
        RPC 失败时四个计数全 0 降级（列表仍可用，计数不阻塞主视图）。
        """
        counts = {'all': 0, 'draft': 0, 'published': 0, 'comparison': 0}
        try:
            stub = report_config_service.stub
            resp = stub.CountReportsByTabs(report_pb.CountReportsByTabsRequest())
            if resp.success:
                data = _loads(resp.data, {}) or {}
                for tab in counts:
                    counts[tab] = int(data.get(tab, 0) or 0)
            else:
                logger.warning('报告 Tab 计数失败（降级为 0）: %s', resp.message)
            return success_response(counts)
        except Exception as e:
            # 计数失败不阻塞主视图：保留 200 + 全 0 降级（INT-280 既有口径）
            logger.exception('报告 Tab 计数失败（降级为 0）: %s', e)
            return success_response(counts)

    # ------------------------------------------------------------------
    # 报告详情
    # ------------------------------------------------------------------

    @staticmethod
    def get_one(report_id):
        try:
            stub = report_config_service.stub
            resp = stub.GetReportDetail(report_pb.GetReportDetailRequest(
                report_id=int(report_id)))
            if not resp.success:
                # INT-566 P1-5：不存在/私有非 owner 详情 → HTTP 404（防探测口径统一）。
                # 业务码经服务侧 fold_business_code 折进 data JSON，此处提取区分
                # 404（不存在/越权）与其余失败（500 等）。
                _data = _loads(resp.data, {}) or {}
                _code = _data.get('code') if isinstance(_data, dict) else None
                if _code == 404:
                    return error_response(resp.message or '未找到测试报告',
                                          code=404, http_code=404)
                return error_response(resp.message or '查询失败', code=_code or 400)
            data = _loads(resp.data, {}) or {}
            # INT-466：admin 访问私有报告详情落 PRIVATE_RESOURCE_ACCESS 审计（旁路）
            from api_gateway.application.services.visibility.visibility_audit import (
                maybe_audit_private_detail,
            )
            maybe_audit_private_detail('report', report_id, data)
            return success_response(data)
        except Exception as e:
            return error_response(f'查询报告失败: {str(e)}')

    @staticmethod
    def get_by_task(task_id):
        """按任务查询最新报告（INT-262：对齐 report_service 直连 /by_task 路由）。

        任务无报告时 404，与 get_one 口径一致。
        """
        try:
            stub = report_config_service.stub
            resp = stub.GetReportByTask(report_pb.GetReportByTaskRequest(
                task_id=int(task_id)))
            if not resp.success:
                return error_response(resp.message or '未找到测试报告',
                                      code=404, http_code=404)
            data = _loads(resp.data, {}) or {}
            return success_response(data)
        except Exception as e:
            return error_response(f'查询报告失败: {str(e)}')

    @staticmethod
    def get_progress(report_id):
        """报告生成进度查询（从任务/报告生成状态推导，report_service 读侧）。"""
        try:
            stub = report_config_service.stub
            resp = stub.GetReportProgress(report_pb.GetReportProgressRequest(
                report_id=int(report_id)))
            if not resp.success:
                return error_response(resp.message or '未找到测试报告', code=404, http_code=404)
            data = _loads(resp.data, {}) or {}
            return success_response(data)
        except Exception as e:
            return error_response(f'查询报告进度失败: {str(e)}')

    # ------------------------------------------------------------------
    # 报告用例列表
    # ------------------------------------------------------------------

    @staticmethod
    def get_report_cases(report_id):
        try:
            params = {k: v[0] if isinstance(v, list) else v
                      for k, v in request.args.to_dict().items()}
            query = ReportCaseListQuery.model_validate(params)
        except Exception as e:
            return error_response(f'参数错误: {str(e)}', 400)

        try:
            stub = report_config_service.stub
            resp = stub.GetReportCases(report_pb.GetReportCasesRequest(
                report_id=int(report_id),
                data=_dumps({
                    'keyword': query.keyword or '',
                    'category': query.category or '',
                    'tags': query.tags or [],
                    'page': query.page,
                    'per_page': query.per_page,
                })))
            if not resp.success:
                return error_response(resp.message or '查询失败')
            data = _loads(resp.data, {}) or {}
            return success_response(data)
        except Exception as e:
            return error_response(f'查询报告用例失败: {str(e)}')

    @staticmethod
    def get_case_dimension_raw_response(report_id, case_id, dimension_id):
        """按需读取报告某用例某维度的 API 原始响应（INT-1752）。

        GET /reports/{id}/cases/{cid}/dimensions/{dim_id}/raw-response（report:read）。
        默认关闭：不随报告详情下发，仅显式请求时读取；返回单页切片
        （offset/limit，默认 20k、上限 200k 字符，has_more/next_offset 翻页）。
        data.available=False 表示该用例/维度没有可展开的原始响应（非 API 用例等）。
        """
        try:
            query = ReportRawResponseQuery.model_validate(
                {k: v[0] if isinstance(v, list) else v
                 for k, v in request.args.to_dict().items()})
        except Exception as e:
            return error_response(f'参数错误: {str(e)}', 400)

        try:
            stub = report_config_service.stub
            resp = stub.GetCaseDimensionRawResponse(report_pb.GetCaseDimensionRawResponseRequest(
                report_id=int(report_id),
                case_id=str(case_id),
                dimension_id=int(dimension_id),
                offset=query.offset,
                limit=query.limit,
                round_number=query.round_number,
            ))
            if not resp.success:
                return error_response(resp.message or '读取原始响应失败', http_code=resp.code or 400)
            return success_response(_loads(resp.data, {}) or {})
        except Exception as e:
            return error_response(f'读取 API 原始响应失败: {str(e)}')

    # ------------------------------------------------------------------
    # 搜索报告用例
    # ------------------------------------------------------------------

    @staticmethod
    def search_report_cases(report_id):
        try:
            body = request.get_json() or {}
            req = ReportSearchCasesRequest.model_validate(body)
        except Exception as e:
            return error_response(f'参数错误: {str(e)}', 400)

        try:
            stub = report_config_service.stub
            resp = stub.SearchReportCases(report_pb.SearchReportCasesRequest(
                report_id=int(report_id),
                data=_dumps({
                    'keyword': req.keyword or '',
                    'category': req.category or '',
                    'categories': req.categories or [],
                    'tags': req.tags or [],
                    'include_untagged': req.include_untagged or False,
                    'metrics': req.metrics or [],
                    'sort_by': req.sort_by or 'name',
                    'sort_metric': req.sort_metric or '',
                    'sort_resource': req.sort_resource or '',
                    'sort_order': req.sort_order or 'asc',
                    'page': req.page,
                    'per_page': req.per_page,
                })))
            if not resp.success:
                return error_response(resp.message or '搜索失败')
            data = _loads(resp.data, {}) or {}
            return success_response(data)
        except Exception as e:
            return error_response(f'搜索报告用例失败: {str(e)}')

    # ------------------------------------------------------------------
    # 导出报告
    # ------------------------------------------------------------------

    @staticmethod
    def export():
        try:
            body = request.get_json()
            if body:
                req = ReportExportRequest.model_validate(body)
                report_ids = req.ids
                format_type = req.format
            else:
                query = _parse_query_params(ReportExportQuery)
                ids_str = query.ids
                if not ids_str:
                    return error_response('缺少必要参数: ids', 400)
                report_ids = [int(rid.strip()) for rid in str(ids_str).split(',') if rid.strip()]
                if not report_ids:
                    return error_response('无效的报告 ID 列表', 400)
                format_type = query.format
        except Exception as e:
            return error_response(f'参数错误: {str(e)}', 400)

        try:
            stub = report_config_service.stub
            resp = stub.ExportReports(report_pb.ExportReportsRequest(
                data=_dumps({'ids': report_ids, 'format': format_type})))
            if not resp.success:
                return error_response(resp.message or '导出失败')
            data = _loads(resp.data, {}) or {}
            # 如果返回 base64 文件内容，返回特殊结构供路由层转换为二进制响应
            if data.get('content_base64'):
                return {
                    'binary': True,
                    'content': base64.b64decode(data['content_base64']),
                    'mime_type': data.get('mime_type', 'application/octet-stream'),
                    'filename': data.get('filename', 'export'),
                }
            return success_response(data)
        except Exception as e:
            return error_response(f'导出报告失败: {str(e)}')

    # ------------------------------------------------------------------
    # 导出历史（INT-1555：报告中心「导出历史」页签）
    # ------------------------------------------------------------------

    @staticmethod
    def get_export_history():
        try:
            query = _parse_query_params(ReportExportHistoryQuery)
        except Exception as e:
            return error_response(f'参数错误: {str(e)}', 400)

        try:
            stub = report_config_service.stub
            resp = stub.ListExportHistory(report_pb.ListExportHistoryRequest(
                data=_dumps({'page': query.page,
                             'per_page': query.per_page})))
            if not resp.success:
                return error_response(resp.message or '查询导出历史失败')
            return success_response(_loads(resp.data, {}) or {})
        except Exception as e:
            return error_response(f'查询导出历史失败: {str(e)}')

    # ------------------------------------------------------------------
    # 用例平均值
    # ------------------------------------------------------------------

    @staticmethod
    def get_case_averages_by_filters():
        try:
            body = request.get_json() or {}
            req = GetCaseAveragesRequest.model_validate(body)
            if not req.task_id and not req.report_id:
                return error_response('缺少必要参数: taskId 或 reportId', 400)
        except Exception as e:
            return error_response(f'参数错误: {str(e)}', 400)

        try:
            stub = report_config_service.stub
            resp = stub.GetCaseAverages(report_pb.GetCaseAveragesRequest(
                data=_dumps({
                    'task_id': req.task_id,
                    'report_id': req.report_id,
                    'category': req.category or '',
                    'tags': req.tags or [],
                    'categories': req.categories or [],
                    'include_untagged': req.include_untagged or False,
                })))
            if not resp.success:
                return error_response(resp.message or '查询失败')
            data = _loads(resp.data, {}) or {}
            return success_response(data)
        except Exception as e:
            return error_response(f'获取用例平均值失败: {str(e)}')

    # ------------------------------------------------------------------
    # 报告统计分析（INT-791：/reports/statistics*，供 G04 报告统计分析页）
    # ------------------------------------------------------------------

    @staticmethod
    def get_statistics():
        try:
            params = {k: v[0] if isinstance(v, list) else v
                      for k, v in request.args.to_dict().items()}
            query = ReportStatisticsQuery.model_validate(params)
        except Exception as e:
            return error_response(f'参数错误: {str(e)}', 400)

        try:
            stub = report_config_service.stub
            resp = stub.GetStatistics(report_pb.GetStatisticsRequest(
                data=_dumps(query.model_dump(by_alias=False, exclude_none=True))))
            if not resp.success:
                return error_response(resp.message or '统计分析失败')
            data = _loads(resp.data, {}) or {}
            return success_response(data)
        except Exception as e:
            return error_response(f'统计分析失败: {str(e)}')

    @staticmethod
    def get_statistics_trend():
        try:
            params = {k: v[0] if isinstance(v, list) else v
                      for k, v in request.args.to_dict().items()}
            query = ReportStatisticsTrendQuery.model_validate(params)
        except Exception as e:
            return error_response(f'参数错误: {str(e)}', 400)

        try:
            stub = report_config_service.stub
            resp = stub.GetStatisticsTrend(report_pb.GetStatisticsTrendRequest(
                data=_dumps(query.model_dump(by_alias=False, exclude_none=True))))
            if not resp.success:
                return error_response(resp.message or '趋势分析失败')
            data = _loads(resp.data, {}) or {}
            return success_response(data)
        except Exception as e:
            return error_response(f'趋势分析失败: {str(e)}')

    @staticmethod
    def generate_statistics_report():
        try:
            body = request.get_json() or {}
            req = GenerateStatisticsReportRequest.model_validate(body)
        except Exception as e:
            return error_response(f'参数错误: {str(e)}', 400)

        try:
            stub = report_config_service.stub
            resp = stub.GenerateStatisticsReport(report_pb.GenerateStatisticsReportRequest(
                data=_dumps(req.model_dump(by_alias=False, exclude_none=True))))
            if not resp.success:
                return error_response(resp.message or '报表生成失败')
            data = _loads(resp.data, {}) or {}
            # 复用 binary 下载链路：zip_base64 → Blob 下载（对齐 export 链路）
            if data.get('content_base64'):
                return {
                    'binary': True,
                    'content': base64.b64decode(data['content_base64']),
                    'mime_type': data.get('mime_type', 'application/octet-stream'),
                    'filename': data.get('filename', 'statistics_report'),
                }
            return success_response(data)
        except Exception as e:
            return error_response(f'报表生成失败: {str(e)}')

    # ------------------------------------------------------------------
    # 下载用例日志
    # ------------------------------------------------------------------

    @staticmethod
    def download_case_logs(report_id, case_id):
        if not case_id:
            return error_response('case_id 不能为空', 400)

        # INT-1062：?files= URL 编码 JSON 字符串数组（如 ["a.txt","b.log"]），
        # 缺省 = 整包（向后兼容）；空数组/非法元素 → 400
        files = None
        files_raw = request.args.get('files')
        if files_raw:
            try:
                parsed = json.loads(files_raw)
            except (ValueError, TypeError):
                return error_response('files 参数必须是 URL 编码的 JSON 字符串数组', 400)
            if not isinstance(parsed, list):
                return error_response('files 参数必须是数组', 400)
            if not parsed:
                return error_response('files 参数为空数组', 400)
            if not all(isinstance(f, str) and f for f in parsed):
                return error_response('files 参数必须是非空字符串数组', 400)
            files = parsed

        try:
            stub = report_config_service.stub
            resp = stub.DownloadCaseLogs(report_pb.DownloadCaseLogsRequest(
                report_id=int(report_id),
                case_id=str(case_id),
                files=files or []))
            if not resp.success:
                return error_response(resp.message or '下载失败',
                                      http_code=resp.code or 400,
                                      detail=_loads(resp.data, {}) or None)
            data = _loads(resp.data, {}) or {}
            # INT-1116：传输层改造 —— OSS 预签名 URL 优先（整包不过 gRPC）；
            # 本地降级（无 OSS）回退 base64 字节流
            if data.get('download_url'):
                return success_response({
                    'download_url': data['download_url'],
                    'filename': data.get('filename', 'logs.zip'),
                    'size': data.get('size'),
                })
            if data.get('content_base64'):
                return {
                    'binary': True,
                    'content': base64.b64decode(data['content_base64']),
                    'mime_type': data.get('mime_type', 'application/zip'),
                    'filename': data.get('filename', 'logs.zip'),
                }
            return success_response(data)
        except Exception as e:
            return error_response(f'下载用例日志失败: {str(e)}')

    @staticmethod
    def list_case_logs(report_id, case_id):
        """查询用例日志文件列表（GET /reports/{id}/cases/{cid}/logs，report:read）。

        返回 {items: [{name, size, updated_at?, download_url}]}，name 与下载 ZIP
        arcname / files= 同一套逻辑名（INT-1062）。

        INT-1116 返工（审计 P1）：列表只给元数据，不下发 OSS 内容直链；对所有条目
        统一补回退下载 URL（logs/download?files=<json>，经下载端点 report:download_log
        校验，内容下载一律收敛在下载权限；guest 仅 report:read 点链接即 403）。
        """
        if not case_id:
            return error_response('case_id 不能为空', 400)

        try:
            stub = report_config_service.stub
            resp = stub.ListCaseLogs(report_pb.ListCaseLogsRequest(
                report_id=int(report_id),
                case_id=str(case_id)))
            if not resp.success:
                return error_response(resp.message or '查询日志文件列表失败',
                                      http_code=resp.code or 400,
                                      detail=_loads(resp.data, {}) or None)
            data = _loads(resp.data, {}) or {}
            items = data.get('items') or []
            # INT-1116 返工（审计 P1）：内容下载一律收敛在 report:download_log。
            # 对全部条目统一补回退下载 URL（logs/download?files= 经下载端点校验权限）；
            # 即使服务端带回直链也覆盖为回退 URL，防止越权回归。
            for item in items:
                files_json = json.dumps([item.get('name', '')], ensure_ascii=False)
                item['download_url'] = (
                    f'/api/v1/reports/{report_id}/cases/{case_id}/logs/download'
                    f'?files={quote(files_json, safe="")}')
            data['items'] = items
            return success_response(data)
        except Exception as e:
            return error_response(f'查询日志文件列表失败: {str(e)}')

    # ------------------------------------------------------------------
    # 报告分享（INT-971）
    # ------------------------------------------------------------------

    @staticmethod
    def list_shares(report_id):
        """报告分享列表（GET /reports/{report_id}/share，report:update）。"""
        try:
            stub = report_config_service.stub
            resp = stub.ListReportShares(report_pb.ListReportSharesRequest(
                data=_dumps({'report_id': int(report_id)})))
            if not resp.success:
                return error_response(resp.message or '查询分享列表失败',
                                      http_code=resp.code or 400,
                                      detail=_loads(resp.data, {}) or None)
            data = _loads(resp.data, {}) or {}
            return success_response(data)
        except Exception as e:
            return error_response(f'查询分享列表失败: {str(e)}')

    @staticmethod
    def get_shared_report(token):
        """公开读取分享（GET /reports/shared/{token}，PUBLIC_PATHS 免登录路由）。

        handler 内自校验（token 有效性/密码/访问口径），可选解析 Bearer 得
        user_id（失败当匿名）。访问计数在 report_service 200 放行时原子递增。
        """
        if not token:
            return error_response('缺少分享 token', 404)

        # 可选解析 Bearer token → user_id（TokenService.verify 失败当匿名）
        user_id = None
        auth_header = request.headers.get('Authorization', '')
        if auth_header.startswith('Bearer '):
            try:
                from api_gateway.application.services.auth.token_service import TokenService
                payload = TokenService.verify(auth_header[7:])
                user_id = payload.get('user_id') or None
            except Exception:
                user_id = None

        password = request.args.get('password')
        try:
            stub = report_config_service.stub
            resp = stub.GetSharedReport(report_pb.GetSharedReportRequest(
                data=_dumps({
                    'token': token,
                    'password': password,
                    'user_id': user_id,
                })))
            if not resp.success:
                data = _loads(resp.data, {}) or {}
                detail = data or None
                if data.get('share_requires_password'):
                    detail = {'share_requires_password': True}
                return error_response(resp.message or '读取分享失败',
                                      http_code=resp.code or 404,
                                      detail=detail)
            data = _loads(resp.data, {}) or {}
            return success_response(data)
        except Exception as e:
            return error_response(f'读取分享失败: {str(e)}')
