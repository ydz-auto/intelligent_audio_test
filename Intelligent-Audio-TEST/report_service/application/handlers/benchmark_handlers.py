# -*- coding: utf-8 -*-
"""Benchmark CQRS 处理器。

- BenchmarkCommandHandler：写侧（排行计算 / 数据源 / 基线导入 / 映射更新）
- BenchmarkQueryHandler：读侧（只读 ReadModel 与配置表，无写副作用）

接口层（HTTP 路由 / gRPC servicer）只与本层交互。
"""
from __future__ import annotations

import logging

from report_service.application.commands.benchmark_commands import (
    ComputeBenchmarkRankingCommand,
    CreateBenchmarkMetricMappingCommand,
    CreateBenchmarkReportCommand,
    CreateBenchmarkSourceCommand,
    ImportBenchmarkBaselinesCommand,
    UpdateBenchmarkMetricMappingCommand,
)
from report_service.application.queries.benchmark_queries import (
    GetBenchmarkRankingQuery,
    GetBenchmarkRankingSubjectsQuery,
    GetBenchmarkReportQuery,
    ListBenchmarkBaselinesQuery,
    ListBenchmarkMetricMappingsQuery,
    ListBenchmarkReportsQuery,
    ListBenchmarkSourcesQuery,
)
from report_service.application.services.benchmark_baseline_service import (
    BenchmarkBaselineService,
    benchmark_baseline_service,
)
from report_service.application.services.benchmark_ranking_service import (
    BenchmarkRankingService,
    benchmark_ranking_service,
)
from report_service.application.services.benchmark_report_service import (
    BenchmarkReportService,
    benchmark_report_service,
)
from report_service.config.config import Config

logger = logging.getLogger(__name__)


def _default_repo():
    from report_service.infrastructure.persistence.benchmark_repository import (
        BenchmarkRepositoryImpl,
    )
    return BenchmarkRepositoryImpl()


class BenchmarkCommandHandler:
    """Benchmark 写侧处理器。"""

    def __init__(self, ranking_service: BenchmarkRankingService = None,
                 baseline_service: BenchmarkBaselineService = None,
                 report_service: BenchmarkReportService = None):
        self._ranking_service = ranking_service or benchmark_ranking_service
        self._baseline_service = baseline_service or benchmark_baseline_service
        self._report_service = report_service or benchmark_report_service

    def handle_compute_ranking(self, command: ComputeBenchmarkRankingCommand) -> dict:
        return self._ranking_service.compute_ranking(command)

    def handle_create_source(self, command: CreateBenchmarkSourceCommand) -> dict:
        return self._baseline_service.create_source(command)

    def handle_import_baselines(self, command: ImportBenchmarkBaselinesCommand) -> dict:
        return self._baseline_service.import_baselines(command)

    def handle_update_metric_mapping(self, command: UpdateBenchmarkMetricMappingCommand) -> dict:
        return self._baseline_service.update_metric_mapping(command)

    def handle_create_metric_mapping(self, command: CreateBenchmarkMetricMappingCommand) -> dict:
        return self._baseline_service.create_metric_mapping(command)

    def handle_create_report(self, command: CreateBenchmarkReportCommand) -> dict:
        """发布 Benchmark 报告（INT-481 写侧）。"""
        return self._report_service.publish(command)


