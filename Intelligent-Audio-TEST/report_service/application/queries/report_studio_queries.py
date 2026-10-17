# -*- coding: utf-8 -*-
"""Report Studio 查询（Query）对象（INT-673）

CQRS 读侧入口：查询是 immutable 的读取意图描述，本身不包含业务逻辑。
Handler 接收查询后通过 ReportStudioService / 仓储读取 ReadModel 返回。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict


@dataclass(frozen=True)
class GetStudioDocumentQuery:
    """当前版本、Markdown、图表引用、ETag。"""
    data: Dict[str, Any]


@dataclass(frozen=True)
class ListStudioDocumentVersionsQuery:
    """不可变版本列表。"""
    data: Dict[str, Any]


@dataclass(frozen=True)
class GetStudioChartDataQuery:
    """按当前报告数据 + ChartSpec 返回图表数据。"""
    data: Dict[str, Any]


@dataclass(frozen=True)
class GetStudioExportJobQuery:
    """作业状态轮询 + 下载引用。"""
    data: Dict[str, Any]


@dataclass(frozen=True)
class DownloadStudioExportQuery:
    """已完成产物鉴权下载。"""
    data: Dict[str, Any]
