# -*- coding: utf-8 -*-
"""报告命令（Command）对象。

CQRS 写模型入口：命令是 immutable 的意图描述，本身不包含业务逻辑。
Handler 接收命令后通过 repository 操作聚合根完成写操作。

所有命令均为 frozen dataclass，保证不可变。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict

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
    """删除报告命令（软删除）。

    Attributes:
        report_id: 报告 ID
    """
    report_id: int
