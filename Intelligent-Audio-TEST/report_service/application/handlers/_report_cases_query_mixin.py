# -*- coding: utf-8 -*-
"""报告查询处理器 Mixin — 用例列表 / 搜索 / 导出（从 report_handlers.py 拆分，P4-5）。

handle_get_report_cases / handle_search_report_cases / handle_export_reports
及其 HTML 导出辅助。
"""
import logging

logger = logging.getLogger(__name__)


class ReportCasesQueryMixin:
    """报告用例列表 / 搜索 / 导出查询（依赖 self.repository）"""

    def handle_get_report_cases(self, report_id: int, params_dict: dict) -> dict:
        """处理查询报告用例列表（薄处理器：解析参数 -> 调用服务 -> 格式化响应）。

        Args:
            report_id: 报告 ID
            params_dict: 查询参数，含 keyword/category/tags/page/per_page 等

        Returns:
            dict: {items, total, page, perPage, pages}
        """
        from report_service.application.services.report_aggregation_service import ReportAggregationService

        aggregate = self.repository.get_by_id(report_id)
        if aggregate is None:
            return self._empty_paged_response()
        aggregate.cases = self.repository.load_cases(report_id)

        # 构建用例字典列表
        all_cases = [ReportAggregationService.build_case_dict_from_entity(c) for c in aggregate.cases]

        # 客户端过滤
        keyword = params_dict.get('keyword')
        category = params_dict.get('category')
        tags = params_dict.get('tags') or []
        filtered = ReportAggregationService.filter_cases(all_cases, keyword, category, tags)

        # 分页
        page = max(int(params_dict.get('page') or 1), 1)
        per_page = max(int(params_dict.get('per_page') or 20), 1)
        paged_cases, total, pages = ReportAggregationService.paginate(filtered, page, per_page)

        # 构建前端用例项
        items = [ReportAggregationService.build_case_item(case) for case in paged_cases]

        return {
            "items": items,
            "total": total,
            "page": page,
            "perPage": per_page,
            "pages": pages
        }

    def handle_search_report_cases(self, report_id: int, params_dict: dict) -> dict:
        """处理搜索报告用例（薄处理器：解析参数 -> 调用服务 -> 格式化响应）。"""
        from report_service.application.services.report_aggregation_service import ReportAggregationService

        aggregate = self.repository.get_by_id(report_id)
        if aggregate is None:
            return self._empty_paged_response()
        aggregate.cases = self.repository.load_cases(report_id)

        # 构建用例字典列表
        all_cases = [ReportAggregationService.build_case_dict_from_entity(c) for c in aggregate.cases]

        # 解析搜索参数
        keyword = params_dict.get('keyword')
        category = params_dict.get('category')
        categories = params_dict.get('categories') or []
        include_untagged = params_dict.get('include_untagged') or False
        metrics_filter = params_dict.get('metrics') or []
        tags = ReportAggregationService.parse_tags(params_dict.get('tags') or [])

        # 高级过滤
        filtered = ReportAggregationService.filter_cases_advanced(
            all_cases, keyword, category, categories, tags, include_untagged, metrics_filter
        )

        # 排序与分页
        page = max(int(params_dict.get('page') or 1), 1)
        per_page = max(int(params_dict.get('per_page') or 20), 1)
        sort_by = (params_dict.get('sort_by') or 'name').lower()
        sort_order = (params_dict.get('sort_order') or 'asc').lower()
        sort_metric = params_dict.get('sort_metric')
        paged_cases, total, pages = ReportAggregationService.sort_and_paginate_cases(
            filtered, sort_by, sort_order, sort_metric, page, per_page
        )

        # 构建前端用例项
        items = [ReportAggregationService.build_case_item(case) for case in paged_cases]

        return {
            "items": items,
            "total": total,
            "page": page,
            "perPage": per_page,
            "pages": pages
        }

    @staticmethod
    def _empty_paged_response() -> dict:
        """空分页响应（统一契约）。"""
        return {'items': [], 'total': 0, 'page': 1, 'perPage': 20, 'pages': 1}

    # ---- 导出 ----

    def handle_export_reports(self, report_ids: list, format_type: str) -> dict:
        """处理导出报告（薄处理器：解析参数 -> 调用服务 -> 格式化响应）。

        Args:
            report_ids: 报告 ID 列表
            format_type: 导出格式（excel/pdf/csv/html）

        Returns:
            dict: {filename, format, content_base64, mime_type}
        """
        # HTML 导出：完整报告详情（所见即所得），仅支持单个报告
        if format_type == 'html':
            return self._build_html_export(report_ids)

        from report_service.application.services.report_aggregation_service import ReportAggregationService
        export_data = ReportAggregationService.build_export_data(report_ids, self.repository)
        if export_data is None:
            return {'success': False, 'message': '未找到指定报告'}

        return ReportAggregationService.build_export_payload(export_data, format_type)

    def _build_html_export(self, report_ids: list) -> dict:
        """构建 HTML 导出响应。

        HTML 导出仅支持单个报告，复用完整报告数据（所见即所得）。
        通过 report_repository.load_full_report_data 获取摘要/元数据/统计等，
        再调用 HtmlReportRenderer.render 渲染为自包含 HTML。

        Args:
            report_ids: 报告 ID 列表（仅取第一个）

        Returns:
            dict: {filename, format, content_base64, mime_type} 或 {success: False, message}
        """
        import base64
        from shared.utils.query_utils import now_cst
        from report_service.application.services.html_report_renderer import HtmlReportRenderer

        if not report_ids or len(report_ids) != 1:
            return {'success': False, 'message': 'HTML 导出仅支持单个报告，请选择一个报告'}

        report_id = int(report_ids[0])
        aggregate = self.repository.get_by_id(report_id)
        if aggregate is None:
            return {'success': False, 'message': '未找到指定报告'}

        summary_data = self.repository.load_full_report_data(report_id)
        if summary_data is None:
            return {'success': False, 'message': '报告数据未迁移，请先运行迁移脚本'}

        report_data = self._assemble_html_report_data(aggregate, summary_data)
        html_content = HtmlReportRenderer.render(report_data)

        return {
            'filename': self._build_html_filename(report_id, report_data['name']),
            'format': 'html',
            'content_base64': base64.b64encode(html_content.encode('utf-8')).decode('utf-8'),
            'mime_type': 'text/html; charset=utf-8',
        }

    @staticmethod
    def _assemble_html_report_data(aggregate, summary_data) -> dict:
        """组装报告数据（与 get_one API 返回的 data 字段结构一致）。"""
        config = aggregate.config or {}
        return {
            'id': aggregate.id,
            'name': config.get('name', '未命名报告'),
            'type': aggregate.report_type,
            'task_id': aggregate.task_id,
            'task_name': config.get('task_name', ''),
            'summary': summary_data,
            'description': config.get('description', ''),
            'status': aggregate.status,
            'analysis': config.get('analysis', ''),
            'created_at': str(aggregate.created_at) if aggregate.created_at else None,
        }

    @staticmethod
    def _build_html_filename(report_id: int, report_name: str) -> str:
        """构建 HTML 导出文件名（清理非法字符）。"""
        from shared.utils.query_utils import now_cst
        filename = f"report_{report_id}_{report_name}_{now_cst().strftime('%Y%m%d')}.html"
        return filename.replace('/', '_').replace('\\', '_').replace(':', '_').replace('"', '_')

    # ---- 委托服务层的静态辅助（保持原 ReportQueryHandler 接口兼容） ----

    @staticmethod
    def _normalize_audio_paths_in_results(algorithm_results):
        """将 algorithm_results 中 audio_file 路径规范化（委托服务层）。"""
        from report_service.application.services.report_aggregation_service import ReportAggregationService
        return ReportAggregationService._normalize_audio_paths_in_results(algorithm_results)

    @staticmethod
    def _expand_algorithm_results_for_report(algorithm_results, algorithm_type=None):
        """报告页 algorithm_results 后处理（委托服务层）。"""
        from report_service.application.services.report_aggregation_service import ReportAggregationService
        return ReportAggregationService._expand_algorithm_results_for_report(algorithm_results, algorithm_type)

    @staticmethod
    def _expand_reference_params_for_report(reference_params):
        """报告页 reference_params 后处理（委托服务层）。"""
        from report_service.application.services.report_aggregation_service import ReportAggregationService
        return ReportAggregationService._expand_reference_params_for_report(reference_params)
