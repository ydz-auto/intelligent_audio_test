# -*- coding: utf-8 -*-
"""报告命令/查询处理器（CQRS Handler）。

职责：
- 接收 Command/Query 对象
- 通过 report_repository 操作聚合根（不直接 import PO）
- 返回聚合根或聚合根列表

遵循 DDD 分层：application 层只依赖 domain 与 repository，
不感知 ORM/PO，保持领域层与基础设施解耦。
"""
from __future__ import annotations

from typing import List, Optional
import logging

from report_service.domain.entities import ReportAggregate, ReportStatus
from report_service.infrastructure.persistence.report_repository import report_repository
from report_service.application.commands.report_commands import (
    CreateReportCommand,
    DeleteReportCommand,
    GenerateReportCommand,
    UpdateReportStatusCommand,
)
from report_service.application.queries.report_queries import (
    GetReportByTaskQuery,
    GetReportQuery,
    GetReportSummaryQuery,
    GetTrendDataQuery,
    ListReportsQuery,
)

logger = logging.getLogger(__name__)


class ReportCommandHandler:
    """报告命令处理器。

    处理所有写操作命令，通过 report_repository 操作聚合根。
    支持注入自定义仓储实例以便单元测试。
    """

    def __init__(self, repository=report_repository) -> None:
        """初始化命令处理器。

        Args:
            repository: 报告仓储实例，默认使用模块级单例 report_repository
        """
        self.repository = repository

    def handle_create(self, command: CreateReportCommand) -> int:
        """处理创建报告命令。

        构造一个处于 pending 状态的聚合根并持久化。

        Args:
            command: CreateReportCommand

        Returns:
            新创建的报告 ID
        """
        aggregate = ReportAggregate(
            id=0,
            task_id=command.task_id,
            report_type=command.report_type,
            status=ReportStatus.PENDING.value,
            config=dict(command.config),
        )
        return self.repository.add(aggregate)

    def handle_generate(self, command: GenerateReportCommand) -> Optional[int]:
        """处理生成报告命令。

        流程：查找任务最新报告 -> 标记为 generating；
        若报告不存在则创建新报告并直接标记为 generating。

        Args:
            command: GenerateReportCommand

        Returns:
            报告 ID；若无法处理返回 None
        """
        aggregate = self.repository.get_by_task(command.task_id)
        if aggregate is None:
            # 任务尚无报告，新建并直接进入 generating
            aggregate = ReportAggregate(
                id=0,
                task_id=command.task_id,
                report_type=command.report_type,
                status=ReportStatus.GENERATING.value,
                config={},
            )
            return self.repository.add(aggregate)
        # 已存在报告：更新类型并标记为 generating
        aggregate.report_type = command.report_type
        aggregate.mark_generating()
        self.repository.save(aggregate)
        return aggregate.id

    def handle_generate_task_report(self, task_id: int, name: str = None, description: str = None) -> dict:
        """处理生成任务报告命令。

        委托 ReportTaskGenerator 执行异步生成。
        """
        from report_service.application.services.report_task_generator import ReportTaskGenerator
        return ReportTaskGenerator.generate_task_report(task_id, name, description)

    def handle_generate_compare_report(self, task_ids: list, name: str = None, description: str = None) -> dict:
        """处理生成对比报告命令。"""
        from report_service.application.services.report_compare_generator import ReportCompareGenerator
        return ReportCompareGenerator.compare(task_ids, name, description)

    def handle_generate_secondary_compare_report(self, report_ids: list, description: str = None) -> dict:
        """处理生成二次对比报告命令。"""
        from report_service.application.services.report_compare_generator import ReportCompareGenerator
        return ReportCompareGenerator.secondary_compare(report_ids, description)

    def handle_update_status(self, command: UpdateReportStatusCommand) -> None:
        """处理更新报告状态命令。

        Args:
            command: UpdateReportStatusCommand
        """
        self.repository.update_status(command.report_id, command.status)

    def handle_delete(self, command: DeleteReportCommand) -> bool:
        """处理删除报告命令（软删除）。

        Args:
            command: DeleteReportCommand

        Returns:
            True 表示删除成功，False 表示报告不存在
        """
        return self.repository.soft_delete(command.report_id)


