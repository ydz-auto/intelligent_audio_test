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
        """处理查询报告用例列表。

        加载报告聚合根及子实体（cases），按 keyword/category/tags 过滤后分页，
        对 voice_llm 多轮场景做 question/answer 与参考参数展开。

        Args:
            report_id: 报告 ID
            params_dict: 查询参数，含 keyword/category/tags/page/per_page 等

        Returns:
            dict: {items, total, page, perPage, pages}
        """
        from report_service.application.services.report_helpers import ReportHelpers

        aggregate = self.repository.get_by_id(report_id)
        if aggregate is None:
            return {'items': [], 'total': 0, 'page': 1, 'perPage': 20, 'pages': 1}
        # 加载用例子实体
        aggregate.cases = self.repository.load_cases(report_id)

        all_cases = []
        for c in aggregate.cases:
            rs = c.result_summary or {}
            case_dict = {
                'test_case_id': c.test_case_id,
                'name': rs.get('name'),
                'description': rs.get('description'),
                'category': rs.get('category'),
                'tags': rs.get('tags') or [],
                'metrics': rs.get('metrics') or {},
                'results': rs.get('results') or [],
                'audios': rs.get('audios') or [],
                'reference_params': rs.get('reference_params') or {},
                'algorithm_results': rs.get('algorithm_results') or {},
                'algorithm_type': rs.get('algorithm_type'),
                'logs': rs.get('logs'),
            }
            all_cases.append(case_dict)

        keyword = params_dict.get('keyword')
        category = params_dict.get('category')
        tags = params_dict.get('tags') or []

        # 客户端过滤
        filtered = []
        for case in all_cases:
            if not isinstance(case, dict):
                continue
            if keyword:
                kw = str(keyword).lower()
                case_name = str(case.get('name') or '').lower()
                case_desc = str(case.get('description') or '').lower()
                if kw not in case_name and kw not in case_desc:
                    continue
            if category:
                if str(case.get('category')) != str(category):
                    continue
            if tags:
                case_tags = case.get('tags') or []
                if not all(str(t) in [str(ct) for ct in case_tags] for t in tags):
                    continue
            filtered.append(case)

        page = max(int(params_dict.get('page') or 1), 1)
        per_page = max(int(params_dict.get('per_page') or 20), 1)
        total = len(filtered)
        start = (page - 1) * per_page
        end = start + per_page
        paged_cases = filtered[start:end]

        items = []
        for case in paged_cases:
            raw_algo_results = case.get('algorithm_results')
            raw_ref_params = case.get('reference_params')
            expanded_algo = ReportQueryHandler._expand_algorithm_results_for_report(
                raw_algo_results, case.get('algorithm_type')
            )
            expanded_ref = ReportQueryHandler._expand_reference_params_for_report(raw_ref_params)
            items.append({
                "id": case.get('test_case_id'),
                "name": case.get('name'),
                "description": case.get('description') or "",
                "category": case.get('category'),
                "tags": case.get('tags') or [],
                "metrics": case.get('metrics') or {},
                "results": case.get('results') or [],
                "audios": case.get('audios') or [],
                "referenceParams": expanded_ref,
                "algorithmResults": expanded_algo,
                "algorithmType": case.get('algorithm_type'),
                "logs": case.get('logs')
            })

        pages = (total + per_page - 1) // per_page if per_page > 0 else 1
        return {
            "items": items,
            "total": total,
            "page": page,
            "perPage": per_page,
            "pages": pages
        }

    def handle_search_report_cases(self, report_id: int, params_dict: dict) -> dict:
        """处理搜索报告用例。

        与 handle_get_report_cases 类似，但支持 include_untagged 参数，
        tags 可以是逗号分隔字符串或列表。

        Args:
            report_id: 报告 ID
            params_dict: 搜索参数，含 keyword/category/tags/include_untagged/page/per_page

        Returns:
            dict: {items, total, page, perPage, pages}
        """
        from report_service.application.services.report_helpers import ReportHelpers

        aggregate = self.repository.get_by_id(report_id)
        if aggregate is None:
            return {'items': [], 'total': 0, 'page': 1, 'perPage': 20, 'pages': 1}
        aggregate.cases = self.repository.load_cases(report_id)

        all_cases = []
        for c in aggregate.cases:
            rs = c.result_summary or {}
            case_dict = {
                'test_case_id': c.test_case_id,
                'name': rs.get('name'),
                'description': rs.get('description'),
                'category': rs.get('category'),
                'tags': rs.get('tags') or [],
                'metrics': rs.get('metrics') or {},
                'results': rs.get('results') or [],
                'audios': rs.get('audios') or [],
                'reference_params': rs.get('reference_params') or {},
                'algorithm_results': rs.get('algorithm_results') or {},
                'algorithm_type': rs.get('algorithm_type'),
                'logs': rs.get('logs'),
            }
            all_cases.append(case_dict)

        keyword = params_dict.get('keyword')
        category = params_dict.get('category')
        include_untagged = params_dict.get('include_untagged') or False

        raw_tags = params_dict.get('tags') or []
        tags = []
        if isinstance(raw_tags, list):
            for t in raw_tags:
                if t is None:
                    continue
                parts = [p.strip() for p in str(t).split(',') if p.strip()]
                tags.extend(parts)
        else:
            tags = [t.strip() for t in str(raw_tags).split(',') if t.strip()]

        # 客户端过滤
        filtered = []
        tag_set = set(str(t) for t in tags)
        for case in all_cases:
            if not isinstance(case, dict):
                continue
            if keyword:
                kw = str(keyword).lower()
                case_name = str(case.get('name') or '').lower()
                case_desc = str(case.get('description') or '').lower()
                if kw not in case_name and kw not in case_desc:
                    continue
            if category:
                if str(case.get('category')) != str(category):
                    continue
            case_tags = case.get('tags') or []
            if include_untagged and not tag_set:
                if case_tags:
                    continue
            elif tag_set:
                if not all(str(t) in [str(ct) for ct in case_tags] for t in tags):
                    continue
            filtered.append(case)

        page = max(int(params_dict.get('page') or 1), 1)
        per_page = max(int(params_dict.get('per_page') or 20), 1)
        total = len(filtered)
        start = (page - 1) * per_page
        end = start + per_page
        paged_cases = filtered[start:end]

        items = []
        for case in paged_cases:
            raw_algo_results = case.get('algorithm_results')
            raw_ref_params = case.get('reference_params')
            expanded_algo = ReportQueryHandler._expand_algorithm_results_for_report(
                raw_algo_results, case.get('algorithm_type')
            )
            expanded_ref = ReportQueryHandler._expand_reference_params_for_report(raw_ref_params)
            items.append({
                "id": case.get('test_case_id'),
                "name": case.get('name'),
                "description": case.get('description') or "",
                "category": case.get('category'),
                "tags": case.get('tags') or [],
                "metrics": case.get('metrics') or {},
                "results": case.get('results') or [],
                "audios": case.get('audios') or [],
                "referenceParams": expanded_ref,
                "algorithmResults": expanded_algo,
                "algorithmType": case.get('algorithm_type'),
                "logs": case.get('logs')
            })

        pages = (total + per_page - 1) // per_page if per_page > 0 else 1
        return {
            "items": items,
            "total": total,
            "page": page,
            "perPage": per_page,
            "pages": pages
        }

    def handle_export_reports(self, report_ids: list, format_type: str) -> dict:
        """处理导出报告。

        按 report_ids 拉取报告及摘要信息，构建导出数据列表，
        根据 format_type 生成 Excel/PDF/CSV 文件并以 base64 编码返回。

        Args:
            report_ids: 报告 ID 列表
            format_type: 导出格式（excel/pdf/csv）

        Returns:
            dict: {filename, format, content_base64, mime_type}
        """
        export_data = self._query_export_data(report_ids)
        if export_data is None:
            return {'success': False, 'message': '未找到指定报告'}

        return self._build_export_payload(export_data, format_type)

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
    def _expand_algorithm_results_for_report(algorithm_results, algorithm_type=None):
        """报告页 algorithm_results 后处理：

        对 voice_llm 多轮场景，把 rounds 数组展开成
        question@round:N / answer@round:N 文本字段。

        Args:
            algorithm_results: 算法结果列表
            algorithm_type: 算法类型

        Returns:
            展开后的 algorithm_results 列表
        """
        if not isinstance(algorithm_results, list):
            return algorithm_results
        # 找到 rounds 字段
        rounds_item = None
        for item in algorithm_results:
            if not isinstance(item, dict):
                continue
            code = item.get('paramCode') or item.get('param_code')
            if code == 'rounds':
                rounds_item = item
                break
        if not rounds_item:
            return algorithm_results
        rounds_value = rounds_item.get('value')
        if not isinstance(rounds_value, list) or not rounds_value:
            return algorithm_results

        # 构建展开后的新列表：保留非 rounds 字段，rounds 替换为 question@round:N/answer@round:N
        expanded = []
        device = rounds_item.get('device', 'default')
        for item in algorithm_results:
            if item is rounds_item:
                continue
            expanded.append(item)

        for r_idx, r_item in enumerate(rounds_value):
            if not isinstance(r_item, dict):
                continue
            raw_round = r_item.get('roundNumber')
            if raw_round is None:
                raw_round = r_item.get('round')
            rn = (raw_round + 1) if isinstance(raw_round, int) else (r_idx + 1)
            output = r_item.get('output') or {}
            for sub_key in ('question', 'answer'):
                val = output.get(sub_key)
                if val:
                    expanded.append({
                        'device': device,
                        'param_code': f'{sub_key}@round:{rn}',
                        'paramCode': f'{sub_key}@round:{rn}',
                        'param_type': 'text',
                        'paramType': 'text',
                        'label': f'{sub_key} (第{rn}轮)',
                        'value': val,
                        'round_number': rn,
                        'roundNumber': rn,
                    })
        # rounds 整体保留（标记为 json）
        rounds_item_copy = dict(rounds_item)
        rounds_item_copy['param_type'] = 'json'
        rounds_item_copy['paramType'] = 'json'
        expanded.append(rounds_item_copy)
        return expanded

    @staticmethod
    def _expand_reference_params_for_report(reference_params):
        """报告页 reference_params 后处理：

        调用 algo_get_reference_params_for_report 做多轮展开，
        兼容 reference_params 是字典（已是报告格式）或 DB 原始列格式。

        Args:
            reference_params: 参考参数（dict 或 list）

        Returns:
            展开后的参考参数字典
        """
        if not reference_params:
            return {}
        try:
            from report_service.infrastructure.clients.grpc_clients import _grpc_algo_get_reference_params_for_report
            # 如果已经是扁平字典格式（code -> {code, type, value}），直接原样返回
            if isinstance(reference_params, dict):
                # 判断是否是 reference_params_col 格式（list of {round_number, reference_params_path}）
                if any(isinstance(v, dict) and ('reference_params_path' in v or 'referenceParamsPath' in v) for v in reference_params.values()):
                    return _grpc_algo_get_reference_params_for_report(reference_params)
                # 已经是展开后的字典格式或含 round_number 多轮格式
                return reference_params
            if isinstance(reference_params, list):
                return _grpc_algo_get_reference_params_for_report(reference_params)
        except Exception:
            logger.debug("gRPC 展开参考参数失败", exc_info=True)
        return reference_params

    def _query_export_data(self, report_ids: list) -> list:
        """查询指定报告及其摘要信息，构建导出数据列表。

        Args:
            report_ids: 报告 ID 列表

        Returns:
            list[dict]: 导出数据列表；无数据时返回 None
        """
        export_data = []
        for rid in report_ids:
            try:
                aggregate = self.repository.get_by_id(int(rid))
                if aggregate is None:
                    continue
                # 加载摘要以取 total_cases / pass_rate
                summaries = self.repository.load_summaries(int(rid))
            except Exception:
                continue

            summary_info = summaries[0].metadata if summaries else {}
            if summary_info:
                total_cases = summary_info.get('total_cases') or 0
                pass_rate = summary_info.get('pass_rate') or 0
            else:
                total_cases = 0
                pass_rate = 0
            created_at = aggregate.created_at
            if created_at:
                try:
                    from datetime import datetime
                    dt = datetime.fromisoformat(str(created_at).replace('Z', '+00:00'))
                    gen_time = dt.strftime('%Y-%m-%d %H:%M:%S')
                except Exception:
                    gen_time = "N/A"
            else:
                gen_time = "N/A"
            export_data.append({
                "报告ID": str(aggregate.id),
                "报告名称": aggregate.config.get('name') if aggregate.config else None,
                "报告类型": aggregate.report_type,
                "生成时间": gen_time,
                "总用例数": str(total_cases),
                "成功率": f"{pass_rate}%",
                "分析结论": (aggregate.config.get('analysis') if aggregate.config else None) or "无"
            })
        return export_data if export_data else None

    @staticmethod
    def _build_export_payload(export_data: list, format_type: str) -> dict:
        """根据格式类型构建导出响应，返回包含 base64 编码文件内容的字典。

        Args:
            export_data: 导出数据列表
            format_type: 导出格式（excel/pdf/csv）

        Returns:
            dict: {filename, format, content_base64, mime_type}
        """
        import base64
        import io as _io
        from shared.utils.query_utils import now_cst

        if format_type == 'excel':
            import pandas as pd
            df = pd.DataFrame(export_data)
            output = _io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, index=False, sheet_name='报告')
            output.seek(0)
            filename = f"reports_export_{now_cst().strftime('%Y%m%d')}.xlsx"
            mime_type = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            return {
                'filename': filename,
                'format': 'excel',
                'content_base64': base64.b64encode(output.getvalue()).decode('utf-8'),
                'mime_type': mime_type,
            }
        elif format_type == 'pdf':
            from reportlab.lib import colors
            from reportlab.lib.pagesizes import A4, landscape
            from reportlab.platypus import SimpleDocTemplate, Table, TableStyle

            output = _io.BytesIO()
            doc = SimpleDocTemplate(output, pagesize=landscape(A4))
            elements = []

            data = [list(export_data[0].keys())]
            for item in export_data:
                data.append(list(item.values()))

            table = Table(data)
            style = TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.gray),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 0), (-1, 0), 12),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                ('GRID', (0, 0), (-1, -1), 1, colors.black)
            ])
            table.setStyle(style)
            elements.append(table)

            doc.build(elements)
            output.seek(0)
            filename = f"reports_export_{now_cst().strftime('%Y%m%d')}.pdf"
            mime_type = 'application/pdf'
            return {
                'filename': filename,
                'format': 'pdf',
                'content_base64': base64.b64encode(output.getvalue()).decode('utf-8'),
                'mime_type': mime_type,
            }
        else:
            # CSV
            buf = _io.BytesIO()
            buf.write('\ufeff'.encode('utf-8-sig'))
            headers = list(export_data[0].keys())
            buf.write((",".join(headers) + "\n").encode('utf-8-sig'))
            for row in export_data:
                csv_row = [row[h] for h in headers]
                csv_row = [f'"{r}"' if ',' in str(r) else str(r) for r in csv_row]
                buf.write((",".join(csv_row) + "\n").encode('utf-8-sig'))
            buf.seek(0)
            filename = f"reports_export_{now_cst().strftime('%Y%m%d')}.csv"
            mime_type = 'text/csv'
            return {
                'filename': filename,
                'format': 'csv',
                'content_base64': base64.b64encode(buf.getvalue()).decode('utf-8'),
                'mime_type': mime_type,
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
        """计算平均值、正态分布、资源列表等统计信息。

        Args:
            task: 任务对象
            filtered_case_ids: 过滤后的用例 ID 列表
            test_results: 测试结果列表
            task_id: 任务 ID

        Returns:
            dict: 统计信息字典
        """
        from report_service.application.services.report_helpers import ReportHelpers
        from report_service.application.services.report_utils import ReportUtils
        from report_service.infrastructure.clients.grpc_clients import (
            _grpc_list_dimensions_all,
            _grpc_get_dimension_params,
            _grpc_get_dimension_results_by_result_ids as _grpc_get_dim_results,
            _grpc_get_task_devices,
            _grpc_get_task_apis,
            _grpc_get_devices_by_ids,
            _grpc_get_apis_by_ids,
            _grpc_list_testcases_by_ids,
            _dim_id, _dim_name,
        )

        def _r_get(r, key, default=None):
            if isinstance(r, dict):
                return r.get(key, default)
            return getattr(r, key, default)

        all_dimensions_all = _grpc_list_dimensions_all()
        used_dim_ids = set()
        res_ids = [_r_get(r, 'id') for r in test_results]
        res_ids = [rid for rid in res_ids if rid is not None]
        if res_ids:
            dim_map = _grpc_get_dim_results(res_ids)
            for rid, items in dim_map.items():
                for it in items:
                    if isinstance(it, dict):
                        dim_id = it.get('dimension_id')
                        if dim_id is not None:
                            used_dim_ids.add(dim_id)

        all_dimensions = [d for d in all_dimensions_all if _dim_id(d) in used_dim_ids] if used_dim_ids else all_dimensions_all

        # 过滤掉 visible_in_report=False 的维度
        all_output_dim_ids = set()
        visible_dim_ids = set()
        for dim in all_dimensions_all:
            dim_id = _dim_id(dim)
            if dim_id is None:
                continue
            params = _grpc_get_dimension_params(dim_id)
            for p in params:
                if not isinstance(p, dict):
                    continue
                if p.get('param_direction') != 'output':
                    continue
                if p.get('deleted', False):
                    continue
                all_output_dim_ids.add(dim_id)
                if p.get('visible_in_report', True):
                    visible_dim_ids.add(dim_id)

        # 有 output 参数但没有任何 visible=True 的维度 → 隐藏
        hidden_dim_ids = all_output_dim_ids - visible_dim_ids
        if hidden_dim_ids:
            all_dimensions = [d for d in all_dimensions if _dim_id(d) not in hidden_dim_ids]
        metric_name_to_id = {str(_dim_name(dim)): int(_dim_id(dim)) for dim in all_dimensions if _dim_id(dim) is not None and _dim_name(dim) is not None}

        dimension_scores = {}
        dimension_counts = {}

        for result in test_results:
            result_id = _r_get(result, 'id')
            dim_values = ReportHelpers.extract_dimension_values(result_id, all_dimensions)
            for dim_name, score in dim_values.items():
                if score is not None:
                    if dim_name not in dimension_scores:
                        dimension_scores[dim_name] = 0
                        dimension_counts[dim_name] = 0
                    dimension_scores[dim_name] += score
                    dimension_counts[dim_name] += 1

        averages_map = {dim_name: (total / dimension_counts[dim_name]) for dim_name, total in dimension_scores.items() if dimension_counts[dim_name] > 0}
        overall_averages = [
            {"id": metric_name_to_id.get(str(dim_name)), "metric": str(dim_name), "value": value}
            for dim_name, value in sorted(averages_map.items(), key=lambda kv: kv[0])
        ]

        # 通过 gRPC 查询 TaskDevice / TaskAPI
        task_devices = _grpc_get_task_devices(task_id)
        task_apis = _grpc_get_task_apis(task_id)

        # 收集 device_ids / api_ids
        device_ids = [td.get('device_id') if isinstance(td, dict) else getattr(td, 'device_id', None) for td in task_devices]
        device_ids = [did for did in device_ids if did is not None]
        api_ids = [ta.get('api_id') if isinstance(ta, dict) else getattr(ta, 'api_id', None) for ta in task_apis]
        api_ids = [aid for aid in api_ids if aid is not None]

        # 通过 gRPC 批量查询 Device / API
        devices_map = _grpc_get_devices_by_ids(device_ids) if device_ids else {}
        apis_map = _grpc_get_apis_by_ids(api_ids) if api_ids else {}

        # 构建带时间前缀的资源列表
        time_prefix = ReportHelpers.get_task_time_prefix(task)
        resources = []
        resource_headers = []
        for td in task_devices:
            td_device_id = td.get('device_id') if isinstance(td, dict) else getattr(td, 'device_id', None)
            d = devices_map.get(td_device_id) if td_device_id else None
            if d:
                d_id = d.get('id') if isinstance(d, dict) else getattr(d, 'id', None)
                d_name = d.get('name') if isinstance(d, dict) else getattr(d, 'name', '')
                d_app_version = d.get('app_version') if isinstance(d, dict) else getattr(d, 'app_version', None)
                key = f"{time_prefix}-{d_id}-{str(d_name).lower()}"
                resources.append(key)
                resource_headers.append(
                    {
                        "key": key,
                        "label": ReportUtils._format_resource_label(task, d_name, d_app_version, use_time_prefix=False) or key,
                        "type": "device",
                        "id": int(d_id) if d_id is not None else None,
                        "name": str(d_name),
                        "version": str(d_app_version) if d_app_version is not None else None,
                        "editable": True,
                    }
                )
        for ta in task_apis:
            ta_api_id = ta.get('api_id') if isinstance(ta, dict) else getattr(ta, 'api_id', None)
            a = apis_map.get(ta_api_id) if ta_api_id else None
            if a:
                a_id = a.get('id') if isinstance(a, dict) else getattr(a, 'id', None)
                a_name = a.get('name') if isinstance(a, dict) else getattr(a, 'name', '')
                key = f"{time_prefix}-{a_id}-{str(a_name).lower()}"
                resources.append(key)
                version = ReportUtils._extract_api_version(a)
                resource_headers.append(
                    {
                        "key": key,
                        "label": ReportUtils._format_resource_label(task, a_name, version, use_time_prefix=False) or key,
                        "type": "api",
                        "id": int(a_id) if a_id is not None else None,
                        "name": str(a_name),
                        "version": version,
                        "editable": True,
                    }
                )

        # 通过 gRPC 批量查询 TestCase（用于获取 group.name）
        test_case_ids_to_fetch = set()
        for result in test_results:
            tc_id = _r_get(result, 'test_case_id')
            if tc_id is not None:
                test_case_ids_to_fetch.add(tc_id)
        test_cases_map = {}
        if test_case_ids_to_fetch:
            tcs = _grpc_list_testcases_by_ids(list(test_case_ids_to_fetch))
            for tc in tcs.values() if isinstance(tcs, dict) else tcs:
                tc_id = tc.get('id') if isinstance(tc, dict) else getattr(tc, 'id', None)
                if tc_id is not None:
                    test_cases_map[tc_id] = tc

        metric_data = {}
        dim_names = [_dim_name(dim) for dim in all_dimensions]
        raw_data = {res: {dn: [] for dn in dim_names} for res in resources}

        accumulator = {}

        for result in test_results:
            # 使用带时间前缀的资源名称
            resource = ReportHelpers.get_resource_name(result, task, use_time_prefix=False)
            if resource not in resources:
                continue

            result_tc_id = _r_get(result, 'test_case_id')
            test_case = test_cases_map.get(result_tc_id) if result_tc_id else None
            if not test_case:
                continue

            # 获取 group name
            if isinstance(test_case, dict):
                g = test_case.get('group')
                if isinstance(g, dict):
                    cat_name = g.get('name') or "未分类"
                elif g is not None:
                    cat_name = getattr(g, 'name', None) or "未分类"
                else:
                    cat_name = "未分类"
            else:
                g = getattr(test_case, 'group', None)
                cat_name = getattr(g, 'name', None) if g else "未分类"

            if cat_name not in accumulator:
                accumulator[cat_name] = {}
            if resource not in accumulator[cat_name]:
                accumulator[cat_name][resource] = {dn: {'sum': 0, 'count': 0} for dn in dim_names}

            result_id = _r_get(result, 'id')
            dim_values = ReportHelpers.extract_dimension_values(result_id, all_dimensions)
            for dim_name, score in dim_values.items():
                if score is not None:
                    accumulator[cat_name][resource][dim_name]['sum'] += score
                    accumulator[cat_name][resource][dim_name]['count'] += 1
                    if dim_name in raw_data[resource]:
                        raw_data[resource][dim_name].append(score)

        for cat_name, res_data in accumulator.items():
            metric_data[cat_name] = {}
            for res, dims in res_data.items():
                metric_data[cat_name][res] = {}
                for dim_name, stats in dims.items():
                    metric_data[cat_name][res][dim_name] = (stats['sum'] / stats['count']) if stats['count'] > 0 else 0

        normal_distribution_data = ReportHelpers.calculate_normal_distribution(raw_data)

        return {
            'filtered_case_ids': filtered_case_ids,
            'test_results': test_results,
            'overall_averages': overall_averages,
            'averages_map': averages_map,
            'metric_data': metric_data,
            'raw_data': raw_data,
            'normal_distribution_data': normal_distribution_data,
            'resources': resources,
            'resource_headers': resource_headers,
            'metric_name_to_id': metric_name_to_id,
        }
