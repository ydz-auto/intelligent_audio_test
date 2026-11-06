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
            "per_page": per_page,
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
        sort_resource = params_dict.get('sort_resource')
        paged_cases, total, pages = ReportAggregationService.sort_and_paginate_cases(
            filtered, sort_by, sort_order, sort_metric, page, per_page, sort_resource
        )

        # 构建前端用例项
        items = [ReportAggregationService.build_case_item(case) for case in paged_cases]

        return {
            "items": items,
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": pages
        }

    @staticmethod
    def _empty_paged_response() -> dict:
        """空分页响应（统一契约）。"""
        return {'items': [], 'total': 0, 'page': 1, 'per_page': 20, 'pages': 1}

    def handle_get_report_cases_raw_payload(self, report_id: int) -> dict:
        """返回报告用例**原始九字段 payload**（INT-1996：task_service 发布冻结 M1 前置）。

        与 ``handle_get_report_cases`` 的区别：不经响应装配层
        （``build_case_dict_from_entity`` / ``build_case_item`` 的 null/[] 归一
        与 algorithmResults/referenceParams 展开），直接经
        ``report_case_snapshot_store`` 解引用出口给出**原始列值**——null/[] 原样
        保留。task_service 冻结侧按已发布任务契约自行 ``_to_json``/``_to_json_obj``
        归一，保证改造前后 ``canonical_bytes`` 逐字节一致。

        Returns:
            dict: ``{'cases': [{id, test_case_id, name, description, category,
                   tags, metrics, results, audios, reference_params,
                   algorithm_results, algorithm_type, logs}, ...]}``
        """
        rows = self.repository.get_cases_by_report_id(report_id)
        return {
            'cases': [
                {
                    'id': getattr(c, 'id', None),
                    'test_case_id': getattr(c, 'test_case_id', None),
                    'name': getattr(c, 'name', None),
                    'description': getattr(c, 'description', None),
                    'category': getattr(c, 'category', None),
                    'tags': getattr(c, 'tags', None),
                    'metrics': getattr(c, 'metrics', None),
                    'results': getattr(c, 'results', None),
                    'audios': getattr(c, 'audios', None),
                    'reference_params': getattr(c, 'reference_params', None),
                    'algorithm_results': getattr(c, 'algorithm_results', None),
                    'algorithm_type': getattr(c, 'algorithm_type', None),
                    'logs': getattr(c, 'logs', None),
                }
                for c in rows
            ],
        }

    # ---- API 原始响应按需展开（INT-1752）----

    #: 未指定 limit 时的单页字符数
    RAW_RESPONSE_DEFAULT_LIMIT = 20000
    #: 单页字符数上限（请求超过按上限截断）
    RAW_RESPONSE_MAX_LIMIT = 200000
    #: 单次读取的原始响应字符上限（超出只取前 N 字符并标记 truncated）
    RAW_RESPONSE_MAX_TOTAL = 8 * 1024 * 1024

    def handle_get_case_dimension_raw_response(self, report_id: int, params_dict: dict) -> dict:
        """报告详情按需读取某用例某维度的 API 原始响应（INT-1752）。

        默认不随报告详情下发：只有显式请求该端点才读取 api_raw_response，
        且按 offset/limit 分页返回，HTTP 响应大小恒定，不随原始响应线性增长。

        Args:
            report_id: 报告 ID
            params_dict: case_id(str) / dimension_id(int) / offset / limit / round_number

        Returns:
            dict: available 为 False 时表示该用例/维度没有可展开的原始响应
            （非 API 用例、维度无原始响应、维度不属于该用例等），message 说明原因；
            available 为 True 时含 content 分页切片与 total_chars/next_offset/has_more。
        """
        import json
        import time

        started = time.perf_counter()

        def _elapsed():
            return round((time.perf_counter() - started) * 1000, 2)

        case_id = str(params_dict.get('case_id') or '').strip()
        try:
            dimension_id = int(params_dict.get('dimension_id'))
        except (TypeError, ValueError):
            return {'available': False, 'message': 'dimension_id 非法', 'elapsed_ms': _elapsed()}
        try:
            offset = max(int(params_dict.get('offset') or 0), 0)
        except (TypeError, ValueError):
            offset = 0
        try:
            limit = int(params_dict.get('limit') or 0)
        except (TypeError, ValueError):
            limit = 0
        if limit <= 0:
            limit = self.RAW_RESPONSE_DEFAULT_LIMIT
        limit = min(limit, self.RAW_RESPONSE_MAX_LIMIT)
        try:
            round_number = int(params_dict.get('round_number') or 0)
        except (TypeError, ValueError):
            round_number = 0

        base = {
            'available': False,
            'report_id': report_id,
            'test_case_id': case_id,
            'dimension_id': dimension_id,
            'offset': offset,
            'limit': limit,
        }

        aggregate = self.repository.get_by_id(report_id)
        if aggregate is None:
            return {**base, 'message': '报告不存在或已删除', 'elapsed_ms': _elapsed()}

        # 用例必须属于该报告（防止跨报告/跨任务探测）
        report_case_ids = {
            str(getattr(c, 'test_case_id', '') or '')
            for c in self.repository.load_cases(report_id) or []
        }
        if case_id not in report_case_ids:
            return {**base, 'message': '该用例不属于此报告', 'elapsed_ms': _elapsed()}

        # 报告覆盖的任务集合：主任务 → 对比矩阵 comparison_data.task_ids → 摘要兜底。
        # 对比/二次对比报告的 test_reports.task_id 落 0/NULL（ReportAggregate(task_id=0)
        # 且 _report_po_to_entity 把 None 归一成 0），源任务只在对比矩阵里，
        # 因此不能直接用 aggregate.task_id，必须复用报告源任务解析口径。
        task_ids = self._resolve_report_source_task_ids(report_id) or []
        if not task_ids:
            return {**base, 'message': '报告未关联任务', 'elapsed_ms': _elapsed()}

        from report_service.infrastructure.clients.grpc_clients import (
            _grpc_get_dimension_by_ids,
            _grpc_get_dimension_results_by_result_ids,
            _grpc_get_test_results_by_task_and_case,
        )

        try:
            results = _grpc_get_test_results_by_task_and_case([case_id], task_ids) or []
        except Exception as e:  # noqa: BLE001
            logger.warning("raw response: 查询测试结果失败 %s", e)
            results = []

        # 真实契约：_grpc_get_test_results_by_task_and_case 返回 list[dict]（经 dto_to_dict），
        # _grpc_get_dimension_by_ids 返回 {dim_id_str: dict}；按对象属性取会恒判为非 API 用例。
        def _field(obj, key):
            return obj.get(key) if isinstance(obj, dict) else getattr(obj, key, None)

        # 只有 API 结果才有原始响应入口；设备（e2e）结果直接返回不可用
        api_results = [r for r in results if _field(r, 'api_id')]
        if not api_results:
            return {**base, 'message': '该用例非 API 用例，无 API 原始响应', 'elapsed_ms': _elapsed()}

        result_ids = [rid for rid in (_field(r, 'id') for r in api_results) if rid is not None]
        if not result_ids:
            return {**base, 'message': '该用例尚无测试结果', 'elapsed_ms': _elapsed()}

        try:
            dim_map = _grpc_get_dimension_results_by_result_ids(result_ids, include_body=True) or {}
        except Exception as e:  # noqa: BLE001
            logger.warning("raw response: 查询维度结果失败 %s", e)
            dim_map = {}

        candidates = []
        for rid in result_ids:
            for item in dim_map.get(rid, []) or []:
                if not isinstance(item, dict):
                    continue
                if item.get('dimension_id') != dimension_id:
                    continue
                if item.get('api_raw_response') is None:
                    continue
                candidates.append(item)
        if not candidates:
            return {**base, 'message': '该维度未留存 API 原始响应', 'elapsed_ms': _elapsed()}

        def _round_of(item):
            value = item.get('round_number')
            return value if value is not None else None

        chosen = None
        if round_number:
            chosen = next((it for it in candidates if _round_of(it) == round_number), None)
        if chosen is None:
            # 未指定轮次：整体（round_number 为空）优先，其次最早一轮
            chosen = next((it for it in candidates if _round_of(it) is None), None)
        if chosen is None:
            chosen = min(candidates, key=lambda it: (_round_of(it) is None, _round_of(it) or 0))

        raw = chosen.get('api_raw_response')
        if isinstance(raw, str):
            content = raw
        else:
            try:
                content = json.dumps(raw, ensure_ascii=False, default=str)
            except (TypeError, ValueError):
                content = str(raw)

        total_chars = len(content)
        truncated = total_chars > self.RAW_RESPONSE_MAX_TOTAL
        if truncated:
            content = content[:self.RAW_RESPONSE_MAX_TOTAL]
            total_chars = len(content)
        page = content[offset:offset + limit]
        next_offset = offset + len(page)
        has_more = next_offset < total_chars

        dimension_name = None
        try:
            dims = _grpc_get_dimension_by_ids([dimension_id]) or {}
            dim_dto = dims.get(str(dimension_id)) or dims.get(dimension_id)
            dimension_name = _field(dim_dto, 'name') if dim_dto is not None else None
        except Exception:  # noqa: BLE001
            dimension_name = None

        return {
            **base,
            'available': True,
            'message': '',
            'dimension_name': dimension_name,
            'round_number': _round_of(chosen),
            'source_result_id': chosen.get('test_result_id') or chosen.get('result_id'),
            'content': page,
            'content_type': 'application/json',
            'total_chars': total_chars,
            'next_offset': next_offset,
            'has_more': has_more,
            'truncated': truncated,
            'elapsed_ms': _elapsed(),
        }

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
        """组装报告数据（与 get_one API 返回的 data 字段结构一致）。

        INT-1776：task_name 从未持久化（config 里没有该键），此处向
        task_service 补名，失败 / 超时降级为 ''（hero 不输出任务行）。
        """
        from report_service.application.services.report_task_name_enricher import (
            enrich_task_names,
        )

        config = aggregate.config or {}
        report_data = {
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
        enrich_task_names([report_data])
        return report_data

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
