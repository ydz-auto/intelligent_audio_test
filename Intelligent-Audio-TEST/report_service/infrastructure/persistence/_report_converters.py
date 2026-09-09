# -*- coding: utf-8 -*-
"""Report PO ↔ Entity 转换器（从 report_repository.py 拆分，P4-5 大文件拆分）。

ReportAggregate / ReportSummaryEntity / ReportCaseEntity /
ReportMetricStatsEntity / ReportRawDataEntity / ReportComparisonMatrixEntity
的双向显式映射（DDD PO ↔ Entity）。

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
"""
from __future__ import annotations

import json
from typing import Optional

from report_service.infrastructure.persistence.models import (
    Report,
    ReportSummary,
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


# ========== JSON 工具函数 ==========

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
        name=po.name or '',
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
    # 聚合根 name 为空时不覆盖 PO 既有名称（兼容未携带 name 的写路径）
    po.name = aggregate.name or po.name or ''
    po.type = aggregate.report_type
    po.status = aggregate.status
    po.analysis = _safe_json_dumps(aggregate.config) or ''
    po.deleted = aggregate.deleted