class BenchmarkQueryHandler:
    """Benchmark 读侧处理器（只读）。"""

    def __init__(self, repo=None):
        self._repo = repo

    @property
    def repo(self):
        if self._repo is None:
            self._repo = _default_repo()
        return self._repo

    def handle_get_ranking(self, query: GetBenchmarkRankingQuery) -> dict:
        try:
            rows = self.repo.query_rankings({
                'suite': query.suite or '',
                'category': query.category or '',
                'metric_code': query.metric_code or '',
                'source': query.source or '',
                'published_task_id': query.published_task_id,
                'subject_name': query.subject_name or '',
            })
            # INT-297：列表信封统一（无分页语义：单页全量）
            return {'success': True, 'message': 'ok',
                    'data': {'items': rows, 'total': len(rows),
                             'page': 1, 'per_page': len(rows) or 1, 'pages': 1}, 'code': 0}
        except Exception:
            logger.exception('查询 Benchmark 排行失败')
            return {'success': False, 'message': '查询排行失败，请稍后重试', 'data': None, 'code': 500}

    def handle_get_ranking_subjects(self, query: GetBenchmarkRankingSubjectsQuery) -> dict:
        try:
            subjects = self.repo.list_ranking_subjects(suite=query.suite or '')
            # INT-297：列表信封统一（无分页语义：单页全量）
            return {'success': True, 'message': 'ok',
                    'data': {'items': subjects, 'total': len(subjects),
                             'page': 1, 'per_page': len(subjects) or 1, 'pages': 1}, 'code': 0}
        except Exception:
            logger.exception('查询 Benchmark 被测主体失败')
            return {'success': False, 'message': '查询被测主体失败，请稍后重试', 'data': None, 'code': 500}

    def handle_list_sources(self, query: ListBenchmarkSourcesQuery) -> dict:
        try:
            data = self.repo.list_sources(
                page=max(int(query.page), 1),
                per_page=min(max(int(query.per_page), 1), Config.BENCHMARK_MAX_PER_PAGE),
                source_type=query.source_type or '',
            )
            return {'success': True, 'message': 'ok', 'data': data, 'code': 0}
        except Exception:
            logger.exception('查询 Benchmark 数据源失败')
            return {'success': False, 'message': '查询数据源失败，请稍后重试', 'data': None, 'code': 500}

    def handle_list_baselines(self, query: ListBenchmarkBaselinesQuery) -> dict:
        try:
            data = self.repo.list_current_baselines(
                category=query.category or '',
                metric_code=query.metric_code or '',
                source_id=query.source_id,
                page=max(int(query.page), 1),
                per_page=min(max(int(query.per_page), 1), Config.BENCHMARK_MAX_PER_PAGE),
            )
            return {'success': True, 'message': 'ok', 'data': data, 'code': 0}
        except Exception:
            logger.exception('查询 Benchmark 基线失败')
            return {'success': False, 'message': '查询基线失败，请稍后重试', 'data': None, 'code': 500}

    def handle_list_metric_mappings(self, query: ListBenchmarkMetricMappingsQuery) -> dict:
        try:
            mappings = self.repo.list_metric_mappings(active_only=query.active_only)
            items = [
                {
                    'id': m.id,
                    'dimension_name': m.dimension_name,
                    'metric_code': m.metric_code,
                    'metric_name': m.metric_name,
                    'unit': m.unit,
                    'direction': m.direction.value,
                    'scenario_tags': m.scenario_tags,
                    'active': m.active,
                }
                for m in mappings
            ]
            # INT-297：列表信封统一（无分页语义：单页全量）
            return {'success': True, 'message': 'ok',
                    'data': {'items': items, 'total': len(items),
                             'page': 1, 'per_page': len(items) or 1, 'pages': 1}, 'code': 0}
        except Exception:
            logger.exception('查询 Benchmark 指标映射失败')
            return {'success': False, 'message': '查询指标映射失败，请稍后重试', 'data': None, 'code': 500}

    # ---------- Benchmark 报告发布记录（INT-481 读侧） ----------

    def handle_list_reports(self, query: ListBenchmarkReportsQuery) -> dict:
        try:
            data = self.repo.list_benchmark_reports(
                {
                    'suite': query.suite or '',
                    'category': query.category or '',
                    'source': query.source or '',
                    'task_id': query.task_id,
                },
                page=max(int(query.page), 1),
                per_page=min(max(int(query.per_page), 1), Config.BENCHMARK_MAX_PER_PAGE),
            )
            return {'success': True, 'message': 'ok', 'data': data, 'code': 0}
        except Exception:
            logger.exception('查询 Benchmark 报告列表失败')
            return {'success': False, 'message': '查询 Benchmark 报告失败，请稍后重试',
                    'data': None, 'code': 500}

    def handle_get_report(self, query: GetBenchmarkReportQuery) -> dict:
        try:
            record = self.repo.get_benchmark_report(query.report_id)
            if record is None:
                return {'success': False, 'message': 'Benchmark 报告不存在',
                        'data': None, 'code': 404}
            return {'success': True, 'message': 'ok', 'data': record, 'code': 0}
        except Exception:
            logger.exception('查询 Benchmark 报告详情失败')
            return {'success': False, 'message': '查询 Benchmark 报告失败，请稍后重试',
                    'data': None, 'code': 500}
