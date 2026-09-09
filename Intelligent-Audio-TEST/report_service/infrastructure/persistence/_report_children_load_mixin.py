# -*- coding: utf-8 -*-
"""Report 子实体集合加载 Mixin（从 report_repository.py 拆分，P4-5 大文件拆分）。

职责：加载报告聚合根的子实体（摘要/用例/指标统计/原始数据/对比矩阵），
以及报告完整数据查询（用于 HTML 导出）。
"""
from __future__ import annotations

import json
from typing import List, Optional

from shared.models.database import get_db_session
from shared.utils.db_session import with_session

from report_service.domain.entities import (
    ReportSummaryEntity,
    ReportCaseEntity,
    ReportMetricStatsEntity,
    ReportRawDataEntity,
    ReportComparisonMatrixEntity,
)
from report_service.infrastructure.persistence._report_converters import (
    _summary_po_to_entity,
    _case_po_to_entity,
    _metric_stats_po_to_entity,
    _raw_data_po_to_entity,
    _comparison_po_to_entity,
)
from report_service.infrastructure.persistence.models import (
    ReportSummary,
    ReportSummaryMeta,
    ReportRawData,
    ReportCase,
    ReportMetricStats,
    ReportComparisonMatrix,
)


# ========== JSON 列转换工具 ==========

def _to_json(val):
    """将 JSON 列字段统一转为 Python 对象（list/dict，默认 list）。"""
    if val is None:
        return []
    if isinstance(val, (list, dict)):
        return val
    if isinstance(val, str):
        try:
            return json.loads(val)
        except Exception:
            return []
    return val


def _to_json_obj(val):
    """将 JSON 列字段统一转为 dict（默认空 dict）。"""
    if val is None:
        return {}
    if isinstance(val, dict):
        return val
    if isinstance(val, str):
        try:
            obj = json.loads(val)
            return obj if isinstance(obj, dict) else {}
        except Exception:
            return {}
    return {}


class ReportChildrenLoadMixin:
    """Report 子实体集合加载（依赖 _report_converters 转换函数）。"""

    @with_session
    def load_summaries(self, report_id: int) -> List[ReportSummaryEntity]:
        """加载报告的摘要实体列表。"""
        session = get_db_session()
        rows = (
            session.query(ReportSummary)
            .filter(ReportSummary.report_id == report_id)
            .all()
        )
        return [_summary_po_to_entity(po) for po in rows]

    @with_session
    def load_cases(self, report_id: int) -> List[ReportCaseEntity]:
        """加载报告的用例实体列表。"""
        session = get_db_session()
        rows = (
            session.query(ReportCase)
            .filter(ReportCase.report_id == report_id)
            .all()
        )
        return [_case_po_to_entity(po) for po in rows]

    @with_session
    def load_metric_stats(self, report_id: int) -> List[ReportMetricStatsEntity]:
        """加载报告的指标统计实体列表。"""
        session = get_db_session()
        rows = (
            session.query(ReportMetricStats)
            .filter(ReportMetricStats.report_id == report_id)
            .all()
        )
        return [_metric_stats_po_to_entity(po) for po in rows]

    @with_session
    def load_raw_data(self, report_id: int) -> List[ReportRawDataEntity]:
        """加载报告的原始数据实体列表。"""
        session = get_db_session()
        rows = (
            session.query(ReportRawData)
            .filter(ReportRawData.report_id == report_id)
            .all()
        )
        return [_raw_data_po_to_entity(po) for po in rows]

    @with_session
    def load_comparison(self, report_id: int) -> Optional[ReportComparisonMatrixEntity]:
        """加载报告的对比矩阵实体（单条）。"""
        session = get_db_session()
        po = (
            session.query(ReportComparisonMatrix)
            .filter(ReportComparisonMatrix.report_id == report_id)
            .first()
        )
        if po is None:
            return None
        return _comparison_po_to_entity(po)

    def load_full_report_data(self, report_id: int) -> Optional[dict]:
        """加载报告完整数据（用于 HTML 导出）。

        一次性查询 ReportSummary / ReportSummaryMeta / ReportMetricStats /
        ReportRawData，返回 dict 格式的完整报告数据。

        Args:
            report_id: 报告 ID

        Returns:
            包含完整报告数据的 dict，或 None（报告不存在）
        """
        session = get_db_session()
        try:
            return self._load_full_data_in_session(session, report_id)
        finally:
            session.close()

    @staticmethod
    def _load_full_data_in_session(session, report_id: int) -> Optional[dict]:
        """在给定 session 内加载报告完整数据（单一职责小方法）。"""
        # 查询摘要 / 元数据 / 指标统计 / 原始数据
        summary_po = (
            session.query(ReportSummary)
            .filter(ReportSummary.report_id == report_id)
            .first()
        )
        if not summary_po:
            return None
        meta_po = (
            session.query(ReportSummaryMeta)
            .filter(ReportSummaryMeta.report_id == report_id)
            .first()
        )
        stats_po = (
            session.query(ReportMetricStats)
            .filter(ReportMetricStats.report_id == report_id)
            .first()
        )
        raw_po = (
            session.query(ReportRawData)
            .filter(ReportRawData.report_id == report_id)
            .first()
        )
        return ReportChildrenLoadMixin._build_full_data_dict(
            summary_po, meta_po, stats_po, raw_po
        )

    @staticmethod
    def _build_full_data_dict(summary_po, meta_po, stats_po, raw_po) -> dict:
        """将查询到的 4 个 PO 组装为完整报告数据 dict。"""
        return {
            'total_cases': summary_po.total_cases or 0,
            'completed_cases': summary_po.completed_cases or 0,
            'failed_cases': summary_po.failed_cases or 0,
            'pass_rate': summary_po.pass_rate or 0.0,
            'raw_data': _to_json(raw_po.raw_data) if raw_po else [],
            'case_categories': _to_json(meta_po.case_categories) if meta_po else [],
            'all_case_tags': _to_json(meta_po.all_case_tags) if meta_po else [],
            'devices': _to_json(meta_po.devices) if meta_po else [],
            'apis': _to_json(meta_po.apis) if meta_po else [],
            'resources': _to_json(meta_po.resources) if meta_po else [],
            'resource_headers': _to_json(meta_po.resource_headers) if meta_po else [],
            'all_metrics': _to_json(meta_po.all_metrics) if meta_po else [],
            'field_mappings': _to_json_obj(meta_po.field_mappings) if meta_po else {},
            # metric_data/tag_metric_data/tag_category_metric_data 保存为 JSON 数组
            #（部分版本为 dict），_to_json 统一保留原类型，避免数组被 _to_json_obj 丢弃
            'metric_data': _to_json(stats_po.metric_data) if stats_po else [],
            'tag_metric_data': _to_json(stats_po.tag_metric_data) if stats_po else [],
            'tag_category_metric_data': _to_json(stats_po.tag_category_metric_data) if stats_po else [],
            'case_type_stats': _to_json(stats_po.case_type_stats) if stats_po else [],
            'device_stats': _to_json(stats_po.device_stats) if stats_po else [],
            'api_stats': _to_json(stats_po.api_stats) if stats_po else [],
        }
