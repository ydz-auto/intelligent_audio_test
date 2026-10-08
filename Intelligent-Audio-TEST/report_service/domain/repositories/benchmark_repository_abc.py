# -*- coding: utf-8 -*-
"""Benchmark 排行仓储接口（领域层 ABC，实现在 infrastructure/persistence）

严格 CQRS：
- 写侧（排行计算 / 基线导入 / 映射更新）：replace_ranking_rows / insert 域方法
- 读侧（排行查询 / 基线查询）：只读查询方法，无任何写副作用
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from report_service.domain.entities.benchmark import MetricMapping


class BenchmarkRepository(ABC):
    """Benchmark 排行聚合仓储接口。"""

    # ---------- 排行 ReadModel（写侧：整体刷新） ----------

    @abstractmethod
    def replace_ranking_rows(self, group_keys: List[Dict[str, Any]], rows: List[Dict[str, Any]]) -> int:
        """按组键刷新排行 ReadModel（同事务：删组内旧行 + 插入新行）。

        组键 = (category, metric_code, scenario_key, source)：
        排行按 被测类别 + 指标 + 场景 分组（双轨按口径合并），suite 仅作行级
        展示元数据（外部基线无测试集概念）。

        Args:
            group_keys: 参与本轮计算的组键列表
                [{category, metric_code, scenario_key, source}, ...]
            rows: 新排行行 dict 列表（含组键字段）

        Returns:
            写入行数
        """
        ...

    # ---------- 排行 ReadModel（读侧） ----------

    @abstractmethod
    def query_rankings(self, filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """按条件查询排行 ReadModel（suite/category/metricCode/source/publishedTaskId/subjectName）。"""
        ...

    @abstractmethod
    def list_ranking_subjects(self, suite: Optional[str] = None) -> List[str]:
        """查询参与排行的被测主体名列表（去重）。"""
        ...

    # ---------- 指标映射 ----------

    @abstractmethod
    def list_metric_mappings(self, active_only: bool = False) -> List[MetricMapping]:
        """列出指标映射（active_only=True 仅启用项）。"""
        ...

    @abstractmethod
    def get_metric_mapping(self, mapping_id: int) -> Optional[MetricMapping]:
        """按 ID 查指标映射。"""
        ...

    @abstractmethod
    def update_metric_mapping(self, mapping_id: int, updates: Dict[str, Any]) -> Optional[MetricMapping]:
        """更新指标映射（unit/direction/scenario_tags/active/metric_name）。"""
        ...

    # ---------- 外部基线数据源 ----------

    @abstractmethod
    def create_source(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """创建外部基线数据源，返回 {id, ...}。"""
        ...

    @abstractmethod
    def get_source(self, source_id: int) -> Optional[Dict[str, Any]]:
        """按 ID 查数据源。"""
        ...

    @abstractmethod
    def list_sources(self, page: int, per_page: int, source_type: str = '') -> Dict[str, Any]:
        """分页列数据源，返回 {items, total, page, per_page, pages}。"""
        ...

    # ---------- 外部基线条目（不可变快照版本） ----------

    @abstractmethod
    def list_baseline_versions(self, source_id: int, category: str) -> List[Dict[str, Any]]:
        """列出某数据源某类别下的全部版本（version 去重 + is_current 标记）。"""
        ...

    @abstractmethod
    def get_baseline_rows(self, source_id: int, category: str, version: int) -> List[Dict[str, Any]]:
        """读取某版本的基线行（不可变快照内容，用于幂等比对）。"""
        ...

    @abstractmethod
    def insert_baseline_version(
        self, rows: List[Dict[str, Any]], demote_source_id: int, demote_category: str,
    ) -> Dict[str, Any]:
        """写入新版本基线行（同事务：锁内分配版本号 → 旧版本 is_current 翻转
        False → 新行 is_current=True）。

        版本号由实现在本事务内分配（当前最大版本 + 1），调用方传入的行
        不携带 version / is_current。

        Returns:
            {'version': 新版本号, 'ids': 新行 ID 列表}
        """
        ...

    @abstractmethod
    def list_current_baselines(
        self, category: str = '', metric_code: str = '', source_id: Optional[int] = None,
        page: int = 1, per_page: int = 20,
    ) -> Dict[str, Any]:
        """分页列当前生效（is_current=True）的基线条目。"""
        ...

    @abstractmethod
    def list_all_current_baselines(
        self, category: str = '', metric_code: str = '', source_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """列全部当前生效（is_current=True）的基线条目（排行计算读侧用，不分页）。"""
        ...
