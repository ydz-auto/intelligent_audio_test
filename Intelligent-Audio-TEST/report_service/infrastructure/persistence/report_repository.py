# -*- coding: utf-8 -*-
"""ReportRepository - 报告聚合根仓储实现（写模型）。

仓储职责：
- 从 DB 加载 Report PO 及关联子表，并转换为 ReportAggregate 聚合根
- 将聚合根的变更持久化回 DB（Entity → PO 字段映射）
- 提供按条件查询聚合根的方法

仓储只处理写模型，读取走 read_models（查询处理器）。

P5+DOMAIN 改造：PO ↔ Entity 显式转换，聚合根不再持有 ORM 引用，
领域层与 SQLAlchemy 完全隔离。

字段映射约定（PO 字段 → 聚合根/子实体字段）：
- Report(type)            → ReportAggregate.report_type
- Report(status)          → ReportAggregate.status
- Report(task_id)         → ReportAggregate.task_id
- Report(analysis)        → ReportAggregate.config        （JSON 文本 ↔ dict）
- Report(created_at)      → ReportAggregate.created_at
- Report(deleted)         → ReportAggregate.deleted
- ReportSummary           → ReportSummaryEntity           （聚合摘要字段）
- ReportCase              → ReportCaseEntity              （用例结果汇总）
- ReportMetricStats       → ReportMetricStatsEntity       （指标统计分组）
- ReportRawData           → ReportRawDataEntity           （原始数据）
- ReportComparisonMatrix  → ReportComparisonMatrixEntity  （对比矩阵）

说明：
- ReportSummaryMeta 在领域层无对应实体，仓储内部暂不单独加载，
  若后续有需求可扩展 ReportSummaryMetaEntity 与对应转换函数。
- Report PO 的 name/description/analysis 等 Text 字段中，analysis 用于
  承载聚合根的 config（JSON 序列化），保持向上兼容。
"""
from __future__ import annotations

import json
from typing import List, Optional

from shared.models.database import get_db_session
from report_service.infrastructure.persistence.models import (
    Report,
    ReportSummary,
    ReportSummaryMeta,
    ReportRawData,
    ReportCase,
    ReportMetricStats,
    ReportComparisonMatrix,
)

from report_service.domain.entities import (
    ReportAggregate,
    ReportSummaryEntity,
    ReportCaseEntity,
    ReportMetricStatsEntity,
    ReportRawDataEntity,
    ReportComparisonMatrixEntity,
    ReportStatus,
)
from report_service.domain.repositories.report_repository_abc import (
    ReportRepositoryABC,
)


# ========== 工具函数 ==========

def _safe_json_loads(value, default):
    """安全反序列化 JSON 字段；非字符串或解析失败时返回默认值。"""
    if value is None:
        return default() if callable(default) else default
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (ValueError, TypeError):
            return default() if callable(default) else default
    return default() if callable(default) else default


def _safe_json_dumps(value) -> Optional[str]:
    """安全序列化为 JSON 字符串；None 保持为 None。"""
    if value is None:
        return None
    if isinstance(value, str):
        # 已是字符串则原样返回（避免双重转义）
        return value
    try:
        return json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        return None


# ========== PO → Entity 转换 ==========

def _summary_po_to_entity(po: ReportSummary) -> ReportSummaryEntity:
    """ReportSummary PO → ReportSummaryEntity 实体。

    将摘要表的小数据量字段整合到 metric_name/metric_value/metadata 结构中，
    便于领域层以统一形态处理。
    """
    metadata = {
        'task_ids': po.task_ids if po.task_ids is not None else [],
        'total_cases': po.total_cases or 0,
        'completed_cases': po.completed_cases or 0,
        'failed_cases': po.failed_cases or 0,
        'pass_rate': po.pass_rate or 0.0,
        'duration': po.duration or 0.0,
        'started_at': po.started_at.isoformat() if po.started_at else None,
        'completed_at': po.completed_at.isoformat() if po.completed_at else None,
    }
    return ReportSummaryEntity(
        id=po.id,
        report_id=po.report_id,
        metric_name='summary',
        metric_value=po.pass_rate or 0.0,
        metadata=metadata,
    )


