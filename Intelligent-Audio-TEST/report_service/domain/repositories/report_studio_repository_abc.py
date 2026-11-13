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
    def list_documents(self, report_id: Optional[int] = None,
                       source_type: Optional[str] = None,
                       parent_doc_id: Optional[str] = None,
                       created_by: Optional[int] = None,
                       limit: int = 100, offset: int = 0):
        """按报告 / 来源类型 / 父文档过滤文档列表（INT-1763 §6.4）。

        返回 ``(rows, total)``。调用方必须显式给出过滤条件——平台报告文档
        列表须同时带 ``report_id`` 与 ``source_type='platform_report'``，
        避免上传文档混入。
        """

    @abstractmethod
    def update_document(self, doc_id: str, expected_version: int,
                        markdown: str, chart_refs: List[str], style_prefs: Dict[str, Any],
                        etag_hash: str, new_version: int,
                        snapshot: ReportStudioVersion) -> Optional[int]:
        """乐观锁更新文档并落新版本快照（同事务）。

        expected_version 与 current_version 不一致时返回 None（调用方转 409）。
        成功返回新版本号。
        """

    @abstractmethod
    def find_document_by_content(self, report_id: int, source_type: str,
                                 created_by: Optional[int],
                                 markdown_content: str
                                 ) -> Optional[ReportStudioDocument]:
        """按「报告 + 来源 + 操作人 + 正文」查已有文档（起草幂等用，INT-2471）。

        重复起草同一报告且正文完全一致时复用原文档，不产生第二份文档 / 版本。
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
    def find_latest_export_job(self, doc_id: str, version: int, fmt: str,
                               theme: Optional[str],
                               created_by: Optional[int] = None
                               ) -> Optional[ReportStudioExportJob]:
        """按「文档 + 固定版本 + 格式 + 主题 + 操作人」读最近一次导出作业。

        导出幂等用：同一产物的进行中 / 已完成作业复用，不重复渲染文件。
        ``created_by`` 是必给的隔离维度（INT-2471 复审 P2-1）：作业按操作人
        归属，复用到他人作业会返回一个当前用户下载被拒（403）的引用，
        因此复用只在本人的作业里找；``None`` 表示未认证运行（AUTH_MODE=off），
        只匹配 ``created_by IS NULL`` 的作业，与起草幂等口径一致。
        """

    @abstractmethod
    def update_export_job(self, export_id: str, **fields) -> bool:
        """更新作业字段（status/progress/file_path/error）。"""
