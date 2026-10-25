# -*- coding: utf-8 -*-
"""Report Studio 领域实体（INT-673，设计文档 §15.4）

documents / document_versions / chart_specs / export_jobs 四聚合的
轻量领域对象：承载不可变快照语义（版本只插不改、作业状态机），
持久化由 infrastructure 仓储负责。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from shared.models.common_enums import ReportStudioSourceType


@dataclass(frozen=True)
class ReportStudioDocument:
    """Report Studio 文档聚合根。

    INT-1763：``report_id`` 可空（上传文档 / 孤儿 Agent 总结没有平台报告行），
    来源由 ``source_type``（``ReportStudioSourceType``）承载；html/pptx 上传件记
    ``source_file_path`` / ``source_format`` / ``source_file_size``，md 只进正文。
    """
    doc_id: str
    report_id: Optional[int]
    title: str
    markdown_content: str = ''
    chart_refs: List[str] = field(default_factory=list)
    style_prefs: Dict[str, Any] = field(default_factory=dict)
    current_version: int = 1
    etag_hash: str = ''
    agent_session_id: Optional[str] = None
    created_by: Optional[int] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    source_type: str = ReportStudioSourceType.PLATFORM_REPORT.value
    parent_doc_id: Optional[str] = None
    source_file_path: Optional[str] = None
    source_format: Optional[str] = None
    source_file_size: Optional[int] = None


@dataclass(frozen=True)
class ReportStudioVersion:
    """Report Studio 文档不可变版本快照。"""
    id: int
    doc_id: str
    version: int
    markdown_content: str
    chart_specs: Dict[str, Any] = field(default_factory=dict)
    parent_version: Optional[int] = None
    snapshot_reason: str = 'manual_edit'
    created_by: Optional[int] = None
    created_at: Optional[str] = None


@dataclass(frozen=True)
class ReportStudioChartSpec:
    """Report Studio 图表定义源。

    INT-1763：``report_id`` 可空（源为上传文档时没有平台报告行），读取侧
    遇到空值返回「需重新绑定报告」语义，不做 int(None) 强转。
    """
    chart_id: str
    doc_id: str
    report_id: Optional[int]
    metric_params: Dict[str, Any] = field(default_factory=dict)
    style: Dict[str, Any] = field(default_factory=dict)
    version: int = 1
    created_by: Optional[int] = None
    created_at: Optional[str] = None


@dataclass(frozen=True)
class ReportStudioExportJob:
    """Report Studio 导出异步作业。"""
    export_id: str
    doc_id: str
    version: int
    format: str
    theme: Optional[str] = None
    status: str = 'pending'
    file_path: Optional[str] = None
    error: Optional[str] = None
    progress: int = 0
    created_by: Optional[int] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