def _case_po_to_entity(po: ReportCase) -> ReportCaseEntity:
    """ReportCase PO → ReportCaseEntity 实体。

    将用例表的多字段结果数据整合到 result_summary 字典，
    保留 score（若有）。
    """
    result_summary = {
        'name': po.name,
        'description': po.description,
        'category': po.category,
        'tags': po.tags if po.tags is not None else [],
        'metrics': po.metrics if po.metrics is not None else {},
        'results': po.results if po.results is not None else [],
        'audios': po.audios if po.audios is not None else [],
        'reference_params': po.reference_params if po.reference_params is not None else {},
        'algorithm_results': po.algorithm_results if po.algorithm_results is not None else {},
        'algorithm_type': po.algorithm_type,
        'logs': po.logs,
    }
    # score 字段 PO 表中无独立列，从 metrics 中尝试提取
    score = None
    metrics = po.metrics if isinstance(po.metrics, dict) else {}
    if isinstance(metrics.get('score'), (int, float)):
        score = float(metrics.get('score'))
    return ReportCaseEntity(
        id=po.id,
        report_id=po.report_id,
        test_case_id=po.test_case_id or '',
        result_summary=result_summary,
        score=score,
    )


def _metric_stats_po_to_entity(po: ReportMetricStats) -> ReportMetricStatsEntity:
    """ReportMetricStats PO → ReportMetricStatsEntity 实体。

    PO 以 JSON 分组存储，转换为实体时提取总体统计信息；
    详细分组数据保留在 avg 等字段无法覆盖的部分，领域层按需扩展。
    """
    metric_data = po.metric_data if po.metric_data is not None else {}
    # 从 metric_data 中尝试提取总体统计
    avg = 0.0
    min_val = 0.0
    max_val = 0.0
    std_dev = 0.0
    sample_count = 0
    if isinstance(metric_data, dict):
        if isinstance(metric_data.get('avg'), (int, float)):
            avg = float(metric_data.get('avg'))
        if isinstance(metric_data.get('min'), (int, float)):
            min_val = float(metric_data.get('min'))
        if isinstance(metric_data.get('max'), (int, float)):
            max_val = float(metric_data.get('max'))
        if isinstance(metric_data.get('std_dev'), (int, float)):
            std_dev = float(metric_data.get('std_dev'))
        if isinstance(metric_data.get('sample_count'), int):
            sample_count = int(metric_data.get('sample_count'))
    return ReportMetricStatsEntity(
        id=po.id,
        report_id=po.report_id,
        metric_name='overall',
        avg=avg,
        min=min_val,
        max=max_val,
        std_dev=std_dev,
        sample_count=sample_count,
    )


def _raw_data_po_to_entity(po: ReportRawData) -> ReportRawDataEntity:
    """ReportRawData PO → ReportRawDataEntity 实体。"""
    data = po.raw_data if po.raw_data is not None else {}
    if isinstance(po.raw_data, str):
        data = _safe_json_loads(po.raw_data, {})
    return ReportRawDataEntity(
        id=po.id,
        report_id=po.report_id,
        data_type='raw',
        data=data if isinstance(data, dict) else {},
    )


def _comparison_po_to_entity(po: ReportComparisonMatrix) -> ReportComparisonMatrixEntity:
    """ReportComparisonMatrix PO → ReportComparisonMatrixEntity 实体。

    PO 仅存储 comparison_matrix JSON 与 report_id，无 source/target task_id
    独立列，从 comparison_data 中尝试提取以填充实体字段。
    """
    comparison_data = po.comparison_matrix if po.comparison_matrix is not None else {}
    if isinstance(po.comparison_matrix, str):
        comparison_data = _safe_json_loads(po.comparison_matrix, {})
    if not isinstance(comparison_data, dict):
        comparison_data = {}
    source_task_id = comparison_data.get('source_task_id', 0) or 0
    target_task_id = comparison_data.get('target_task_id', 0) or 0
    return ReportComparisonMatrixEntity(
        id=po.id,
        report_id=po.report_id,
        source_task_id=int(source_task_id),
        target_task_id=int(target_task_id),
        comparison_data=comparison_data,
    )


