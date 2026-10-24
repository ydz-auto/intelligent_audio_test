# -*- coding: utf-8 -*-
"""Report Studio CQRS 处理器（INT-673）

- ReportStudioCommandHandler：写侧（文档创建/编辑/版本恢复/导出作业创建）
- ReportStudioQueryHandler：读侧（文档/版本/图表/作业查询与下载）

接口层（gRPC servicer）只与本层交互；业务逻辑委托 ReportStudioService。
"""
from __future__ import annotations

import logging

from report_service.application.services.report_studio_service import (
    ReportStudioService,
    report_studio_service,
)

logger = logging.getLogger(__name__)


class ReportStudioCommandHandler:
    """Report Studio 写侧处理器。"""

    def __init__(self, service: ReportStudioService = None):
        self._service = service or report_studio_service

    def handle_create_document(self, data: dict) -> dict:
        return self._service.create_document(data)

    def handle_create_upload_document(self, data: dict) -> dict:
        """文件型独立报告导入（INT-1763 §6.2，source_type=uploaded_file）。"""
        return self._service.create_upload_document(data)

    def handle_update_document(self, data: dict) -> dict:
        return self._service.update_document(data)

    def handle_restore_version(self, data: dict) -> dict:
        return self._service.restore_version(data)

    def handle_create_export_job(self, data: dict) -> dict:
        return self._service.create_export_job(data)


class ReportStudioQueryHandler:
    """Report Studio 读侧处理器（只读）。"""

    def __init__(self, service: ReportStudioService = None):
        self._service = service or report_studio_service

    def handle_get_document(self, data: dict) -> dict:
        return self._service.get_document(data)

    def handle_list_documents(self, data: dict) -> dict:
        return self._service.list_documents(data)

    def handle_list_versions(self, data: dict) -> dict:
        return self._service.list_versions(data)

    def handle_get_chart_data(self, data: dict) -> dict:
        return self._service.get_chart_data(data)

    def handle_get_export_job(self, data: dict) -> dict:
        return self._service.get_export_job(data)

    def handle_download_export(self, data: dict) -> dict:
        return self._service.download_export(data)
