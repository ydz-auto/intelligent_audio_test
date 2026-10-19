# -*- coding: utf-8 -*-
"""Report 主表写入/删除 Mixin（从 report_repository.py 拆分，P4-5 大文件拆分）。

职责：聚合根持久化（save/add）、状态流转（update_status）、
软删除与硬删除（soft_delete/hard_delete）。
"""
from __future__ import annotations

from shared.infrastructure.user_context import get_current_user_id
from shared.models.database import get_db_session
from shared.utils.db_session import SoftDeleteMixin, with_session

from report_service.domain.entities import ReportAggregate
from report_service.infrastructure.persistence._report_converters import (
    _apply_report_to_po,
    _safe_json_dumps,
    _safe_json_loads,
)


class ReportPersistMixin:
    """Report 主表写入与删除（依赖 PO_CLASS 与 _apply_report_to_po）。"""

    PO_CLASS = None  # 由 ReportRepository 提供（Report）

    @with_session(auto_commit=True)
    def save(self, aggregate: ReportAggregate) -> None:
        """持久化聚合根变更。

        P5+DOMAIN: 通过 PO ↔ Entity 转换，将聚合根字段写回 PO，
        不再依赖 aggregate.orm 属性。
        仅更新主表字段；子实体集合的变更需通过对应的 save_* 方法处理。
        """
        session = get_db_session()
        po = session.get(self.PO_CLASS, aggregate.id)
        if po is None:
            # 不应发生（save 只更新已存在的聚合），但容错处理
            raise ValueError(f"Report id={aggregate.id} 不存在，无法 save")
        _apply_report_to_po(aggregate, po)

    @with_session(auto_commit=True)
    def add(self, aggregate: ReportAggregate) -> int:
        """新增报告聚合根。

        Returns:
            新报告 ID。

        P5+DOMAIN: 从聚合根字段构造新 PO，不再依赖 aggregate.orm。
        仅写入主表；子实体集合需通过对应 add_* 方法单独写入。
        """
        session = get_db_session()
        po = self.PO_CLASS(
            task_id=aggregate.task_id,
            name=aggregate.name or '',
            type=aggregate.report_type,
            status=aggregate.status,
            analysis=_safe_json_dumps(aggregate.config) or '',
            deleted=aggregate.deleted,
            visibility=aggregate.visibility or 'shared',
            created_by_user_id=get_current_user_id(),
        )
        session.add(po)
        session.flush()
        new_id = po.id
        # 将生成的 ID 回写聚合根
        aggregate.id = new_id
        return new_id

    @with_session(auto_commit=True)
    def update_status(self, report_id: int, status: str) -> None:
        """更新报告状态。

        用于报告生成流转（pending → generating → completed/failed）。
        """
        session = get_db_session()
        po = session.get(self.PO_CLASS, report_id)
        if po is None:
            raise ValueError(f"Report id={report_id} 不存在，无法 update_status")
        po.status = status

    @with_session(auto_commit=True)
    def update_report_fields(self, report_id: int, fields: dict) -> bool:
        """更新报告主表字段 + 摘要快照（单事务，对齐旧库 PUT /reports/{id} 语义）。

        fields 键约定（由 Handler 归一后传入，均为"提供才更新"语义）：
        - name: str              → PO.name，并同步 config['name']（详情读取兜底路径）
        - description: str       → PO.description，并同步 config['description']
        - analysis: str          → config['analysis'] / config['conclusion']
          （新库 analysis 列复用为 config JSON，文本结论入 config，避免破坏 JSON 结构）
        - status: str            → PO.status
        - summary: dict          → 4 张快照子表（键已归一为 snake_case）：
            report_summaries:    total_cases/completed_cases/failed_cases/pass_rate
            report_raw_data:     raw_data
            report_metric_stats: metric_data/tag_metric_data/case_type_stats
            report_summary_meta: case_categories/all_case_tags/resource_headers/all_metrics

        Returns:
            True 表示更新成功，False 表示报告不存在。
        """
        session = get_db_session()
        po = session.get(self.PO_CLASS, report_id)
        if po is None or po.deleted:
            return False

        summary = fields.get('summary')
        config = _safe_json_loads(po.analysis, {})
        if not isinstance(config, dict):
            config = {}

        if fields.get('name') is not None:
            po.name = str(fields['name'])
            config['name'] = fields['name']
        if fields.get('description') is not None:
            po.description = str(fields['description'])
            config['description'] = fields['description']
        if fields.get('analysis') is not None:
            config['analysis'] = fields['analysis']
            config['conclusion'] = fields['analysis']
        if fields.get('status') is not None:
            po.status = str(fields['status'])
        # INT-466：可见性切换真实落库（None 不更新；值已由 Handler 二值校验）
        if fields.get('visibility') is not None:
            po.visibility = str(fields['visibility'])
        po.updated_by_user_id = get_current_user_id()
        po.analysis = _safe_json_dumps(config) or ''

        if summary is not None:
            self._apply_summary_snapshot(session, report_id, summary)

        session.flush()
        return True

    @staticmethod
    def _apply_summary_snapshot(session, report_id: int, summary: dict) -> None:
        """将归一化后的 summary 快照写入 4 张子表（存在才更新，不新建）。"""
        from report_service.infrastructure.persistence.models import (
            ReportSummary,
            ReportSummaryMeta,
            ReportRawData,
            ReportMetricStats,
        )

        summary_po = session.query(ReportSummary).filter(
            ReportSummary.report_id == report_id).first()
        if summary_po is not None:
            if 'total_cases' in summary:
                summary_po.total_cases = summary['total_cases']
            if 'completed_cases' in summary:
                summary_po.completed_cases = summary['completed_cases']
            if 'failed_cases' in summary:
                summary_po.failed_cases = summary['failed_cases']
            if 'pass_rate' in summary:
                summary_po.pass_rate = summary['pass_rate']

        meta_po = session.query(ReportSummaryMeta).filter(
            ReportSummaryMeta.report_id == report_id).first()
        if meta_po is not None:
            if 'case_categories' in summary:
                meta_po.case_categories = _safe_json_dumps(summary['case_categories'])
            if 'all_case_tags' in summary:
                meta_po.all_case_tags = _safe_json_dumps(summary['all_case_tags'])
            if 'resource_headers' in summary:
                meta_po.resource_headers = _safe_json_dumps(summary['resource_headers'])
            if 'all_metrics' in summary:
                meta_po.all_metrics = _safe_json_dumps(summary['all_metrics'])

        raw_po = session.query(ReportRawData).filter(
            ReportRawData.report_id == report_id).first()
        if raw_po is not None and 'raw_data' in summary:
            raw_po.raw_data = _safe_json_dumps(summary['raw_data'])

        stats_po = session.query(ReportMetricStats).filter(
            ReportMetricStats.report_id == report_id).first()
        if stats_po is not None:
            if 'metric_data' in summary:
                stats_po.metric_data = _safe_json_dumps(summary['metric_data'])
            if 'tag_metric_data' in summary:
                stats_po.tag_metric_data = _safe_json_dumps(summary['tag_metric_data'])
            if 'case_type_stats' in summary:
                stats_po.case_type_stats = _safe_json_dumps(summary['case_type_stats'])

    @with_session(auto_commit=True)
    def hard_delete(self, report_id: int) -> bool:
        """硬删除报告及其所有子表记录。

        级联删除 ReportSummary、ReportSummaryMeta、ReportRawData、
        ReportCase、ReportMetricStats、ReportComparisonMatrix。

        Returns:
            True 表示删除成功，False 表示报告不存在。
        """
        from report_service.infrastructure.persistence.models import (
            ReportSummary,
            ReportSummaryMeta,
            ReportRawData,
            ReportCase,
            ReportMetricStats,
            ReportComparisonMatrix,
        )

        session = get_db_session()
        po = session.get(self.PO_CLASS, report_id)
        if po is None:
            return False
        # 级联删除子表
        child_models = (
            ReportSummary,
            ReportSummaryMeta,
            ReportRawData,
            ReportCase,
            ReportMetricStats,
            ReportComparisonMatrix,
        )
        for model in child_models:
            session.query(model).filter(
                model.report_id == report_id
            ).delete(synchronize_session=False)
        # 删除主表
        session.delete(po)
        return True


# 注意：soft_delete 由 SoftDeleteMixin 通用提供（依赖 PO_CLASS）