def _report_po_to_entity(po: Report) -> ReportAggregate:
    """Report PO → ReportAggregate 聚合根。

    仅映射报告主表字段；子实体集合按需通过 Repository 方法加载，
    这里不主动触发 relationship 查询，避免 N+1。
    """
    # config 来自 analysis 文本字段（JSON 序列化存储）
    config = _safe_json_loads(po.analysis, {})
    if not isinstance(config, dict):
        config = {}
    return ReportAggregate(
        id=po.id,
        task_id=po.task_id or 0,
        report_type=po.type or 'standard',
        status=po.status or ReportStatus.PENDING.value,
        config=config,
        created_at=po.created_at,
        summaries=[],   # 子实体按需加载
        cases=[],
        metric_stats=[],
        raw_data=[],
        deleted=po.deleted or False,
    )


# ========== Entity → PO 转换（写回） ==========

def _apply_summary_entity_to_po(entity: ReportSummaryEntity, po: ReportSummary) -> None:
    """将 ReportSummaryEntity 可写字段映射回 ReportSummary PO。

    实体的 metadata 承载摘要明细字段，写回时拆解到 PO 各列。
    """
    metadata = entity.metadata or {}
    po.pass_rate = entity.metric_value
    po.task_ids = metadata.get('task_ids')
    po.total_cases = metadata.get('total_cases')
    po.completed_cases = metadata.get('completed_cases')
    po.failed_cases = metadata.get('failed_cases')
    po.duration = metadata.get('duration')
    # started_at / completed_at 在 metadata 中为 ISO 字符串，PO 为 DateTime；
    # 由 SQLAlchemy/驱动隐式处理字符串→DateTime，写回时若失败上层 rollback。
    po.started_at = metadata.get('started_at')
    po.completed_at = metadata.get('completed_at')


def _apply_case_entity_to_po(entity: ReportCaseEntity, po: ReportCase) -> None:
    """将 ReportCaseEntity 可写字段映射回 ReportCase PO。"""
    rs = entity.result_summary or {}
    po.test_case_id = entity.test_case_id
    po.name = rs.get('name')
    po.description = rs.get('description')
    po.category = rs.get('category')
    po.tags = rs.get('tags')
    po.metrics = rs.get('metrics')
    po.results = rs.get('results')
    po.audios = rs.get('audios')
    po.reference_params = rs.get('reference_params')
    po.algorithm_results = rs.get('algorithm_results')
    po.algorithm_type = rs.get('algorithm_type')
    po.logs = rs.get('logs')


def _apply_metric_stats_entity_to_po(entity: ReportMetricStatsEntity, po: ReportMetricStats) -> None:
    """将 ReportMetricStatsEntity 可写字段映射回 ReportMetricStats PO。

    实体仅承载总体统计，写回时同步更新 metric_data 中的总体字段。
    """
    metric_data = po.metric_data if isinstance(po.metric_data, dict) else {}
    metric_data['avg'] = entity.avg
    metric_data['min'] = entity.min
    metric_data['max'] = entity.max
    metric_data['std_dev'] = entity.std_dev
    metric_data['sample_count'] = entity.sample_count
    po.metric_data = metric_data


def _apply_raw_data_entity_to_po(entity: ReportRawDataEntity, po: ReportRawData) -> None:
    """将 ReportRawDataEntity 可写字段映射回 ReportRawData PO。"""
    po.raw_data = entity.data


