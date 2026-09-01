# -*- coding: utf-8 -*-
"""Report 子实体直接写入 Mixin（从 report_repository.py 拆分，P4-5 大文件拆分）。

职责：供报告生成引擎使用的子实体直接写入方法（入参为 dict），
统一通过 _add_po 辅助方法消除重复的 session/flush/commit 模板。
"""
from __future__ import annotations

from shared.models.database import get_db_session

from report_service.infrastructure.persistence.models import (
    ReportSummary,
    ReportSummaryMeta,
    ReportRawData,
    ReportCase,
    ReportMetricStats,
    ReportComparisonMatrix,
)


class ReportChildrenWriteMixin:
    """Report 子实体直接写入（入参 dict，供报告生成引擎使用）。"""

    @staticmethod
    def _add_po(po) -> int:
        """新增 PO 并返回自增 ID（统一 session/flush/commit 模板）。"""
        session = get_db_session()
        try:
            session.add(po)
            session.flush()
            new_id = po.id
            session.commit()
            return new_id
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def add_summary(self, report_id: int, summary_data: dict) -> int:
        """创建报告摘要记录。

        Args:
            report_id: 报告 ID
            summary_data: 摘要数据字典，含 total_cases/completed_cases/failed_cases/
                          pass_rate/duration/started_at/completed_at 等字段

        Returns:
            新创建的摘要记录 ID
        """
        po = ReportSummary(
            report_id=report_id,
            total_cases=summary_data.get('total_cases', 0),
            completed_cases=summary_data.get('completed_cases', 0),
            failed_cases=summary_data.get('failed_cases', 0),
            pass_rate=summary_data.get('pass_rate', 0) or summary_data.get('overall_success_rate', 0),
            duration=summary_data.get('duration', 0),
            started_at=summary_data.get('started_at'),
            completed_at=summary_data.get('completed_at'),
            task_ids=summary_data.get('task_ids'),
        )
        return self._add_po(po)

    def add_summary_meta(self, report_id: int, meta_data: dict) -> int:
        """创建报告摘要元数据记录。

        Args:
            report_id: 报告 ID
            meta_data: 元数据字典，含 dimension_values/case_categories/all_case_tags/
                       devices/apis/resources/resource_headers/all_metrics 等字段

        Returns:
            新创建的元数据记录 ID
        """
        po = ReportSummaryMeta(
            report_id=report_id,
            dimension_values=meta_data.get('dimension_values'),
            case_categories=meta_data.get('case_categories'),
            all_case_tags=meta_data.get('all_case_tags'),
            devices=meta_data.get('devices'),
            apis=meta_data.get('apis'),
            resources=meta_data.get('resources'),
            resource_headers=meta_data.get('resource_headers'),
            all_metrics=meta_data.get('all_metrics'),
            field_mappings=meta_data.get('field_mappings'),
        )
        return self._add_po(po)

    def add_raw_data(self, report_id: int, raw_data: dict) -> int:
        """创建报告原始数据记录。

        Args:
            report_id: 报告 ID
            raw_data: 原始数据字典，含 raw_data（JSON）字段

        Returns:
            新创建的原始数据记录 ID
        """
        po = ReportRawData(
            report_id=report_id,
            raw_data=raw_data.get('raw_data'),
        )
        return self._add_po(po)

    def add_case(self, report_id: int, case_data: dict) -> int:
        """创建报告用例记录。

        Args:
            report_id: 报告 ID
            case_data: 用例数据字典，含 test_case_id/name/description/category/tags/
                       metrics/results/audios/reference_params/algorithm_results/
                       algorithm_type/logs 等字段

        Returns:
            新创建的用例记录 ID
        """
        po = ReportCase(
            report_id=report_id,
            test_case_id=case_data.get('test_case_id'),
            name=case_data.get('name'),
            description=case_data.get('description'),
            category=case_data.get('category'),
            tags=case_data.get('tags'),
            metrics=case_data.get('metrics'),
            results=case_data.get('results'),
            audios=case_data.get('audios'),
            reference_params=case_data.get('reference_params'),
            algorithm_results=case_data.get('algorithm_results'),
            algorithm_type=case_data.get('algorithm_type'),
            logs=case_data.get('logs'),
        )
        return self._add_po(po)

    def add_metric_stats(self, report_id: int, stats_data: dict) -> int:
        """创建报告指标统计记录。

        Args:
            report_id: 报告 ID
            stats_data: 统计数据字典，含 metric_data/tag_metric_data/tag_category_metric_data/
                        case_type_stats/device_stats/api_stats 等字段

        Returns:
            新创建的指标统计记录 ID
        """
        po = ReportMetricStats(
            report_id=report_id,
            metric_data=stats_data.get('metric_data'),
            tag_metric_data=stats_data.get('tag_metric_data'),
            tag_category_metric_data=stats_data.get('tag_category_metric_data'),
            case_type_stats=stats_data.get('case_type_stats'),
            device_stats=stats_data.get('device_stats'),
            api_stats=stats_data.get('api_stats'),
        )
        return self._add_po(po)

    def add_comparison_matrix(self, report_id: int, comparison_data: dict) -> int:
        """创建报告对比矩阵记录。

        Args:
            report_id: 报告 ID
            comparison_data: 对比数据字典，含 comparison_matrix（JSON）字段

        Returns:
            新创建的对比矩阵记录 ID
        """
        po = ReportComparisonMatrix(
            report_id=report_id,
            comparison_matrix=comparison_data.get('comparison_matrix'),
        )
        return self._add_po(po)
