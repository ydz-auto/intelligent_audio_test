# -*- coding: utf-8 -*-
"""报告仓储抽象接口（ABC）

DDD 规则3：Repository 必须继承 ABC。本模块定义领域层的仓储抽象接口，
infrastructure/persistence/report_repository.py 提供具体实现（ReportRepository）。

抽象方法签名与具体实现保持一致，确保上层通过依赖注入使用接口，
不直接依赖 ORM 实现。

仓储职责：
- 从 DB 加载 Report PO 及关联子表，并转换为 ReportAggregate 聚合根
- 将聚合根的变更持久化回 DB（Entity → PO 字段映射）
- 提供按条件查询聚合根的方法

仓储只处理写模型，读取走 read_models（查询处理器）。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:  # 避免循环引用，仅用于类型注解
    from report_service.domain.entities import (
        ReportAggregate,
        ReportSummaryEntity,
        ReportCaseEntity,
        ReportMetricStatsEntity,
        ReportRawDataEntity,
        ReportComparisonMatrixEntity,
    )


class ReportRepositoryABC(ABC):
    """报告聚合根仓储抽象接口。

    遵循 DDD 仓储模式：外部只看到聚合根，不感知 ORM。
    """

    # ---- 查询 ----

    @abstractmethod
    def get_by_id(self, report_id: int) -> Optional['ReportAggregate']:
        """按 ID 加载报告聚合根（不含子实体集合）。

        Returns:
            ReportAggregate 或 None（报告不存在或已软删除）。
        """

    @abstractmethod
    def get_by_task(self, task_id: int) -> Optional['ReportAggregate']:
        """按任务 ID 加载报告聚合根（取最新一条未删除报告）。"""

    @abstractmethod
    def list_reports(
        self,
        status: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> List['ReportAggregate']:
        """分页列出报告聚合根（未删除）。

        Args:
            status: 可选状态过滤（pending/generating/completed/failed）
            page: 页码（从 1 开始）
            page_size: 每页数量

        Returns:
            聚合根列表（不含子实体集合）。
        """

    # ---- 子实体集合加载 ----

    @abstractmethod
    def load_summaries(self, report_id: int) -> List['ReportSummaryEntity']:
        """加载报告的摘要实体列表。"""

    @abstractmethod
    def load_cases(self, report_id: int) -> List['ReportCaseEntity']:
        """加载报告的用例实体列表。"""

    @abstractmethod
    def load_metric_stats(self, report_id: int) -> List['ReportMetricStatsEntity']:
        """加载报告的指标统计实体列表。"""

    @abstractmethod
    def load_raw_data(self, report_id: int) -> List['ReportRawDataEntity']:
        """加载报告的原始数据实体列表。"""

    @abstractmethod
    def load_comparison(self, report_id: int) -> Optional['ReportComparisonMatrixEntity']:
        """加载报告的对比矩阵实体（单条）。"""

    # ---- 写入 ----

    @abstractmethod
    def save(self, aggregate: 'ReportAggregate') -> None:
        """持久化聚合根变更。

        仅更新主表字段；子实体集合的变更需通过对应的 save_* 方法处理。
        """

    @abstractmethod
    def add(self, aggregate: 'ReportAggregate') -> int:
        """新增报告聚合根。

        Returns:
            新报告 ID。
        """

    @abstractmethod
    def soft_delete(self, report_id: int) -> bool:
        """软删除报告。

        Returns:
            True 表示删除成功，False 表示报告不存在。
        """

    @abstractmethod
    def update_status(self, report_id: int, status: str) -> None:
        """更新报告状态。

        用于报告生成流转（pending → generating → completed/failed）。
        """

    # ---- 子实体直接写入（供报告生成引擎使用，入参为 dict） ----

    @abstractmethod
    def add_summary(self, report_id: int, summary_data: dict) -> int:
        """创建报告摘要记录。

        Returns:
            新创建的摘要记录 ID
        """

    @abstractmethod
    def add_summary_meta(self, report_id: int, meta_data: dict) -> int:
        """创建报告摘要元数据记录。

        Returns:
            新创建的元数据记录 ID
        """

    @abstractmethod
    def add_raw_data(self, report_id: int, raw_data: dict) -> int:
        """创建报告原始数据记录。

        Returns:
            新创建的原始数据记录 ID
        """

    @abstractmethod
    def add_case(self, report_id: int, case_data: dict) -> int:
        """创建报告用例记录。

        Returns:
            新创建的用例记录 ID
        """

    @abstractmethod
    def add_metric_stats(self, report_id: int, stats_data: dict) -> int:
        """创建报告指标统计记录。

        Returns:
            新创建的指标统计记录 ID
        """

    @abstractmethod
    def add_comparison_matrix(self, report_id: int, comparison_data: dict) -> int:
        """创建报告对比矩阵记录。

        Returns:
            新创建的对比矩阵记录 ID
        """

    # ---- 原始 PO 查询（供报告生成引擎直接使用 PO） ----

    @abstractmethod
    def get_report_by_id_raw(self, report_id: int):
        """按 ID 查询原始 Report PO（不转换为实体）。

        供报告生成引擎检查已存在报告使用，返回 PO 或 None。
        """

    @abstractmethod
    def get_report_by_task_id_raw(self, task_id: int):
        """按 task_id 查询原始 Report PO（不转换为实体）。

        取最新一条未删除报告，返回 PO 或 None。
        """

    @abstractmethod
    def get_cases_by_report_id(self, report_id: int) -> list:
        """按 report_id 查询原始 ReportCase PO 列表。

        供报告生成引擎读取已存用例数据使用，返回 PO 列表。
        """

    @abstractmethod
    def get_trend_data(
        self,
        report_type: Optional[str] = None,
        task_id: Optional[int] = None,
        limit: int = 50,
    ) -> list:
        """查询报告趋势数据。

        按 created_at 升序返回已完成报告及其摘要，用于计算成功率/时长趋势。

        Returns:
            list[dict]: 每条含 report_id/name/created_at/pass_rate/duration
        """

    @abstractmethod
    def hard_delete(self, report_id: int) -> bool:
        """硬删除报告及其所有子表记录。

        级联删除 ReportSummary、ReportSummaryMeta、ReportRawData、
        ReportCase、ReportMetricStats、ReportComparisonMatrix。

        Returns:
            True 表示删除成功，False 表示报告不存在。
        """