def _apply_comparison_entity_to_po(entity: ReportComparisonMatrixEntity, po: ReportComparisonMatrix) -> None:
    """将 ReportComparisonMatrixEntity 可写字段映射回 ReportComparisonMatrix PO。"""
    comparison_data = dict(entity.comparison_data or {})
    # 回写 source/target task_id 以保持一致性
    comparison_data['source_task_id'] = entity.source_task_id
    comparison_data['target_task_id'] = entity.target_task_id
    po.comparison_matrix = comparison_data


def _apply_report_to_po(aggregate: ReportAggregate, po: Report) -> None:
    """将聚合根可写字段映射回 Report PO（不含 id/created_at 等元数据）。

    config 序列化为 JSON 文本后写入 analysis 列。
    """
    po.task_id = aggregate.task_id
    po.type = aggregate.report_type
    po.status = aggregate.status
    po.analysis = _safe_json_dumps(aggregate.config) or ''
    po.deleted = aggregate.deleted


# ========== ReportRepository ==========

class ReportRepository(ReportRepositoryABC):
    """报告聚合根仓储。

    遵循 DDD 仓储模式：外部只看到聚合根，不感知 ORM。
    每个方法内部管理 DB session 生命周期（commit/rollback/close）。

    P5+DOMAIN: 通过 PO ↔ Entity 显式转换，聚合根不再持有 ORM 引用。
    """

    # ---- 查询 ----

    def get_by_id(self, report_id: int) -> Optional[ReportAggregate]:
        """按 ID 加载报告聚合根（不含子实体集合）。

        Returns:
            ReportAggregate 或 None（报告不存在或已软删除）。
        """
        session = get_db_session()
        try:
            po = session.get(Report, report_id)
            if po is None or po.deleted:
                return None
            return _report_po_to_entity(po)
        finally:
            session.close()

    def get_by_task(self, task_id: int) -> Optional[ReportAggregate]:
        """按任务 ID 加载报告聚合根（取最新一条未删除报告）。

        一个任务可能对应多个报告版本，取最新创建的一条。
        """
        session = get_db_session()
        try:
            po = (
                session.query(Report)
                .filter(Report.task_id == task_id, Report.deleted == False)  # noqa: E712
                .order_by(Report.created_at.desc())
                .first()
            )
            if po is None:
                return None
            return _report_po_to_entity(po)
        finally:
            session.close()

    def list_reports(
        self,
        status: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> List[ReportAggregate]:
        """分页列出报告聚合根（未删除）。

        Args:
            status: 可选状态过滤（pending/generating/completed/failed）
            page: 页码（从 1 开始）
            page_size: 每页数量

        Returns:
            聚合根列表（不含子实体集合）。
        """
        session = get_db_session()
        try:
            query = session.query(Report).filter(Report.deleted == False)  # noqa: E712
            if status:
                query = query.filter(Report.status == status)
            query = query.order_by(Report.created_at.desc())
            # 分页：limit/offset（避免依赖 Flask-SQLAlchemy paginate）
            page = max(page, 1)
            page_size = max(page_size, 1)
            rows = query.limit(page_size).offset((page - 1) * page_size).all()
            return [_report_po_to_entity(po) for po in rows]
        finally:
            session.close()

    # ---- 子实体集合加载 ----

    def load_summaries(self, report_id: int) -> List[ReportSummaryEntity]:
        """加载报告的摘要实体列表。"""
        session = get_db_session()
        try:
            rows = (
                session.query(ReportSummary)
                .filter(ReportSummary.report_id == report_id)
                .all()
            )
            return [_summary_po_to_entity(po) for po in rows]
        finally:
            session.close()

    def load_cases(self, report_id: int) -> List[ReportCaseEntity]:
        """加载报告的用例实体列表。"""
        session = get_db_session()
        try:
            rows = (
                session.query(ReportCase)
                .filter(ReportCase.report_id == report_id)
                .all()
            )
            return [_case_po_to_entity(po) for po in rows]
        finally:
            session.close()

    def load_metric_stats(self, report_id: int) -> List[ReportMetricStatsEntity]:
        """加载报告的指标统计实体列表。"""
        session = get_db_session()
        try:
            rows = (
                session.query(ReportMetricStats)
                .filter(ReportMetricStats.report_id == report_id)
                .all()
            )
            return [_metric_stats_po_to_entity(po) for po in rows]
        finally:
            session.close()

    def load_raw_data(self, report_id: int) -> List[ReportRawDataEntity]:
        """加载报告的原始数据实体列表。"""
        session = get_db_session()
        try:
            rows = (
                session.query(ReportRawData)
                .filter(ReportRawData.report_id == report_id)
                .all()
            )
            return [_raw_data_po_to_entity(po) for po in rows]
        finally:
            session.close()

    def load_comparison(self, report_id: int) -> Optional[ReportComparisonMatrixEntity]:
        """加载报告的对比矩阵实体（单条）。"""
        session = get_db_session()
        try:
            po = (
                session.query(ReportComparisonMatrix)
                .filter(ReportComparisonMatrix.report_id == report_id)
                .first()
            )
            if po is None:
                return None
            return _comparison_po_to_entity(po)
        finally:
            session.close()

    def load_full_report_data(self, report_id: int) -> Optional[dict]:
        """加载报告完整数据（用于 HTML 导出）。

        一次性查询 ReportSummary / ReportSummaryMeta / ReportMetricStats /
        ReportRawData，返回 dict 格式的完整报告数据。

        Args:
            report_id: 报告 ID

        Returns:
            包含完整报告数据的 dict，或 None（报告不存在）
        """
        import json as _json
        session = get_db_session()
        try:
            # 查询摘要
            summary_po = (
                session.query(ReportSummary)
                .filter(ReportSummary.report_id == report_id)
                .first()
            )
            # 查询摘要元数据
            meta_po = (
                session.query(ReportSummaryMeta)
                .filter(ReportSummaryMeta.report_id == report_id)
                .first()
            )
            # 查询指标统计
            stats_po = (
                session.query(ReportMetricStats)
                .filter(ReportMetricStats.report_id == report_id)
                .first()
            )
            # 查询原始数据
            raw_po = (
                session.query(ReportRawData)
                .filter(ReportRawData.report_id == report_id)
                .first()
            )

            if not summary_po:
                return None

            def _to_json(val):
                """将 JSON 列字段统一转为 Python 对象。"""
                if val is None:
                    return []
                if isinstance(val, (list, dict)):
                    return val
                if isinstance(val, str):
                    try:
                        return _json.loads(val)
                    except Exception:
                        return []
                return val

            def _to_json_obj(val):
                """将 JSON 列字段统一转为 dict。"""
                if val is None:
                    return {}
                if isinstance(val, dict):
                    return val
                if isinstance(val, str):
                    try:
                        obj = _json.loads(val)
                        return obj if isinstance(obj, dict) else {}
                    except Exception:
                        return {}
                return {}

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
                'metric_data': _to_json_obj(stats_po.metric_data) if stats_po else {},
                'tag_metric_data': _to_json_obj(stats_po.tag_metric_data) if stats_po else {},
                'tag_category_metric_data': _to_json_obj(stats_po.tag_category_metric_data) if stats_po else {},
                'case_type_stats': _to_json(stats_po.case_type_stats) if stats_po else [],
                'device_stats': _to_json(stats_po.device_stats) if stats_po else [],
                'api_stats': _to_json(stats_po.api_stats) if stats_po else [],
            }
        finally:
            session.close()

    # ---- 写入 ----

    def save(self, aggregate: ReportAggregate) -> None:
        """持久化聚合根变更。

        P5+DOMAIN: 通过 PO ↔ Entity 转换，将聚合根字段写回 PO，
        不再依赖 aggregate.orm 属性。
        仅更新主表字段；子实体集合的变更需通过对应的 save_* 方法处理。
        """
        session = get_db_session()
        try:
            po = session.get(Report, aggregate.id)
            if po is None:
                # 不应发生（save 只更新已存在的聚合），但容错处理
                raise ValueError(f"Report id={aggregate.id} 不存在，无法 save")
            _apply_report_to_po(aggregate, po)
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def add(self, aggregate: ReportAggregate) -> int:
        """新增报告聚合根。

        Returns:
            新报告 ID。

        P5+DOMAIN: 从聚合根字段构造新 PO，不再依赖 aggregate.orm。
        仅写入主表；子实体集合需通过对应 add_* 方法单独写入。
        """
        session = get_db_session()
        try:
            po = Report(
                task_id=aggregate.task_id,
                type=aggregate.report_type,
                status=aggregate.status,
                analysis=_safe_json_dumps(aggregate.config) or '',
                deleted=aggregate.deleted,
            )
            session.add(po)
            session.flush()
            new_id = po.id
            session.commit()
            # 将生成的 ID 回写聚合根
            aggregate.id = new_id
            return new_id
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def soft_delete(self, report_id: int) -> bool:
        """软删除报告。

        Returns:
            True 表示删除成功，False 表示报告不存在。
        """
        session = get_db_session()
        try:
            po = session.get(Report, report_id)
            if po is None:
                return False
            po.deleted = True
            session.commit()
            return True
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def update_status(self, report_id: int, status: str) -> None:
        """更新报告状态。

        用于报告生成流转（pending → generating → completed/failed）。
        """
        session = get_db_session()
        try:
            po = session.get(Report, report_id)
            if po is None:
                raise ValueError(f"Report id={report_id} 不存在，无法 update_status")
            po.status = status
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # ---- 子实体直接写入（供报告生成引擎使用，入参为 dict） ----

    def add_summary(self, report_id: int, summary_data: dict) -> int:
        """创建报告摘要记录。

        Args:
            report_id: 报告 ID
            summary_data: 摘要数据字典，含 total_cases/completed_cases/failed_cases/
                          pass_rate/duration/started_at/completed_at 等字段

        Returns:
            新创建的摘要记录 ID
        """
        session = get_db_session()
        try:
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

    def add_summary_meta(self, report_id: int, meta_data: dict) -> int:
        """创建报告摘要元数据记录。

        Args:
            report_id: 报告 ID
            meta_data: 元数据字典，含 dimension_values/case_categories/all_case_tags/
                       devices/apis/resources/resource_headers/all_metrics 等字段

        Returns:
            新创建的元数据记录 ID
        """
        session = get_db_session()
        try:
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

    def add_raw_data(self, report_id: int, raw_data: dict) -> int:
        """创建报告原始数据记录。

        Args:
            report_id: 报告 ID
            raw_data: 原始数据字典，含 raw_data（JSON）字段

        Returns:
            新创建的原始数据记录 ID
        """
        session = get_db_session()
        try:
            po = ReportRawData(
                report_id=report_id,
                raw_data=raw_data.get('raw_data'),
            )
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
        session = get_db_session()
        try:
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

    def add_metric_stats(self, report_id: int, stats_data: dict) -> int:
        """创建报告指标统计记录。

        Args:
            report_id: 报告 ID
            stats_data: 统计数据字典，含 metric_data/tag_metric_data/tag_category_metric_data/
                        case_type_stats/device_stats/api_stats 等字段

        Returns:
            新创建的指标统计记录 ID
        """
        session = get_db_session()
        try:
            po = ReportMetricStats(
                report_id=report_id,
                metric_data=stats_data.get('metric_data'),
                tag_metric_data=stats_data.get('tag_metric_data'),
                tag_category_metric_data=stats_data.get('tag_category_metric_data'),
                case_type_stats=stats_data.get('case_type_stats'),
                device_stats=stats_data.get('device_stats'),
                api_stats=stats_data.get('api_stats'),
            )
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

    def add_comparison_matrix(self, report_id: int, comparison_data: dict) -> int:
        """创建报告对比矩阵记录。

        Args:
            report_id: 报告 ID
            comparison_data: 对比数据字典，含 comparison_matrix（JSON）字段

        Returns:
            新创建的对比矩阵记录 ID
        """
        session = get_db_session()
        try:
            po = ReportComparisonMatrix(
                report_id=report_id,
                comparison_matrix=comparison_data.get('comparison_matrix'),
            )
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

    # ---- 原始 PO 查询（供报告生成引擎直接使用 PO） ----

    def get_report_by_id_raw(self, report_id: int):
        """按 ID 查询原始 Report PO（不转换为实体）。

        供报告生成引擎检查已存在报告使用，返回 PO 或 None。
        """
        session = get_db_session()
        try:
            return session.get(Report, report_id)
        finally:
            session.close()

    def get_report_by_task_id_raw(self, task_id: int):
        """按 task_id 查询原始 Report PO（不转换为实体）。

        取最新一条未删除报告，返回 PO 或 None。
        """
        session = get_db_session()
        try:
            return (
                session.query(Report)
                .filter(Report.task_id == task_id, Report.deleted == False)  # noqa: E712
                .order_by(Report.created_at.desc())
                .first()
            )
        finally:
            session.close()

    def get_cases_by_report_id(self, report_id: int) -> list:
        """按 report_id 查询原始 ReportCase PO 列表。

        供报告生成引擎读取已存用例数据使用，返回 PO 列表。
        """
        session = get_db_session()
        try:
            return (
                session.query(ReportCase)
                .filter(ReportCase.report_id == report_id)
                .all()
            )
        finally:
            session.close()

    def get_trend_data(
        self,
        report_type: Optional[str] = None,
        task_id: Optional[int] = None,
        limit: int = 50,
    ) -> list:
        """查询报告趋势数据。

        按 created_at 升序返回已完成报告及其摘要，用于计算成功率/时长趋势。

        Args:
            report_type: 可选报告类型过滤（如 'task'）
            task_id: 可选任务 ID 过滤
            limit: 最多返回条数

        Returns:
            list[dict]: 每条含 report_id/name/created_at/pass_rate/duration
        """
        session = get_db_session()
        try:
            query = (
                session.query(Report, ReportSummary)
                .outerjoin(ReportSummary, Report.id == ReportSummary.report_id)
                .filter(Report.deleted == False)  # noqa: E712
            )
            if report_type:
                query = query.filter(Report.type == report_type)
            if task_id:
                query = query.filter(Report.task_id == task_id)
            query = query.order_by(Report.created_at.asc()).limit(limit)
            rows = query.all()
            return [
                {
                    'report_id': r.id,
                    'name': r.name,
                    'created_at': r.created_at,
                    'pass_rate': s.pass_rate if s else 0,
                    'duration': s.duration if s else 0,
                }
                for r, s in rows
            ]
        finally:
            session.close()

    def hard_delete(self, report_id: int) -> bool:
        """硬删除报告及其所有子表记录。

        级联删除 ReportSummary、ReportSummaryMeta、ReportRawData、
        ReportCase、ReportMetricStats、ReportComparisonMatrix。

        Returns:
            True 表示删除成功，False 表示报告不存在。
        """
        session = get_db_session()
        try:
            po = session.get(Report, report_id)
            if po is None:
                return False
            # 级联删除子表
            session.query(ReportSummary).filter(ReportSummary.report_id == report_id).delete(synchronize_session=False)
            session.query(ReportSummaryMeta).filter(ReportSummaryMeta.report_id == report_id).delete(synchronize_session=False)
            session.query(ReportRawData).filter(ReportRawData.report_id == report_id).delete(synchronize_session=False)
            session.query(ReportCase).filter(ReportCase.report_id == report_id).delete(synchronize_session=False)
            session.query(ReportMetricStats).filter(ReportMetricStats.report_id == report_id).delete(synchronize_session=False)
            session.query(ReportComparisonMatrix).filter(ReportComparisonMatrix.report_id == report_id).delete(synchronize_session=False)
            # 删除主表
            session.delete(po)
            session.commit()
            return True
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


# 模块级单例
report_repository = ReportRepository()
