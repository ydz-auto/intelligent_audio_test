# -*- coding: utf-8 -*-
"""Report Studio 仓储抽象（INT-673）

Domain 层不依赖基础设施：抽象只声明持久化契约，SQLAlchemy 实现位于
report_service/infrastructure/persistence/report_studio_repository.py。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from report_service.domain.entities.report_studio import (
    ReportStudioChartSpec,
    ReportStudioDocument,
    ReportStudioExportJob,
    ReportStudioVersion,
)


class ReportStudioRepository(ABC):
    """Report Studio 四聚合的仓储接口。"""

    # ---- 文档 ----
    @abstractmethod
    def create_document(self, doc: ReportStudioDocument, version: ReportStudioVersion) -> None:
        """同一数据库事务落文档当前版 + 初始版本快照。"""

    @abstractmethod
    def get_document(self, doc_id: str) -> Optional[ReportStudioDocument]:
        """按 doc_id 读文档（不含版本）。"""

    @abstractmethod
    def update_document(self, doc_id: str, expected_version: int,
                        markdown: str, chart_refs: List[str], style_prefs: Dict[str, Any],
                        etag_hash: str, new_version: int,
                        snapshot: ReportStudioVersion) -> Optional[int]:
        """乐观锁更新文档并落新版本快照（同事务）。

        expected_version 与 current_version 不一致时返回 None（调用方转 409）。
        成功返回新版本号。
        """

    # ---- 版本 ----
    @abstractmethod
    def list_versions(self, doc_id: str) -> List[ReportStudioVersion]:
        """版本列表（升序）。"""

    @abstractmethod
    def get_version(self, doc_id: str, version: int) -> Optional[ReportStudioVersion]:
        """按 doc_id + version 读不可变快照。"""

    @abstractmethod
    def restore_version(self, doc_id: str, expected_version: int,
                        target: ReportStudioVersion, new_version: int,
                        new_etag: str) -> Optional[int]:
        """恢复历史版本为新版本（同事务，不覆盖历史）。"""

    # ---- 图表 ----
    @abstractmethod
    def get_chart_spec(self, doc_id: str, chart_id: str) -> Optional[ReportStudioChartSpec]:
        """按 doc_id + chart_id 读图表定义。"""

    @abstractmethod
    def create_chart_spec(self, spec: ReportStudioChartSpec) -> None:
        """创建图表定义。"""

    # ---- 导出作业 ----
    @abstractmethod
    def create_export_job(self, job: ReportStudioExportJob) -> None:
        """创建导出作业（status=pending）。"""

    @abstractmethod
    def get_export_job(self, export_id: str) -> Optional[ReportStudioExportJob]:
        """按 export_id 读作业。"""

    @abstractmethod
    def update_export_job(self, export_id: str, **fields) -> bool:
        """更新作业字段（status/progress/file_path/error）。"""
