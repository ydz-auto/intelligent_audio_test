# -*- coding: utf-8 -*-
"""报告命令（Command）对象。

CQRS 写模型入口：命令是 immutable 的意图描述，本身不包含业务逻辑。
Handler 接收命令后通过 repository 操作聚合根完成写操作。

所有命令均为 frozen dataclass，保证不可变。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from report_service.domain.entities import ReportStatus, ReportType


@dataclass(frozen=True)
class CreateReportCommand:
    """创建报告命令。

    用于新建一个处于 pending 状态的报告聚合根。

    Attributes:
        task_id: 关联任务 ID
        report_type: 报告类型（standard/comparison/detailed）
        config: 报告配置，承载生成选项等元数据（JSON 字段）
    """
    task_id: int
    report_type: str = ReportType.STANDARD.value
    config: Dict[str, Any] = field(default_factory=dict)
    # INT-423 数据可见性：新建时可指定 private/shared，默认 shared
    visibility: Optional[str] = None


@dataclass(frozen=True)
class GenerateReportCommand:
    """生成报告命令。

    触发报告生成流程（pending -> generating -> completed/failed）。
    Handler 会查找任务的最新报告并将其标记为 generating，
    若不存在则新建报告并标记为 generating。

    Attributes:
        task_id: 关联任务 ID
        report_type: 报告类型
    """
    task_id: int
    report_type: str = ReportType.STANDARD.value


@dataclass(frozen=True)
class UpdateReportCommand:
    """更新报告命令。

    对齐旧库 PUT /reports/{id} 语义：主表字段（name/description/analysis/status）
    + 摘要快照（summary）一并落库。None 字段表示"不更新"（部分更新）。

    Attributes:
        report_id: 报告 ID
        name: 报告名称（含 title 别名，由 Handler 归一）
        description: 报告描述
        analysis: 分析/结论文本（含 conclusion 别名，由 Handler 归一）
        status: 目标状态
        summary: 摘要快照 dict（键已归一为 snake_case）
    """
    report_id: int
    name: Optional[str] = None
    description: Optional[str] = None
    analysis: Optional[str] = None
    status: Optional[str] = None
    summary: Optional[Dict[str, Any]] = None


@dataclass(frozen=True)
class UpdateReportStatusCommand:
    """更新报告状态命令。

    用于报告状态流转（如 generating -> completed/failed）。

    Attributes:
        report_id: 报告 ID
        status: 目标状态（pending/generating/completed/failed）
    """
    report_id: int
    status: str = ReportStatus.PENDING.value


@dataclass(frozen=True)
class DeleteReportCommand:
    """删除报告命令。

    Attributes:
        report_id: 报告 ID
        hard: True 硬删除（含子表级联），False 软删除
    """
    report_id: int
    hard: bool = False
