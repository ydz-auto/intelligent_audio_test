# -*- coding: utf-8 -*-
"""Report 聚合根 + 子实体 + 状态枚举（纯领域对象，不依赖 SQLAlchemy / db.Model）

DDD 分层原则：
- domain 层只含纯领域逻辑，不依赖基础设施（DB/HTTP/线程池）
- 领域实体 ≠ PO：PO 是持久化层概念（继承 db.Model），领域实体是领域层概念（纯业务对象）
- Repository 负责在 PO ↔ Entity 之间做转换

归属：report_service（报告上下文）
对应 PO：Report / ReportSummary / ReportSummaryMeta / ReportRawData
        / ReportCase / ReportMetricStats / ReportComparisonMatrix
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class ReportStatus(str, Enum):
    """报告状态枚举（与 PO Report.status 字段值保持一致）。"""
    PENDING = 'pending'
    GENERATING = 'generating'
    COMPLETED = 'completed'
    FAILED = 'failed'

    @classmethod
    def is_terminal(cls, status: str) -> bool:
        """判断状态是否为终态。"""
        return status in (cls.COMPLETED.value, cls.FAILED.value)

    @classmethod
    def is_running(cls, status: str) -> bool:
        """判断状态是否为生成中。"""
        return status == cls.GENERATING.value


class ReportType(str, Enum):
    """报告类型枚举（与 PO Report.type 字段值保持一致）。"""
    STANDARD = 'standard'
    COMPARISON = 'comparison'
    DETAILED = 'detailed'


@dataclass
class ReportSummaryEntity:
    """报告摘要实体（聚合内实体）

    对应 PO ReportSummary，存储报告的小数据量摘要信息。
    """
    id: int
    report_id: int
    metric_name: str
    metric_value: float
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ReportSummaryMetaEntity:
    """报告摘要元数据实体（聚合内实体）

    对应 PO ReportSummaryMeta，存储报告摘要的 JSON 元数据。
    """
    id: int
    summary_id: int
    meta_key: str
    meta_value: Any = None


@dataclass
class ReportCaseEntity:
    """报告用例实体（聚合内实体）

    对应 PO ReportCase，存储报告的单个用例详情。
    """
    id: int
    report_id: int
    test_case_id: str
    result_summary: Dict[str, Any] = field(default_factory=dict)
    score: Optional[float] = None


@dataclass
class ReportMetricStatsEntity:
    """报告指标统计实体（聚合内实体）

    对应 PO ReportMetricStats，存储报告的分组指标统计数据。
    """
    id: int
    report_id: int
    metric_name: str
    avg: float = 0.0
    min: float = 0.0
    max: float = 0.0
    std_dev: float = 0.0
    sample_count: int = 0


@dataclass
class ReportRawDataEntity:
    """报告原始数据实体（聚合内实体）

    对应 PO ReportRawData，存储报告的原始维度分数数据。
    """
    id: int
    report_id: int
    data_type: str
    data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ReportComparisonMatrixEntity:
    """报告对比矩阵实体（聚合内实体）

    对应 PO ReportComparisonMatrix，存储对比报告的矩阵数据。
    """
    id: int
    report_id: int
    source_task_id: int
    target_task_id: int
    comparison_data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ReportAggregate:
    """Report 聚合根（纯领域对象）

    报告的核心聚合根，包含报告元数据 + 关联子实体集合。
    状态流转、子实体添加等领域行为通过聚合根方法提供。

    注意：领域层不持有 PO 引用，通过 Repository 加载 PO 后转换为聚合根。
    """
    id: int
    task_id: int
    report_type: str = ReportType.STANDARD.value
    status: str = ReportStatus.PENDING.value
    config: Dict[str, Any] = field(default_factory=dict)
    created_at: Optional[Any] = None
    summaries: List[ReportSummaryEntity] = field(default_factory=list)
    cases: List[ReportCaseEntity] = field(default_factory=list)
    metric_stats: List[ReportMetricStatsEntity] = field(default_factory=list)
    raw_data: List[ReportRawDataEntity] = field(default_factory=list)
    deleted: bool = False

    # ---- 状态查询 ----
    def is_completed(self) -> bool:
        """是否已完成。"""
        return self.status == ReportStatus.COMPLETED.value

    def is_generating(self) -> bool:
        """是否生成中。"""
        return self.status == ReportStatus.GENERATING.value

    def is_failed(self) -> bool:
        """是否失败。"""
        return self.status == ReportStatus.FAILED.value

    # ---- 状态流转 ----
    def mark_generating(self) -> None:
        """标记报告为生成中。"""
        self.status = ReportStatus.GENERATING.value

    def mark_completed(self) -> None:
        """标记报告为已完成。"""
        self.status = ReportStatus.COMPLETED.value

    def mark_failed(self, reason: str = '') -> None:
        """标记报告为失败。

        Args:
            reason: 失败原因
        """
        self.status = ReportStatus.FAILED.value
        # 失败原因记入 config，便于上游消费
        if reason:
            self.config = dict(self.config)
            self.config['fail_reason'] = reason

    # ---- 子实体管理 ----
    def add_summary(self, summary: ReportSummaryEntity) -> None:
        """添加摘要实体到聚合。"""
        self.summaries.append(summary)

    def add_case(self, case: ReportCaseEntity) -> None:
        """添加用例实体到聚合。"""
        self.cases.append(case)

    def soft_delete(self) -> None:
        """软删除。"""
        self.deleted = True

    def __repr__(self) -> str:
        return (f"<ReportAggregate id={self.id} task_id={self.task_id} "
                f"type={self.report_type} status={self.status}>")