class ReportQueryHandler:
    """报告查询处理器。

    处理所有读操作查询，通过 report_repository 加载聚合根。
    支持注入自定义仓储实例以便单元测试。
    """

    def __init__(self, repository=report_repository) -> None:
        """初始化查询处理器。

        Args:
            repository: 报告仓储实例，默认使用模块级单例 report_repository
        """
        self.repository = repository

    def handle_get(self, query: GetReportQuery) -> Optional[ReportAggregate]:
        """处理按 ID 查询报告（不含子实体集合）。

        Args:
            query: GetReportQuery

        Returns:
            ReportAggregate 或 None（报告不存在或已软删除）
        """
        return self.repository.get_by_id(query.report_id)

    def handle_get_by_task(self, query: GetReportByTaskQuery) -> Optional[ReportAggregate]:
        """处理按任务 ID 查询最新报告。

        Args:
            query: GetReportByTaskQuery

        Returns:
            ReportAggregate 或 None
        """
        return self.repository.get_by_task(query.task_id)

    def handle_list(self, query: ListReportsQuery) -> List[ReportAggregate]:
        """处理分页列出报告。

        Args:
            query: ListReportsQuery

        Returns:
            聚合根列表（不含子实体集合）
        """
        return self.repository.list_reports(
            status=query.status,
            page=query.page,
            page_size=query.page_size,
        )

    def handle_get_summary(self, query: GetReportSummaryQuery) -> Optional[ReportAggregate]:
        """处理查询报告摘要（含子实体集合）。

        加载主聚合根后，附加 summaries/cases/metric_stats/raw_data 等子实体。

        Args:
            query: GetReportSummaryQuery

        Returns:
            填充了子实体的 ReportAggregate，或 None（报告不存在）
        """
        aggregate = self.repository.get_by_id(query.report_id)
        if aggregate is None:
            return None
        # 加载子实体集合并填充到聚合根
        aggregate.summaries = self.repository.load_summaries(query.report_id)
        aggregate.cases = self.repository.load_cases(query.report_id)
        aggregate.metric_stats = self.repository.load_metric_stats(query.report_id)
        aggregate.raw_data = self.repository.load_raw_data(query.report_id)
        return aggregate

    def handle_get_trend(self, query: GetTrendDataQuery) -> list:
        """处理查询报告趋势数据。

        返回按 created_at 升序排列的报告列表，每条含成功率/时长，
        并计算与前一条相比的变化量。

        Args:
            query: GetTrendDataQuery

        Returns:
            list[dict]: 趋势数据列表
        """
        rows = self.repository.get_trend_data(
            report_type=query.report_type,
            task_id=query.task_id,
            limit=query.limit,
        )
        trend_data = []
        prev_rate = None
        prev_duration = None
        for row in rows:
            rate = row.get('pass_rate', 0) or 0
            duration = row.get('duration', 0) or 0
            delta_rate = round(rate - prev_rate, 2) if prev_rate is not None else 0
            delta_dur_pct = round((duration - prev_duration) / prev_duration * 100, 2) if prev_duration else 0
            trend_data.append({
                'report_id': row.get('report_id'),
                'name': row.get('name'),
                'created_at': row.get('created_at').isoformat() if row.get('created_at') else None,
                'success_rate': rate,
                'avg_duration': duration,
                'delta_success_rate': delta_rate,
                'delta_duration_percent': delta_dur_pct,
            })
            prev_rate = rate
            prev_duration = duration
        return trend_data

    # ---- 参考参数构建（供 api_gateway task_query_service 通过 gRPC 调用）----

    def handle_build_reference_params(self, case_info: dict, case_results: list, test_type: str = 'api') -> dict:
        """构建参考参数和音频列表。

        从 case_results 中提取 adjusted_reference_params，或回退到 case_info.reference_params / config，
        再通过 algorithm_service gRPC 获取标准化的参考参数格式。
        同时构建音频列表。

        Args:
            case_info: TestCase 信息 dict
            case_results: 测试结果列表
            test_type: 测试类型

        Returns:
            dict: {reference_params, audios_list}
        """
        from report_service.application.services.report_data_builder import ReportDataBuilder
        from report_service.application.services.report_helpers import ReportHelpers
        from types import SimpleNamespace

        case = SimpleNamespace(**case_info) if isinstance(case_info, dict) else case_info
        results = case_results or []

        ref_params = ReportDataBuilder._get_reference_params(case, results, test_type)
        audios_list = ReportHelpers._build_audios_list(case)

        return {'reference_params': ref_params, 'audios_list': audios_list}

    # ---- 报告用例查询 / 搜索 / 导出 / 平均值 / 日志下载 ----

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
            return {'items': [], 'total': 0, 'page': 1, 'perPage': 20, 'pages': 1}
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
            return {'items': [], 'total': 0, 'page': 1, 'perPage': 20, 'pages': 1}
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

    def handle_get_case_averages(self, params_dict: dict) -> dict:
        """处理按分组和标签查询用例平均值。

        流程：解析参数 -> 查询用例和结果 -> 计算平均值/正态分布/资源列表 -> 格式化响应。

        Args:
            params_dict: 参数字典，含 task_id/category/tags/categories/include_untagged

        Returns:
            dict: 平均值统计响应
        """
        from report_service.application.services.report_helpers import ReportHelpers
        from report_service.application.services.report_utils import ReportUtils

        task_id = params_dict.get('task_id')
        category = params_dict.get('category')
        tags = params_dict.get('tags') or []
        categories = params_dict.get('categories') or []
        include_untagged = params_dict.get('include_untagged') or False

        if not task_id:
            return {'success': False, 'message': '缺少必要参数: task_id'}

        query_result = self._query_cases_for_averages(
            task_id, category, categories, tags, include_untagged
        )
        if not isinstance(query_result, tuple):
            return query_result
        task, filtered_case_ids, test_results = query_result

        stats = self._calculate_averages(task, filtered_case_ids, test_results, task_id)

        return {
            "total_cases": len(stats['filtered_case_ids']),
            "total_results": len(stats['test_results']),
            "overall_averages": stats['overall_averages'],
            "overall_averages_map": stats['averages_map'],
            "metric_data": ReportUtils.flatten_metric_data(stats['metric_data'], {}, stats['metric_name_to_id']),
            "raw_data": ReportUtils.flatten_raw_data(stats['raw_data']),
            "normal_distribution": stats['normal_distribution_data'],
            "resources": stats['resources'],
            "resource_headers": stats['resource_headers'],
            "filters": {
                "category": category,
                "tags": tags
            }
        }

    def handle_download_case_logs(self, report_id: int, case_id: str) -> dict:
        """处理下载用例日志。

        查询报告关联任务的合并关系、TestResult，从存储列出 case 日志文件，
        打包成 ZIP 以 base64 编码返回。

        Args:
            report_id: 报告 ID
            case_id: 用例 ID

        Returns:
            dict: {filename, content_base64, size} 或 {success: False, message}
        """
        query_result = self._query_case_logs(report_id, case_id)
        if not isinstance(query_result, tuple):
            return query_result
        task_ids_to_search, test_result = query_result

        return self._format_logs_download(task_ids_to_search, test_result, report_id, case_id)

    # ---- 导出 / 平均值 / 日志下载 私有辅助方法 ----

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

        # 组装报告数据（与 get_one API 返回的 data 字段结构一致）
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

        html_content = HtmlReportRenderer.render(report_data)

        # 清理文件名中的非法字符
        report_name = config.get('name', f'report_{report_id}')
        filename = f"report_{report_id}_{report_name}_{now_cst().strftime('%Y%m%d')}.html"
        filename = filename.replace('/', '_').replace('\\', '_').replace(':', '_').replace('"', '_')

        return {
            'filename': filename,
            'format': 'html',
            'content_base64': base64.b64encode(html_content.encode('utf-8')).decode('utf-8'),
            'mime_type': 'text/html; charset=utf-8',
        }

    def _query_case_logs(self, report_id: int, case_id: str):
        """查询用例日志相关数据。

        Args:
            report_id: 报告 ID
            case_id: 用例 ID

        Returns:
            tuple(task_ids_to_search, test_result) 或错误 dict
        """
        from report_service.infrastructure.clients.grpc_clients import _grpc_get_test_results_by_task_ids

        aggregate = self.repository.get_by_id(report_id)
        if aggregate is None:
            return {'success': False, 'message': '未找到测试报告'}

        task_id = aggregate.task_id
        if not task_id:
            return {'success': False, 'message': '该报告没有关联的任务ID'}

        # 通过 gRPC 查询 TaskMergeRelation
        task_ids_to_search = [task_id]
        try:
            from report_service.infrastructure.clients.grpc_clients import _grpc_get_task_merge_relations
            relations = _grpc_get_task_merge_relations(task_id)
            if relations:
                task_ids_to_search = [it.get('source_task_id') for it in relations]
        except Exception:
            logger.debug("gRPC 查询任务合并关系失败 task_id=%s", task_id, exc_info=True)

        # 通过 gRPC 查询 TestResult（按 task_id 批量查询后客户端过滤 test_case_id）
        all_test_results = _grpc_get_test_results_by_task_ids(task_ids_to_search)
        test_result = None
        for tr in all_test_results:
            tr_tc_id = tr.get('test_case_id') if isinstance(tr, dict) else getattr(tr, 'test_case_id', None)
            if tr_tc_id is not None and str(tr_tc_id) == str(case_id):
                test_result = tr
                break

        return task_ids_to_search, test_result

    @staticmethod
    def _format_logs_download(task_ids_to_search: list, test_result, report_id: int, case_id: str) -> dict:
        """根据查询到的日志数据构建 ZIP 并以 base64 编码返回。

        Args:
            task_ids_to_search: 需搜索的任务 ID 列表
            test_result: 测试结果对象
            report_id: 报告 ID
            case_id: 用例 ID

        Returns:
            dict: {filename, content_base64, size} 或 {success: False, message}
        """
        import base64
        import io as _io
        import json as _json
        import os as _os
        import zipfile as _zipfile
        from shared.infrastructure.storage import storage
        from shared.utils.result_data_store import load_full_result_data

        zip_filename = f"case_{case_id}_logs.zip"

        zip_buffer = _io.BytesIO()
        found_any = False
        with _zipfile.ZipFile(zip_buffer, 'w', _zipfile.ZIP_DEFLATED) as zf:
            for search_task_id in task_ids_to_search:
                # OSS: 列出 case-result bucket 下 {task_id}/{case_id}/ 的所有文件
                oss_prefix = f'{search_task_id}/{case_id}/'
                try:
                    oss_keys = storage.list_objects('case_result', prefix=oss_prefix)
                except Exception:
                    oss_keys = []
                if oss_keys:
                    found_any = True
                    for oss_key in oss_keys:
                        # 下载文件内容
                        try:
                            file_data = storage.load_bytes(f'case_result/{oss_key}')
                            arcname = oss_key[len(oss_prefix):]  # 去掉前缀
                            if len(task_ids_to_search) > 1:
                                arcname = _os.path.join(f"task_{search_task_id}", arcname)
                            zf.writestr(arcname, file_data)
                        except Exception:
                            continue

            full_data = {}
            if test_result:
                tr_result_data = test_result.get('result_data') if isinstance(test_result, dict) else getattr(test_result, 'result_data', None)
                tr_result_data_path = test_result.get('result_data_path') if isinstance(test_result, dict) else getattr(test_result, 'result_data_path', None)
                full_data = load_full_result_data(tr_result_data, tr_result_data_path)
            if test_result and full_data and 'adjusted_reference_params' in full_data:
                adjusted_params = full_data['adjusted_reference_params']
                if adjusted_params:
                    params_json = _json.dumps(adjusted_params, ensure_ascii=False, indent=2)
                    zf.writestr("adjusted_reference_params.json", params_json)

        if not found_any:
            return {'success': False, 'message': '未找到用例日志目录'}

        zip_buffer.seek(0)
        zip_data = zip_buffer.getvalue()
        total_size = len(zip_data)

        return {
            'filename': zip_filename,
            'content_base64': base64.b64encode(zip_data).decode('utf-8'),
            'size': total_size,
        }

    def _query_cases_for_averages(self, task_id: int, category, categories, tags, include_untagged):
        """查询用例和结果（含任务解析、合并关系处理）。

        Args:
            task_id: 任务 ID
            category: 单个分类
            categories: 分类列表
            tags: 标签列表
            include_untagged: 是否包含未标记用例

        Returns:
            tuple(task, filtered_case_ids, test_results) 或错误 dict
        """
        from report_service.infrastructure.clients.grpc_clients import _grpc_get_tasks_by_ids

        _tasks = _grpc_get_tasks_by_ids([task_id])
        task = _tasks[0] if _tasks else None
        if not task:
            return {'success': False, 'message': '未找到指定任务'}

        # 通过 gRPC 查询 TaskMergeRelation
        task_type = task.get('type') if isinstance(task, dict) else getattr(task, 'type', None)
        if task_type == 'merged':
            merge_relations = []
            try:
                from report_service.infrastructure.clients.grpc_clients import _grpc_get_task_merge_relations
                merge_relations = _grpc_get_task_merge_relations(task_id)
            except Exception:
                logger.debug("gRPC 查询合并任务关系失败 task_id=%s", task_id, exc_info=True)
            if merge_relations:
                source_task_ids = [it.get('source_task_id') for it in merge_relations]
                task_id_filter = source_task_ids
                result_task_filter = source_task_ids
            else:
                task_id_filter = task_id
                result_task_filter = task_id
        else:
            task_id_filter = task_id
            result_task_filter = task_id

        filtered_case_ids, test_results = self._query_test_cases_and_results(
            task_id_filter, result_task_filter,
            category, categories, tags, include_untagged
        )
        return task, filtered_case_ids, test_results

    def _query_test_cases_and_results(self, task_id_filter, result_task_filter,
                                       category, categories, tags, include_untagged):
        """查询测试用例和结果，返回 (filtered_case_ids, test_results)。

        Args:
            task_id_filter: 任务 ID 过滤（int 或 list）
            result_task_filter: 结果任务过滤（int 或 list）
            category: 单个分类
            categories: 分类列表
            tags: 标签列表
            include_untagged: 是否包含未标记用例

        Returns:
            tuple(filtered_case_ids, test_results)
        """
        from report_service.application.services.report_query_builder import (
            _grpc_get_task_case_ids,
        )
        from report_service.infrastructure.clients.grpc_clients import (
            _grpc_list_testcases_by_ids,
            _grpc_get_test_results_by_task_ids,
        )

        # 通过 gRPC 查询 TaskCase（获取 task 关联的 test_case_id 列表）
        if isinstance(task_id_filter, list):
            all_tc_ids = set()
            for tid in task_id_filter:
                tc_ids = _grpc_get_task_case_ids(tid)
                all_tc_ids.update(tc_ids)
            test_case_ids = list(all_tc_ids)
        else:
            test_case_ids = _grpc_get_task_case_ids(task_id_filter)

        # 通过 gRPC 批量查询 TestCase
        test_cases = _grpc_list_testcases_by_ids(test_case_ids) if test_case_ids else {}

        # 客户端按 category / categories / tags 过滤
        def _tc_group_name(tc):
            if isinstance(tc, dict):
                g = tc.get('group')
                if isinstance(g, dict):
                    return g.get('name')
                return g
            g = getattr(tc, 'group', None)
            if g is not None:
                return getattr(g, 'name', None)
            return None

        def _tc_tags(tc):
            if isinstance(tc, dict):
                t = tc.get('tags')
                if t is None:
                    return []
                if isinstance(t, list):
                    # tags 可能是字符串列表或对象列表
                    result = []
                    for tag in t:
                        if isinstance(tag, dict):
                            result.append(tag.get('name'))
                        else:
                            result.append(tag)
                    return result
                return t
            t = getattr(tc, 'tags', None)
            if t is None:
                return []
            return t

        def _tc_has_tag(tc, tag_names):
            tc_tags = _tc_tags(tc)
            tc_tag_set = set(str(t) for t in tc_tags if t is not None)
            for tn in tag_names:
                if str(tn) in tc_tag_set:
                    return True
            return False

        def _tc_has_any_tag(tc):
            tc_tags = _tc_tags(tc)
            return len(tc_tags) > 0

        filtered_cases = []
        for tc in test_cases.values() if isinstance(test_cases, dict) else test_cases:
            group_name = _tc_group_name(tc)
            # category 过滤
            if category and category != 'all':
                if group_name != category:
                    continue
            # categories 过滤
            if categories and len(categories) > 0:
                if group_name not in categories:
                    continue
            # tags 过滤
            if include_untagged:
                if tags and len(tags) > 0:
                    if not _tc_has_tag(tc, tags) and _tc_has_any_tag(tc):
                        continue
                else:
                    if _tc_has_any_tag(tc):
                        continue
            elif tags and len(tags) > 0:
                if not _tc_has_tag(tc, tags):
                    continue
            filtered_cases.append(tc)

        filtered_case_ids = []
        for case in filtered_cases:
            cid = case.get('id') if isinstance(case, dict) else getattr(case, 'id', None)
            if cid is not None:
                filtered_case_ids.append(cid)

        # 通过 gRPC 查询 TestResult
        if isinstance(result_task_filter, list):
            all_test_results = _grpc_get_test_results_by_task_ids(result_task_filter)
        else:
            all_test_results = _grpc_get_test_results_by_task_ids([result_task_filter])

        # 客户端按 test_case_id 过滤
        filtered_case_id_set = {str(cid) for cid in filtered_case_ids}
        test_results = []
        for tr in all_test_results:
            tr_tc_id = tr.get('test_case_id') if isinstance(tr, dict) else getattr(tr, 'test_case_id', None)
            if tr_tc_id is not None and str(tr_tc_id) in filtered_case_id_set:
                test_results.append(tr)

        return filtered_case_ids, test_results

    def _calculate_averages(self, task, filtered_case_ids: list, test_results: list, task_id: int) -> dict:
        """计算平均值、正态分布、资源列表等统计信息（委托服务层）。

        Args:
            task: 任务对象
            filtered_case_ids: 过滤后的用例 ID 列表
            test_results: 测试结果列表
            task_id: 任务 ID

        Returns:
            dict: 统计信息字典
        """
        from report_service.application.services.report_aggregation_service import ReportAggregationService
        return ReportAggregationService.calculate_averages(task, filtered_case_ids, test_results, task_id)
